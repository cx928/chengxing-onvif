"""RTSP 帧源 / FFmpeg-based frame source.

一个摄像机只启动一路解码，检测与叠加共享同一帧流：
``ffmpeg -i rtsp://... -vf scale=W:H,fps=N -f rawvideo -pix_fmt bgr24 pipe:1``
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..hw.ffmpeg import FFmpegTool, probe_media
from ..logbus import warn
from ..util import CREATE_NO_WINDOW, popen_hidden


@dataclass
class FrameStats:
    running: bool = False
    connecting: bool = False
    fps: float = 0.0
    frames: int = 0
    width: int = 0
    height: int = 0
    reconnects: int = 0
    lastError: str = ""
    lastFrameAt: float = 0.0
    sourceWidth: int = 0
    sourceHeight: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "connecting": self.connecting,
            "fps": round(self.fps, 1),
            "frames": self.frames,
            "width": self.width,
            "height": self.height,
            "reconnects": self.reconnects,
            "lastError": self.lastError,
            "lastFrameAt": self.lastFrameAt,
            "sourceWidth": self.sourceWidth,
            "sourceHeight": self.sourceHeight,
        }


class FrameSource:
    def __init__(
        self,
        url: str,
        *,
        ffmpeg: FFmpegTool | None,
        target_width: int = 1280,
        fps: float = 10.0,
        transport: str = "tcp",
        decoder: str = "",
        name: str = "camera",
        max_width: int = 1920,
        max_height: int = 1080,
    ) -> None:
        self.url = url
        self.ffmpeg = ffmpeg
        self.target_width = max(160, min(int(target_width or 1280), max_width))
        self.fps = max(1.0, min(float(fps or 10), 30.0))
        self.transport = transport or "tcp"
        self.decoder = decoder if decoder not in ("", "none", "software") else ""
        self.name = name
        self.max_height = max_height

        self.width = 0
        self.height = 0
        self.stats = FrameStats()

        self._seq = 0
        self._frame: np.ndarray | None = None
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None
        self._frame_bytes = 0

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"frames-{self.name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._kill_proc()
        with self._cond:
            self._cond.notify_all()
        if self._thread:
            self._thread.join(timeout=3)
        self.stats.running = False

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ------------------------------------------------------------------ 帧访问
    def wait_frame(self, last_seq: int, timeout: float = 2.0) -> tuple[int, np.ndarray | None]:
        """等待比 last_seq 更新的帧；返回 (seq, frame)。调用方不得原地修改 frame。"""
        with self._cond:
            if self._seq == last_seq:
                self._cond.wait(timeout)
            return self._seq, self._frame

    def latest(self) -> tuple[int, np.ndarray | None]:
        with self._cond:
            return self._seq, self._frame

    def snapshot_jpeg(self, quality: int = 82) -> bytes | None:
        seq, frame = self.latest()
        if frame is None:
            return None
        try:
            import cv2

            ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
            return buffer.tobytes() if ok else None
        except Exception:
            return None

    # ------------------------------------------------------------------ 内部
    def _probe_size(self) -> tuple[int, int]:
        ffprobe = self.ffmpeg.ffprobe if self.ffmpeg else None
        info = probe_media(self.url, ffprobe, timeout=12)
        if info.get("ok") and info.get("width"):
            src_w, src_h = int(info["width"]), int(info["height"])
            self.stats.sourceWidth = src_w
            self.stats.sourceHeight = src_h
            width = min(self.target_width, src_w or self.target_width)
            height = int(round(width * src_h / max(1, src_w) / 2) * 2)
            height = max(2, min(height, self.max_height))
            return width, height
        if info.get("error"):
            self.stats.lastError = str(info["error"])[:300]
        width = self.target_width
        return width, int(round(width * 9 / 16 / 2) * 2)

    def _build_command(self) -> list[str]:
        assert self.ffmpeg is not None
        args = [
            str(self.ffmpeg.path),
            "-hide_banner", "-loglevel", "error", "-nostdin",
        ]
        if self.decoder:
            args += ["-hwaccel", self.decoder]
        args += [
            "-rtsp_transport", self.transport,
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-i", self.url,
            "-an", "-sn", "-dn",
            "-vf", f"scale={self.width}:{self.height}:flags=bilinear,fps={self.fps:g}",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1",
        ]
        return args

    def _kill_proc(self) -> None:
        proc = self._proc
        self._proc = None
        if not proc:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _run(self) -> None:
        if self.ffmpeg is None:
            self.stats.lastError = "未找到 FFmpeg"
            warn(f"[{self.name}] 未找到 FFmpeg，无法解码视频", "stream")
            return
        self.stats.connecting = True
        self.width, self.height = self._probe_size()
        self._frame_bytes = self.width * self.height * 3
        self.stats.width, self.stats.height = self.width, self.height
        backoff = 1.0
        buffer = bytearray(self._frame_bytes)
        view = memoryview(buffer)

        while not self._stop.is_set():
            try:
                self._proc = popen_hidden(
                    self._build_command(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=self._frame_bytes * 2,
                )
            except Exception as exc:
                self.stats.lastError = f"启动 FFmpeg 失败: {exc}"
                warn(f"[{self.name}] 启动解码失败: {exc}", "stream")
                self._sleep(backoff)
                backoff = min(backoff * 1.8, 15.0)
                continue

            self.stats.running = True
            self.stats.connecting = False
            frames_this_round = 0
            started_at = time.monotonic()
            read_error = ""
            stdout = self._proc.stdout
            try:
                while not self._stop.is_set() and stdout is not None:
                    filled = 0
                    while filled < self._frame_bytes:
                        chunk = stdout.readinto(view[filled:])
                        if not chunk:
                            read_error = "视频流结束"
                            break
                        filled += chunk
                    if filled < self._frame_bytes:
                        break
                    frame = np.frombuffer(buffer, dtype=np.uint8, count=self._frame_bytes).reshape(
                        self.height, self.width, 3
                    )
                    self._publish(frame, started_at, frames_this_round)
                    frames_this_round += 1
                    if frames_this_round > 10:
                        backoff = 1.0
            except Exception as exc:
                read_error = str(exc)
            finally:
                self.stats.running = False
                stderr_tail = ""
                if self._proc and self._proc.stderr:
                    try:
                        stderr_tail = self._proc.stderr.read(1500).decode("utf-8", "ignore").strip()
                    except Exception:
                        pass
                self._kill_proc()
                if read_error or stderr_tail:
                    message = (stderr_tail or read_error).replace("\n", " ")[:300]
                    self.stats.lastError = message
                    if not self._stop.is_set():
                        warn(f"[{self.name}] 视频流中断: {message}", "stream")
                # 硬件解码失败时自动回退软件解码
                if self.decoder and frames_this_round == 0 and not self._stop.is_set():
                    disabled = self.decoder
                    self.decoder = ""
                    self.stats.lastError = f"硬件解码 {disabled} 不可用，已回退软件解码"
                    warn(f"[{self.name}] {self.stats.lastError}", "stream")
                    self._sleep(0.3)
                    continue
                if not self._stop.is_set():
                    self.stats.reconnects += 1
                    self._sleep(backoff)
                    backoff = min(backoff * 1.8, 15.0)
        self.stats.running = False

    def _publish(self, frame: np.ndarray, started_at: float, count: int) -> None:
        with self._cond:
            self._seq += 1
            self._frame = frame
            self.stats.frames += 1
            self.stats.lastFrameAt = time.time()
            elapsed = time.monotonic() - started_at
            if elapsed > 0:
                self.stats.fps = count / elapsed
            self._cond.notify_all()

    def _sleep(self, seconds: float) -> None:
        self._stop.wait(seconds)
