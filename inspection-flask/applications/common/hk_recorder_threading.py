from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import cv2

import settings

# 连续抓图失败计数，达到阈值时升级为 warning 日志（每摄像头独立计数）
_FAIL_COUNTS: dict[int, int] = {}
_FAIL_WARN_THRESHOLD = 5


def _read_frame_from_camera(camera):
    """从摄像头读取一帧。

    优先读取 frame_path 指定的图片文件（调试用）。
    若未配置或读取失败则返回 None，避免把占位图当作真实检测输入。
    """
    frame_path = getattr(camera, "frame_path", None)
    if frame_path:
        image_path = Path(frame_path)
        if image_path.exists():
            image = cv2.imread(str(image_path))
            if image is not None:
                return image
    return None


def get_img(cameras, app):
    """遍历启用的摄像头，抓取最新帧并写入全局缓存。
    每个摄像头只保留最新帧，旧帧由新帧直接覆盖。"""
    for camera in cameras:
        if int(getattr(camera, "enable", 0)) != 1:
            continue

        cid = int(camera.id)
        image = _read_frame_from_camera(camera)

        if image is None or image.size == 0:
            _FAIL_COUNTS[cid] = _FAIL_COUNTS.get(cid, 0) + 1
            fail_count = _FAIL_COUNTS[cid]
            app.config["hk_images"].pop(cid, None)
            app.config["hk_images_datetime"].pop(cid, None)
            if fail_count == 1 or fail_count % _FAIL_WARN_THRESHOLD == 0:
                app.logger.warning(
                    "camera %s 连续第 %d 次抓图失败，请检查设备连接或 frame_path 配置",
                    cid,
                    fail_count,
                )
            continue

        # 抓图成功，重置失败计数
        if _FAIL_COUNTS.get(cid, 0) > 0:
            app.logger.info("camera %s 抓图恢复正常", cid)
        _FAIL_COUNTS[cid] = 0

        # 写入缓存：每个摄像头只保留最新帧
        app.config["hk_images"][cid] = image
        app.config["hk_images_datetime"][cid] = datetime.now()


class HKRecorderThread(threading.Thread):
    def __init__(self, manager, camera):
        super().__init__(daemon=True, name=f"HKRecorderThread-{camera.id}")
        self.manager = manager
        self.camera = camera

    def run(self):
        self.manager.run_once(cameras=[self.camera])


class HKRecorder:
    def __init__(self, manager, camera):
        self.manager = manager
        self.camera = camera

    def run(self, app):
        self.manager.run_once(app=app, cameras=[self.camera])


class HKRecorderThreadManager:
    def __init__(self, app=None):
        self.app = app
        self.cameras: dict[str, object] = {}
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

    def bind_app(self, app):
        self.app = app

    def register_camera(self, camera):
        with self._lock:
            self.cameras[str(camera.id)] = camera

    def unregister_camera(self, camera_id):
        with self._lock:
            self.cameras.pop(str(camera_id), None)
        try:
            cache_key = int(camera_id)
        except (TypeError, ValueError):
            cache_key = camera_id
        _FAIL_COUNTS.pop(cache_key, None)
        if self.app is not None:
            self.app.config.get("hk_images", {}).pop(cache_key, None)
            self.app.config.get("hk_images_datetime", {}).pop(cache_key, None)

    def list_cameras(self):
        with self._lock:
            return list(self.cameras.values())

    def run_once(self, app=None, cameras=None):
        app = app or self.app
        if app is None:
            return

        camera_list = self.list_cameras() if cameras is None else cameras
        try:
            get_img(camera_list, app)
        except Exception as exc:  # pragma: no cover - 依赖运行环境
            trace = traceback.format_exc()
            app.logger.error("抓图失败: %s\n%s", exc, trace)

    def _loop(self):
        if self.app is None:
            return

        with self.app.app_context():
            while self._running:
                self.run_once(self.app)
                time.sleep(settings.get_image_interval)

    def start_background(self):
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="HKRecorderThreadManager",
        )
        self._thread.start()

    def stop_background(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def run(self, app):
        self.bind_app(app)
        self.run_once(app=app)
