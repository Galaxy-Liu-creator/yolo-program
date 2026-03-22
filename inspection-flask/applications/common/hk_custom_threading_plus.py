from __future__ import annotations

import threading
import time
import traceback
from collections import deque

import settings
from violation_module.vio_workwear_missing import WorkwearMissingViolation


class HKCustomThread(threading.Thread):
    def __init__(self, camera, app):
        super().__init__(daemon=True, name=f"HKCustomThread-{camera.id}")
        self.camera = camera
        self.app = app
        self._running = threading.Event()
        self._running.set()
        self.window = deque(maxlen=settings.TEMPORAL_WINDOW_SIZE)
        self.last_processed_ts = None
        self.last_alert_ts = None

    def stop(self):
        self._running.clear()

    def fetch_frame(self):
        frame = self.app.config["hk_images"].get(self.camera.id)
        timestamp = self.app.config["hk_images_datetime"].get(self.camera.id)
        if frame is None or timestamp is None:
            return None, None
        if timestamp == self.last_processed_ts:
            return None, None
        self.last_processed_ts = timestamp
        return frame.copy(), timestamp

    def detect_persons(self, frame):
        detector = self.app.config["person_model"]
        return detector.infer(frame, conf_threshold=settings.PERSON_CONF)

    def _in_roi(self, bbox):
        roi = getattr(self.camera, "roi", None)
        if not roi:
            return True
        x1, y1, x2, y2 = bbox
        rx1, ry1, rx2, ry2 = roi
        return x1 >= rx1 and y1 >= ry1 and x2 <= rx2 and y2 <= ry2

    def _crop_person(self, frame, bbox):
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(frame.shape[1], x2)
        y2 = min(frame.shape[0], y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    def build_person_contexts(self, frame, persons):
        workwear_detector = self.app.config["workwear_model"]
        contexts = []
        for person in persons:
            bbox = person.get("bbox", [])
            if len(bbox) != 4:
                continue
            x1, y1, x2, y2 = bbox
            area = max(0, x2 - x1) * max(0, y2 - y1)
            if area < settings.MIN_PERSON_BOX_AREA:
                continue

            crop = self._crop_person(frame, bbox)
            workwear_items = []
            if crop is not None:
                workwear_items = workwear_detector.infer(
                    crop,
                    conf_threshold=settings.WORKWEAR_CONF,
                )

            contexts.append(
                {
                    "bbox": bbox,
                    "confidence": float(person.get("confidence", 0.0)),
                    "label": person.get("label", "person"),
                    "area": area,
                    "in_roi": self._in_roi(bbox),
                    "workwear_items": workwear_items,
                    "has_workwear": bool(workwear_items),
                }
            )
        return contexts

    def run_rule_engine(self):
        """对当前时间窗口内的帧批次执行工服违规规则判定。
        返回违规事件记录字典（由 WorkwearMissingViolation.run() 内部完成图片保存），
        若未触发则返回 None。"""
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

    def _alert_suppressed(self, timestamp):
        """判断当前时刻是否在告警抑制窗口内，避免同一摄像头短时间重复报警。"""
        if self.last_alert_ts is None:
            return False
        suppression = getattr(settings, "alert_suppression_seconds", 300)
        return (timestamp - self.last_alert_ts).total_seconds() < suppression

    def emit_event(self, event):
        """将违规事件写入全局队列并记录日志。event 为 save_violate_photo 返回的记录字典。"""
        if not isinstance(event, dict):
            return
        self.app.config["violation_events"].append(event)
        self.app.logger.warning(
            "camera %s 触发违规 [%s] 于 %s，证据图: %s",
            self.camera.id,
            event.get("rule_name") or event.get("rule_code", "unknown"),
            event.get("position_time", ""),
            event.get("href", ""),
        )

    def run(self):
        idle = getattr(settings, "thread_idle_sleep", 2)
        round_sleep = getattr(settings, "round_interval", 0) or idle

        recorder_manager = self.app.config["hk_recorder_thread_manager"]
        recorder_manager.register_camera(self.camera)
        self.app.logger.info("camera %s 工服检测线程启动", self.camera.id)

        while self._running.is_set():
            try:
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
                    time.sleep(round_sleep)
                    continue

                event = self.run_rule_engine()
                if event:
                    self.last_alert_ts = timestamp
                    self.emit_event(event)
                time.sleep(round_sleep)
            except Exception as exc:  # pragma: no cover - 依赖运行环境
                trace = traceback.format_exc()
                self.app.logger.error(
                    "camera %s 检测循环异常: %s\n%s", self.camera.id, exc, trace
                )
                time.sleep(idle)

        self.app.logger.info("camera %s 工服检测线程已停止", self.camera.id)


class ThreadManager:
    def __init__(self, app=None):
        self.app = app
        self.threads = {}
        self._lock = threading.Lock()

    def bind_app(self, app):
        self.app = app

    def add_thread(self, camera):
        if self.app is None:
            return False

        camera_id = str(camera.id)
        with self._lock:
            thread = self.threads.get(camera_id)
            if thread is not None and thread.is_alive():
                return False

            new_thread = HKCustomThread(camera, self.app)
            self.threads[camera_id] = new_thread
            new_thread.start()
            return True

    def stop_thread(self, camera_id):
        camera_id = str(camera_id)
        with self._lock:
            thread = self.threads.pop(camera_id, None)
        if thread is None:
            return False
        thread.stop()
        thread.join(timeout=1.0)
        return True

    def stop_all_threads(self, app=None):
        app = app or self.app
        camera_ids = list(self.threads.keys())
        for camera_id in camera_ids:
            self.stop_thread(camera_id)
        if app is not None:
            app.logger.warning("all detect threads stopped")

    def restart_all_threads(self, app=None):
        """重启所有启用摄像头的检测线程。错峰启动，避免同时加载模型造成资源竞争。"""
        app = app or self.app
        if app is None:
            return

        self.stop_all_threads(app)
        for camera in app.config["camera_registry"].values():
            if int(camera.enable) != 1:
                continue
            if self.add_thread(camera):
                app.logger.info("重启工服检测线程 camera %s", camera.id)
                time.sleep(0.2)  # 错峰启动，避免多摄像头同时初始化占满资源