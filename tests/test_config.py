"""单元测试：配置存储与迁移。"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("CXONVIF_HOME", tempfile.mkdtemp(prefix="cx-test-home-"))

from cxonvif.config import (  # noqa: E402
    CameraConfig,
    ConfigStore,
    DetectConfig,
    SourceConfig,
    camera_from_payload,
)


class ConfigStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "config.json"
        self.store = ConfigStore(self.path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_default_auth_created(self) -> None:
        config = self.store.config
        self.assertTrue(config.auth.passwordHash)
        self.assertTrue(config.auth.passwordSalt)
        self.assertTrue(self.store.verify_password("cx123456"))
        self.assertFalse(self.store.verify_password("wrong"))

    def test_add_camera_allocates_ids_and_ports(self) -> None:
        first = self.store.add_camera(CameraConfig(name="前门", source=SourceConfig(mainUrl="rtsp://a/1")))
        second = self.store.add_camera(CameraConfig(name="后门", source=SourceConfig(mainUrl="rtsp://a/2")))
        self.assertEqual(first.id, 1)
        self.assertEqual(second.id, 2)
        self.assertNotEqual(first.onvif.port, second.onvif.port)
        self.assertTrue(first.pathName.startswith("cam1"))

    def test_ascii_path_name(self) -> None:
        camera = self.store.add_camera(CameraConfig(name="园区 前门 #1", source=SourceConfig(mainUrl="rtsp://a/1")))
        self.assertRegex(camera.pathName, r"^[A-Za-z0-9_\-]+$")

    def test_update_camera_deep_merge(self) -> None:
        camera = self.store.add_camera(CameraConfig(name="前门", source=SourceConfig(mainUrl="rtsp://a/1")))
        updated = self.store.update_camera(camera.id, {"detect": {"confidence": 0.7, "targets": ["person"]}})
        self.assertIsNotNone(updated)
        self.assertAlmostEqual(updated.detect.confidence, 0.7)
        self.assertEqual(updated.detect.targets, ["person"])
        self.assertEqual(updated.source.mainUrl, "rtsp://a/1")

    def test_roundtrip_persistence(self) -> None:
        self.store.add_camera(CameraConfig(
            name="仓库",
            source=SourceConfig(mainUrl="rtsp://a/1", subUrl="rtsp://a/2"),
            detect=DetectConfig(targets=["vehicle"], zones=[]),
        ))
        self.store.save()
        reloaded = ConfigStore(self.path)
        self.assertEqual(len(reloaded.cameras), 1)
        self.assertEqual(reloaded.cameras[0].name, "仓库")
        self.assertEqual(reloaded.cameras[0].detect.targets, ["vehicle"])

    def test_public_dict_masks_credentials(self) -> None:
        camera = self.store.add_camera(CameraConfig(
            name="前门",
            source=SourceConfig(mainUrl="rtsp://admin:secret@10.0.0.1:554/main"),
        ))
        public = camera.public_dict()
        self.assertNotIn("secret", public["source"]["mainUrl"])
        self.assertIn("****", public["source"]["mainUrl"])
        self.assertTrue(public["onvif"]["passwordSet"])
        self.assertEqual(public["onvif"]["password"], "")

    def test_update_settings_keeps_auth_flags(self) -> None:
        self.store.update_settings({"requireLogin": False, "webPort": 6001})
        self.assertFalse(self.store.config.auth.requireLogin)
        self.assertEqual(self.store.config.settings["webPort"], 6001)
        self.store.update_settings({"requireLogin": True})
        self.assertTrue(self.store.config.auth.requireLogin)

    def test_set_password(self) -> None:
        self.store.set_password("NewPass123!", must_change=False)
        self.assertTrue(self.store.verify_password("NewPass123!"))
        self.assertFalse(self.store.verify_password("cx123456"))

    def test_camera_from_payload(self) -> None:
        camera = camera_from_payload({
            "name": "测试",
            "source": {"mainUrl": "rtsp://x/1", "mainWidth": 1280},
            "detect": {"targets": ["person"], "confidence": 0.5},
            "onvif": {"port": 8100, "profile": "mercury"},
        })
        self.assertIsInstance(camera, CameraConfig)
        self.assertEqual(camera.source.mainWidth, 1280)
        self.assertEqual(camera.onvif.profile, "mercury")
        self.assertEqual(camera.detect.targets, ["person"])

    def test_import_legacy(self) -> None:
        legacy = {
            "cameras": [{
                "id": 1, "name": "旧摄像机", "uuid": "u-1",
                "mainStreamUrl": "rtsp://admin:pw@10.0.0.9:554/h264/ch1/main/av_stream",
                "subStreamUrl": "rtsp://admin:pw@10.0.0.9:554/h264/ch1/sub/av_stream",
                "mainWidth": 1920, "mainHeight": 1080,
                "aiModel": "yolov8m.pt", "aiTargets": ["person", "vehicle"],
                "aiConfidenceThreshold": 55, "onvifPort": 9001,
            }],
            "settings": {"webPort": 5552, "rtspPort": 8554},
        }
        legacy_path = Path(self.temp.name) / "legacy.json"
        legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
        count, warnings = self.store.import_legacy_config(legacy_path)
        self.assertEqual(count, 1)
        self.assertEqual(warnings, [])
        imported = self.store.cameras[0]
        self.assertEqual(imported.name, "旧摄像机")
        self.assertEqual(imported.detect.model, "yolov8m")
        self.assertAlmostEqual(imported.detect.confidence, 0.55)


if __name__ == "__main__":
    unittest.main()
