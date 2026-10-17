"""ONNX Runtime 后端 —— 通用 ONNX 检测模型。

设备映射：
* ``cpu``                → CPUExecutionProvider
* ``cuda:0``             → CUDAExecutionProvider / TensorRT
* ``dml``                → DirectML（Windows 上 Intel/AMD/NVIDIA 通用）
* ``openvino``           → OpenVINO Execution Provider（Intel 核显/独显/NPU）
* ``rocm``               → ROCm（Linux）
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from ..base import Detector, DetectorError
from ..models import ModelSpec
from ..postprocess import decode_detections, letterbox
from ..types import Detection

_PROVIDER_MAP = {
    "cuda": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    "tensorrt": ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"],
    "dml": ["DmlExecutionProvider", "CPUExecutionProvider"],
    "openvino": ["OpenVINOExecutionProvider", "CPUExecutionProvider"],
    "rocm": ["ROCMExecutionProvider", "CPUExecutionProvider"],
    "cpu": ["CPUExecutionProvider"],
}


class OnnxRuntimeDetector(Detector):
    backend = "onnxruntime"
    display_name = "ONNX Runtime"

    def __init__(self, detect, spec: ModelSpec | None = None, *, device: str = "cpu") -> None:
        super().__init__(detect, spec, device=device)
        self.session = None
        self.input_name = ""
        self.output_names: list[str] = []
        self.providers: list[str] = []
        self._dynamic = False

    # ------------------------------------------------------------------ 加载
    def _provider_config(self) -> tuple[list[str], list[tuple[str, dict[str, Any]]]]:
        device = (self.device or "cpu").lower()
        key = "cpu"
        options: dict[str, Any] = {}
        if device.startswith("cuda"):
            key = "cuda"
        elif device.startswith("tensorrt"):
            key = "tensorrt"
        elif device in {"dml", "directml"}:
            key = "dml"
            options = {"device_id": 0}
        elif device.startswith("openvino"):
            key = "openvino"
            options = {"device_type": "GPU" if "gpu" in device else "CPU"}
        elif device.startswith("rocm"):
            key = "rocm"
        providers = _PROVIDER_MAP[key]
        configured: list[tuple[str, dict[str, Any]]] = []
        for provider in providers:
            configured.append((provider, options if provider != "CPUExecutionProvider" else {}))
        return providers, configured

    def load(self) -> None:
        try:
            import onnxruntime as ort  # type: ignore
        except Exception as exc:
            self.load_error = f"未安装 onnxruntime：{exc}"
            raise DetectorError(self.load_error) from exc

        if not self.model_path or not self.model_path.exists():
            self.load_error = "ONNX 模型文件缺失"
            raise DetectorError(self.load_error)

        available = set(ort.get_available_providers())
        requested, configured = self._provider_config()
        providers = [name for name, _ in configured if name in available]
        if not providers:
            providers = ["CPUExecutionProvider"]
            self.device = "cpu"
        if "CPUExecutionProvider" not in providers:
            providers.append("CPUExecutionProvider")

        options_obj = ort.SessionOptions()
        options_obj.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options_obj.intra_op_num_threads = 0

        try:
            self.session = ort.InferenceSession(
                str(self.model_path),
                sess_options=options_obj,
                providers=providers,
            )
        except Exception as exc:
            # 指定 provider 失败时自动回退 CPU
            try:
                self.session = ort.InferenceSession(
                    str(self.model_path),
                    sess_options=options_obj,
                    providers=["CPUExecutionProvider"],
                )
                providers = ["CPUExecutionProvider"]
                self.device = "cpu"
            except Exception as exc2:
                self.load_error = f"ONNX 会话创建失败：{exc2}"
                raise DetectorError(self.load_error) from exc2

        inputs = self.session.get_inputs()
        if not inputs:
            self.load_error = "ONNX 模型没有输入"
            raise DetectorError(self.load_error)
        self.input_name = inputs[0].name
        shape = inputs[0].shape
        if len(shape) == 4 and isinstance(shape[2], int) and shape[2] > 0:
            self.input_size = int(shape[2])
        else:
            self._dynamic = True
        self.output_names = [output.name for output in self.session.get_outputs()]
        self.providers = list(self.session.get_providers())
        self.loaded = True
        self.load_error = ""

    # ------------------------------------------------------------------ 推理
    def _prepare(self, frame: np.ndarray) -> tuple[np.ndarray, float, tuple[int, int]]:
        padded, scale, pad = letterbox(frame, self.input_size)
        rgb = padded[:, :, ::-1]
        tensor = rgb.transpose(2, 0, 1).astype(np.float32) / 255.0
        return np.ascontiguousarray(tensor[None, ...]), scale, pad

    def infer(self, frame: np.ndarray, *, confidence: float, iou: float) -> list[Detection]:
        if self.session is None:
            raise DetectorError("ONNX 会话尚未创建")
        started = time.perf_counter()
        tensor, scale, pad = self._prepare(frame)
        outputs = self.session.run(self.output_names, {self.input_name: tensor})
        original_size = (frame.shape[1], frame.shape[0])

        best: list[Detection] = []
        for index, output in enumerate(outputs):
            array = np.asarray(output)
            if array.ndim < 2:
                continue
            # 分类/分割输出通常维度不匹配，跳过
            if array.ndim == 4:
                array = array[0]
            try:
                detections = decode_detections(
                    array,
                    labels=self.labels,
                    class_map=self.detect.classMap,
                    conf_threshold=confidence,
                    iou_threshold=iou,
                    input_size=self.input_size,
                    output_format=self.output_format,
                    scale=scale,
                    pad=pad,
                    original_size=original_size,
                    max_detections=int(self.detect.maxDetections),
                )
            except Exception:
                continue
            if len(detections) > len(best):
                best = detections
        self.last_inference_ms = (time.perf_counter() - started) * 1000
        return best

    def describe(self) -> dict[str, Any]:
        data = super().describe()
        data["providers"] = self.providers
        return data
