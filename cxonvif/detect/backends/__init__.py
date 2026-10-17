"""检测后端集合。"""

from .mock_backend import MockDetector
from .onnx_backend import OnnxRuntimeDetector
from .openvino_backend import OpenVinoDetector
from .ultralytics_backend import UltralyticsDetector

__all__ = ["MockDetector", "OnnxRuntimeDetector", "OpenVinoDetector", "UltralyticsDetector"]
