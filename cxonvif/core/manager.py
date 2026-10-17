"""摄像机管理器 / Camera manager (engine orchestration)."""

from __future__ import annotations

import platform
import sys
import threading
import time
from collections import deque
from typing import Any

from .. import brand
from ..bus import EventBus
from ..config import AppConfig, CameraConfig, ConfigStore
from ..detect.models import list_models
from ..detect.types import DetectionEvent
from ..emulate import AlarmPusher
from ..hw.ffmpeg import resolve_ffmpeg
from ..hw.probe import HardwareProfile, get_profile
from ..logbus import BUS, error, info, warn
from ..onvif.profiles import list_profiles
from ..stream.mediamtx import MediaMTXManager
from ..util import local_ip, now_iso
from ..version import CURRENT_VERSION, version_string
from .camera import VirtualCamera


class CameraManager:
    def __init__(self, store: ConfigStore) -> None:
        self.store = store
        self.settings: dict[str, Any] = store.config.settings
        self.local_ip = local_ip()
        self.events = EventBus(history=1000)
        self.ffmpeg = resolve_ffmpeg(self.settings.get("ffmpegPath", ""))
        self.hardware: HardwareProfile = get_profile(self.settings)
        self.mediamtx = MediaMTXManager(self.settings)
        self.cameras: dict[int, VirtualCamera] = {}
        self.last_events: deque[dict] = deque(maxlen=300)
        self.started_at = 0.0
        self.running = False
        self.mediamtx_status: dict[str, Any] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ 生命周期
    def start_mediamtx(self) -> tuple[bool, str]:
        """先启动 MediaMTX；Web 服务随后启动（鉴权回调依赖 Web 端口）。"""
        ok, message = self.mediamtx.start(
            self.store.config,
            web_port=int(self.settings.get("webPort", 5552)),
            lan_ip=self.local_ip,
        )
        self.mediamtx_status = self.mediamtx.status()
        return ok, message

    def start_cameras(self) -> list[str]:
        messages: list[str] = []
        self.started_at = time.time()
        auto_start = [c for c in self.store.cameras if c.autoStart and c.enabled]
        for config in auto_start:
            camera = self._ensure_runtime(config)
            try:
                camera.start()
            except Exception as exc:
                camera.status = "error"
                camera.last_error = str(exc)
                messages.append(f"{config.name}: {exc}")
                warn(f"[{config.name}] 启动异常：{exc}", "manager")
        self.running = True
        info(f"引擎启动完成：{len(auto_start)} 路摄像机 · 本机 {self.local_ip}", "manager")
        return messages

    def start(self) -> tuple[bool, list[str]]:
        ok, message = self.start_mediamtx()
        messages = [f"MediaMTX: {message}"]
        if not ok:
            error(f"MediaMTX 启动失败：{message}", "manager")
        messages.extend(self.start_cameras())
        return ok, messages

    def stop(self) -> None:
        self.running = False
        for camera in list(self.cameras.values()):
            try:
                camera.stop()
            except Exception:
                pass
        self.cameras.clear()
        self.mediamtx.stop()
        info("引擎已停止", "manager")

    # ------------------------------------------------------------------ 摄像机运行时
    def _ensure_runtime(self, config: CameraConfig) -> VirtualCamera:
        camera = self.cameras.get(config.id)
        if camera is None:
            camera = VirtualCamera(config, self)
            self.cameras[config.id] = camera
        else:
            camera.config = config
        return camera

    def camera(self, camera_id: int) -> VirtualCamera | None:
        return self.cameras.get(int(camera_id))

    def start_camera(self, camera_id: int) -> tuple[bool, str]:
        config = self.store.get_camera(camera_id)
        if not config:
            return False, "摄像机不存在"
        camera = self._ensure_runtime(config)
        ok = camera.start()
        return ok, camera.last_error or "已启动"

    def stop_camera(self, camera_id: int) -> tuple[bool, str]:
        camera = self.cameras.get(int(camera_id))
        if not camera:
            return False, "摄像机未运行"
        camera.stop()
        return True, "已停止"

    def restart_camera(self, camera_id: int) -> tuple[bool, str]:
        camera = self.cameras.get(int(camera_id))
        if not camera:
            return self.start_camera(camera_id)
        ok = camera.restart()
        return ok, camera.last_error or "已重启"

    # ------------------------------------------------------------------ CRUD
    def add_camera(self, config: CameraConfig) -> VirtualCamera:
        saved = self.store.add_camera(config)
        self.reload_mediamtx()
        runtime = self._ensure_runtime(saved)
        if saved.enabled and saved.autoStart:
            runtime.start()
        self.publish_camera_state(runtime)
        return runtime

    def update_camera(self, camera_id: int, data: dict[str, Any]) -> VirtualCamera | None:
        was_running = bool(self.cameras.get(int(camera_id)) and self.cameras[int(camera_id)].status == "running")
        saved = self.store.update_camera(camera_id, data)
        if not saved:
            return None
        self.reload_mediamtx()
        runtime = self._ensure_runtime(saved)
        if was_running:
            runtime.restart()
        self.publish_camera_state(runtime)
        return runtime

    def delete_camera(self, camera_id: int) -> bool:
        runtime = self.cameras.pop(int(camera_id), None)
        if runtime:
            runtime.stop()
        ok = self.store.delete_camera(camera_id)
        if ok:
            self.reload_mediamtx()
            self.events.publish({"type": "camera_deleted", "cameraId": int(camera_id), "timestamp": now_iso()})
        return ok

    def reload_mediamtx(self) -> None:
        """配置变更后重启 MediaMTX（短暂中断，叠加推流会自动重连）。"""
        if not self.running:
            return
        ok, message = self.mediamtx.restart(
            self.store.config,
            web_port=int(self.settings.get("webPort", 5552)),
            lan_ip=self.local_ip,
        )
        self.mediamtx_status = self.mediamtx.status()
        if not ok:
            warn(f"MediaMTX 重载失败：{message}", "manager")

    def apply_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        settings = self.store.update_settings(data)
        self.settings = settings
        restart_required = any(
            key in data for key in ("webPort", "rtspPort", "hlsPort", "webrtcPort", "mediamtxApiPort", "bind")
        )
        if "ffmpegPath" in data or "mediamtxPath" in data:
            self.ffmpeg = resolve_ffmpeg(settings.get("ffmpegPath", ""))
            self.mediamtx = MediaMTXManager(settings)
        if not restart_required and self.running:
            self.reload_mediamtx()
        return {"settings": settings, "restartRequired": restart_required}

    # ------------------------------------------------------------------ 事件
    def note_event(self, camera: VirtualCamera, event: DetectionEvent) -> None:
        summary = {
            "type": "detection",
            "cameraId": camera.id,
            "cameraName": camera.name,
            "groups": sorted(event.groups),
            "active": event.active,
            "source": event.source,
            "timestamp": event.timestamp,
            "confidence": {k: round(v, 3) for k, v in event.confidence.items()},
            "snapshot": bool(event.snapshot_path),
        }
        self.last_events.appendleft(summary)
        BUS.append(
            "INFO",
            "event",
            f"[{camera.name}] {','.join(sorted(event.groups))} → {'触发' if event.active else '结束'} ({event.source})",
        )

    def publish_camera_state(self, camera: VirtualCamera) -> None:
        self.events.publish(
            {
                "type": "camera_state",
                "cameraId": camera.id,
                "cameraName": camera.name,
                "status": camera.status,
                "error": camera.last_error,
                "timestamp": now_iso(),
            }
        )

    # ------------------------------------------------------------------ MediaMTX 鉴权
    def mediamtx_auth(self, payload: dict[str, Any]) -> tuple[bool, str]:
        action = str(payload.get("action", ""))
        ip = str(payload.get("ip", ""))
        path = str(payload.get("path", ""))
        user = str(payload.get("user", ""))
        password = str(payload.get("password", ""))

        if action in ("api", "metrics", "pprof"):
            return True, "ok"
        if action == "publish":
            if ip in ("127.0.0.1", "::1", self.local_ip):
                return True, "本地推流"
            return False, "仅允许本机推流"
        if action in ("read", "playback"):
            if not self.settings.get("rtspAuthEnabled", False):
                return True, "开放读取"
            expected_user = str(self.settings.get("rtspUsername", "cx"))
            expected_pass = str(self.settings.get("rtspPassword", ""))
            if user == expected_user and password == expected_pass:
                return True, "认证通过"
            if not user and not expected_pass:
                return True, "无密码"
            return False, "RTSP 认证失败"
        return True, f"未限制的动作 {action}"

    def is_ip_whitelisted(self, ip: str | None) -> bool:
        """ONVIF 免认证 IP：仅本机。"""
        return ip in ("127.0.0.1", "::1")

    # ------------------------------------------------------------------ 状态
    def status(self) -> dict[str, Any]:
        cameras = []
        for config in self.store.cameras:
            runtime = self.cameras.get(config.id)
            if runtime:
                cameras.append(runtime.state())
            else:
                cameras.append(
                    {
                        "id": config.id,
                        "name": config.name,
                        "status": "stopped",
                        "enabled": config.enabled,
                        "config": config.public_dict(),
                        "onvif": {
                            "port": config.onvif.port,
                            "profile": config.onvif.profile,
                            "xaddr": f"http://{self.local_ip}:{config.onvif.port}/onvif/device_service",
                        },
                        "streams": {
                            "main": {"url": f"rtsp://{self.local_ip}:{self.settings.get('rtspPort')}/{config.basePath}_main"},
                            "overlay": {"enabled": config.overlay.enabled,
                                        "url": f"rtsp://{self.local_ip}:{self.settings.get('rtspPort')}/{config.overlayPath}"},
                        },
                    }
                )
        return {
            "running": self.running,
            "uptime": int(time.time() - self.started_at) if self.started_at else 0,
            "captures": len(cameras),
            "cameras": cameras,
            "mediamtx": self.mediamtx.status(),
        }

    def system_info(self) -> dict[str, Any]:
        return {
            "brand": brand.BRAND_ZH,
            "brandEn": brand.BRAND_EN,
            "product": brand.PRODUCT,
            "tagline": brand.TAGLINE,
            "version": CURRENT_VERSION,
            "versionString": version_string(),
            "host": platform.node(),
            "localIp": self.local_ip,
            "os": f"{platform.system()} {platform.release()}",
            "python": sys.version.split()[0],
            "uptime": int(time.time() - self.started_at) if self.started_at else 0,
            "ports": {
                "web": int(self.settings.get("webPort", 5552)),
                "rtsp": int(self.settings.get("rtspPort", 8554)),
                "hls": int(self.settings.get("hlsPort", 8888)),
                "webrtc": int(self.settings.get("webrtcPort", 8889)),
                "onvifStart": int(self.settings.get("onvifPortStart", 8001)),
            },
            "hardware": self.hardware.to_dict(),
            "ffmpeg": {
                "path": str(self.ffmpeg.path) if self.ffmpeg else "",
                "version": self.ffmpeg.version if self.ffmpeg else "",
                "available": self.ffmpeg is not None,
            },
            "mediamtx": self.mediamtx.status(),
            "counts": {
                "cameras": len(self.store.cameras),
                "running": sum(1 for c in self.cameras.values() if c.status == "running"),
            },
            "models": {"installed": [m for m in list_models() if m["installed"]],
                       "registry": [m["key"] for m in list_models()]},
            "profiles": list_profiles(),
            "links": {
                "bilibili": brand.BILIBILI,
                "github": brand.GITHUB_URL,
                "email": brand.EMAIL,
            },
            "license": "MIT",
            "copyright": brand.COPYRIGHT,
        }

    def events_since(self, seq: int) -> list[dict]:
        return self.events.since(seq)

    def recent_events(self, limit: int = 100) -> list[dict]:
        return list(self.last_events)[:limit]

    def test_push(self, camera_id: int) -> tuple[bool, str]:
        config = self.store.get_camera(camera_id)
        if not config:
            return False, "摄像机不存在"
        if not config.mercury.pushUrl:
            return False, "未配置推送地址"
        pusher = AlarmPusher(config, device_ip=self.local_ip)
        from ..detect.types import Detection

        event = DetectionEvent(
            camera_id=config.id,
            camera_name=config.name,
            groups={"person"},
            active=True,
            timestamp=now_iso(),
            confidence={"person": 0.91},
            detections=[Detection(label="person", confidence=0.91, box=(0.3, 0.3, 0.6, 0.8), group="person", class_id=0)],
            source="test",
        )
        ok = pusher.push(event)
        return ok, pusher.stats.lastError or ("推送成功" if ok else "推送失败")
