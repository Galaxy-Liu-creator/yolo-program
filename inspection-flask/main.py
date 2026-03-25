"""YOLOv11 加油站工服检测管线 — 独立诊断与验证工具。

不依赖 Flask 应用上下文，可直接通过命令行运行，支持以下模式：

  python main.py check              验证模型加载与推理设备
  python main.py image <path>       对单张图片或目录执行检测
  python main.py image <path> -o <dir>  检测结果可视化并输出到指定目录

使用场景：
  - 部署前快速验证权重文件与推理环境是否就绪
  - 对离线图片批量跑检测，评估模型准确率
  - 无需启动 Flask 服务即可调试检测链路
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import settings
from utils.models import (
    PersonDetector,
    WorkwearDetector,
    load_detection_models,
    select_runtime_device,
)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _load_models() -> tuple[PersonDetector, WorkwearDetector, str]:
    device = select_runtime_device()
    print(f"[INFO] 推理设备: {device}")
    t0 = time.perf_counter()
    person_model, workwear_model = load_detection_models(device)
    elapsed = time.perf_counter() - t0
    print(f"[INFO] 模型加载完成，耗时 {elapsed:.2f}s")
    return person_model, workwear_model, device


def _draw_results(
    frame: np.ndarray,
    person_contexts: list[dict],
) -> np.ndarray:
    """在帧上绘制人员框与工服检测结果，返回标注后的图像副本。"""
    canvas = frame.copy()
    for ctx in person_contexts:
        x1, y1, x2, y2 = ctx["bbox"]
        has_ww = ctx.get("has_workwear", False)
        color = (0, 180, 0) if has_ww else (0, 0, 220)
        label_text = "OK" if has_ww else "NO_WORKWEAR"
        conf = ctx.get("confidence", 0.0)
        tag = f"{label_text} {conf:.2f}"

        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        cv2.rectangle(canvas, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(canvas, tag, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        for item in ctx.get("workwear_items", []):
            bx1, by1, bx2, by2 = item["bbox"]
            bx1 += x1
            by1 += y1
            bx2 += x1
            by2 += y1
            wlabel = f"{item['label']} {item['confidence']:.2f}"
            cv2.rectangle(canvas, (bx1, by1), (bx2, by2), (0, 160, 0), 1)
            cv2.putText(canvas, wlabel, (bx1, by1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 160, 0), 1)
    return canvas


def _build_person_contexts(
    frame: np.ndarray,
    persons: list[dict],
    workwear_model: WorkwearDetector,
) -> list[dict]:
    """复用与 HKCustomThread.build_person_contexts 相同的逻辑构建人员上下文。"""
    min_area = getattr(settings, "MIN_PERSON_BOX_AREA", 3000)
    workwear_conf = getattr(settings, "WORKWEAR_CONF", 0.45)
    use_white_bg = getattr(settings, "USE_WHITE_BG_MASK", False)
    workwear_labels = getattr(settings, "WORKWEAR_LABELS", [])

    contexts: list[dict] = []
    for person in persons:
        bbox = person.get("bbox", [])
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = bbox
        area = max(0, x2 - x1) * max(0, y2 - y1)
        if area < min_area:
            continue

        if use_white_bg:
            crop = _make_white_bg_crop(frame, bbox)
        else:
            crop = _crop_person(frame, bbox)

        workwear_items: list[dict] = []
        if crop is not None and crop.size > 0:
            workwear_items = workwear_model.infer(crop, conf_threshold=workwear_conf)

        has_workwear = any(
            item.get("label") in workwear_labels for item in workwear_items
        )
        contexts.append(
            {
                "bbox": bbox,
                "confidence": float(person.get("confidence", 0.0)),
                "label": person.get("label", "person"),
                "area": area,
                "workwear_items": workwear_items,
                "has_workwear": has_workwear,
            }
        )
    return contexts


def _crop_person(frame: np.ndarray, bbox: list) -> np.ndarray | None:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(frame.shape[1], x2)
    y2 = min(frame.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2]


def _make_white_bg_crop(frame: np.ndarray, bbox: list) -> np.ndarray:
    h, w = frame.shape[:2]
    x1 = max(0, int(bbox[0]))
    y1 = max(0, int(bbox[1]))
    x2 = min(w, int(bbox[2]))
    y2 = min(h, int(bbox[3]))
    white = np.ones((h, w, 3), dtype=np.uint8) * 255
    white[y1:y2, x1:x2] = frame[y1:y2, x1:x2]
    return white[y1:y2, x1:x2]


def _process_single_image(
    image_path: Path,
    person_model: PersonDetector,
    workwear_model: WorkwearDetector,
    output_dir: Path | None,
) -> dict:
    """对单张图片执行完整检测管线并打印结果。"""
    frame = cv2.imread(str(image_path))
    if frame is None:
        print(f"[WARN] 无法读取图片: {image_path}")
        return {"path": str(image_path), "error": "unreadable"}

    t0 = time.perf_counter()
    persons = person_model.infer(frame, conf_threshold=getattr(settings, "PERSON_CONF", 0.55))
    t_person = time.perf_counter() - t0

    t1 = time.perf_counter()
    contexts = _build_person_contexts(frame, persons, workwear_model)
    t_workwear = time.perf_counter() - t1

    total_persons = len(persons)
    valid_persons = len(contexts)
    violation_count = sum(1 for c in contexts if not c.get("has_workwear", False))
    compliant_count = valid_persons - violation_count

    print(f"\n  {image_path.name}")
    print(f"    人员检测: {total_persons} 人 ({t_person * 1000:.1f}ms)")
    print(f"    有效目标: {valid_persons} 人 (面积 >= {getattr(settings, 'MIN_PERSON_BOX_AREA', 3000)})")
    print(f"    穿戴合规: {compliant_count}    未穿工服: {violation_count}")
    print(f"    工服检测耗时: {t_workwear * 1000:.1f}ms (共 {valid_persons} 次裁剪推理)")

    for i, ctx in enumerate(contexts):
        status = "合规" if ctx["has_workwear"] else "违规"
        items_str = ", ".join(
            f"{it['label']}({it['confidence']:.2f})" for it in ctx.get("workwear_items", [])
        ) or "无"
        print(f"      [{i}] {status} conf={ctx['confidence']:.2f} area={ctx['area']} 工服={items_str}")

    if output_dir is not None:
        canvas = _draw_results(frame, contexts)
        out_path = output_dir / f"det_{image_path.stem}.jpg"
        cv2.imwrite(str(out_path), canvas)
        print(f"    可视化已保存: {out_path}")

    return {
        "path": str(image_path),
        "total_persons": total_persons,
        "valid_persons": valid_persons,
        "compliant": compliant_count,
        "violations": violation_count,
    }


def cmd_check(_args: argparse.Namespace) -> None:
    """验证模型加载与推理设备是否就绪。"""
    print("=" * 60)
    print("YOLOv11 工服检测管线 — 环境检查")
    print("=" * 60)

    print(f"\n[配置]")
    print(f"  PERSON_WEIGHT      : {settings.PERSON_WEIGHT}")
    print(f"  WORKWEAR_WEIGHT    : {settings.WORKWEAR_WEIGHT}")
    print(f"  PERSON_CONF        : {getattr(settings, 'PERSON_CONF', 0.55)}")
    print(f"  WORKWEAR_CONF      : {getattr(settings, 'WORKWEAR_CONF', 0.45)}")
    print(f"  WORKWEAR_LABELS    : {getattr(settings, 'WORKWEAR_LABELS', [])}")
    print(f"  MIN_PERSON_BOX_AREA: {getattr(settings, 'MIN_PERSON_BOX_AREA', 3000)}")
    print(f"  TEMPORAL_WINDOW    : {getattr(settings, 'TEMPORAL_WINDOW_SIZE', 5)}")
    print(f"  TRIGGER_RATIO      : {getattr(settings, 'TEMPORAL_TRIGGER_RATIO', 0.6)}")

    person_ok = Path(settings.PERSON_WEIGHT).exists()
    workwear_ok = Path(settings.WORKWEAR_WEIGHT).exists()
    print(f"\n[权重文件]")
    print(f"  人员检测: {'存在' if person_ok else '缺失'}")
    print(f"  工服检测: {'存在' if workwear_ok else '缺失'}")

    if not (person_ok and workwear_ok):
        print("\n[结果] 权重文件不完整，请先将 .pt 文件放入 weights/ 目录")
        sys.exit(1)

    person_model, workwear_model, device = _load_models()

    dummy = np.zeros((640, 640, 3), dtype=np.uint8)
    t0 = time.perf_counter()
    person_model.infer(dummy)
    t_warmup_person = time.perf_counter() - t0

    crop = np.zeros((128, 64, 3), dtype=np.uint8)
    t1 = time.perf_counter()
    workwear_model.infer(crop)
    t_warmup_workwear = time.perf_counter() - t1

    print(f"\n[预热推理]")
    print(f"  人员检测 warmup: {t_warmup_person * 1000:.1f}ms")
    print(f"  工服检测 warmup: {t_warmup_workwear * 1000:.1f}ms")

    print(f"\n[结果] 环境检查通过，检测管线就绪 (device={device})")


def cmd_image(args: argparse.Namespace) -> None:
    """对单张图片或目录执行工服检测。"""
    target = Path(args.path)
    if not target.exists():
        print(f"[ERROR] 路径不存在: {target}")
        sys.exit(1)

    output_dir: Path | None = None
    if args.output:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)

    person_model, workwear_model, device = _load_models()

    if target.is_file():
        image_paths = [target]
    else:
        image_paths = sorted(
            p for p in target.iterdir()
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
        )
        if not image_paths:
            print(f"[WARN] 目录中未找到图片文件: {target}")
            sys.exit(1)

    print(f"\n待处理图片: {len(image_paths)} 张")
    print("-" * 60)

    results = []
    t_total = time.perf_counter()
    for img_path in image_paths:
        results.append(_process_single_image(img_path, person_model, workwear_model, output_dir))
    elapsed_total = time.perf_counter() - t_total

    valid_results = [r for r in results if "error" not in r]
    total_persons = sum(r["total_persons"] for r in valid_results)
    total_valid = sum(r["valid_persons"] for r in valid_results)
    total_violations = sum(r["violations"] for r in valid_results)
    total_compliant = sum(r["compliant"] for r in valid_results)

    print("\n" + "=" * 60)
    print("汇总")
    print(f"  图片数量: {len(image_paths)} (成功 {len(valid_results)})")
    print(f"  检测人数: {total_persons} (有效 {total_valid})")
    print(f"  穿戴合规: {total_compliant}    未穿工服: {total_violations}")
    print(f"  总耗时: {elapsed_total:.2f}s  平均: {elapsed_total / max(len(valid_results), 1) * 1000:.1f}ms/张")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="YOLOv11 加油站工服检测管线 — 独立诊断与验证工具",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用子命令")

    subparsers.add_parser("check", help="验证模型加载与推理设备")

    image_parser = subparsers.add_parser("image", help="对图片执行工服检测")
    image_parser.add_argument("path", help="图片路径或包含图片的目录")
    image_parser.add_argument("-o", "--output", help="可视化结果输出目录（可选）")

    args = parser.parse_args()

    if args.command == "check":
        cmd_check(args)
    elif args.command == "image":
        cmd_image(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
