"""主动推送通道 / Active alarm push.

部分录像机（尤其是国产 NVR / 平台）除了 ONVIF 订阅，还支持 HTTP 报警推送。
这里提供通用 JSON、表单、大华风格、海康风格、以及“水星/TP-LINK 兼容”模板。
"""

from __future__ import annotations

import base64
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

from ..config import CameraConfig, MercuryConfig
from ..detect.types import DetectionEvent
from ..logbus import warn
from ..util import now_iso


@dataclass
class PushStats:
    sent: int = 0
    failed: int = 0
    lastError: str = ""
    lastSentAt: float = 0.0
    lastStatus: int = 0


class AlarmPusher:
    """按配置把检测事件推送到 NVR / 平台。"""

    def __init__(self, camera: CameraConfig, device_ip: str = "") -> None:
        self.camera = camera
        self.device_ip = device_ip
        self.config: MercuryConfig = camera.mercury
        self.stats = PushStats()
        self._lock = threading.Lock()
        self._last_sent: dict[str, float] = {}

    # ------------------------------------------------------------------ 载荷
    def _group_label(self, group: str) -> str:
        return {
            "person": "人形",
            "vehicle": "车辆",
            "animal": "动物",
            "package": "物品",
            "face": "人脸",
            "motion": "移动",
        }.get(group, group)

    def build_payload(self, event: DetectionEvent) -> tuple[bytes, str, dict[str, str]]:
        groups = sorted(event.groups)
        primary = groups[0] if groups else "motion"
        label = self._group_label(primary)
        confidence = int(round(max(event.confidence.values(), default=0.0) * 100))
        snapshot_b64 = ""
        if event.snapshot_bytes and self.config.includeSnapshot:
            snapshot_b64 = base64.b64encode(event.snapshot_bytes).decode("ascii")

        headers: dict[str, str] = {"Content-Type": "application/json; charset=utf-8"}
        if self.config.pushToken:
            headers["Authorization"] = f"Bearer {self.config.pushToken}"
        headers.update(self.config.extraHeaders or {})

        fmt = (self.config.pushFormat or "json").lower()
        if fmt == "hikvision":
            # 海康 ISAPI 事件风格（XML）
            xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<EventNotificationAlert version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
                f"<ipAddress>{self.device_ip}</ipAddress>"
                f"<channelName>{self.camera.name}</channelName>"
                f"<dateTime>{event.timestamp}</dateTime>"
                f"<eventType>{'VMD' if primary == 'motion' else 'fielddetection'}</eventType>"
                f"<eventState>{'active' if event.active else 'inactive'}</eventState>"
                f"<eventDescription>{label}</eventDescription>"
                "<DetectionRegionList/>"
                "</EventNotificationAlert>"
            )
            headers["Content-Type"] = "application/xml; charset=utf-8"
            return xml.encode("utf-8"), "application/xml", headers

        if fmt == "dahua":
            # 大华 AlarmCenter 风格 JSON
            payload = {
                "method": "event",
                "params": {
                    "events": [
                        {
                            "Code": "CrossRegionDetection" if primary != "motion" else "VideoMotion",
                            "Action": "Start" if event.active else "Stop",
                            "Index": self.camera.id,
                            "Data": {
                                "Name": label,
                                "Object": {"ObjectType": primary, "Confidence": confidence},
                                "PTS": int(time.time() * 1000),
                            },
                        }
                    ]
                },
            }
            return json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json", headers

        if fmt == "tplink":
            # 水星 / TP-LINK 云平台风格（报警推送）
            payload = {
                "method": "push_alarm",
                "device_id": self.camera.uuid,
                "device_name": self.camera.name,
                "alarm_type": "people" if primary == "person" else "vehicle" if primary == "vehicle" else "motion",
                "alarm_time": event.timestamp,
                "channel": 0,
                "status": 1 if event.active else 0,
                "confidence": confidence,
                "image": snapshot_b64,
            }
            return json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json", headers

        if fmt == "form":
            from urllib.parse import urlencode

            fields = {
                "camera_id": str(self.camera.id),
                "camera_name": self.camera.name,
                "event": primary,
                "label": label,
                "active": "1" if event.active else "0",
                "confidence": str(confidence),
                "timestamp": event.timestamp,
            }
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            return urlencode(fields).encode("utf-8"), "application/x-www-form-urlencoded", headers

        payload = {
            "event": "detection",
            "cameraId": self.camera.id,
            "cameraName": self.camera.name,
            "uuid": self.camera.uuid,
            "active": event.active,
            "groups": groups,
            "label": label,
            "confidence": confidence,
            "timestamp": event.timestamp or now_iso(),
            "detections": [d.to_dict() for d in event.detections],
            "image": snapshot_b64,
            "brand": "程星 ONVIF",
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json", headers

    # ------------------------------------------------------------------ 发送
    def push(self, event: DetectionEvent) -> bool:
        if not self.config.pushEnabled or not self.config.pushUrl:
            return False
        key = ",".join(sorted(event.groups)) + str(event.active)
        cooldown = max(0.0, float(self.config.eventCooldown))
        now = time.time()
        with self._lock:
            if cooldown and now - self._last_sent.get(key, 0.0) < cooldown:
                return False
            self._last_sent[key] = now

        body, content_type, headers = self.build_payload(event)
        headers = {**headers, "Content-Type": content_type}
        attempts = max(1, int(self.config.pushRetries) + 1)
        for attempt in range(attempts):
            try:
                import requests

                response = requests.post(
                    self.config.pushUrl,
                    data=body,
                    headers=headers,
                    timeout=float(self.config.pushTimeout or 5.0),
                )
                self.stats.lastStatus = response.status_code
                if 200 <= response.status_code < 300:
                    self.stats.sent += 1
                    self.stats.lastSentAt = time.time()
                    return True
                self.stats.failed += 1
                self.stats.lastError = f"HTTP {response.status_code}: {response.text[:200]}"
            except Exception as exc:
                self.stats.failed += 1
                self.stats.lastError = str(exc)[:300]
            if attempt < attempts - 1:
                time.sleep(0.5 * (attempt + 1))
        warn(f"[{self.camera.name}] 报警推送失败：{self.stats.lastError}", "push")
        return False

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.config.pushEnabled and self.config.pushUrl),
            "url": self.config.pushUrl,
            "format": self.config.pushFormat,
            "sent": self.stats.sent,
            "failed": self.stats.failed,
            "lastError": self.stats.lastError,
            "lastStatus": self.stats.lastStatus,
            "lastSentAt": self.stats.lastSentAt,
        }
