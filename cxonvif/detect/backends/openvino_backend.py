"""OpenVINO 后端 —— Intel 核显 / 独显 / NPU 原生加速。

支持 OpenVINO IR（.xml + .bin）以及直接读取 ONNX 模型（OpenVINO 会自动转换）。
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from ..base import Detector, DetectorError
from ..models import ModelSpec
from ..postprocess import decode_detections, letterbox
from ..types import Detection


class OpenVinoDetector(Detector):
    backend = "openvino"
    display_name = "OpenVINO"

    def __init__(self, detect, spec: ModelSpec | None = None, *, device: str = "CPU") -> None:
        super().__init__(detect, spec, device=device)
        self.compiled = None
        self.core = None
        self.input_key = None
        self.available_devices: list[str] = []

    def load(self) -> None:
        try:
            import openvino as ov  # type: ignore
        except Exception as exc:
            self.load_error = f"未安装 openvino：{exc}"
            raise DetectorError(self.load_error) from exc
        if not self.model_path or not self.model_path.exists():
            self.load_error = "OpenVINO 模型文件缺失"
            raise DetectorError(self.load_error)

        try:
            self.core = ov.Core()
            self.available_devices = [str(d) for d in self.core.available_devices]
            device = self.device
            if device in {"auto", ""}:
                device = "AUTO"
            if device.upper() == "AUTO" and not any(d.startswith("GPU") for d in self.available_devices):
                device = "CPU"
            model = self.core.read_model(str(self.model_path))
            self.compiled = self.core.compile_model(model, device)
            self.device = device
            input_layer = self.compiled.input(0)
            self.input_key = input_layer
            shape = list(input_layer.partial_shape)
            if len(shape) == 4 and shape[2].is_static:
                self.input_size = int(shape[2].get_length())
        except Exception as exc:
            self.load_error = f"OpenVINO 编译失败：{exc}"
            raise DetectorError(self.load_error) from exc
        self.loaded = True

    def infer(self, frame: np.ndarray, *, confidence: float, iou: float) -> list[Detection]:
        if self.compiled is None:
            raise DetectorError("OpenVINO 模型尚未编译")
        started = time.perf_counter()
        padded, scale, pad = letterbox(frame, self.input_size)
        rgb = padded[:, :, ::-1]
        tensor = np.ascontiguousarray(rgb.transpose(2, 0, 1)[None, ...].astype(np.float32) / 255.0)
        try:
            outputs = self.compiled([tensor])
        except Exception as exc:
            # 部分 IR 需要 NHWC
            try:
                outputs = self.compiled([np.ascontiguousarray(padded[None, ...].astype(np.float32) / 255.0)])
                scale, pad = 1.0, (0, 0)
            except Exception:
                raise DetectorError(f"OpenVINO 推理失败：{exc}") from exc

        original_size = (frame.shape[1], frame.shape[0])
        best: list[Detection] = []
        for output in list(outputs.values()):
            array = np.asarray(output)
            if array.ndim < 2:
                continue
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
        data["availableDevices"] = self.available_devices
        return data
