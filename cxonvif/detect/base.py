"""检测后端抽象 / Detector interface and factory."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..config import DetectConfig
from ..logbus import info, warn
from .models import COCO_LABELS, MODELS, ModelSpec, download_model, model_path, resolve_model
from .types import Detection


class DetectorError(RuntimeError):
    pass


class Detector:
    """所有检测后端的统一接口。"""

    backend = "base"
    display_name = "Base"

    def __init__(self, detect: DetectConfig, spec: ModelSpec | None = None, *, device: str = "auto") -> None:
        self.detect = detect
        self.spec = spec
        self.device = device
        self.labels: tuple[str, ...] = spec.labels if spec and spec.labels else COCO_LABELS
        self.input_size = spec.inputSize if spec else 640
        self.output_format = spec.outputFormat if spec else "auto"
        self.model_path: Path | None = None
        self.loaded = False
        self.load_error = ""
        self.last_inference_ms = 0.0

    # ---- 生命周期 ----
    def load(self) -> None:  # pragma: no cover - 抽象方法
        raise NotImplementedError

    def close(self) -> None:
        self.loaded = False

    # ---- 推理 ----
    def infer(self, frame: np.ndarray, *, confidence: float, iou: float) -> list[Detection]:
        raise NotImplementedError

    # ---- 元信息 ----
    def describe(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "name": self.display_name,
            "device": self.device,
            "model": self.spec.name if self.spec else (self.model_path.name if self.model_path else "custom"),
            "labels": len(self.labels),
            "inputSize": self.input_size,
            "loaded": self.loaded,
            "error": self.load_error,
        }

    def _group(self, label: str) -> str:
        return self.detect.classMap.get(label, "other")


@dataclass
class DetectorRequest:
    detect: DetectConfig
    backend: str = "auto"
    device: str = "auto"
    model_path: str = ""


def resolve_device(requested: str, backend: str) -> str:
    if requested and requested != "auto":
        return requested
    if backend == "ultralytics":
        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                return "cuda:0"
        except Exception:
            pass
        try:
            import torch_directml  # type: ignore  # noqa: F401

            return "dml"
        except Exception:
            pass
        try:
            import torch  # type: ignore

            if hasattr(torch, "xpu") and torch.xpu.is_available():  # type: ignore[attr-defined]
                return "xpu"
        except Exception:
            pass
        return "cpu"
    if backend == "onnxruntime":
        try:
            import onnxruntime  # type: ignore

            providers = onnxruntime.get_available_providers()
            for candidate, device in (
                ("CUDAExecutionProvider", "cuda:0"),
                ("TensorrtExecutionProvider", "tensorrt"),
                ("DmlExecutionProvider", "dml"),
                ("OpenVINOExecutionProvider", "openvino"),
                ("ROCMExecutionProvider", "rocm"),
            ):
                if candidate in providers:
                    return device
        except Exception:
            pass
        return "cpu"
    if backend == "openvino":
        try:
            import openvino as ov  # type: ignore

            devices = [str(d) for d in ov.Core().available_devices]
            for prefix in ("GPU", "NPU"):
                for device in devices:
                    if device.startswith(prefix):
                        return device
        except Exception:
            pass
        return "CPU"
    return "cpu"


def _ensure_model_file(spec: ModelSpec | None, model_path_hint: str) -> Path | None:
    """定位或下载模型文件。"""
    if model_path_hint:
        path = Path(model_path_hint).expanduser()
        if path.exists():
            return path
        raise DetectorError(f"模型文件不存在：{path}")
    if spec is None:
        return None
    if spec.family == "custom":
        from ..paths import MODELS_DIR

        matches = sorted(MODELS_DIR.glob("*")) if MODELS_DIR.exists() else []
        for candidate in matches:
            if candidate.suffix.lower() in {".pt", ".onnx", ".xml", ".engine"}:
                return candidate
        raise DetectorError("models 目录中没有可用的自定义模型")
    existing = model_path(spec)
    if existing:
        return existing
    if spec.url:
        ok, message = download_model(spec.key)
        if not ok:
            raise DetectorError(message)
        return model_path(spec)
    return None


def create_detector(request: DetectorRequest) -> Detector:
    """按模型类型和后端偏好创建检测器。"""
    detect = request.detect
    backend = request.backend or "auto"

    # 模拟后端不需要任何模型文件
    if backend == "mock":
        from .backends.mock_backend import MockDetector

        detector: Detector = MockDetector(detect, None, device="mock")
        detector.load()
        return detector

    spec = resolve_model(detect.model)

    model_file: Path | None
    try:
        model_file = _ensure_model_file(spec, request.model_path or "")
    except DetectorError:
        raise

    suffix = (model_file.suffix.lower() if model_file else (Path(spec.filename).suffix.lower() if spec and spec.filename else ".pt"))
    if backend == "auto":
        if suffix in {".onnx", ".engine", ".plan"}:
            backend = "onnxruntime"
        elif suffix == ".xml":
            backend = "openvino"
        elif suffix == ".pt":
            backend = "ultralytics"
        else:
            backend = "ultralytics"

    device = resolve_device(request.device or detect.device, backend)

    if backend == "ultralytics":
        from .backends.ultralytics_backend import UltralyticsDetector

        detector = UltralyticsDetector(detect, spec, device=device)
    elif backend == "onnxruntime":
        from .backends.onnx_backend import OnnxRuntimeDetector

        detector = OnnxRuntimeDetector(detect, spec, device=device)
    elif backend == "openvino":
        from .backends.openvino_backend import OpenVinoDetector

        detector = OpenVinoDetector(detect, spec, device=device)
    else:
        raise DetectorError(f"未知检测后端：{backend}")

    if model_file:
        detector.model_path = model_file
    detector.load()
    info(f"检测器就绪：{detector.describe()}", "detect")
    return detector


def backend_installed(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False
