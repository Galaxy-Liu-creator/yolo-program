from __future__ import annotations

import cv2
import numpy as np


def is_box_overlap(box_a: list, box_b: list) -> float:
    """计算两个边界框的 IoU（交并比）。

    Args:
        box_a: [x1, y1, x2, y2]
        box_b: [x1, y1, x2, y2]

    Returns:
        IoU 值，范围 [0, 1]。两框无交集时返回 0.0。
    """
    ax1, ay1, ax2, ay2 = box_a[0], box_a[1], box_a[2], box_a[3]
    bx1, by1, bx2, by2 = box_b[0], box_b[1], box_b[2], box_b[3]

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    if inter_area == 0:
        return 0.0

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def has_compliant_workwear(person_context: dict, workwear_labels: list[str]) -> bool:
    """判断单个人员上下文是否包含至少一件合规工服。

    Args:
        person_context: 由 HKCustomThread.build_person_contexts() 生成的人员字典，
                        结构为 {"workwear_items": [{"label": str, "confidence": float}, ...], ...}
        workwear_labels: 合规工服类别列表，命中任一即视为穿戴合规。

    Returns:
        True：检测到合规工服；False：未检测到或 workwear_items 为空。
    """
    workwear_items = person_context.get("workwear_items", [])
    return any(item.get("label") in workwear_labels for item in workwear_items)


def count_violation_frames(
    window: list[dict],
    workwear_labels: list[str],
    min_area: int = 3000,
) -> int:
    """统计时间窗口内违规帧的数量。

    遍历窗口中每一帧的人员列表，若该帧存在至少一个有效人员未穿合规工服，
    则计为违规帧。

    Args:
        window:          时间窗口帧列表，每项为 {"persons": [...], "timestamp": ..., ...}
        workwear_labels: 合规工服类别列表。
        min_area:        人员框最小面积阈值，小于此值的目标跳过。

    Returns:
        违规帧数量（整数）。
    """
    count = 0
    for frame_item in window:
        persons = frame_item.get("persons", []) if isinstance(frame_item, dict) else []
        for person in persons:
            if not person.get("in_roi", True):
                continue
            if person.get("area", 0) < min_area:
                continue
            if not has_compliant_workwear(person, workwear_labels):
                count += 1
                break
    return count


def draw_person_workwear_boxes(
    frame: np.ndarray,
    person_contexts: list[dict],
) -> np.ndarray:
    """在图像上绘制人员框和工服检测框（调试可视化用途）。

    - 人员框（合规）：绿色
    - 人员框（违规 / 无工服）：红色
    - 工服框：深绿色

    坐标约定：workwear_items 的 bbox 为相对裁剪图的局部坐标，
    绘制时会换算回原帧坐标系。

    Args:
        frame:           原始帧（BGR 格式 numpy 数组），不会被修改（内部 copy）。
        person_contexts: build_person_contexts() 输出的人员上下文列表。

    Returns:
        绘制了标注框的图像副本。
    """
    vis = frame.copy()

    for person in person_contexts:
        bbox = person.get("bbox", [])
        if len(bbox) != 4:
            continue
        px1, py1, px2, py2 = [int(v) for v in bbox]
        has_workwear = person.get("has_workwear", False)

        person_color = (0, 200, 0) if has_workwear else (0, 0, 220)
        cv2.rectangle(vis, (px1, py1), (px2, py2), person_color, 2)
        conf = person.get("confidence", 0.0)
        label_text = f"person {conf:.2f}"
        cv2.putText(
            vis, label_text, (px1, max(py1 - 6, 10)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, person_color, 1, cv2.LINE_AA,
        )

        for item in person.get("workwear_items", []):
            wb = item.get("bbox", [])
            if len(wb) != 4:
                continue
            wx1 = px1 + int(wb[0])
            wy1 = py1 + int(wb[1])
            wx2 = px1 + int(wb[2])
            wy2 = py1 + int(wb[3])
            cv2.rectangle(vis, (wx1, wy1), (wx2, wy2), (0, 180, 0), 1)
            wlabel = f"{item.get('label', '')} {item.get('confidence', 0.0):.2f}"
            cv2.putText(
                vis, wlabel, (wx1, max(wy1 - 4, 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 180, 0), 1, cv2.LINE_AA,
            )

    return vis
