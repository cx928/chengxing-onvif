"""MediaMTX 进程与配置管理。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

import yaml

from ..config import AppConfig, CameraConfig
from ..hw.ffmpeg import resolve_ffmpeg
from ..logbus import error, info, warn
from ..paths import HOME, LAYOUT, find_asset
from ..util import popen_hidden, port_free, port_owner_pid, read_json, run_command

BINARY_NAME = "mediamtx.exe" if os.name == "nt" else "mediamtx"
RELEASE_API = "https://api.github.com/repos/bluenviron/mediamtx/releases/latest"


class MediaMTXError(RuntimeError):
    pass


def _platform_asset() -> str:
    if sys.platform == "win32":
        return "windows_amd64.zip" if os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64").endswith("64") else "windows_386.zip"
    if sys.platform == "darwin":
        machine = os.uname().machine if hasattr(os, "uname") else "arm64"
        return "darwin_arm64.tar.gz" if machine in ("arm64", "aarch64") else "darwin_amd64.tar.gz"
    machine = os.uname().machine if hasattr(os, "uname") else "x86_64"
    return "linux_arm64v8.tar.gz" if machine in ("aarch64", "arm64") else "linux_amd64.tar.gz"


def find_binary(configured: str = "") -> Path | None:
    if configured:
        path = Path(configured)
        if path.is_dir():
            path = path / BINARY_NAME
        if path.exists():
            return path
    env = os.environ.get("CXONVIF_MEDIAMTX")
    if env and Path(env).exists():
        return Path(env)
    for candidate in (
        HOME / "vendor" / "mediamtx" / BINARY_NAME,
        LAYOUT["vendor"] / "mediamtx" / BINARY_NAME,
    ):
        if candidate.exists():
            return candidate
    for relative in ((BINARY_NAME,), ("mediamtx", BINARY_NAME), ("vendor", "mediamtx", BINARY_NAME)):
        found = find_asset(*relative)
        if found:
            return found
    system = shutil.which("mediamtx")
    return Path(system) if system else None


def download_binary(progress=None) -> Path | None:
    """从 GitHub Releases 下载 MediaMTX。"""
    target_dir = HOME / "vendor" / "mediamtx"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / BINARY_NAME
    if target.exists():
        return target
    import requests

    info("正在获取 MediaMTX 最新版本…", "mediamtx")
    try:
        response = requests.get(RELEASE_API, timeout=30, headers={"User-Agent": "cxonvif"})
        response.raise_for_status()
        release = response.json()
    except Exception as exc:
        error(f"获取 MediaMTX 版本信息失败：{exc}", "mediamtx")
        return None

    asset_name = None
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        if _platform_asset().split(".")[0] in name:
            asset_name = asset
            break
    if not asset_name:
        error("未找到适配当前平台的 MediaMTX 发行包", "mediamtx")
        return None

    url = asset_name["browser_download_url"]
    total = int(asset_name.get("size") or 0)
    info(f"下载 MediaMTX {release.get('tag_name')} …", "mediamtx")
    try:
        with requests.get(url, stream=True, timeout=120) as response:
            response.raise_for_status()
            package = target_dir / asset_name["name"]
            downloaded = 0
            with open(package, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress and total:
                        progress(downloaded, total)
        if package.suffix == ".zip":
            with zipfile.ZipFile(package) as archive:
                member = next((m for m in archive.namelist() if Path(m).name == BINARY_NAME), None)
                if not member:
                    raise MediaMTXError("压缩包中未找到 mediamtx 可执行文件")
                with archive.open(member) as source, open(target, "wb") as destination:
                    shutil.copyfileobj(source, destination)
        else:
            import tarfile

            with tarfile.open(package) as archive:
                member = next((m for m in archive.getmembers() if Path(m.name).name == BINARY_NAME), None)
                if not member:
                    raise MediaMTXError("压缩包中未找到 mediamtx 可执行文件")
                source = archive.extractfile(member)
                assert source is not None
                with open(target, "wb") as destination:
                    shutil.copyfileobj(source, destination)
        package.unlink(missing_ok=True)
        if os.name != "nt":
            target.chmod(0o755)
        info(f"MediaMTX 已就绪：{target}", "mediamtx")
        return target
    except Exception as exc:
        error(f"MediaMTX 下载失败：{exc}", "mediamtx")
        return None


class MediaMTXManager:
    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}
        self.binary: Path | None = find_binary(self.settings.get("mediamtxPath", ""))
        self.config_path = HOME / "mediamtx.yml"
        self.log_path = LAYOUT["logs"] / "mediamtx.log"
        self.process: subprocess.Popen | None = None
        self.api_port = int(self.settings.get("mediamtxApiPort", 9997))
        self.rtsp_port = int(self.settings.get("rtspPort", 8554))
        self._lock = threading.RLock()
        self.last_error = ""
        self._paths: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ 配置
    def build_config(self, config: AppConfig, *, web_port: int, lan_ip: str) -> dict[str, Any]:
        settings = config.settings
        self.api_port = int(settings.get("mediamtxApiPort", 9997))
        self.rtsp_port = int(settings.get("rtspPort", 8554))
        hls_port = int(settings.get("hlsPort", 8888))
        webrtc_port = int(settings.get("webrtcPort", 8889))

        paths: dict[str, Any] = {}
        for camera in config.cameras:
            if not camera.enabled:
                continue
            base = camera.basePath
            main_url = camera.source.url("main")
            if main_url:
                paths[f"{base}_main"] = {
                    "source": main_url,
                    "sourceOnDemand": True,
                    "sourceOnDemandStartTimeout": "10s",
                    "sourceOnDemandCloseAfter": "30s",
                    "rtspTransport": camera.source.transport or "tcp",
                    "record": bool(camera.stream.record),
                }
            if camera.stream.enableSubstream and camera.source.subUrl and not camera.stream.useMainAsSubstream:
                paths[f"{base}_sub"] = {
                    "source": camera.source.subUrl,
                    "sourceOnDemand": True,
                    "sourceOnDemandStartTimeout": "10s",
                    "sourceOnDemandCloseAfter": "30s",
                    "rtspTransport": camera.source.transport or "tcp",
                    "record": False,
                }
            if camera.overlay.enabled:
                # 由引擎内的叠加进程推送；无 source 的路径用于接收推流
                paths[camera.overlayPath] = {
                    "source": "publisher",
                    "sourceOnDemand": False,
                    "overridePublisher": True,
                    "record": bool(camera.stream.record),
                }

        # 虚拟路径：识别本机摄像头（可选）
        document: dict[str, Any] = {
            "logLevel": "error",
            "logDestinations": ["file"],
            "logFile": str(self.log_path),
            "readTimeout": "30s",
            "writeTimeout": "30s",
            "writeQueueSize": 32768,
            "udpMaxPayloadSize": 1472,
            "api": True,
            "apiAddress": f"127.0.0.1:{self.api_port}",
            "metrics": False,
            "pprof": False,
            "playback": False,
            "rtsp": True,
            "rtspAddress": f":{self.rtsp_port}",
            "rtspTransports": ["tcp"],
            "rtspEncryption": "no",
            "rtpAddress": f":{int(settings.get('rtpPort', 8000))}",
            "rtcpAddress": f":{int(settings.get('rtcpPort', 8001))}",
            "rtmp": False,
            "hls": True,
            "hlsAddress": f":{hls_port}",
            "hlsVariant": "lowLatency",
            "hlsSegmentCount": 3,
            "hlsSegmentDuration": "1s",
            "hlsPartDuration": "200ms",
            "hlsAlwaysRemux": False,
            "hlsAllowOrigins": ["*"],
            "webrtc": True,
            "webrtcAddress": f":{webrtc_port}",
            "webrtcAllowOrigins": ["*"],
            "webrtcLocalUDPAddress": f":{int(settings.get('webrtcUdpPort', 8189))}",
            "webrtcAdditionalHosts": [lan_ip] if lan_ip else [],
            "srt": False,
            "authMethod": "http",
            "authHTTPAddress": f"http://127.0.0.1:{web_port}/api/internal/mediamtx/auth",
            "authHTTPExclude": [
                {"action": "api"},
                {"action": "metrics"},
            ],
            "pathDefaults": {
                "sourceOnDemand": True,
                "sourceOnDemandStartTimeout": "10s",
                "sourceOnDemandCloseAfter": "30s",
                "rtspTransport": "tcp",
            },
            "paths": paths,
        }
        self._paths = paths
        return document

    def write_config(self, config: AppConfig, *, web_port: int, lan_ip: str) -> Path:
        document = self.build_config(config, web_port=web_port, lan_ip=lan_ip)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(document, handle, allow_unicode=True, sort_keys=False)
        return self.config_path

    # ------------------------------------------------------------------ 进程
    def ensure_binary(self, *, auto_download: bool = True) -> Path | None:
        if self.binary and self.binary.exists():
            return self.binary
        self.binary = find_binary(self.settings.get("mediamtxPath", ""))
        if self.binary:
            return self.binary
        if auto_download:
            self.binary = download_binary()
        return self.binary

    def _cleanup_stale(self) -> None:
        """清理使用本配置的残留 MediaMTX（引擎异常退出时可能留下）。"""
        try:
            import psutil

            config_path = str(self.config_path)
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    name = (proc.info.get("name") or "").lower()
                    cmdline = " ".join(proc.info.get("cmdline") or [])
                    if "mediamtx" not in name or config_path not in cmdline:
                        continue
                    info(f"清理残留 MediaMTX 进程 {proc.pid}", "mediamtx")
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        proc.kill()
                except Exception:
                    continue
        except Exception:
            pass

    def start(self, config: AppConfig, *, web_port: int, lan_ip: str) -> tuple[bool, str]:
        with self._lock:
            if self.is_running():
                return True, "已在运行"
            binary = self.ensure_binary()
            if not binary:
                self.last_error = "缺少 MediaMTX 可执行文件（可设置 mediamtxPath 或联网自动下载）"
                return False, self.last_error
            self._cleanup_stale()
            if not port_free(self.rtsp_port):
                owner = port_owner_pid(self.rtsp_port)
                suffix = f"（进程 {owner}）" if owner else ""
                self.last_error = f"RTSP 端口 {self.rtsp_port} 已被占用{suffix}"
                return False, self.last_error
            if not port_free(self.api_port, "127.0.0.1"):
                owner = port_owner_pid(self.api_port)
                suffix = f"（进程 {owner}）" if owner else ""
                self.last_error = f"MediaMTX API 端口 {self.api_port} 已被占用{suffix}"
                return False, self.last_error
            config_file = self.write_config(config, web_port=web_port, lan_ip=lan_ip)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                log_handle = open(self.log_path, "ab")
                self.process = popen_hidden(
                    [str(binary), str(config_file)],
                    stdout=log_handle,
                    stderr=log_handle,
                    cwd=str(binary.parent),
                )
            except Exception as exc:
                self.last_error = f"启动 MediaMTX 失败：{exc}"
                error(self.last_error, "mediamtx")
                return False, self.last_error

            deadline = time.time() + 12
            while time.time() < deadline:
                if self.process.poll() is not None:
                    tail = self._tail_log()
                    self.last_error = f"MediaMTX 退出（{self.process.returncode}）：{tail}"
                    error(self.last_error, "mediamtx")
                    return False, self.last_error
                if self._api_ready():
                    if self.process.poll() is not None:
                        continue
                    owner = port_owner_pid(self.rtsp_port)
                    if owner and self.process.pid and owner != self.process.pid:
                        self.last_error = f"RTSP 端口 {self.rtsp_port} 被其它进程占用（进程 {owner}）"
                        error(self.last_error, "mediamtx")
                        try:
                            self.process.terminate()
                        except Exception:
                            pass
                        return False, self.last_error
                    info(f"MediaMTX 已启动 · RTSP :{self.rtsp_port} · API :{self.api_port}", "mediamtx")
                    return True, "已启动"
                time.sleep(0.35)
            self.last_error = "MediaMTX 启动超时"
            return False, self.last_error

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            process = self.process
            self.process = None
            if not process:
                return
            try:
                process.terminate()
                process.wait(timeout=timeout)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

    def restart(self, config: AppConfig, *, web_port: int, lan_ip: str) -> tuple[bool, str]:
        self.stop()
        time.sleep(0.4)
        return self.start(config, web_port=web_port, lan_ip=lan_ip)

    def is_running(self) -> bool:
        return bool(self.process and self.process.poll() is None)

    def status(self) -> dict[str, Any]:
        return {
            "running": self.is_running(),
            "binary": str(self.binary) if self.binary else "",
            "rtspPort": self.rtsp_port,
            "apiPort": self.api_port,
            "configPath": str(self.config_path),
            "paths": sorted(self._paths.keys()),
            "lastError": self.last_error,
            "pid": self.process.pid if self.is_running() and self.process else 0,
        }

    def _tail_log(self, limit: int = 600) -> str:
        try:
            with open(self.log_path, "rb") as handle:
                handle.seek(max(0, os.path.getsize(self.log_path) - 4000))
                data = handle.read().decode("utf-8", "ignore")
            lines = [line for line in data.splitlines() if " ERR" in line or "error" in line.lower()]
            return " | ".join(lines[-3:])[:limit] or data[-limit:]
        except OSError:
            return ""

    # ------------------------------------------------------------------ API
    def _api_url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.api_port}{path}"

    def _api_ready(self) -> bool:
        import urllib.request

        try:
            with urllib.request.urlopen(self._api_url("/v3/config/global/get"), timeout=1.5) as response:
                return response.status == 200
        except Exception:
            return False

    def api_get(self, path: str, timeout: float = 4.0) -> Any:
        import urllib.request

        with urllib.request.urlopen(self._api_url(path), timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8") or "null")

    def paths_status(self) -> list[dict[str, Any]]:
        try:
            payload = self.api_get("/v3/paths/list")
            return payload.get("items", []) if isinstance(payload, dict) else []
        except Exception:
            return []

    def path_ready(self, name: str) -> bool:
        for item in self.paths_status():
            if item.get("name") == name:
                return bool(item.get("ready"))
        return False


def ffmpeg_for_overlay(settings: dict[str, Any]):
    return resolve_ffmpeg(settings.get("ffmpegPath", ""))
