"""检测子系统：模型注册、后端、跟踪、区域、叠加、管线。"""

from .base import Detector, DetectorError, DetectorRequest, create_detector
from .models import MODELS, ModelSpec, list_models, list_custom_models, resolve_model
from .types import Detection, DetectionEvent, FrameResult, GROUP_LABELS_ZH

__all__ = [
    "Detector",
    "DetectorError",
    "DetectorRequest",
    "create_detector",
    "MODELS",
    "ModelSpec",
    "list_models",
    "list_custom_models",
    "resolve_model",
    "Detection",
    "DetectionEvent",
    "FrameResult",
    "GROUP_LABELS_ZH",
]
