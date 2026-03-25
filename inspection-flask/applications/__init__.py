import logging
import os
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from flask_cors import CORS

import settings
from applications.common.hk_custom_threading_plus import ThreadManager
from applications.common.flask_log import handle_global_exceptions
from applications.common.hk_recorder_threading import HKRecorderThreadManager
from applications.common.script import init_script
from applications.config import BaseConfig
from applications.extensions import init_plugs
from applications.view import init_bps
from utils.models import load_detection_models, select_runtime_device

# ── 以下为尚未加入工程的旧 YOLOv5 模块，待对应文件补齐后按需恢复 ──────────────
# from lying_module.Lying_Detect import Lying_Detect
# from utils.models import get_all_models          # YOLOv5 风格，已弃用
# from utils.torch_utils import select_device      # YOLOv5 风格，已弃用
# from insightface_module.FaceRecognition import FaceRecognition  # 警务专用，已弃用
# from applications.models import Camera           # 旧摄像头模型，已由 HKCamera 替代


def setup_logging(app):
    log_folder = 'logs'
    log_file = os.path.join(log_folder, 'app.log')
    if not os.path.exists(log_folder):
        try:
            os.makedirs(log_folder)
        except OSError as e:
            print(f"Failed to create log directory: {log_folder} - {e}")
    handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(filename)s:%(lineno)d')
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)


def init_detection_models(app):
    app.config["person_model"] = None
    app.config["workwear_model"] = None
    app.config["device"] = None
    app.config["detection_pipeline_ready"] = False
    app.config["detection_model_init_error"] = None

    try:
        device = select_runtime_device()
        person_model, workwear_model = load_detection_models(device)
    except Exception as exc:  # pragma: no cover - 依赖运行环境
        app.config["detection_model_init_error"] = str(exc)
        app.logger.exception("YOLOv11 模型初始化失败: %s", exc)
        return

    app.config["person_model"] = person_model
    app.config["workwear_model"] = workwear_model
    app.config["device"] = device
    app.config["detection_pipeline_ready"] = True
    app.logger.info("YOLOv11 模型初始化完成，device=%s", device)


def create_app():
    app = Flask(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    CORS(app)
    app.config.from_object(BaseConfig)
    setup_logging(app)

    # ══════════════════════════════════════════════════════════════════════════
    # 第一阶段：模型加载
    # ──────────────────────────────────────────────────────────────────────────
    init_detection_models(app)
    # ══════════════════════════════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════════════════════════
    # 第二阶段：线程管理器 & 全局缓存初始化（不依赖模型，直接激活）
    # ──────────────────────────────────────────────────────────────────────────
    hk_thread_manager = ThreadManager()
    hk_thread_manager.bind_app(app)
    app.config['hk_threadManager'] = hk_thread_manager

    app.config['hk_images']          = {}   # 摄像头最新帧缓存 {camera_id: ndarray}
    app.config['hk_images_datetime'] = {}   # 对应抓图时间戳   {camera_id: datetime}

    hk_recorder = HKRecorderThreadManager()
    hk_recorder.bind_app(app)
    app.config['hk_recorder_thread_manager'] = hk_recorder

    app.config['violation_events'] = []     # 全局违规事件队列（供页面或推送消费）
    app.config['camera_registry']  = {}     # 当前启用摄像头注册表 {camera_id: HKCamera}
    # ══════════════════════════════════════════════════════════════════════════

    # 注册 Flask 插件
    init_plugs(app)
    # 注册蓝图
    init_bps(app)
    # 注册命令
    init_script(app)

    # ══════════════════════════════════════════════════════════════════════════
    # 第三阶段：定时调度（不依赖模型，直接激活）
    # ──────────────────────────────────────────────────────────────────────────
    with app.app_context():
        scheduler = BackgroundScheduler()
        # 定时抓图：按 get_image_interval 周期驱动海康录像线程取帧
        scheduler.add_job(
            app.config['hk_recorder_thread_manager'].run,
            trigger='interval',
            seconds=settings.get_image_interval,
            args=(app,),
        )
        # 每天凌晨 4 点重启所有检测线程，避免长时间运行后线程失效
        scheduler.add_job(
            app.config['hk_threadManager'].restart_all_threads,
            trigger='cron',
            hour=4,
            minute=0,
            args=(app,),
        )
        # 启动后延迟 2 个采集周期再做一次全量重启，确保摄像头初始化完成
        re_start_time = datetime.now() + timedelta(seconds=settings.get_image_interval * 2)
        scheduler.add_job(
            app.config['hk_threadManager'].restart_all_threads,
            trigger='date',
            run_date=re_start_time,
            args=(app,),
        )
        scheduler.start()
        app.config["scheduler"] = scheduler
    # ══════════════════════════════════════════════════════════════════════════

    # 注册全局异常处理
    handle_global_exceptions(app)

    return app
