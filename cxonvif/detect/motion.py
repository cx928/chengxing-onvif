"""轻量运动门控 / Motion gate.

先用人眼级像素差分判断“有没有动静”，只有触发后才跑 AI，
显著降低多路摄像头场景的 CPU/GPU 占用。
"""

from __future__ import annotations

import time

import numpy as np


class MotionGate:
    def __init__(self, sensitivity: int = 55, *, hold_seconds: float = 2.0, min_area: float = 0.0) -> None:
        self.sensitivity = max(1, min(100, int(sensitivity)))
        self.hold_seconds = hold_seconds
        self.min_area = min_area
        self._previous: np.ndarray | None = None
        self._last_motion = 0.0
        self.last_ratio = 0.0
        self.last_error = ""

    def _threshold(self) -> tuple[float, float]:
        # 灵敏度越高，像素差阈值与面积占比阈值越低
        pixel_threshold = 10.0 + (100 - self.sensitivity) * 0.32
        ratio_threshold = 0.0012 + (100 - self.sensitivity) * 0.00006
        return pixel_threshold, max(ratio_threshold, self.min_area)

    def update(self, frame: np.ndarray) -> bool:
        if frame is None:
            return False
        try:
            import cv2
        except Exception:
            return True

        try:
            small = cv2.resize(frame, (96, 54), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
        except Exception as exc:  # pragma: no cover
            self.last_error = str(exc)
            return True

        if self._previous is None:
            self._previous = gray.astype(np.float32)
            return False

        pixel_threshold, ratio_threshold = self._threshold()
        diff = cv2.absdiff(gray.astype(np.float32), self._previous)
        self._previous = self._previous * 0.65 + gray.astype(np.float32) * 0.35
        ratio = float(np.count_nonzero(diff > pixel_threshold)) / diff.size
        self.last_ratio = ratio
        if ratio >= ratio_threshold:
            self._last_motion = time.time()
            return True
        return (time.time() - self._last_motion) <= self.hold_seconds

    @property
    def active(self) -> bool:
        return (time.time() - self._last_motion) <= self.hold_seconds

    def reset(self) -> None:
        self._previous = None
        self._last_motion = 0.0
