from __future__ import annotations

import logging

import settings
from violation_module.base import BaseVio

LOGGER = logging.getLogger(__name__)


class WorkwearMissingViolation(BaseVio):
    """YOLOv11 未穿工服规则。

    规则口径：
    1. 只统计 ROI 内、面积满足阈值的人体目标。
    2. 按 track_id 维度做时序判定：同一人连续违规才触发，不同人拼出的违规帧不累计。
    3. 任一 track 的「违规帧数 / 该 track 出现帧数 >= trigger_ratio」即触发告警。
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

        track_stats: dict[int, dict] = {}

        for frame_idx, frame_item in enumerate(self.targets):
            persons = self._extract_persons(frame_item)
            for person in persons:
                if not self._is_valid_person(person, min_area):
                    continue

                track_id = person.get("track_id")
                if track_id is None:
                    continue

                if track_id not in track_stats:
                    track_stats[track_id] = {
                        "appear": 0,
                        "violation": 0,
                        "best_conf": 0.0,
                    }

                track_stats[track_id]["appear"] += 1

                if not self._has_compliant_workwear(person, workwear_labels):
                    track_stats[track_id]["violation"] += 1
                    self._add_person_to_plot(frame_idx, person)
                    conf = float(person.get("confidence", 0.0))
                    if conf > track_stats[track_id]["best_conf"]:
                        track_stats[track_id]["best_conf"] = conf

        if not track_stats:
            self.plot_targets.clear()
            return None

        triggered_track = None
        for tid, stats in track_stats.items():
            if stats["appear"] == 0:
                continue
            ratio = stats["violation"] / stats["appear"]
            if ratio >= trigger_ratio:
                triggered_track = tid
                break

        if triggered_track is None or not self.plot_targets:
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

        detected = {
            str(item.get("label", "")).strip()
            for item in workwear_items
            if isinstance(item, dict)
        }

        mode = getattr(settings, "WORKWEAR_COMPLIANCE_MODE", "any")
        if mode == "all":
            required = set(getattr(settings, "WORKWEAR_REQUIRED_LABELS", []))
            if not required:
                return bool(detected & workwear_labels)
            return required.issubset(detected)

        return bool(detected & workwear_labels)

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
