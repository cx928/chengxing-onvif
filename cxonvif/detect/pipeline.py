"""检测管线 / Analytics pipeline.

单摄像机内的一条线程：
帧源 → 运动门控 → 推理 → 跟踪 → 区域过滤 → 目标组状态机 → 事件回调。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..config import CameraConfig
from ..hw.ffmpeg import FFmpegTool
from ..hw.probe import HardwareProfile
from ..logbus import error, info, warn
from ..paths import SNAPSHOT_DIR
from ..stream.frames import FrameSource
from ..util import now_iso
from .base import Detector, DetectorError, DetectorRequest, create_detector
from .motion import MotionGate
from .tracker import IoUTracker
from .types import Detection, DetectionEvent
from .zones import filter_detections

EventCallback = Callable[[DetectionEvent], None]


@dataclass
class PipelineStatus:
    running: bool = False
    enabled: bool = False
    model: str = ""
    backend: str = ""
    device: str = ""
    loaded: bool = False
    lastError: str = ""
    inferenceFps: float = 0.0
    inferenceMs: float = 0.0
    inferenceCount: int = 0
    detections: int = 0
    motion: bool = False
    motionRatio: float = 0.0
    activeGroups: list[str] = field(default_factory=list)
    startedAt: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "enabled": self.enabled,
            "model": self.model,
            "backend": self.backend,
            "device": self.device,
            "loaded": self.loaded,
            "lastError": self.lastError,
            "inferenceFps": round(self.inferenceFps, 2),
            "inferenceMs": round(self.inferenceMs, 1),
            "inferenceCount": self.inferenceCount,
            "detections": self.detections,
            "motion": self.motion,
            "motionRatio": round(self.motionRatio, 4),
            "activeGroups": self.activeGroups,
        }


class AnalyticsPipeline:
    def __init__(
        self,
        camera: CameraConfig,
        *,
        hardware: HardwareProfile,
        frame_source: FrameSource,
        on_event: EventCallback,
        ffmpeg: FFmpegTool | None = None,
    ) -> None:
        self.camera = camera
        self.hardware = hardware
        self.frame_source = frame_source
        self.on_event = on_event
        self.ffmpeg = ffmpeg

        self.detector: Detector | None = None
        self.tracker = IoUTracker()
        self.gate = MotionGate(camera.detect.motionSensitivity)
        self.status = PipelineStatus(enabled=camera.detect.enabled)
        self.latest_detections: list[Detection] = []
        self.last_result_at = 0.0

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._detector_retry_at = 0.0
        self._group_seen: dict[str, float] = {}
        self._group_active: set[str] = set()
        self._group_confidence: dict[str, float] = {}
        self._lock = threading.Lock()
        self._snapshot_lock = threading.Lock()

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.status.running = True
        self.status.startedAt = time.time()
        self._thread = threading.Thread(target=self._run, name=f"analytics-{self.camera.id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=4)
        if self.detector:
            try:
                self.detector.close()
            except Exception:
                pass
        self.status.running = False
        self.latest_detections = []

    # ------------------------------------------------------------------ 供叠加/接口使用
    def detections_for_overlay(self) -> tuple[list[Detection], list]:
        with self._lock:
            return list(self.latest_detections), list(self.camera.detect.zones)

    # ------------------------------------------------------------------ 主循环
    def _ensure_detector(self) -> bool:
        if self.detector and self.detector.loaded:
            return True
        now = time.time()
        if now < self._detector_retry_at:
            return False
        request = DetectorRequest(
            detect=self.camera.detect,
            backend=self.camera.detect.backend,
            device=self.camera.detect.device,
        )
        try:
            self.detector = create_detector(request)
        except Exception as exc:
            self.detector = None
            self.status.lastError = str(exc)[:300]
            self.status.loaded = False
            self._detector_retry_at = now + 60
            warn(f"[{self.camera.name}] 检测器初始化失败：{exc}", "detect")
            return False
        self.status.model = self.detector.spec.name if self.detector.spec else self.camera.detect.model
        self.status.backend = self.detector.backend
        self.status.device = self.detector.device
        self.status.loaded = True
        self.status.lastError = ""
        return True

    def _run(self) -> None:
        cfg = self.camera.detect
        interval = 1.0 / max(0.2, float(cfg.fps))
        next_infer = 0.0
        last_seq = 0
        infer_window_start = time.monotonic()
        infer_window_count = 0

        while not self._stop.is_set():
            seq, frame = self.frame_source.wait_frame(last_seq, timeout=1.5)
            if frame is None or seq == last_seq:
                continue
            last_seq = seq

            now = time.time()
            motion = True
            if cfg.motionGate:
                motion = self.gate.update(frame)
                self.status.motion = motion
                self.status.motionRatio = self.gate.last_ratio
                if not motion:
                    self._expire_groups(now)
                    continue

            if now < next_infer:
                self._expire_groups(now)
                continue
            next_infer = now + interval

            if not self._ensure_detector() or not self.detector:
                continue

            try:
                started = time.perf_counter()
                detections = self.detector.infer(
                    frame,
                    confidence=float(cfg.confidence),
                    iou=float(cfg.iou),
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
            except DetectorError as exc:
                self.status.lastError = str(exc)[:300]
                warn(f"[{self.camera.name}] 推理失败：{exc}", "detect")
                continue
            except Exception as exc:
                self.status.lastError = str(exc)[:300]
                warn(f"[{self.camera.name}] 推理异常：{exc}", "detect")
                continue

            if cfg.tracker:
                detections = self.tracker.update(detections)
            detections = filter_detections(detections, cfg.zones)
            detections = [d for d in detections if d.area >= float(cfg.minBox)][: int(cfg.maxDetections)]

            with self._lock:
                self.latest_detections = detections
            self.last_result_at = now
            self.status.detections = len(detections)
            self.status.inferenceMs = elapsed_ms
            self.status.inferenceCount += 1
            infer_window_count += 1
            window = time.monotonic() - infer_window_start
            if window >= 3.0:
                self.status.inferenceFps = infer_window_count / window
                infer_window_start = time.monotonic()
                infer_window_count = 0

            self._update_groups(detections, frame, now)
            self._expire_groups(now)
        self.status.running = False

    # ------------------------------------------------------------------ 状态机
    def _update_groups(self, detections: list[Detection], frame: np.ndarray, now: float) -> None:
        cfg = self.camera.detect
        targets = set(cfg.targets or ["person"])
        present: dict[str, float] = {}
        for detection in detections:
            group = detection.group
            if group not in targets and "all" not in targets:
                continue
            present[group] = max(present.get(group, 0.0), detection.confidence)

        for group, confidence in present.items():
            self._group_seen[group] = now
            self._group_confidence[group] = confidence
            if group not in self._group_active:
                self._group_active.add(group)
                self.status.activeGroups = sorted(self._group_active)
                self._emit(group, True, [d for d in detections if d.group == group], frame, confidence)

    def _expire_groups(self, now: float) -> None:
        cooldown = max(0.5, float(self.camera.detect.cooldown))
        expired = [
            group for group in list(self._group_active)
            if now - self._group_seen.get(group, 0.0) > cooldown
        ]
        for group in expired:
            self._group_active.discard(group)
            self._group_seen.pop(group, None)
            self.status.activeGroups = sorted(self._group_active)
            self._emit(group, False, [], None, self._group_confidence.get(group, 0.0))

    def _emit(
        self,
        group: str,
        active: bool,
        detections: list[Detection],
        frame: np.ndarray | None,
        confidence: float,
    ) -> None:
        snapshot_path = ""
        snapshot_bytes = None
        if active and self.camera.detect.saveSnapshot and frame is not None:
            snapshot_bytes, snapshot_path = self._save_snapshot(group, frame)
        event = DetectionEvent(
            camera_id=self.camera.id,
            camera_name=self.camera.name,
            groups={group},
            active=active,
            timestamp=now_iso(),
            confidence={group: float(confidence)},
            detections=detections if active else [],
            snapshot_path=snapshot_path,
            snapshot_bytes=snapshot_bytes if active and self.camera.mercury.includeSnapshot else None,
            source="ai",
        )
        try:
            self.on_event(event)
        except Exception as exc:  # pragma: no cover
            error(f"[{self.camera.name}] 事件回调失败：{exc}", "detect")

    def _save_snapshot(self, group: str, frame: np.ndarray) -> tuple[bytes | None, str]:
        with self._snapshot_lock:
            try:
                import cv2

                ok, buffer = cv2.imencode(
                    ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(self.camera.mercury.snapshotQuality)]
                )
                if not ok:
                    return None, ""
                data = buffer.tobytes()
                SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
                name = f"cam{self.camera.id}_{group}_{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time()*1000)%1000}.jpg"
                path = SNAPSHOT_DIR / name
                path.write_bytes(data)
                self._cleanup_snapshots()
                return data, str(path)
            except Exception:
                return None, ""

    def _cleanup_snapshots(self, keep: int = 400) -> None:
        try:
            files = sorted(SNAPSHOT_DIR.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
            for stale in files[:-keep]:
                stale.unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------ 状态
    def status_dict(self) -> dict[str, Any]:
        data = self.status.to_dict()
        data["fps"] = self.frame_source.stats.to_dict()
        if self.detector:
            data["detector"] = self.detector.describe()
        return data

    def trigger_test(self) -> None:
        """触发一次测试事件（用于调试 ONVIF / 推送）。"""
        event = DetectionEvent(
            camera_id=self.camera.id,
            camera_name=self.camera.name,
            groups={"person"},
            active=True,
            timestamp=now_iso(),
            confidence={"person": 0.95},
            source="test",
        )
        self.on_event(event)
        deactivate = DetectionEvent(
            camera_id=self.camera.id,
            camera_name=self.camera.name,
            groups={"person"},
            active=False,
            timestamp=now_iso(),
            confidence={"person": 0.0},
            source="test",
        )
        timer = threading.Timer(3.0, lambda: self.on_event(deactivate))
        timer.daemon = True
        timer.start()
