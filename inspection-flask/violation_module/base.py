from abc import ABCMeta, abstractmethod

from flask import current_app, has_app_context

import settings

from utils.plots import plot_one_box, plot_txt_PIL


def format_targets_for_log(original_targets):
    formatted_targets = []
    if not isinstance(original_targets, list):
        return formatted_targets

    for frame_item in original_targets:
        if isinstance(frame_item, dict):
            persons = frame_item.get("persons", [])
            formatted_targets.append(
                {
                    "camera_id": frame_item.get("camera_id"),
                    "timestamp": str(frame_item.get("timestamp")),
                    "persons": [
                        {
                            "bbox": person.get("bbox"),
                            "confidence": person.get("confidence"),
                            "label": person.get("label"),
                            "has_workwear": person.get("has_workwear"),
                            "workwear_count": len(person.get("workwear_items", []))
                            if isinstance(person.get("workwear_items", []), list)
                            else 0,
                        }
                        for person in persons
                        if isinstance(person, dict)
                    ],
                }
            )
            continue

        if not isinstance(frame_item, list):
            continue

        legacy_persons = []
        for person in frame_item:
            if not isinstance(person, list) or len(person) < 6:
                continue
            if person[5] != "person":
                continue
            legacy_persons.append(person[:7])
        formatted_targets.append(legacy_persons)

    return formatted_targets


def _iter_plot_boxes(target_group):
    if not isinstance(target_group, list):
        return

    for item in target_group:
        if isinstance(item, list) and len(item) >= 6 and not isinstance(item[0], list):
            yield item
            continue
        if isinstance(item, list):
            for nested in item:
                if isinstance(nested, list) and len(nested) >= 6:
                    yield nested


def _extract_plot_confidence(target_group) -> float:
    if (
        isinstance(target_group, list)
        and len(target_group) >= 3
        and isinstance(target_group[2], (int, float))
    ):
        return float(target_group[2])

    confidences = []
    for target in _iter_plot_boxes(target_group):
        try:
            confidences.append(float(target[4]))
        except (TypeError, ValueError, IndexError):
            continue
    return max(confidences, default=float("-inf"))


class BaseVio(metaclass=ABCMeta):
    person_label = ["person"]
    vio_type = None
    camera_id = None
    frames = None
    datetime_list = None
    targets = None
    station_id = None
    dept_id = None
    sub_id = None
    plot_targets = None

    def __init__(self):
        self.vio_type = ""
        self.camera_id = ""
        self.frames = []
        self.datetime_list = []
        self.targets = []
        self.station_id = ""
        self.dept_id = ""
        self.sub_id = ""
        self.plot_targets = {}

    def init(self, frames, datetime_list, targets, vio_type=None, camera_id=None, station_id=None, dept_id=None,
             sub_id=None):
        self.vio_type = vio_type
        self.camera_id = camera_id
        self.frames = frames
        self.datetime_list = datetime_list
        self.targets = targets
        self.station_id = station_id
        self.dept_id = dept_id
        self.sub_id = sub_id
        self.plot_targets = {}

    @abstractmethod
    def run(self):
        pass

    def add_plot_targets(self, key, up_box_list):
        if key in self.plot_targets:
            self.plot_targets[key].append(up_box_list)
        else:
            self.plot_targets[key] = [up_box_list]

    def save(self, name, box_color=None):
        """从 plot_targets 中挑选置信度最高的帧并保存证据图。"""
        from applications.view.system.hk_camera import save_violate_photo

        color = box_color if box_color is not None else [0, 165, 255]

        max_conf = float("-inf")
        max_conf_each = None
        for each, lists in self.plot_targets.items():
            max_each_conf = max(
                (_extract_plot_confidence(target_group) for target_group in lists),
                default=float("-inf"),
            )
            if max_each_conf > max_conf:
                max_conf = max_each_conf
                max_conf_each = each

        if max_conf_each is None or max_conf_each >= len(self.frames):
            self.plot_targets.clear()
            return None

        max_conf_lists = self.plot_targets[max_conf_each]
        source_frame = self.frames[max_conf_each]
        if source_frame is None or not max_conf_lists:
            self.plot_targets.clear()
            return None

        if has_app_context():
            logger = current_app.logger

            def save_with_context(*args, **kwargs):
                return save_violate_photo(*args, **kwargs)
        else:
            from app import app

            logger = app.logger

            def save_with_context(*args, **kwargs):
                with app.app_context():
                    return save_violate_photo(*args, **kwargs)

        vio_image = source_frame.copy()
        logger.warning(
            "工服检测-摄像头 %s 触发告警，即将保存证据图，本轮目标：%s",
            self.camera_id,
            format_targets_for_log(self.targets),
        )
        for target_list in max_conf_lists:
            for target in _iter_plot_boxes(target_list):
                try:
                    confidence = float(target[4])
                except (TypeError, ValueError, IndexError):
                    continue

                logger.warning(
                    "工服检测-摄像头 %s 标注框：%s 标签=%s 置信度=%.2f",
                    self.camera_id,
                    target[:4],
                    target[5],
                    confidence,
                )
                plot_one_box(
                    target[:4],
                    vio_image,
                    color=color,
                    label=f"{target[5]} {confidence:.2f}",
                    line_thickness=1,
                )

        vio_image = plot_txt_PIL(box=[20, 20], img=vio_image, label=name, color=color)
        save_result = save_with_context(
            self.vio_type,
            self.camera_id,
            vio_image,
            self.station_id,
            self.dept_id,
            self.sub_id,
            settings.VIO_IMAGE_PATH,
            self.datetime_list[max_conf_each] if max_conf_each < len(self.datetime_list) else None,
            rule_name=name,
        )
        self.plot_targets.clear()
        if save_result:
            return True
        return None
