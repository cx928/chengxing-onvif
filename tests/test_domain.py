"""单元测试：厂商画像、区域规则、水星事件。"""

from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("CXONVIF_HOME", tempfile.mkdtemp(prefix="cx-test-home-"))

from cxonvif.config import CameraConfig, DetectConfig, OnvifConfig, SourceConfig, Zone  # noqa: E402
from cxonvif.detect.types import Detection, DetectionEvent  # noqa: E402
from cxonvif.detect.zones import filter_detections, point_in_polygon  # noqa: E402
from cxonvif.emulate.mercury import MercuryEmulator  # noqa: E402
from cxonvif.emulate.push import AlarmPusher  # noqa: E402
from cxonvif.onvif.profiles import get_profile, resolve_profile, topic_map  # noqa: E402


class ProfileTests(unittest.TestCase):
    def test_mercury_identity(self) -> None:
        camera = CameraConfig(name="前门", onvif=OnvifConfig(profile="mercury"))
        profile = resolve_profile(camera)
        self.assertEqual(profile.manufacturer, "MERCURY")
        self.assertIn("MIPC", profile.model)
        self.assertTrue(any("NetworkVideoTransmitter" in scope for scope in profile.scope_list("前门")))

    def test_scope_name_is_uri_safe(self) -> None:
        camera = CameraConfig(name="园区 前门", onvif=OnvifConfig(profile="mercury"))
        scopes = resolve_profile(camera).scope_list(camera.name)
        name_scope = [s for s in scopes if "/name/" in s][0]
        self.assertNotIn(" ", name_scope)
        self.assertIn("%20", name_scope)

    def test_override_identity(self) -> None:
        camera = CameraConfig(
            name="x",
            onvif=OnvifConfig(profile="mercury", manufacturer="CUSTOM", model="MODEL-1"),
        )
        identity = resolve_profile(camera).device_identity()
        self.assertEqual(identity["manufacturer"], "CUSTOM")
        self.assertEqual(identity["model"], "MODEL-1")

    def test_topic_map_override(self) -> None:
        camera = CameraConfig(
            name="x",
            onvif=OnvifConfig(
                profile="mercury",
                eventTopics={"person": [{"topic": "tns1:RuleEngine/PeopleDetector/PeopleDetected", "dataName": "State"}]},
            ),
        )
        topics = topic_map(camera)
        self.assertEqual(topics["person"][0].topic, "tns1:RuleEngine/PeopleDetector/PeopleDetected")
        self.assertTrue(topics["motion"])

    def test_profiles_have_topics(self) -> None:
        for key in ("mercury", "tplink_vigi", "hikvision", "dahua", "uniview", "unifi", "generic"):
            profile = get_profile(key)
            self.assertTrue(profile.topics, f"{key} 没有事件主题")
            self.assertTrue(profile.manufacturer)


class ZoneTests(unittest.TestCase):
    def test_point_in_polygon(self) -> None:
        square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        self.assertTrue(point_in_polygon(0.5, 0.5, square))
        self.assertFalse(point_in_polygon(1.5, 0.5, square))
        self.assertFalse(point_in_polygon(0.5, 0.5, [(0.6, 0.6), (0.9, 0.6), (0.9, 0.9)]))

    def test_include_and_exclude(self) -> None:
        detection_in = Detection(label="person", confidence=0.9, box=(0.1, 0.1, 0.2, 0.2), group="person")
        detection_out = Detection(label="person", confidence=0.9, box=(0.8, 0.8, 0.9, 0.9), group="person")
        zones = [Zone(type="include", points=[[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]])]
        result = filter_detections([detection_in, detection_out], zones)
        self.assertEqual(result, [detection_in])

        exclude = [Zone(type="exclude", points=[[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]])]
        result = filter_detections([detection_in, detection_out], exclude)
        self.assertEqual(result, [detection_out])


class MercuryEventTests(unittest.TestCase):
    def setUp(self) -> None:
        self.camera = CameraConfig(
            id=1,
            name="前门",
            source=SourceConfig(mainUrl="rtsp://x/1"),
            detect=DetectConfig(targets=["person", "vehicle"]),
            onvif=OnvifConfig(profile="mercury"),
        )
        self.emulator = MercuryEmulator(self.camera, None)

    def test_build_events_for_person(self) -> None:
        event = DetectionEvent(
            camera_id=1, camera_name="前门", groups={"person"}, active=True,
            timestamp="2026-01-01T00:00:00.000Z", confidence={"person": 0.9},
        )
        events = self.emulator.build_events(event)
        topics = {item["topic"] for item in events}
        self.assertIn("tns1:RuleEngine/CellMotionDetector/Motion", topics)
        self.assertTrue(any("PeopleDetector" in topic for topic in topics))
        self.assertTrue(all(item["value"] == "true" for item in events))
        self.assertTrue(all(item["rule"] for item in events))

    def test_deactivation(self) -> None:
        event = DetectionEvent(
            camera_id=1, camera_name="前门", groups={"person"}, active=False,
            timestamp="2026-01-01T00:00:05.000Z",
        )
        events = self.emulator.build_events(event)
        self.assertTrue(events)
        self.assertTrue(all(item["value"] == "false" for item in events))

    def test_push_payload_json(self) -> None:
        self.camera.mercury.pushEnabled = True
        self.camera.mercury.pushUrl = "http://127.0.0.1:9/alarm"
        self.camera.mercury.pushToken = "secret-token"
        pusher = AlarmPusher(self.camera, device_ip="10.0.0.5")
        event = DetectionEvent(
            camera_id=1, camera_name="前门", groups={"person"}, active=True,
            timestamp="2026-01-01T00:00:00.000Z", confidence={"person": 0.9},
        )
        body, content_type, headers = pusher.build_payload(event)
        self.assertEqual(content_type, "application/json")
        import json

        payload = json.loads(body)
        self.assertEqual(payload["groups"], ["person"])
        self.assertEqual(payload["label"], "人形")
        self.assertIn("Authorization", headers)
        self.assertEqual(headers["Authorization"], "Bearer secret-token")

    def test_push_payload_without_token(self) -> None:
        self.camera.mercury.pushFormat = "json"
        self.camera.mercury.pushToken = ""
        pusher = AlarmPusher(self.camera, device_ip="10.0.0.5")
        event = DetectionEvent(
            camera_id=1, camera_name="前门", groups={"person"}, active=False,
            timestamp="2026-01-01T00:00:00.000Z",
        )
        _, _, headers = pusher.build_payload(event)
        self.assertNotIn("Authorization", headers)

    def test_push_payload_formats(self) -> None:
        for fmt in ("json", "dahua", "hikvision", "tplink", "form"):
            self.camera.mercury.pushFormat = fmt
            pusher = AlarmPusher(self.camera, device_ip="10.0.0.5")
            event = DetectionEvent(
                camera_id=1, camera_name="前门", groups={"vehicle"}, active=True,
                timestamp="2026-01-01T00:00:00.000Z", confidence={"vehicle": 0.8},
            )
            body, content_type, headers = pusher.build_payload(event)
            self.assertTrue(body)
            self.assertTrue(content_type)
            self.assertIn("Content-Type", headers)


if __name__ == "__main__":
    unittest.main()
