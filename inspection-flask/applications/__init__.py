from __future__ import annotations

import logging

from flask import Flask, jsonify

import settings
from applications.common.hk_custom_threading_plus import ThreadManager
from applications.common.hk_recorder_threading import HKRecorderThreadManager


def init_detection_components(app: Flask) -> None:
    from utils.models_v11 import load_detection_models, select_runtime_device

    device = select_runtime_device()
    person_model, workwear_model = load_detection_models(device)

    app.config["device"] = device
    app.config["person_model"] = person_model
    app.config["workwear_model"] = workwear_model
    app.config["camera_registry"] = {}
    app.config["hk_images"] = {}
    app.config["hk_images_datetime"] = {}
    app.config["violate_records"] = []
    app.config["violation_events"] = []
    app.config["ppe_rules"] = {
        "rule_code": "workwear_missing",
        "rule_name": "未穿工服",
        "workwear_labels": list(settings.WORKWEAR_LABELS),
        "window_size": settings.TEMPORAL_WINDOW_SIZE,
        "trigger_ratio": settings.TEMPORAL_TRIGGER_RATIO,
        "min_person_box_area": settings.MIN_PERSON_BOX_AREA,
    }

    recorder_manager = HKRecorderThreadManager(app)
    thread_manager = ThreadManager(app)
    app.config["hk_recorder_thread_manager"] = recorder_manager
    app.config["hk_threadManager"] = thread_manager

    recorder_manager.start_background()

    if not person_model.is_ready:
        app.logger.warning("person model unavailable: %s", person_model.load_error)
    if not workwear_model.is_ready:
        app.logger.warning("workwear model unavailable: %s", workwear_model.load_error)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    app.logger.setLevel(logging.INFO)

    init_detection_components(app)

    from applications.view.system.hk_camera import bp as hk_camera_bp

    app.register_blueprint(hk_camera_bp)

    @app.get("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "device": app.config.get("device"),
                "camera_count": len(app.config["camera_registry"]),
                "violation_count": len(app.config["violate_records"]),
            }
        )

    return app


__all__ = ["create_app", "HKRecorderThreadManager"]
