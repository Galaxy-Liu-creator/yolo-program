from __future__ import annotations

from pathlib import Path

import settings

try:
    import torch
    _torch_available = True
except ImportError:
    _torch_available = False

try:
    from ultralytics import YOLO
    _ultralytics_available = True
except ImportError:
    _ultralytics_available = False


def select_runtime_device() -> str:
    """返回可用的推理设备标识（'cuda:0' 或 'cpu'）。"""
    if _torch_available and torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def _validate_weight_path(weight_path, detector_name: str) -> Path:
    path = Path(weight_path)
    if not path.exists():
        raise FileNotFoundError(f"{detector_name} 权重文件不存在: {path}")
    return path


class PersonDetector:
    """YOLOv11 人员检测器。

    输入整帧图像，输出人员候选框列表，统一格式为：
        {"bbox": [x1, y1, x2, y2], "confidence": float, "label": "person"}
    """

    def __init__(self, weight_path, device: str = "cpu"):
        if not _ultralytics_available:
            raise ImportError("ultralytics 未安装，请执行 pip install ultralytics")
        path = _validate_weight_path(weight_path, "人员检测模型")
        self.model = YOLO(str(path))
        self.device = device

    def infer(self, frame, conf_threshold: float = 0.55) -> list[dict]:
        """对整帧图像执行人员检测，返回置信度高于阈值的监管对象列表。

        过滤标签由 settings.MONITORED_PERSON_LABELS 驱动，不硬绑 "person"。
        """
        monitored = set(getattr(settings, "MONITORED_PERSON_LABELS", ["person"]))
        imgsz = getattr(settings, "IMGSZ", 640)
        results = self.model(
            frame,
            conf=conf_threshold,
            imgsz=imgsz,
            device=self.device,
            verbose=False,
        )
        detections: list[dict] = []
        for result in results:
            for box in result.boxes:
                label = result.names[int(box.cls)]
                if label not in monitored:
                    continue
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                detections.append(
                    {
                        "bbox": [x1, y1, x2, y2],
                        "confidence": float(box.conf),
                        "label": label,
                    }
                )
        return detections


class WorkwearDetector:
    """YOLOv11 工服检测器。

    输入单个人员框区域图像（裁剪图），输出工服相关类别列表，统一格式为：
        {"bbox": [x1, y1, x2, y2], "confidence": float, "label": "work_clothes"}

    bbox 坐标为相对裁剪图的局部坐标。
    """

    def __init__(self, weight_path, device: str = "cpu"):
        if not _ultralytics_available:
            raise ImportError("ultralytics 未安装，请执行 pip install ultralytics")
        path = _validate_weight_path(weight_path, "工服检测模型")
        self.model = YOLO(str(path))
        self.device = device

    def infer(self, person_crop, conf_threshold: float = 0.45) -> list[dict]:
        """对人员裁剪图执行工服检测，返回检测到的工服目标列表。"""
        if person_crop is None or person_crop.size == 0:
            return []
        imgsz = getattr(settings, "IMGSZ", 640)
        results = self.model(
            person_crop,
            conf=conf_threshold,
            imgsz=imgsz,
            device=self.device,
            verbose=False,
        )
        detections: list[dict] = []
        for result in results:
            for box in result.boxes:
                label = result.names[int(box.cls)]
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                detections.append(
                    {
                        "bbox": [x1, y1, x2, y2],
                        "confidence": float(box.conf),
                        "label": label,
                    }
                )
        return detections


def load_person_detector(device: str = "cpu") -> PersonDetector:
    """根据 settings.PERSON_WEIGHT 加载人员检测器。"""
    return PersonDetector(settings.PERSON_WEIGHT, device)


def load_workwear_detector(device: str = "cpu") -> WorkwearDetector:
    """根据 settings.WORKWEAR_WEIGHT 加载工服检测器。"""
    return WorkwearDetector(settings.WORKWEAR_WEIGHT, device)


def load_detection_models(device: str | None = None) -> tuple[PersonDetector, WorkwearDetector]:
    """统一加载 YOLOv11 人员模型与工服模型。"""
    runtime_device = device or select_runtime_device()
    person_model = load_person_detector(runtime_device)
    workwear_model = load_workwear_detector(runtime_device)
    return person_model, workwear_model
