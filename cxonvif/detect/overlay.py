"""检测框叠加渲染 / Overlay renderer.

* 框与标签支持按目标组着色；
* 标签优先使用中文字体（PIL），找不到字体时自动退回 OpenCV 英文标签；
* 支持绘制区域多边形与时间戳。
"""

from __future__ import annotations

import os
import sys
import time
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..config import OverlayConfig, Zone
from .types import GROUP_LABELS_ZH, Detection

GROUP_COLORS = {
    "person": "#22C55E",
    "vehicle": "#3B82F6",
    "animal": "#F59E0B",
    "package": "#A855F7",
    "face": "#EC4899",
    "other": "#94A3B8",
}

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
)


def _hex_to_bgr(value: str, default: tuple[int, int, int] = (143, 214, 0)) -> tuple[int, int, int]:
    value = (value or "").strip().lstrip("#")
    if len(value) != 6:
        return default
    try:
        r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
        return (b, g, r)
    except ValueError:
        return default


@lru_cache(maxsize=1)
def find_cjk_font() -> str:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return ""


class OverlayRenderer:
    def __init__(self, config: OverlayConfig) -> None:
        self.config = config
        self.font_path = find_cjk_font()
        self._fonts: dict[int, object] = {}

    def _font(self, size: int):
        if size not in self._fonts:
            from PIL import ImageFont

            try:
                self._fonts[size] = ImageFont.truetype(self.font_path, size)
            except Exception:
                self._fonts[size] = ImageFont.load_default()
        return self._fonts[size]

    # ------------------------------------------------------------------ 主入口
    def render(
        self,
        frame: np.ndarray,
        detections: list[Detection],
        *,
        zones: list[Zone] | None = None,
    ) -> np.ndarray:
        cfg = self.config
        if not cfg.showBoxes and not cfg.showLabels and not cfg.showZones and not cfg.drawTimestamp:
            return frame
        try:
            import cv2
        except Exception:
            return self._render_pil_only(frame, detections, zones or [])

        height, width = frame.shape[:2]
        if cfg.showZones and zones:
            frame = self._draw_zones_cv(frame, zones, width, height)
        if cfg.showBoxes:
            for detection in detections:
                x1, y1, x2, y2 = self._to_pixels(detection, width, height)
                color = _hex_to_bgr(GROUP_COLORS.get(detection.group, cfg.boxColor), _hex_to_bgr(cfg.boxColor))
                thickness = max(1, int(cfg.boxThickness))
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness, lineType=cv2.LINE_AA)
                # 四角描边，提升辨识度
                length = max(8, int(min(x2 - x1, y2 - y1) * 0.18))
                for start, end in (
                    ((x1, y1), (x1 + length, y1)),
                    ((x1, y1), (x1, y1 + length)),
                    ((x2, y1), (x2 - length, y1)),
                    ((x2, y1), (x2, y1 + length)),
                    ((x1, y2), (x1 + length, y2)),
                    ((x1, y2), (x1, y2 - length)),
                    ((x2, y2), (x2 - length, y2)),
                    ((x2, y2), (x2, y2 - length)),
                ):
                    cv2.line(frame, start, end, color, thickness + 1, lineType=cv2.LINE_AA)

        if cfg.showLabels:
            frame = self._draw_labels(frame, detections, width, height)

        if cfg.drawTimestamp or cfg.extraText:
            frame = self._draw_corner_text(frame, width, height)
        return frame

    # ------------------------------------------------------------------ 绘制细节
    def _to_pixels(self, detection: Detection, width: int, height: int) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = detection.box
        return (
            max(0, min(width - 1, int(x1 * width))),
            max(0, min(height - 1, int(y1 * height))),
            max(0, min(width - 1, int(x2 * width))),
            max(0, min(height - 1, int(y2 * height))),
        )

    def _label_text(self, detection: Detection) -> str:
        cfg = self.config
        group = detection.group
        name = GROUP_LABELS_ZH.get(group, detection.label)
        if self.font_path:
            text = name
        else:
            text = detection.label.capitalize()
        if cfg.showConfidence:
            text += f" {detection.confidence * 100:.0f}%"
        return text

    def _draw_labels(self, frame: np.ndarray, detections: list[Detection], width: int, height: int) -> np.ndarray:
        if not detections:
            return frame
        if self.font_path:
            try:
                return self._draw_labels_pil(frame, detections, width, height)
            except Exception:
                pass
        import cv2

        cfg = self.config
        scale = max(0.3, float(cfg.fontScale))
        thickness = max(1, int(round(scale * 1.6)))
        for detection in detections:
            x1, y1, x2, y2 = self._to_pixels(detection, width, height)
            color = _hex_to_bgr(GROUP_COLORS.get(detection.group, cfg.boxColor), _hex_to_bgr(cfg.boxColor))
            text = self._label_text(detection)
            (text_w, text_h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
            box_y = y1 - text_h - baseline - 6
            if box_y < 0:
                box_y = y1 + 2
            cv2.rectangle(frame, (x1, box_y), (x1 + text_w + 10, box_y + text_h + baseline + 6), color, -1)
            cv2.putText(
                frame, text, (x1 + 5, box_y + text_h + 2),
                cv2.FONT_HERSHEY_SIMPLEX, scale, (10, 14, 20), thickness, cv2.LINE_AA,
            )
        return frame

    def _draw_labels_pil(self, frame: np.ndarray, detections: list[Detection], width: int, height: int) -> np.ndarray:
        import cv2
        from PIL import Image, ImageDraw

        cfg = self.config
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(image, "RGBA")
        font_size = max(12, int(height * 0.021 * (float(cfg.fontScale) / 0.55)))
        font = self._font(font_size)
        pad_x, pad_y = 6, 3
        for detection in detections:
            x1, y1, x2, y2 = self._to_pixels(detection, width, height)
            bgr = _hex_to_bgr(GROUP_COLORS.get(detection.group, cfg.boxColor), _hex_to_bgr(cfg.boxColor))
            color = (bgr[2], bgr[1], bgr[0])
            text = self._label_text(detection)
            try:
                left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
                text_w, text_h = right - left, bottom - top
            except Exception:
                text_w, text_h = len(text) * font_size // 2, font_size
            box_w, box_h = text_w + pad_x * 2, text_h + pad_y * 2
            bx1 = x1
            by1 = y1 - box_h - 2
            if by1 < 0:
                by1 = y1 + 2
            bx1 = max(0, min(width - box_w - 1, bx1))
            draw.rounded_rectangle(
                (bx1, by1, bx1 + box_w, by1 + box_h),
                radius=4,
                fill=color + (235,),
            )
            draw.text((bx1 + pad_x, by1 + pad_y - 1), text, font=font, fill=(8, 12, 18, 255))
        return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)

    def _draw_zones_cv(self, frame: np.ndarray, zones: list[Zone], width: int, height: int) -> np.ndarray:
        import cv2

        overlay = frame.copy()
        for zone in zones:
            points = zone.normalized_points()
            if len(points) < 3:
                continue
            polygon = np.array([[int(x * width), int(y * height)] for x, y in points], dtype=np.int32)
            color = (82, 197, 34) if zone.type == "include" else (59, 130, 246)
            cv2.fillPoly(overlay, [polygon], color)
            cv2.polylines(frame, [polygon], True, color, 2, lineType=cv2.LINE_AA)
        return cv2.addWeighted(overlay, 0.14, frame, 0.86, 0)

    def _draw_corner_text(self, frame: np.ndarray, width: int, height: int) -> np.ndarray:
        import cv2

        cfg = self.config
        parts: list[str] = []
        if cfg.extraText:
            parts.append(cfg.extraText)
        if cfg.drawTimestamp:
            parts.append(time.strftime("%Y-%m-%d %H:%M:%S"))
        text = "  ".join(parts)
        if not text:
            return frame
        scale = max(0.35, float(cfg.fontScale) * 0.8)
        thickness = max(1, int(round(scale * 1.5)))
        (text_w, text_h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
        x, y = 12, 12 + text_h
        cv2.rectangle(frame, (x - 6, y - text_h - 6), (x + text_w + 6, y + baseline + 4), (12, 18, 28), -1)
        cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (226, 232, 240), thickness, cv2.LINE_AA)
        return frame

    # ------------------------------------------------------------------ 无 OpenCV 兜底
    def _render_pil_only(self, frame: np.ndarray, detections: list[Detection], zones: list[Zone]) -> np.ndarray:
        from PIL import Image, ImageDraw

        image = Image.fromarray(frame[:, :, ::-1])
        draw = ImageDraw.Draw(image, "RGBA")
        height, width = frame.shape[:2]
        font_size = max(12, int(height * 0.021))
        font = self._font(font_size) if self.font_path else None
        for detection in detections:
            x1, y1, x2, y2 = self._to_pixels(detection, width, height)
            bgr = _hex_to_bgr(GROUP_COLORS.get(detection.group, self.config.boxColor))
            color = (bgr[2], bgr[1], bgr[0], 255)
            draw.rectangle((x1, y1, x2, y2), outline=color, width=max(1, self.config.boxThickness))
            if self.config.showLabels:
                text = self._label_text(detection)
                draw.rectangle((x1, max(0, y1 - font_size - 8), x1 + len(text) * font_size // 2 + 10, y1), fill=color)
                if font:
                    draw.text((x1 + 4, max(0, y1 - font_size - 5)), text, font=font, fill=(10, 14, 20, 255))
        return np.asarray(image)[:, :, ::-1]
