"""虚拟摄像机 / Virtual camera runtime.

一个 VirtualCamera 聚合：
* ONVIF 设备/媒体/事件服务（独立端口 + WS-Discovery）
* 帧源（FFmpeg 解码）
* AI 检测管线
* 检测框叠加推流
* 水星安防事件模拟与主动推送
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import deque
from typing import Any

from ..config import CameraConfig
from ..detect.pipeline import AnalyticsPipeline
from ..detect.types import DetectionEvent
from ..emulate.mercury import MercuryEmulator
from ..hw.ffmpeg import resolve_ffmpeg
from ..logbus import info, warn
from ..onvif.profiles import resolve_profile, topic_map
from ..onvif.service import ONVIFService
from ..stream.frames import FrameSource
from ..stream.overlay_stream import OverlayStream
from ..util import local_ip, now_iso, slugify


class VirtualCamera:
    def __init__(self, config: CameraConfig, manager: Any) -> None:
        self.config = config
        self.manager = manager
        self.status = "stopped"
        self.last_error = ""
        self.started_at = 0.0

        self.onvif_service: ONVIFService | None = None
        self._onvif_server = None
        self._onvif_thread: threading.Thread | None = None
        self._discovery_started = False

        self.frame_source: FrameSource | None = None
        self.pipeline: AnalyticsPipeline | None = None
        self.overlay: OverlayStream | None = None
        self.mercury: MercuryEmulator | None = None
        self.ffmpeg_tool = None

        self.event_logs: deque[dict] = deque(maxlen=100)
        self.last_event: DetectionEvent | None = None
        self.last_event_at = 0.0
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ 兼容属性
    @property
    def id(self) -> int:
        return self.config.id

    @property
    def uuid(self) -> str:
        return self.config.uuid

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def path_name(self) -> str:
        return self.config.basePath

    @property
    def onvif_port(self) -> int:
        return self.config.onvif.port

    @property
    def onvif_username(self) -> str:
        return self.config.onvif.username

    @property
    def onvif_password(self) -> str:
        return self.config.onvif.password

    @property
    def rtsp_port(self) -> int:
        return int(self.manager.settings.get("rtspPort", 8554))

    @property
    def main_stream_url(self) -> str:
        return self.config.source.url("main")

    @property
    def sub_stream_url(self) -> str:
        return self.config.source.url("sub")

    @property
    def main_width(self) -> int:
        return int(self.config.source.mainWidth)

    @property
    def main_height(self) -> int:
        return int(self.config.source.mainHeight)

    @property
    def main_framerate(self) -> int:
        return int(self.config.source.mainFramerate)

    @property
    def sub_width(self) -> int:
        return int(self.config.source.subWidth)

    @property
    def sub_height(self) -> int:
        return int(self.config.source.subHeight)

    @property
    def sub_framerate(self) -> int:
        return int(self.config.source.subFramerate)

    @property
    def disable_substream(self) -> bool:
        return not self.config.stream.enableSubstream

    @property
    def enable_audio(self) -> bool:
        return bool(self.config.stream.enableAudio)

    @property
    def ip_mode(self) -> str:
        return "dhcp"

    @property
    def assigned_ip(self) -> str:
        return ""

    @property
    def debug_mode(self) -> bool:
        return str(self.manager.settings.get("logLevel", "INFO")).upper() == "DEBUG"

    @property
    def mac_address(self) -> str:
        digest = hashlib.sha256(self.config.uuid.encode("utf-8")).hexdigest()
        parts = [digest[i : i + 2].upper() for i in range(0, 10, 2)]
        return "02:" + ":".join(parts)

    @property
    def serial_number(self) -> str:
        digest = hashlib.sha256((self.config.uuid + self.config.name).encode("utf-8")).hexdigest().upper()
        prefix = self.profile.serialPrefix if self.profile else "CX"
        return f"{prefix}{digest[:12]}"

    def get_effective_ip(self) -> str:
        return self.manager.local_ip

    # ------------------------------------------------------------------ 厂商画像
    @property
    def profile(self):
        return resolve_profile(self.config)

    def profile_identity(self) -> dict[str, str]:
        return self.profile.device_identity()

    def profile_scopes(self) -> list[str]:
        return self.profile.scope_list(self.config.name)

    def profile_topics(self) -> dict[str, list]:
        return topic_map(self.config)

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> bool:
        with self._lock:
            if self.status in ("running", "starting"):
                return True
            self.status = "starting"
            self.last_error = ""
            self.config = self.manager.store.get_camera(self.config.id) or self.config
            self.ffmpeg_tool = resolve_ffmpeg(self.manager.settings.get("ffmpegPath", ""))

            if self.config.onvif.enabled:
                if not self._start_onvif():
                    self.status = "error"
                    return False

            needs_frames = bool(self.config.detect.enabled or self.config.overlay.enabled)
            if needs_frames and self.ffmpeg_tool is None:
                self.last_error = "未找到 FFmpeg，无法拉流与推理"
                self.status = "error"
                warn(f"[{self.name}] {self.last_error}", "camera")
                return False

            if needs_frames:
                self._start_frames()
                if self.config.detect.enabled:
                    self.pipeline = AnalyticsPipeline(
                        self.config,
                        hardware=self.manager.hardware,
                        frame_source=self.frame_source,
                        on_event=self._on_detection,
                        ffmpeg=self.ffmpeg_tool,
                    )
                    self.pipeline.start()
                if self.config.overlay.enabled:
                    self._start_overlay()

            self.mercury = MercuryEmulator(
                self.config,
                self.onvif_service,
                bus=self.manager.events,
                device_ip=self.get_effective_ip(),
            )
            self.mercury.start()

            self.status = "running"
            self.started_at = time.time()
            if self.config.onvif.enabled and self.config.onvif.wsDiscovery and not self._discovery_started:
                self.onvif_service.start_discovery_service(self.get_effective_ip())
                self._discovery_started = True
            info(f"[{self.name}] 已启动 · ONVIF :{self.onvif_port} · 叠加 {self.config.overlay.enabled}", "camera")
            self.manager.publish_camera_state(self)
            return True

    def stop(self) -> None:
        with self._lock:
            if self.status == "stopped":
                return
            self.status = "stopping"
            if self.mercury:
                self.mercury.stop()
                self.mercury = None
            if self.overlay:
                self.overlay.stop()
                self.overlay = None
            if self.pipeline:
                self.pipeline.stop()
                self.pipeline = None
            if self.frame_source:
                self.frame_source.stop()
                self.frame_source = None
            self._stop_onvif()
            self.status = "stopped"
            self.started_at = 0.0
            info(f"[{self.name}] 已停止", "camera")
            self.manager.publish_camera_state(self)

    def restart(self) -> bool:
        self.stop()
        time.sleep(0.3)
        return self.start()

    # ------------------------------------------------------------------ ONVIF
    def _start_onvif(self) -> bool:
        from werkzeug.serving import make_server

        self.onvif_service = ONVIFService(self, self.profile)
        try:
            app = self.onvif_service.create_app()
            bind = self.manager.settings.get("bind", "0.0.0.0") or "0.0.0.0"
            server = make_server(bind, self.onvif_port, app, threaded=True)
            server.daemon_threads = True
        except OSError as exc:
            self.last_error = f"ONVIF 端口 {self.onvif_port} 启动失败：{exc}"
            warn(f"[{self.name}] {self.last_error}", "onvif")
            return False
        except Exception as exc:
            self.last_error = f"ONVIF 服务启动失败：{exc}"
            warn(f"[{self.name}] {self.last_error}", "onvif")
            return False

        self._onvif_server = server
        self._onvif_thread = threading.Thread(
            target=server.serve_forever, name=f"onvif-{self.config.id}", daemon=True
        )
        self._onvif_thread.start()
        return True

    def _stop_onvif(self) -> None:
        self._discovery_started = False
        if self._onvif_server is not None:
            try:
                self._onvif_server.shutdown()
            except Exception:
                pass
            try:
                self._onvif_server.server_close()
            except Exception:
                pass
            self._onvif_server = None
        self.onvif_service = None

    # ------------------------------------------------------------------ 帧与叠加
    def _start_frames(self) -> None:
        target_width = self.config.overlay.width if self.config.overlay.enabled else self.config.detect.frameWidth
        target_width = max(320, min(int(target_width), 1920))
        # 硬件解码默认关闭：兼容性更好；用户可在设置里显式指定 cuda/qsv/d3d11va/vaapi
        decode_mode = str(self.manager.settings.get("decodeMode", "auto") or "auto")
        decoder = decode_mode if decode_mode in ("cuda", "qsv", "d3d11va", "dxva2", "vaapi", "videotoolbox") else ""
        self.frame_source = FrameSource(
            self.config.source.url("main") or self.config.source.url("sub"),
            ffmpeg=self.ffmpeg_tool,
            target_width=target_width,
            fps=max(float(self.config.overlay.fps), float(self.config.detect.fps)),
            transport=self.config.source.transport,
            decoder=decoder,
            name=self.name,
        )
        self.frame_source.start()

    def _start_overlay(self) -> None:
        if not self.frame_source:
            return
        # 等待首帧以确定分辨率
        seq, frame = self.frame_source.wait_frame(0, timeout=12.0)
        if frame is None:
            warn(f"[{self.name}] 未能获取视频帧，叠加推流延后", "overlay")
            width, height = 1280, 720
        else:
            height, width = frame.shape[:2]
        rtsp_url = f"rtsp://127.0.0.1:{self.rtsp_port}/{self.config.overlayPath}"
        self.overlay = OverlayStream(
            self.config,
            ffmpeg=self.ffmpeg_tool,
            hardware=self.manager.hardware,
            rtsp_url=rtsp_url,
            detections_provider=self._overlay_detections,
            frame_provider=self.frame_source.wait_frame,
            width=width,
            height=height,
        )
        self.overlay.start()

    def _overlay_detections(self) -> tuple[list, list]:
        if self.pipeline:
            return self.pipeline.detections_for_overlay()
        return [], list(self.config.detect.zones)

    # ------------------------------------------------------------------ 事件
    def _on_detection(self, event: DetectionEvent) -> None:
        self.last_event = event
        self.last_event_at = time.time()
        record = event.to_dict()
        record["snapshot"] = bool(event.snapshot_path)
        self.event_logs.appendleft(record)
        if self.mercury:
            self.mercury.on_detection(event)
        self.manager.note_event(self, event)

    def trigger_test(self) -> None:
        if self.mercury:
            self.mercury.trigger_test()
        else:
            warn(f"[{self.name}] 摄像机未运行，无法发送测试事件", "camera")

    def snapshot_jpeg(self) -> bytes | None:
        if self.frame_source:
            return self.frame_source.snapshot_jpeg()
        return None

    # ------------------------------------------------------------------ 状态
    def state(self) -> dict[str, Any]:
        config = self.config
        overlay_rtsp = f"rtsp://{self.manager.local_ip}:{self.rtsp_port}/{config.overlayPath}"
        main_rtsp = f"rtsp://{self.manager.local_ip}:{self.rtsp_port}/{config.basePath}_main"
        sub_rtsp = f"rtsp://{self.manager.local_ip}:{self.rtsp_port}/{config.basePath}_sub"
        data: dict[str, Any] = {
            "id": config.id,
            "name": config.name,
            "uuid": config.uuid,
            "enabled": config.enabled,
            "status": self.status,
            "error": self.last_error,
            "startedAt": self.started_at,
            "onvif": {
                "enabled": config.onvif.enabled,
                "port": config.onvif.port,
                "username": config.onvif.username,
                "xaddr": f"http://{self.manager.local_ip}:{config.onvif.port}/onvif/device_service",
                "profile": self.profile.key,
                "profileName": self.profile.name,
                "manufacturer": self.profile.manufacturer,
                "model": self.profile.model,
                "firmware": self.profile.firmware,
                "serial": self.serial_number,
                "mac": self.mac_address,
                "wsDiscovery": config.onvif.wsDiscovery,
            },
            "streams": {
                "main": {
                    "url": main_rtsp,
                    "source": config.source.url("main"),
                    "width": config.source.mainWidth,
                    "height": config.source.mainHeight,
                    "fps": config.source.mainFramerate,
                },
                "sub": {
                    "url": sub_rtsp,
                    "source": config.source.url("sub"),
                    "width": config.source.subWidth,
                    "height": config.source.subHeight,
                    "fps": config.source.subFramerate,
                },
                "overlay": {
                    "enabled": config.overlay.enabled,
                    "url": overlay_rtsp,
                    "path": config.overlayPath,
                },
            },
            "detect": self.pipeline.status_dict() if self.pipeline else {
                "running": False,
                "enabled": config.detect.enabled,
                "model": config.detect.model,
            },
            "overlay": {
                "enabled": config.overlay.enabled,
                "stats": self.overlay.stats.to_dict() if self.overlay else {"running": False},
                "path": config.overlayPath,
            },
            "mercury": self.mercury.status() if self.mercury else {"enabled": config.mercury.enabled},
            "frame": self.frame_source.stats.to_dict() if self.frame_source else {"running": False},
            "lastEventAt": self.last_event_at,
            "snapshotUrl": f"/api/v2/cameras/{config.id}/snapshot?t={int(time.time())}",
            "config": config.public_dict(),
        }
        if self.overlay:
            data["overlay"]["width"] = self.overlay.width
            data["overlay"]["height"] = self.overlay.height
        return data
