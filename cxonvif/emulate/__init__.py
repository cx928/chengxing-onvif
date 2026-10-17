"""水星安防摄像机模拟与报警推送。"""

from .mercury import MercuryEmulator
from .push import AlarmPusher

__all__ = ["MercuryEmulator", "AlarmPusher"]
