"""程星 ONVIF —— 多模型 ONVIF 虚拟摄像机服务器。"""

from .brand import BRAND_EN, BRAND_ZH, PRODUCT
from .version import CURRENT_VERSION

__all__ = ["BRAND_ZH", "BRAND_EN", "PRODUCT", "CURRENT_VERSION"]
__version__ = CURRENT_VERSION
