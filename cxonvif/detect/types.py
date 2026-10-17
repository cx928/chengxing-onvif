"""检测结果数据类型 / Detection data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 目标组（与 NVR / ONVIF 事件语义对齐）
TARGET_GROUPS = ("person", "vehicle", "animal", "package", "face", "other")

GROUP_LABELS_ZH = {
    "person": "人形",
    "vehicle": "车辆",
    "animal": "动物",
    "package": "物品",
    "face": "人脸",
    "other": "其他",
}


@dataclass
class Detection:
    """单个检测框，坐标归一化到 [0, 1]。"""

    label: str
    confidence: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2
    class_id: int = -1
    track_id: int | None = None
    group: str = "other"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.box
        return (x1 + x2) / 2, (y1 + y2) / 2

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.box
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    def iou(self, other: "Detection") -> float:
        ax1, ay1, ax2, ay2 = self.box
        bx1, by1, bx2, by2 = other.box
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": round(float(self.confidence), 4),
            "box": [round(float(v), 5) for v in self.box],
            "classId": self.class_id,
            "trackId": self.track_id,
            "group": self.group,
        }


@dataclass
class FrameResult:
    """一帧的检测输出。"""

    width: int
    height: int
    detections: list[Detection] = field(default_factory=list)
    inference_ms: float = 0.0
    backend: str = ""
    model: str = ""
    timestamp: float = 0.0

    def groups(self) -> set[str]:
        return {d.group for d in self.detections}

    def labels(self) -> set[str]:
        return {d.group for d in self.detections if d.group != "other"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "inferenceMs": round(self.inference_ms, 2),
            "backend": self.backend,
            "model": self.model,
            "detections": [d.to_dict() for d in self.detections],
        }


@dataclass
class DetectionEvent:
    """发往 ONVIF / 推送通道的检测事件。"""

    camera_id: int
    camera_name: str
    groups: set[str]
    active: bool
    timestamp: str
    confidence: dict[str, float] = field(default_factory=dict)
    detections: list[Detection] = field(default_factory=list)
    snapshot_path: str = ""
    snapshot_bytes: bytes | None = None
    source: str = "ai"           # ai | motion | test
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cameraId": self.camera_id,
            "cameraName": self.camera_name,
            "groups": sorted(self.groups),
            "active": self.active,
            "timestamp": self.timestamp,
            "confidence": {k: round(v, 3) for k, v in self.confidence.items()},
            "detections": [d.to_dict() for d in self.detections],
            "source": self.source,
            "extra": self.extra,
        }
