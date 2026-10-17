"""FFmpeg/FFprobe 定位与能力查询。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..paths import HOME, find_asset
from ..util import run_command

_WIN = os.name == "nt"


@dataclass
class FFmpegTool:
    path: Path
    version: str
    configuration: str

    @property
    def directory(self) -> Path:
        return self.path.parent

    @property
    def ffprobe(self) -> Path | None:
        candidate = self.directory / ("ffprobe.exe" if _WIN else "ffprobe")
        return candidate if candidate.exists() else find_ffprobe()


def _candidates(name: str, configured: str = "") -> list[Path]:
    binary = f"{name}.exe" if _WIN else name
    result: list[Path] = []
    if configured:
        configured_path = Path(configured)
        if configured_path.is_dir():
            result.append(configured_path / binary)
        else:
            result.append(configured_path)
    result.append(HOME / "vendor" / "ffmpeg" / binary)
    for relative in (("ffmpeg", binary), ("vendor", "ffmpeg", binary), ("bin", binary)):
        found = find_asset(*relative)
        if found:
            result.append(found)
    system = shutil.which(binary)
    if system:
        result.append(Path(system))
    return result


def find_ffmpeg(configured: str = "") -> Path | None:
    for candidate in _candidates("ffmpeg", configured):
        if candidate and candidate.is_file():
            return candidate
    return None


def find_ffprobe(configured: str = "") -> Path | None:
    ffmpeg = find_ffmpeg(configured)
    if ffmpeg:
        probe = ffmpeg.parent / ("ffprobe.exe" if _WIN else "ffprobe")
        if probe.exists():
            return probe
    for candidate in _candidates("ffprobe", configured):
        if candidate and candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=4)
def _inspect(path_str: str) -> FFmpegTool | None:
    try:
        completed = run_command([path_str, "-hide_banner", "-version"], timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    output = (completed.stdout or "") + (completed.stderr or "")
    match = re.search(r"ffmpeg version (\S+)", output)
    version = match.group(1) if match else "unknown"
    config_match = re.search(r"configuration: (.+)", output)
    configuration = config_match.group(1).strip() if config_match else ""
    return FFmpegTool(path=Path(path_str), version=version, configuration=configuration)


def resolve_ffmpeg(configured: str = "") -> FFmpegTool | None:
    path = find_ffmpeg(configured)
    if not path:
        return None
    return _inspect(str(path))


def ffmpeg_available(configured: str = "") -> bool:
    return resolve_ffmpeg(configured) is not None


@lru_cache(maxsize=4)
def _list_encoders(path_str: str) -> frozenset[str]:
    try:
        completed = run_command([path_str, "-hide_banner", "-encoders"], timeout=20)
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    names: set[str] = set()
    for line in (completed.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            names.add(parts[1])
    return frozenset(names)


def list_encoders(ffmpeg_path: Path | str | None) -> frozenset[str]:
    if not ffmpeg_path:
        return frozenset()
    return _list_encoders(str(ffmpeg_path))


@lru_cache(maxsize=4)
def _list_hwaccels(path_str: str) -> frozenset[str]:
    try:
        completed = run_command([path_str, "-hide_banner", "-hwaccels"], timeout=20)
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    names = set()
    for line in (completed.stdout or "").splitlines():
        line = line.strip()
        if line and ":" not in line:
            names.add(line)
    return frozenset(names)


def list_hwaccels(ffmpeg_path: Path | str | None) -> frozenset[str]:
    if not ffmpeg_path:
        return frozenset()
    return _list_hwaccels(str(ffmpeg_path))


def capture_jpeg(tool: FFmpegTool | None, url: str, *, transport: str = "tcp", timeout: float = 12.0) -> bytes | None:
    """用 FFmpeg 抓取一帧 JPEG。"""
    if not tool or not url:
        return None
    args = [
        str(tool.path), "-hide_banner", "-loglevel", "error", "-nostdin",
        "-rtsp_transport", transport,
        "-i", url, "-frames:v", "1", "-f", "image2", "-q:v", "3", "pipe:1",
    ]
    try:
        completed = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=0x08000000 if _WIN else 0)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or not completed.stdout:
        return None
    return completed.stdout


def probe_media(url: str, ffprobe: Path | None, timeout: float = 12.0) -> dict:
    """探测 RTSP/HTTP 流的基本信息（分辨率、编码、帧率）。"""
    if not ffprobe:
        return {"ok": False, "error": "未找到 ffprobe"}
    args = [
        str(ffprobe), "-hide_banner", "-loglevel", "error",
        "-rtsp_transport", "tcp", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,avg_frame_rate,pix_fmt",
        "-of", "json", "-i", url,
    ]
    try:
        completed = run_command(args, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc)}
    if completed.returncode != 0:
        return {"ok": False, "error": (completed.stderr or "").strip()[-300:]}
    import json

    try:
        payload = json.loads(completed.stdout or "{}")
        stream = (payload.get("streams") or [{}])[0]
    except ValueError:
        return {"ok": False, "error": "无法解析 ffprobe 输出"}
    fps = 0.0
    rate = stream.get("avg_frame_rate") or "0/0"
    try:
        num, den = rate.split("/")
        fps = round(float(num) / float(den), 2) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        pass
    return {
        "ok": True,
        "codec": stream.get("codec_name", ""),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "fps": fps,
        "pixFmt": stream.get("pix_fmt", ""),
    }
