from __future__ import annotations

import settings
from violation_module.base import BaseVio


class WorkwearMissingViolation(BaseVio):
    """加油站工人未穿工服违规规则。

    判定逻辑分三层：
    1. 人员有效性过滤：跳过面积过小或不在 ROI 内的目标。
    2. 单帧工服判定：workwear_items 中有任一 label 命中 WORKWEAR_LABELS 即为合规。
    3. 时序比例判定：窗口内违规帧占比 >= TEMPORAL_TRIGGER_RATIO 时触发告警。
    """

    rule_code = "workwear_missing"
    rule_name = "未穿工服"

    def run(self) -> bool | None:
        """执行违规判定。触发时保存证据图并返回 True，否则返回 None。"""
        workwear_labels = getattr(settings, "WORKWEAR_LABELS", [])
        min_area = getattr(settings, "MIN_PERSON_BOX_AREA", 3000)
        trigger_ratio = getattr(settings, "TEMPORAL_TRIGGER_RATIO", 0.6)

        window_size = len(self.targets)
        if window_size == 0:
            return None

        violation_frame_indices: list[int] = []

        for frame_idx, frame_item in enumerate(self.targets):
            persons = frame_item.get("persons", []) if isinstance(frame_item, dict) else []
            frame_has_violation = False

            for person in persons:
                if not person.get("in_roi", True):
                    continue
                if person.get("area", 0) < min_area:
                    continue

                workwear_items = person.get("workwear_items", [])
                has_compliant = any(
                    item.get("label") in workwear_labels for item in workwear_items
                )
                if not has_compliant:
                    frame_has_violation = True
                    self._add_person_to_plot(frame_idx, person)

            if frame_has_violation:
                violation_frame_indices.append(frame_idx)

        ratio = len(violation_frame_indices) / window_size
        if ratio < trigger_ratio:
            self.plot_targets.clear()
            return None

        return self.save(self.rule_name)

    def _add_person_to_plot(self, frame_idx: int, person: dict):
        """将违规人员的标注信息记入 plot_targets，供 base.save() 选取最优证据帧。"""
        bbox = person.get("bbox", [])
        conf = person.get("confidence", 0.0)
        if len(bbox) != 4:
            return
        x1, y1, x2, y2 = [int(v) for v in bbox]
        target_entry = [x1, y1, x2, y2, conf, "person"]
        up_box_list = [target_entry, target_entry, conf]
        self.add_plot_targets(frame_idx, up_box_list)
