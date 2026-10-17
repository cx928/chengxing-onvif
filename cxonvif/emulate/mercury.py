"""水星安防摄像机模拟 / MERCURY camera emulation.

把 AI 检测结果翻译成录像机能够理解的 ONVIF 事件，并按厂商画像扩展主题，
同时可通过 HTTP 主动推送到 NVR / 平台。

典型用法::

    mercury = MercuryEmulator(camera_config, onvif_service, device_ip="192.168.1.10")
    mercury.start()
    mercury.on_detection(event)     # 由检测管线回调
"""

from __future__ import annotations

import threading
import time
from typing import Any

from ..bus import EventBus
from ..config import CameraConfig
from ..detect.types import DetectionEvent
from ..logbus import info
from ..onvif.profiles import resolve_profile, topic_map
from ..onvif.service import ONVIFService
from .push import AlarmPusher


class MercuryEmulator:
    def __init__(
        self,
        camera: CameraConfig,
        onvif: ONVIFService | None,
        *,
        bus: EventBus | None = None,
        device_ip: str = "",
    ) -> None:
        self.camera = camera
        self.onvif = onvif
        self.bus = bus
        self.profile = resolve_profile(camera)
        self.topics = topic_map(camera)
        self.pusher = AlarmPusher(camera, device_ip=device_ip)
        self.stats: dict[str, Any] = {
            "onvifEvents": 0,
            "pushed": 0,
            "lastEventAt": 0.0,
            "lastGroups": [],
            "active": False,
            "profile": self.profile.key,
            "manufacturer": self.profile.manufacturer,
            "model": self.profile.model,
        }
        self._heartbeat: threading.Thread | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        if self._heartbeat and self._heartbeat.is_alive():
            return
        self._stop.clear()
        self._heartbeat = threading.Thread(target=self._heartbeat_loop, name=f"mercury-{self.camera.id}", daemon=True)
        self._heartbeat.start()

    def stop(self) -> None:
        self._stop.set()
        if self._heartbeat:
            self._heartbeat.join(timeout=2)

    def _heartbeat_loop(self) -> None:
        """定期刷新订阅活跃时间，避免录像机认为订阅过期。"""
        interval = max(10.0, float(self.camera.mercury.heartbeatInterval or 30.0))
        while not self._stop.wait(interval):
            if not self.camera.onvif.sendHeartbeat or not self.onvif:
                continue
            now = time.time()
            for subscription in list(getattr(self.onvif, "subscriptions", {}).values()):
                subscription.last_active = now

    # ------------------------------------------------------------------ 事件转换
    def build_events(self, event: DetectionEvent) -> list[dict[str, Any]]:
        """把检测事件展开成 ONVIF 事件字典列表。"""
        value = "true" if event.active else "false"
        events: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(topic: str, data_name: str, rule: str) -> None:
            if topic in seen:
                return
            seen.add(topic)
            events.append(
                {
                    "topic": topic,
                    "value": value,
                    "data_name": data_name,
                    "timestamp": event.timestamp,
                    "tags": sorted(event.groups),
                    "rule": rule,
                    "type": "ai",
                    "active": event.active,
                }
            )

        if self.camera.onvif.sendMotion:
            for definition in self.topics.get("motion", []):
                add(definition.topic, definition.dataName, "MotionDetector")
            # 移动事件同时附带 VideoSource/MotionAlarm，兼容只认该主题的 NVR
            for definition in self.topics.get("motion", []):
                if definition.topic.endswith("MotionAlarm"):
                    continue

        if self.camera.onvif.sendSmart:
            for group in sorted(event.groups):
                for definition in self.topics.get(group, []):
                    add(definition.topic, definition.dataName, f"{group.capitalize()}Detector")
        return events

    # ------------------------------------------------------------------ 主入口
    def on_detection(self, event: DetectionEvent) -> None:
        if not self.camera.mercury.enabled and not self.camera.onvif.enabled:
            return
        self.stats["lastEventAt"] = time.time()
        self.stats["lastGroups"] = sorted(event.groups)
        self.stats["active"] = bool(event.active)

        events = self.build_events(event)
        queued = 0
        if self.onvif:
            subscriptions = list(getattr(self.onvif, "subscriptions", {}).values())
            for payload in events:
                for subscription in subscriptions:
                    try:
                        subscription.queue.put_nowait(payload)
                        queued += 1
                    except Exception:
                        try:
                            subscription.queue.get_nowait()
                            subscription.queue.put_nowait(payload)
                            queued += 1
                        except Exception:
                            pass
        self.stats["onvifEvents"] += len(events)

        if event.active and self.camera.mercury.pushEnabled:
            if self.pusher.push(event):
                self.stats["pushed"] += 1

        if self.bus:
            self.bus.publish(
                {
                    "type": "detection",
                    "cameraId": self.camera.id,
                    "cameraName": self.camera.name,
                    "groups": sorted(event.groups),
                    "active": event.active,
                    "source": event.source,
                    "timestamp": event.timestamp,
                    "confidence": {k: round(v, 3) for k, v in event.confidence.items()},
                    "detections": [d.to_dict() for d in event.detections],
                    "profile": self.profile.key,
                    "manufacturer": self.profile.manufacturer,
                    "queuedOnvif": queued,
                    "pushed": bool(event.active and self.camera.mercury.pushEnabled),
                }
            )

    # ------------------------------------------------------------------ 状态
    def status(self) -> dict[str, Any]:
        return {
            **self.stats,
            "enabled": bool(self.camera.mercury.enabled),
            "topics": {group: [d.topic for d in definitions] for group, definitions in self.topics.items()},
            "push": self.pusher.status(),
            "identity": self.profile.device_identity(),
        }

    def trigger_test(self) -> None:
        from ..detect.types import Detection
        from ..util import now_iso

        active = DetectionEvent(
            camera_id=self.camera.id,
            camera_name=self.camera.name,
            groups={"person"},
            active=True,
            timestamp=now_iso(),
            confidence={"person": 0.93},
            detections=[Detection(label="person", confidence=0.93, box=(0.3, 0.3, 0.6, 0.8), group="person", class_id=0)],
            source="test",
        )
        self.on_detection(active)
        timer = threading.Timer(3.0, lambda: self.on_detection(
            DetectionEvent(
                camera_id=self.camera.id,
                camera_name=self.camera.name,
                groups={"person"},
                active=False,
                timestamp=now_iso(),
                confidence={"person": 0.0},
                source="test",
            )
        ))
        timer.daemon = True
        timer.start()
        info(f"[{self.camera.name}] 已发送测试检测事件（水星画像 {self.profile.manufacturer}）", "mercury")
