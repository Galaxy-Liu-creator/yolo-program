from __future__ import annotations

import logging

import settings
from violation_module.base import BaseVio

LOGGER = logging.getLogger(__name__)


class WorkwearMissingViolation(BaseVio):
    """YOLOv11 未穿工服规则。

    规则口径：
    1. 只统计 ROI 内、面积满足阈值的人体目标。
    2. 单帧内只要存在一个有效人员未命中任一合规工服标签，即记为违规帧。
    3. 使用“违规帧数 / 有效人员帧数”做时间窗判定，避免空帧稀释触发比例。
    """

    rule_code = "workwear_missing"
    rule_name = "未穿工服"

    def run(self) -> bool | None:
        workwear_labels = self._load_workwear_labels()
        if not workwear_labels:
            LOGGER.warning(
                "WORKWEAR_LABELS is empty, skip %s rule evaluation.",
                self.rule_code,
            )
            self.plot_targets.clear()
            return None

        min_area = self._load_min_person_area()
        trigger_ratio = self._load_trigger_ratio()

        if not self.targets:
            self.plot_targets.clear()
            return None

        violation_frame_indices: list[int] = []
        valid_frame_count = 0

        for frame_idx, frame_item in enumerate(self.targets):
            persons = self._extract_persons(frame_item)
            frame_has_valid_person = False
            frame_has_violation = False

            for person in persons:
                if not self._is_valid_person(person, min_area):
                    continue

                frame_has_valid_person = True
                if self._has_compliant_workwear(person, workwear_labels):
                    continue

                frame_has_violation = True
                self._add_person_to_plot(frame_idx, person)

            if frame_has_valid_person:
                valid_frame_count += 1
            if frame_has_violation:
                violation_frame_indices.append(frame_idx)

        if valid_frame_count == 0:
            self.plot_targets.clear()
            return None

        violation_ratio = len(violation_frame_indices) / valid_frame_count
        if violation_ratio < trigger_ratio or not self.plot_targets:
            self.plot_targets.clear()
            return None

        return self.save(self.rule_name)

    @staticmethod
    def _extract_persons(frame_item: dict | object) -> list[dict]:
        if not isinstance(frame_item, dict):
            return []

        persons = frame_item.get("persons", [])
        if not isinstance(persons, list):
            return []

        return [person for person in persons if isinstance(person, dict)]

    @staticmethod
    def _load_workwear_labels() -> set[str]:
        raw_labels = getattr(settings, "WORKWEAR_LABELS", [])
        if not isinstance(raw_labels, (list, tuple, set)):
            return set()

        return {
            str(label).strip()
            for label in raw_labels
            if str(label).strip()
        }

    @staticmethod
    def _load_min_person_area() -> int:
        raw_value = getattr(settings, "MIN_PERSON_BOX_AREA", 3000)
        try:
            return max(int(raw_value), 0)
        except (TypeError, ValueError):
            return 3000

    @staticmethod
    def _load_trigger_ratio() -> float:
        raw_value = getattr(settings, "TEMPORAL_TRIGGER_RATIO", 0.6)
        try:
            return min(max(float(raw_value), 0.0), 1.0)
        except (TypeError, ValueError):
            return 0.6

    @staticmethod
    def _is_valid_person(person: dict, min_area: int) -> bool:
        bbox = person.get("bbox", [])
        if not isinstance(bbox, list) or len(bbox) != 4:
            return False

        if not person.get("in_roi", True):
            return False

        area = person.get("area", 0)
        try:
            area_value = float(area)
        except (TypeError, ValueError):
            return False

        return area_value >= float(min_area)

    @staticmethod
    def _has_compliant_workwear(person: dict, workwear_labels: set[str]) -> bool:
        workwear_items = person.get("workwear_items", [])
        if not isinstance(workwear_items, list):
            return False

        for item in workwear_items:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).strip()
            if label in workwear_labels:
                return True
        return False

    def _add_person_to_plot(self, frame_idx: int, person: dict) -> None:
        bbox = person.get("bbox", [])
        if len(bbox) != 4:
            return

        try:
            x1, y1, x2, y2 = [int(v) for v in bbox]
            confidence = float(person.get("confidence", 0.0))
        except (TypeError, ValueError):
            return

        person_target = [x1, y1, x2, y2, confidence, "person"]
        self.add_plot_targets(frame_idx, [person_target, [], confidence])
