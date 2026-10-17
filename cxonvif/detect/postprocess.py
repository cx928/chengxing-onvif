"""检测后处理 / Post-processing.

兼容多种输出布局：
* YOLOv8/v11 系列：``(1, 4+nc, N)``，cx,cy,w,h + 类别分数；
* YOLOv5 系列：``(1, N, 5+nc)``，cx,cy,w,h,obj + 类别分数；
* 端到端（YOLOv10/26）：``(1, N, 6)``，x1,y1,x2,y2,score,class；
* RT-DETR：``(1, N, 4+nc)``，归一化 cx,cy,w,h + 类别分数。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .types import Detection


def letterbox(
    image: np.ndarray,
    new_size: int = 640,
    color: tuple[int, int, int] = (114, 114, 114),
) -> tuple[np.ndarray, float, tuple[int, int]]:
    """等比缩放 + 灰边填充，返回 (图像, 缩放比, (pad_w, pad_h))。"""
    import cv2

    height, width = image.shape[:2]
    scale = min(new_size / width, new_size / height)
    resized_w, resized_h = int(round(width * scale)), int(round(height * scale))
    resized = cv2.resize(image, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((new_size, new_size, 3), color, dtype=np.uint8)
    pad_w = (new_size - resized_w) // 2
    pad_h = (new_size - resized_h) // 2
    canvas[pad_h : pad_h + resized_h, pad_w : pad_w + resized_w] = resized
    return canvas, scale, (pad_w, pad_h)


def nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.45) -> list[int]:
    """纯 numpy NMS，输入 xyxy。"""
    if boxes.size == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        index = int(order[0])
        keep.append(index)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[index], x1[rest])
        yy1 = np.maximum(y1[index], y1[rest])
        xx2 = np.minimum(x2[index], x2[rest])
        yy2 = np.minimum(y2[index], y2[rest])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        union = areas[index] + areas[rest] - inter
        iou = np.where(union > 0, inter / union, 0.0)
        order = rest[iou <= iou_threshold]
    return keep


def _normalize_rows(array: np.ndarray, expected_cols: int | None = None) -> np.ndarray:
    """把输出统一成 (N, C)；兼容 (1, C, N) 与 (1, N, C)。"""
    if array.ndim == 3:
        array = array[0]
    elif array.ndim == 4:
        array = array[0]
    else:
        array = np.atleast_2d(array)
    if array.ndim != 2:
        return np.zeros((0, 0), dtype=np.float32)
    if expected_cols:
        if array.shape[1] == expected_cols:
            return array.astype(np.float32, copy=False)
        if array.shape[0] == expected_cols:
            return array.T.astype(np.float32, copy=False)
    # 无明确列数时按“通道数远小于候选数”判断
    if array.shape[0] <= 512 and array.shape[1] > array.shape[0]:
        array = array.T
    return array.astype(np.float32, copy=False)


def _xywh_to_xyxy(boxes: np.ndarray, *, center: bool = True) -> np.ndarray:
    if center:
        x, y, w, h = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        return np.stack([x - w / 2, y - h / 2, x + w / 2, y + h / 2], axis=1)
    x, y, w, h = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    return np.stack([x, y, x + w, y + h], axis=1)


def decode_detections(
    output: Any,
    *,
    labels: tuple[str, ...],
    class_map: dict[str, str],
    conf_threshold: float = 0.45,
    iou_threshold: float = 0.45,
    input_size: int = 640,
    output_format: str = "auto",
    scale: float = 1.0,
    pad: tuple[int, int] = (0, 0),
    original_size: tuple[int, int] | None = None,
    max_detections: int = 30,
) -> list[Detection]:
    """将模型原始输出解码为归一化 Detection 列表。"""
    array = np.asarray(output)
    fmt = output_format if output_format in {"yolo_v8", "yolo_v5", "end2end", "rtdetr"} else _guess_format(_normalize_rows(array))
    if fmt == "end2end":
        expected_cols = 6
    elif fmt == "yolo_v5":
        expected_cols = 5 + len(labels) if labels else None
    else:
        expected_cols = 4 + len(labels) if labels else None
    rows = _normalize_rows(array, expected_cols)
    if rows.size == 0:
        return []
    detections: list[Detection] = []

    if fmt == "end2end":
        detections = _decode_end2end(rows, labels, class_map, conf_threshold, original_size, pad, scale)
    else:
        detections = _decode_dense(
            rows,
            labels,
            class_map,
            conf_threshold,
            iou_threshold,
            fmt,
            input_size,
            original_size,
            pad,
            scale,
            max_detections,
        )

    if fmt == "end2end" and detections:
        detections = _nms_detections(detections, iou_threshold, max_detections)
    return detections[:max_detections]


def _guess_format(array: np.ndarray) -> str:
    shape = getattr(array, "shape", ())
    if len(shape) == 3:
        if shape[-1] == 6 and shape[1] <= 1000:
            return "end2end"
        return "yolo_v8"
    rows = _normalize_rows(array)
    return "end2end" if rows.shape[1:] == (6,) else "yolo_v8"


def _decode_end2end(
    rows: np.ndarray,
    labels: tuple[str, ...],
    class_map: dict[str, str],
    conf_threshold: float,
    original_size: tuple[int, int] | None,
    pad: tuple[int, int],
    scale: float,
) -> list[Detection]:
    detections: list[Detection] = []
    for row in rows:
        if row.shape[0] < 6:
            continue
        score = float(row[4])
        if score < conf_threshold:
            continue
        class_id = int(round(float(row[5])))
        if class_id < 0 or (labels and class_id >= len(labels)):
            continue
        label = labels[class_id] if labels else str(class_id)
        box = _map_box(row[:4], original_size, pad, scale)
        if box is None:
            continue
        detections.append(
            Detection(
                label=label,
                confidence=score,
                box=box,
                class_id=class_id,
                group=class_map.get(label, "other"),
            )
        )
    return detections


def _decode_dense(
    rows: np.ndarray,
    labels: tuple[str, ...],
    class_map: dict[str, str],
    conf_threshold: float,
    iou_threshold: float,
    fmt: str,
    input_size: int,
    original_size: tuple[int, int] | None,
    pad: tuple[int, int],
    scale: float,
    max_detections: int,
) -> list[Detection]:
    cols = rows.shape[1]
    has_objectness = fmt == "yolo_v5" or (cols - 4) == len(labels) + 1
    if labels and cols >= 4 + len(labels) and not has_objectness:
        n_classes = len(labels)
    else:
        n_classes = cols - 4 - (1 if has_objectness else 0)
        if labels and n_classes > len(labels):
            n_classes = len(labels)

    boxes_raw = rows[:, :4]
    if has_objectness:
        objectness = rows[:, 4]
        class_scores = rows[:, 5 : 5 + n_classes]
        scores = objectness[:, None] * class_scores
    else:
        scores = rows[:, 4 : 4 + n_classes]

    if scores.size == 0:
        return []
    class_ids = scores.argmax(axis=1)
    confidences = scores[np.arange(scores.shape[0]), class_ids]
    mask = confidences >= conf_threshold
    if not mask.any():
        return []
    boxes_raw = boxes_raw[mask]
    class_ids = class_ids[mask]
    confidences = confidences[mask]

    # RT-DETR 输出为归一化坐标
    normalized = fmt == "rtdetr" or bool(np.max(boxes_raw) <= 2.0)
    boxes = _xywh_to_xyxy(boxes_raw, center=True)
    if not normalized:
        boxes = boxes / float(input_size)
    np.clip(boxes, 0.0, 1.0, out=boxes)

    keep = nms(boxes, confidences, iou_threshold)
    detections: list[Detection] = []
    for index in keep[:max_detections]:
        class_id = int(class_ids[index])
        label = labels[class_id] if labels and class_id < len(labels) else str(class_id)
        detections.append(
            Detection(
                label=label,
                confidence=float(confidences[index]),
                box=tuple(float(v) for v in boxes[index]),  # type: ignore[arg-type]
                class_id=class_id,
                group=class_map.get(label, "other"),
            )
        )
    return detections


def _map_box(
    raw: np.ndarray,
    original_size: tuple[int, int] | None,
    pad: tuple[int, int],
    scale: float,
) -> tuple[float, float, float, float] | None:
    """端到端模型输出为输入图像像素坐标，需要减去 padding 并归一化。"""
    if original_size is None:
        return None
    x1, y1, x2, y2 = (float(v) for v in raw[:4])
    if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 2.0:
        # 已经是归一化坐标
        return (max(0.0, x1), max(0.0, y1), min(1.0, x2), min(1.0, y2))
    pad_w, pad_h = pad
    x1 = (x1 - pad_w) / max(scale, 1e-6)
    x2 = (x2 - pad_w) / max(scale, 1e-6)
    y1 = (y1 - pad_h) / max(scale, 1e-6)
    y2 = (y2 - pad_h) / max(scale, 1e-6)
    width, height = original_size
    return (
        max(0.0, min(1.0, x1 / width)),
        max(0.0, min(1.0, y1 / height)),
        max(0.0, min(1.0, x2 / width)),
        max(0.0, min(1.0, y2 / height)),
    )


def _nms_detections(detections: list[Detection], iou_threshold: float, max_detections: int) -> list[Detection]:
    if not detections:
        return []
    boxes = np.array([d.box for d in detections], dtype=np.float32)
    scores = np.array([d.confidence for d in detections], dtype=np.float32)
    keep = nms(boxes, scores, iou_threshold)
    return [detections[i] for i in keep][:max_detections]
