"""厂商画像 / ONVIF vendor profiles.

不同品牌的录像机对“设备身份”和“事件主题”有不同期待。这里内置了水星（MERCURY）、
TP-LINK VIGI、海康、大华、宇视、Ubiquiti 等画像，并允许在摄像机配置里覆盖事件主题。

水星安防（MERCURY）是 TP-LINK 旗下安防品牌，其 ONVIF 设备通常上报：
``Manufacturer=MERCURY``，并同时支持标准运动事件与企业级智能事件主题。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import CameraConfig

DEFAULT_SOURCE = (
    ("VideoSourceConfigurationToken", "tt:ReferenceToken"),
    ("Rule", "xs:string"),
)


@dataclass(frozen=True)
class TopicDef:
    topic: str
    dataName: str
    label: str
    groups: tuple[str, ...] = ("person",)
    source: tuple[tuple[str, str], ...] = DEFAULT_SOURCE
    valueType: str = "xs:boolean"

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "dataName": self.dataName,
            "label": self.label,
            "groups": list(self.groups),
        }


@dataclass(frozen=True)
class VendorProfile:
    key: str
    name: str
    manufacturer: str
    model: str
    firmware: str
    hardwareId: str
    scopes: tuple[str, ...]
    topics: tuple[TopicDef, ...]
    description: str = ""
    serialPrefix: str = "CX"
    discoveryTypes: str = "dn:NetworkVideoTransmitter"
    pushFormat: str = "json"

    # ------------------------------------------------------------------ 便捷方法
    def topics_for(self, group: str) -> list[TopicDef]:
        return [topic for topic in self.topics if group in topic.groups or "all" in topic.groups]

    def device_identity(self) -> dict[str, str]:
        return {
            "manufacturer": self.manufacturer,
            "model": self.model,
            "firmware": self.firmware,
            "hardwareId": self.hardwareId,
        }

    def scope_list(self, camera_name: str) -> list[str]:
        from urllib.parse import quote

        scopes = list(self.scopes)
        # 名称必须是合法 URI（中文/空格需转义），否则部分录像机直接拒绝该设备
        scopes.append(f"onvif://www.onvif.org/name/{quote(camera_name.strip() or 'Camera', safe='')}")
        return scopes

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "firmware": self.firmware,
            "hardwareId": self.hardwareId,
            "description": self.description,
            "scopes": list(self.scopes),
            "topics": [topic.to_dict() for topic in self.topics],
            "pushFormat": self.pushFormat,
        }


# --------------------------------------------------------------------------------------
# 事件主题库
# --------------------------------------------------------------------------------------

MOTION_TOPIC = TopicDef(
    topic="tns1:RuleEngine/CellMotionDetector/Motion",
    dataName="IsMotion",
    label="移动侦测",
    groups=("motion", "all"),
    source=(
        ("VideoSourceConfigurationToken", "tt:ReferenceToken"),
        ("VideoAnalyticsConfigurationToken", "tt:ReferenceToken"),
        ("Rule", "xs:string"),
    ),
)
MOTION_ALARM_TOPIC = TopicDef(
    topic="tns1:VideoSource/MotionAlarm",
    dataName="State",
    label="移动报警",
    groups=("motion", "all"),
    source=(("VideoSourceConfigurationToken", "tt:ReferenceToken"),),
)
PEOPLE_TOPIC = TopicDef(
    topic="tns1:RuleEngine/PeopleDetector/PeopleDetected",
    dataName="State",
    label="人形检测",
    groups=("person",),
    source=DEFAULT_SOURCE,
)
VEHICLE_TOPIC = TopicDef(
    topic="tns1:RuleEngine/VehicleDetector/VehicleDetected",
    dataName="State",
    label="车辆检测",
    groups=("vehicle",),
    source=DEFAULT_SOURCE,
)
OBJECTS_INSIDE_TOPIC = TopicDef(
    topic="tns1:RuleEngine/FieldDetector/ObjectsInside",
    dataName="IsInside",
    label="区域入侵（通用智能）",
    groups=("person", "vehicle", "animal"),
    source=DEFAULT_SOURCE,
)
LINE_CROSSED_TOPIC = TopicDef(
    topic="tns1:RuleEngine/LineDetector/Crossed",
    dataName="Crossed",
    label="越界检测",
    groups=("person", "vehicle"),
    source=DEFAULT_SOURCE,
)
CROSSLINE_TOPIC = TopicDef(
    topic="tns1:RuleEngine/CrossLineDetector/Crossed",
    dataName="Crossed",
    label="越界检测（大华风格）",
    groups=("person", "vehicle"),
    source=DEFAULT_SOURCE,
)
INTRUSION_TOPIC = TopicDef(
    topic="tns1:RuleEngine/IntrusionDetector/Inside",
    dataName="State",
    label="区域入侵",
    groups=("person", "vehicle"),
    source=DEFAULT_SOURCE,
)
TAMPER_TOPIC = TopicDef(
    topic="tns1:RuleEngine/TamperDetector/Tamper",
    dataName="IsTamper",
    label="遮挡报警",
    groups=("tamper",),
    source=(("VideoSourceConfigurationToken", "tt:ReferenceToken"),),
)
ANIMAL_TOPIC = TopicDef(
    topic="tns1:RuleEngine/AnimalDetector/AnimalDetected",
    dataName="State",
    label="动物检测",
    groups=("animal",),
    source=DEFAULT_SOURCE,
)
PACKAGE_TOPIC = TopicDef(
    topic="tns1:RuleEngine/PackageDetector/PackageDetected",
    dataName="State",
    label="物品检测",
    groups=("package",),
    source=DEFAULT_SOURCE,
)

GENERIC_SCOPES = (
    "onvif://www.onvif.org/type/NetworkVideoTransmitter",
    "onvif://www.onvif.org/type/video_encoder",
    "onvif://www.onvif.org/Profile/Streaming",
)


PROFILES: dict[str, VendorProfile] = {}


def _register(profile: VendorProfile) -> None:
    PROFILES[profile.key] = profile


_register(
    VendorProfile(
        key="mercury",
        name="水星安防 MERCURY",
        manufacturer="MERCURY",
        model="MIPC434(P)W",
        firmware="1.0.0 Build 250608 Rel.68426n",
        hardwareId="IPC",
        scopes=GENERIC_SCOPES + ("onvif://www.onvif.org/type/audio_encoder",),
        topics=(MOTION_TOPIC, MOTION_ALARM_TOPIC, PEOPLE_TOPIC, VEHICLE_TOPIC, OBJECTS_INSIDE_TOPIC, LINE_CROSSED_TOPIC),
        description="模拟水星（MERCURY）摄像机身份，向水星/TP-LINK 录像机上报移动与人形/车辆检测事件",
        serialPrefix="MERC",
        pushFormat="json",
    )
)
_register(
    VendorProfile(
        key="tplink_vigi",
        name="TP-LINK VIGI",
        manufacturer="TP-LINK",
        model="VIGI C340",
        firmware="1.0.6 Build 240521 Rel.35418n",
        hardwareId="VIGI-C340",
        scopes=GENERIC_SCOPES,
        topics=(MOTION_TOPIC, PEOPLE_TOPIC, VEHICLE_TOPIC, OBJECTS_INSIDE_TOPIC),
        description="TP-LINK VIGI 系列画像",
        serialPrefix="VIGI",
    )
)
_register(
    VendorProfile(
        key="hikvision",
        name="海康威视 Hikvision",
        manufacturer="Hikvision",
        model="DS-2CD2T47G2-L",
        firmware="V5.7.3 build 230828",
        hardwareId="DS-2CD2T47G2-L",
        scopes=GENERIC_SCOPES,
        topics=(MOTION_TOPIC, OBJECTS_INSIDE_TOPIC, LINE_CROSSED_TOPIC),
        description="海康威视画像（区域入侵 / 越界 / 移动）",
        serialPrefix="DS",
        pushFormat="hikvision",
    )
)
_register(
    VendorProfile(
        key="dahua",
        name="大华 Dahua",
        manufacturer="Dahua",
        model="IPC-HFW5442E-ZE",
        firmware="2.820.0000000.0.R",
        hardwareId="IPC-HFW5442E-ZE",
        scopes=GENERIC_SCOPES,
        topics=(MOTION_TOPIC, CROSSLINE_TOPIC, INTRUSION_TOPIC),
        description="大华画像（区域入侵 / 越界 / 移动）",
        serialPrefix="DH",
        pushFormat="dahua",
    )
)
_register(
    VendorProfile(
        key="uniview",
        name="宇视 UNV",
        manufacturer="UNV",
        model="IPC3614SR3-ADF28KM-G",
        firmware="1.0.0",
        hardwareId="IPC3614SR3",
        scopes=GENERIC_SCOPES,
        topics=(MOTION_TOPIC, OBJECTS_INSIDE_TOPIC, LINE_CROSSED_TOPIC),
        description="宇视画像",
        serialPrefix="UNV",
    )
)
_register(
    VendorProfile(
        key="unifi",
        name="Ubiquiti UniFi Protect",
        manufacturer="Ubiquiti Inc.",
        model="UVC G4 Bullet",
        firmware="4.71.0",
        hardwareId="UVC-G4-BULLET",
        scopes=GENERIC_SCOPES,
        topics=(MOTION_TOPIC, PEOPLE_TOPIC, VEHICLE_TOPIC, ANIMAL_TOPIC, PACKAGE_TOPIC),
        description="UniFi Protect 画像（兼容旧版工作流）",
        serialPrefix="UVC",
    )
)
_register(
    VendorProfile(
        key="generic",
        name="通用 ONVIF",
        manufacturer="ChengXing",
        model="CX-IPC-1000",
        firmware="1.0.0",
        hardwareId="CX-IPC",
        scopes=GENERIC_SCOPES,
        topics=(MOTION_TOPIC, OBJECTS_INSIDE_TOPIC, PEOPLE_TOPIC, VEHICLE_TOPIC, ANIMAL_TOPIC, PACKAGE_TOPIC, TAMPER_TOPIC),
        description="标准 ONVIF 事件，兼容大多数 NVR / VMS",
        serialPrefix="CX",
    )
)
_register(
    VendorProfile(
        key="custom",
        name="自定义身份",
        manufacturer="ChengXing",
        model="CX-IPC-CUSTOM",
        firmware="1.0.0",
        hardwareId="CX-IPC-CUSTOM",
        scopes=GENERIC_SCOPES,
        topics=(MOTION_TOPIC,),
        description="完全由摄像机配置决定身份与事件主题",
        serialPrefix="CX",
    )
)


def get_profile(key: str) -> VendorProfile:
    return PROFILES.get((key or "generic").lower(), PROFILES["generic"])


def resolve_profile(camera: CameraConfig) -> VendorProfile:
    """把摄像机配置叠加到厂商画像上。"""
    base = get_profile(camera.onvif.profile)
    manufacturer = camera.onvif.manufacturer or base.manufacturer
    model = camera.onvif.model or base.model
    firmware = camera.onvif.firmware or base.firmware
    hardware_id = camera.onvif.hardwareId or base.hardwareId
    scopes = tuple(camera.onvif.scopes) if camera.onvif.scopes else base.scopes
    return VendorProfile(
        key=base.key,
        name=base.name,
        manufacturer=manufacturer,
        model=model,
        firmware=firmware,
        hardwareId=hardware_id,
        scopes=scopes,
        topics=base.topics,
        description=base.description,
        serialPrefix=base.serialPrefix,
        discoveryTypes=base.discoveryTypes,
        pushFormat=base.pushFormat,
    )


def topic_map(camera: CameraConfig) -> dict[str, list[TopicDef]]:
    """返回 group → TopicDef 列表；配置里的 eventTopics 可覆盖默认值。

    ``onvif.eventTopics`` 结构：
    ``{"person": ["tns1:RuleEngine/PeopleDetector/PeopleDetected"], "motion": [...]}``
    支持数组元素为字符串或 ``{"topic": ..., "dataName": ...}``。
    """
    profile = resolve_profile(camera)
    result: dict[str, list[TopicDef]] = {}
    for group in ("motion", "person", "vehicle", "animal", "package", "face", "tamper"):
        topics = profile.topics_for(group)
        overrides = (camera.onvif.eventTopics or {}).get(group)
        if isinstance(overrides, list) and overrides:
            converted: list[TopicDef] = []
            for item in overrides:
                if isinstance(item, str):
                    converted.append(TopicDef(topic=item, dataName=_default_data_name(item), label=item, groups=(group,)))
                elif isinstance(item, dict) and item.get("topic"):
                    converted.append(
                        TopicDef(
                            topic=str(item["topic"]),
                            dataName=str(item.get("dataName") or _default_data_name(str(item["topic"]))),
                            label=str(item.get("label") or item["topic"]),
                            groups=(group,),
                        )
                    )
            if converted:
                topics = converted
        result[group] = topics
    return result


def _default_data_name(topic: str) -> str:
    tail = topic.rsplit("/", 1)[-1].lower()
    mapping = {
        "motion": "IsMotion",
        "crossed": "Crossed",
        "objectsinside": "IsInside",
        "inside": "State",
        "state": "State",
        "peopledetected": "State",
        "vehicledetected": "State",
        "tamper": "IsTamper",
    }
    return mapping.get(tail, "State")


def list_profiles() -> list[dict[str, Any]]:
    return [profile.to_dict() for profile in PROFILES.values()]
