"""模拟检测后端（单元测试 / 演示模式，无任何重依赖）。"""

from __future__ import annotations

import time

import numpy as np

from ..base import Detector
from ..models import COCO_LABELS
from ..types import Detection


class MockDetector(Detector):
    backend = "mock"
    display_name = "模拟检测器"

    def load(self) -> None:
        self.labels = COCO_LABELS
        self.loaded = True

    def infer(self, frame: np.ndarray, *, confidence: float, iou: float) -> list[Detection]:
        started = time.perf_counter()
        configured = (self.detect.extraArgs or {}).get("mockDetections")
        detections: list[Detection] = []
        if isinstance(configured, list) and configured:
            for item in configured:
                label = str(item.get("label", "person"))
                detections.append(
                    Detection(
                        label=label,
                        confidence=float(item.get("confidence", 0.9)),
                        box=tuple(float(v) for v in item.get("box", [0.3, 0.3, 0.6, 0.8])),  # type: ignore[arg-type]
                        class_id=int(item.get("classId", 0)),
                        group=self._group(label),
                    )
                )
        elif frame is not None and float(frame.mean()) >= 0:
            label = "person"
            detections = [
                Detection(
                    label=label,
                    confidence=max(0.5, min(0.99, confidence + 0.3)),
                    box=(0.32, 0.28, 0.58, 0.86),
                    class_id=0,
                    group=self._group(label),
                )
            ]
        self.last_inference_ms = (time.perf_counter() - started) * 1000
        return detections
