"""叠加推流管线 / Overlay encode & publish pipeline.

帧来源与 AI 检测共享（见 :mod:`cxonvif.stream.frames`），本模块负责：
1. 从最新帧取图并绘制检测框；
2. 用硬件编码器（QSV / NVENC / AMF / VAAPI / VideoToolbox）或 libx264 压缩；
3. 推送到 MediaMTX 的 ``<camera>_overlay`` 路径，供录像机 / 网页播放。
"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..config import CameraConfig
from ..detect.overlay import OverlayRenderer
from ..hw.encoder import decoder_args, encoder_args, needs_hwupload
from ..hw.ffmpeg import FFmpegTool
from ..hw.probe import HardwareProfile
from ..logbus import info, warn
from ..util import popen_hidden


@dataclass
class OverlayStats:
    running: bool = False
    encoder: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    frames: int = 0
    restarts: int = 0
    lastError: str = ""
    startedAt: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "encoder": self.encoder,
            "width": self.width,
            "height": self.height,
            "fps": round(self.fps, 1),
            "frames": self.frames,
            "restarts": self.restarts,
            "lastError": self.lastError,
        }


class OverlayStream:
    def __init__(
        self,
        camera: CameraConfig,
        *,
        ffmpeg: FFmpegTool | None,
        hardware: HardwareProfile,
        rtsp_url: str,
        detections_provider: Callable[[], tuple[list, list]],
        frame_provider: Callable[[int, float], tuple[int, np.ndarray | None]],
        width: int,
        height: int,
    ) -> None:
        self.camera = camera
        self.ffmpeg = ffmpeg
        self.hardware = hardware
        self.rtsp_url = rtsp_url
        self.detections_provider = detections_provider
        self.frame_provider = frame_provider
        self.width = max(2, int(width) // 2 * 2)
        self.height = max(2, int(height) // 2 * 2)
        self.renderer = OverlayRenderer(camera.overlay)
        self.stats = OverlayStats(width=self.width, height=self.height)
        self._encoder = self._pick_encoder()
        self.stats.encoder = self._encoder
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"overlay-{self.camera.id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._kill()
        if self._thread:
            self._thread.join(timeout=3)
        self.stats.running = False

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ------------------------------------------------------------------ 编码器
    def _pick_encoder(self) -> str:
        requested = (self.camera.overlay.encoder or "auto").strip()
        available = {enc.name for enc in self.hardware.encoders if enc.available}
        if requested and requested not in {"auto", ""}:
            if requested in available:
                return requested
            warn(f"[{self.camera.name}] 请求的编码器 {requested} 不可用，改用自动选择", "overlay")
        if self.hardware.recommendedEncoder in available:
            return self.hardware.recommendedEncoder
        return "libx264"

    def _command(self, encoder: str) -> list[str]:
        assert self.ffmpeg is not None
        cfg = self.camera.overlay
        codec = "hevc" if encoder.startswith(("hevc", "libx265")) else "h264"
        args: list[str] = [
            str(self.ffmpeg.path), "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "rawvideo", "-pixel_format", "bgr24",
            "-video_size", f"{self.width}x{self.height}",
            "-framerate", f"{max(1.0, cfg.fps):g}",
            "-i", "pipe:0",
        ]
        if needs_hwupload(encoder):
            args += ["-vaapi_device", "/dev/dri/renderD128", "-vf", "format=nv12,hwupload"]
        elif encoder.endswith("_qsv"):
            args += ["-vf", "format=nv12"]
        else:
            args += ["-vf", "format=yuv420p"]
        args += encoder_args(
            encoder,
            bitrate_kbps=int(cfg.bitrate),
            fps=float(cfg.fps),
            codec=codec,
        )
        args += [
            "-f", "rtsp", "-rtsp_transport", "tcp", "-flush_packets", "1",
            self.rtsp_url,
        ]
        return args

    def _kill(self) -> None:
        process = self._process
        self._process = None
        if not process:
            return
        # 先终止进程，避免 stdin 管道满时 close() 永久阻塞
        try:
            process.terminate()
        except Exception:
            pass
        try:
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        try:
            if process.stdin:
                process.stdin.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ 主循环
    def _run(self) -> None:
        if self.ffmpeg is None:
            self.stats.lastError = "未找到 FFmpeg"
            return
        backoff = 1.0
        last_seq = 0
        fallback_done = False
        started = time.monotonic()
        frames_this_round = 0

        while not self._stop.is_set():
            try:
                self._process = popen_hidden(
                    self._command(self._encoder),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    bufsize=self.width * self.height * 3,
                )
            except Exception as exc:
                self.stats.lastError = f"启动编码器失败：{exc}"
                warn(f"[{self.camera.name}] {self.stats.lastError}", "overlay")
                self._sleep(backoff)
                backoff = min(backoff * 1.8, 15.0)
                continue

            self.stats.running = True
            self.stats.startedAt = time.time()
            started_at = time.monotonic()
            frames_this_round = 0
            last_seq = 0
            while not self._stop.is_set() and self._process.poll() is None:
                seq, frame = self.frame_provider(last_seq, timeout=2.0)
                if frame is None or seq == last_seq:
                    # 长时间没有新帧时输出心跳帧，避免 NVR 断开
                    if time.monotonic() - started > 5 and self.stats.frames == 0:
                        self._sleep(0.2)
                    continue
                last_seq = seq
                try:
                    canvas = frame.copy()
                    detections, zones = self.detections_provider()
                    canvas = self.renderer.render(canvas, detections, zones=zones)
                    if self._process.stdin is None:
                        break
                    self._process.stdin.write(np.ascontiguousarray(canvas).tobytes())
                    self._process.stdin.flush()
                    self.stats.frames += 1
                    frames_this_round += 1
                    self.stats.lastError = ""
                    elapsed = time.monotonic() - started_at
                    if elapsed > 2.0:
                        self.stats.fps = frames_this_round / elapsed
                    if frames_this_round > 5:
                        backoff = 1.0
                except (BrokenPipeError, OSError, ValueError) as exc:
                    self.stats.lastError = f"编码管道中断：{exc}"
                    break

            stderr_tail = ""
            process = self._process
            if process and process.stderr:
                try:
                    stderr_tail = process.stderr.read(1200).decode("utf-8", "ignore").strip()
                except Exception:
                    pass
            self._kill()
            self.stats.running = False
            if self._stop.is_set():
                break
            if stderr_tail:
                self.stats.lastError = stderr_tail.replace("\n", " ")[:300]
                warn(f"[{self.camera.name}] 叠加推流错误：{self.stats.lastError}", "overlay")
            if self._encoder != "libx264" and not fallback_done and _encoder_failed(stderr_tail, self._encoder):
                # 硬件编码器初始化失败：自动退回软件编码
                fallback_done = True
                warn(f"[{self.camera.name}] 硬件编码器 {self._encoder} 不可用，切换 libx264", "overlay")
                self._encoder = "libx264"
                self.stats.encoder = "libx264"
                continue
            self.stats.restarts += 1
            self._sleep(backoff)
            backoff = min(backoff * 1.8, 15.0)
        self.stats.running = False

    def _sleep(self, seconds: float) -> None:
        self._stop.wait(seconds)


_ENCODER_FAILURE_HINTS = (
    "error while opening encoder",
    "cannot load",
    "failed to create",
    "device creation failed",
    "no device available",
    "encoder not found",
    "unknown encoder",
    "function not implemented",
    "dll",
    "provided device",
    "initialization",
    "init failed",
)


def _encoder_failed(stderr_text: str, encoder: str) -> bool:
    """区分“编码器不可用”与“推流网络失败”，避免误降级。"""
    text = (stderr_text or "").lower()
    if not text:
        return False
    if "server returned" in text or "connection refused" in text or "could not write header" in text:
        return False
    if "rtsp" in text and "error" in text and "encoder" not in text:
        return False
    return any(hint in text for hint in _ENCODER_FAILURE_HINTS)
