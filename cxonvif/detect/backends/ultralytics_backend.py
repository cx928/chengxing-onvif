"""Ultralytics 后端（.pt）——覆盖 YOLO 全系、RT-DETR、YOLO-World。"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from ..base import Detector, DetectorError
from ..models import ModelSpec
from ..types import Detection


class UltralyticsDetector(Detector):
    backend = "ultralytics"
    display_name = "Ultralytics PyTorch"

    def __init__(self, detect, spec: ModelSpec | None = None, *, device: str = "cpu") -> None:
        super().__init__(detect, spec, device=device)
        self.model = None
        self.names: tuple[str, ...] = self.labels
        self._task = spec.task if spec else "detect"

    def load(self) -> None:
        try:
            import torch  # noqa: F401
            from ultralytics import YOLO  # type: ignore
        except Exception as exc:
            self.load_error = f"未安装 ultralytics/torch：{exc}"
            raise DetectorError(self.load_error) from exc

        source = str(self.model_path) if self.model_path else (self.spec.filename if self.spec else "yolo11n.pt")
        try:
            self.model = YOLO(source)
        except Exception as exc:
            self.load_error = f"模型加载失败：{exc}"
            raise DetectorError(self.load_error) from exc

        names = getattr(self.model, "names", None)
        if isinstance(names, dict) and names:
            self.names = tuple(str(names[i]) for i in sorted(names))
        elif isinstance(names, (list, tuple)) and names:
            self.names = tuple(str(n) for n in names)
        else:
            self.names = self.labels
        self.labels = self.names
        self.loaded = True
        self.load_error = ""

    def _device_arg(self) -> str | int | None:
        device = (self.device or "cpu").lower()
        if device in {"cpu", "auto", ""}:
            return "cpu"
        if device.startswith("cuda"):
            return 0
        if device in {"dml", "directml"}:
            return "dml"
        if device.startswith("xpu"):
            return "xpu" if device == "xpu" else device
        return device

    def infer(self, frame: np.ndarray, *, confidence: float, iou: float) -> list[Detection]:
        if self.model is None:
            raise DetectorError("模型尚未加载")
        started = time.perf_counter()
        device = self._device_arg()
        kwargs: dict[str, Any] = {
            "imgsz": self.input_size,
            "conf": float(confidence),
            "iou": float(iou),
            "verbose": False,
            "max_det": int(self.detect.maxDetections),
            "device": device,
        }
        try:
            results = self.model.predict(source=frame, **kwargs)
        except Exception:
            # DirectML/XPU 不可用时回退 CPU 一次
            if device not in ("cpu", None):
                self.device = "cpu"
                results = self.model.predict(source=frame, **{**kwargs, "device": "cpu"})
            else:
                raise

        detections: list[Detection] = []
        height, width = frame.shape[:2]
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                try:
                    x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                except Exception:
                    continue
                label = self.names[cls_id] if 0 <= cls_id < len(self.names) else str(cls_id)
                detections.append(
                    Detection(
                        label=label,
                        confidence=conf,
                        box=(
                            max(0.0, min(1.0, x1 / width)),
                            max(0.0, min(1.0, y1 / height)),
                            max(0.0, min(1.0, x2 / width)),
                            max(0.0, min(1.0, y2 / height)),
                        ),
                        class_id=cls_id,
                        group=self._group(label),
                    )
                )
        self.last_inference_ms = (time.perf_counter() - started) * 1000
        return detections
