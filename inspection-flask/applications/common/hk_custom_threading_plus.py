from __future__ import annotations

import threading
import time
import traceback
from collections import deque

import numpy as np

import settings
from violation_module.vio_workwear_missing import WorkwearMissingViolation


def _make_white_bg_crop(frame: np.ndarray, bbox: list) -> np.ndarray:
    """将帧中人员框外区域替换为白色后裁剪，对应原 YOLOv5 add_white_background 逻辑。

    用于兼容在白底格式数据上训练的工服检测模型。
    当 settings.USE_WHITE_BG_MASK=True 时使用，否则使用直接裁剪。
    """
    h, w = frame.shape[:2]
    x1 = max(0, int(bbox[0]))
    y1 = max(0, int(bbox[1]))
    x2 = min(w, int(bbox[2]))
    y2 = min(h, int(bbox[3]))
    white = np.ones((h, w, 3), dtype=np.uint8) * 255
    white[y1:y2, x1:x2] = frame[y1:y2, x1:x2]
    return white[y1:y2, x1:x2]


class HKCustomThread(threading.Thread):
    def __init__(self, camera, app):
        super().__init__(daemon=True, name=f"HKCustomThread-{camera.id}")
        self.camera = camera
        self.app = app
        self._running = threading.Event()
        self._running.set()
        self.window = deque(maxlen=getattr(settings, "TEMPORAL_WINDOW_SIZE", 5))
        self.last_processed_ts = None
        self.last_alert_ts = None
        self._pipeline_error_logged = False

    def stop(self):
        self._running.clear()

    def fetch_frame(self):
        """从全局缓存读取当前摄像头最新帧；若无新帧则返回 (None, None)。"""
        entry = self.app.config["hk_frame_cache"].get(self.camera.id)
        if entry is None:
            return None, None
        frame = entry.get("frame")
        timestamp = entry.get("ts")
        if frame is None or timestamp is None:
            return None, None
        if timestamp == self.last_processed_ts:
            return None, None
        self.last_processed_ts = timestamp
        return frame.copy(), timestamp

    def detect_persons(self, frame):
        """对整帧执行人员检测，返回检测器统一格式结果列表。"""
        detector = self.app.config.get("person_model")
        if detector is None:
            return []
        return detector.infer(frame, conf_threshold=getattr(settings, "PERSON_CONF", 0.55))

    def _pipeline_ready(self) -> bool:
        if self.app.config.get("detection_pipeline_ready", False):
            self._pipeline_error_logged = False
            return True

        if not self._pipeline_error_logged:
            init_error = self.app.config.get("detection_model_init_error") or (
                "person_model / workwear_model 未完成初始化"
            )
            self.app.logger.error(
                "camera %s 检测链路未就绪，线程等待中: %s",
                self.camera.id,
                init_error,
            )
            self._pipeline_error_logged = True
        return False

    def _in_roi(self, bbox: list) -> bool:
        roi = getattr(self.camera, "roi", None)
        if not roi:
            return True
        x1, y1, x2, y2 = bbox
        rx1, ry1, rx2, ry2 = roi
        return x1 >= rx1 and y1 >= ry1 and x2 <= rx2 and y2 <= ry2

    def _crop_person(self, frame: np.ndarray, bbox: list):
        """直接裁剪人员框区域，返回裁剪图；坐标越界时做边界修正。"""
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(frame.shape[1], x2)
        y2 = min(frame.shape[0], y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    def build_person_contexts(self, frame: np.ndarray, persons: list) -> list[dict]:
        """为每个有效人员构建包含工服检测结果的上下文字典。

        由 settings.USE_WHITE_BG_MASK 决定裁剪方式：
          False（默认）：直接裁剪人员框
          True：先将框外区域替换为白色再裁剪（兼容白底训练数据）
        """
        workwear_detector = self.app.config.get("workwear_model")
        if workwear_detector is None:
            return []
        min_area = getattr(settings, "MIN_PERSON_BOX_AREA", 3000)
        workwear_conf = getattr(settings, "WORKWEAR_CONF", 0.45)
        use_white_bg = getattr(settings, "USE_WHITE_BG_MASK", False)

        contexts: list[dict] = []
        for person in persons:
            bbox = person.get("bbox", [])
            if len(bbox) != 4:
                continue
            x1, y1, x2, y2 = bbox
            area = max(0, x2 - x1) * max(0, y2 - y1)
            if area < min_area:
                continue

            if use_white_bg:
                crop = _make_white_bg_crop(frame, bbox)
            else:
                crop = self._crop_person(frame, bbox)

            workwear_items: list[dict] = []
            if crop is not None and crop.size > 0:
                workwear_items = workwear_detector.infer(
                    crop,
                    conf_threshold=workwear_conf,
                )

            workwear_labels = getattr(settings, "WORKWEAR_LABELS", [])
            has_workwear = any(
                item.get("label") in workwear_labels for item in workwear_items
            )

            contexts.append(
                {
                    "bbox": bbox,
                    "confidence": float(person.get("confidence", 0.0)),
                    "label": person.get("label", "person"),
                    "area": area,
                    "in_roi": self._in_roi(bbox),
                    "workwear_items": workwear_items,
                    "has_workwear": has_workwear,
                }
            )
        return contexts

    def run_rule_engine(self) -> bool | None:
        """对当前时间窗口执行工服违规规则判定。

        WorkwearMissingViolation.run() 内部完成证据图保存与数据库写入。
        触发违规时返回 True；窗口未达阈值或无有效人员时返回 None。
        """
        violation = WorkwearMissingViolation()
        frames = [item["frame"] for item in self.window]
        datetime_list = [item["timestamp"] for item in self.window]
        targets = list(self.window)
        vio_type = getattr(settings, "WORKWEAR_VIOLATION_TYPE", "workwear_missing")
        violation.init(
            frames=frames,
            datetime_list=datetime_list,
            targets=targets,
            vio_type=vio_type,
            camera_id=self.camera.id,
            station_id=getattr(self.camera, "station_id", None),
            dept_id=getattr(self.camera, "dept_id", None),
            sub_id=getattr(self.camera, "sub_id", None),
        )
        return violation.run()

    def _alert_suppressed(self, timestamp) -> bool:
        """判断当前时刻是否仍处于告警抑制窗口内，避免同一摄像头短时间重复报警。"""
        if self.last_alert_ts is None:
            return False
        suppression = getattr(settings, "alert_suppression_seconds", 300)
        return (timestamp - self.last_alert_ts).total_seconds() < suppression

    def emit_event(self, triggered):
        """违规触发后记录日志。triggered 为 True（saving 已由 violation.run() 完成）。"""
        if not triggered:
            return
        self.app.logger.warning(
            "camera %s 触发工服未穿戴违规告警，证据图已保存",
            self.camera.id,
        )

    def run(self):
        idle = getattr(settings, "thread_idle_sleep", 2)
        round_sleep = getattr(settings, "round_interval", 0) or idle

        recorder_manager = self.app.config["hk_recorder_thread_manager"]
        recorder_manager.register_camera(self.camera)
        self.app.logger.info("camera %s 工服检测线程启动", self.camera.id)

        try:
            while self._running.is_set():
                try:
                    if not self._pipeline_ready():
                        time.sleep(idle)
                        continue

                    frame, timestamp = self.fetch_frame()
                    if frame is None:
                        recorder_manager.run_once(app=self.app, cameras=[self.camera])
                        time.sleep(idle)
                        continue

                    persons = self.detect_persons(frame)
                    person_contexts = self.build_person_contexts(frame, persons)
                    self.window.append(
                        {
                            "camera_id": self.camera.id,
                            "timestamp": timestamp,
                            "frame": frame,
                            "persons": person_contexts,
                        }
                    )

                    window_size = getattr(settings, "TEMPORAL_WINDOW_SIZE", 5)
                    if len(self.window) < window_size:
                        time.sleep(round_sleep)
                        continue

                    if self._alert_suppressed(timestamp):
                        self.window.clear()
                        time.sleep(round_sleep)
                        continue

                    triggered = self.run_rule_engine()
                    if triggered:
                        self.last_alert_ts = timestamp
                        self.window.clear()
                        self.emit_event(triggered)

                    time.sleep(round_sleep)

                except Exception as exc:  # pragma: no cover
                    trace = traceback.format_exc()
                    self.app.logger.error(
                        "camera %s 检测循环异常: %s\n%s", self.camera.id, exc, trace
                    )
                    time.sleep(idle)
        finally:
            recorder_manager.unregister_camera(self.camera.id)
            self.app.logger.info("camera %s 工服检测线程已停止", self.camera.id)


class ThreadManager:
    def __init__(self, app=None):
        self.app = app
        self.threads: dict[str, HKCustomThread] = {}
        self._lock = threading.Lock()

    def bind_app(self, app):
        self.app = app

    def add_thread(self, camera) -> bool:
        if self.app is None:
            return False
        if not self.app.config.get("detection_pipeline_ready", False):
            init_error = self.app.config.get("detection_model_init_error") or (
                "YOLOv11 检测模型未完成初始化"
            )
            self.app.logger.error(
                "camera %s 检测线程启动失败: %s",
                camera.id,
                init_error,
            )
            return False

        camera_id = str(camera.id)
        with self._lock:
            existing = self.threads.get(camera_id)
            if existing is not None and existing.is_alive():
                return False
            new_thread = HKCustomThread(camera, self.app)
            self.threads[camera_id] = new_thread
            new_thread.start()
            return True

    def stop_thread(self, camera_id) -> bool:
        camera_id = str(camera_id)
        with self._lock:
            thread = self.threads.get(camera_id)
        if thread is None:
            return False
        thread.stop()
        thread.join(timeout=3.0)
        with self._lock:
            if not thread.is_alive():
                self.threads.pop(camera_id, None)
                return True
            if self.app is not None:
                self.app.logger.warning("camera %s 检测线程未在超时时间内退出，保留跟踪", camera_id)
            return False

    def stop_all_threads(self, app=None):
        app = app or self.app
        camera_ids = list(self.threads.keys())
        for camera_id in camera_ids:
            self.stop_thread(camera_id)
        if app is not None:
            app.logger.warning("所有工服检测线程已停止")

    def restart_all_threads(self, app=None):
        """重启所有启用摄像头的检测线程。

        直接查询数据库获取当前启用的摄像头列表，与 camera_registry 缓存解耦，
        确保重启时能反映最新的摄像头启用状态。错峰启动避免资源竞争。
        """
        app = app or self.app
        if app is None:
            return

        self.stop_all_threads(app)

        from applications.models import HKCamera

        with app.app_context():
            cameras = HKCamera.query.filter_by(is_delete=0, enable=1).all()
            for camera in cameras:
                if self.add_thread(camera):
                    app.logger.info("重启工服检测线程 camera %s", camera.id)
                    time.sleep(0.2)
                else:
                    app.logger.warning("工服检测线程 camera %s 重启失败或已在运行", camera.id)
