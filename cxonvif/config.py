"""配置模型与持久化 / Configuration model and store.

设计要点：
* 字段使用 camelCase，可直接与前端 JSON 互转；
* 所有加载路径都做“缺省填充 + 类型纠正”，保证旧配置可平滑升级；
* 写入采用原子替换，并保留 .bak 备份。
"""

from __future__ import annotations

import copy
import threading
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, get_type_hints

from . import security
from .paths import CONFIG_FILE
from .util import atomic_write_json, new_uuid, read_json, slugify
from .version import CONFIG_SCHEMA_VERSION

# --------------------------------------------------------------------------------------
# 默认值
# --------------------------------------------------------------------------------------

DEFAULT_SETTINGS: dict[str, Any] = {
    "webPort": 5552,
    "bind": "0.0.0.0",
    "rtspPort": 8554,
    "onvifPortStart": 8001,
    "mediamtxApiPort": 9997,
    "hlsPort": 8888,
    "webrtcPort": 8889,
    "rtspUsername": "cx",
    "rtspPassword": "",
    "rtspAuthEnabled": False,
    "openBrowser": False,
    "silent": False,
    "theme": "dark",
    "language": "zh-CN",
    "autoStartOnBoot": True,
    "startCamerasOnBoot": True,
    "checkUpdates": True,
    "logLevel": "INFO",
    "ffmpegPath": "",
    "mediamtxPath": "",
    "defaultModel": "yolo11n",
    "defaultBackend": "auto",
    "defaultDevice": "auto",
    "inferenceDevice": "auto",
    "decodeMode": "auto",
    "encoder": "auto",
    "overlayBitrate": 2000,
    "webTitle": "程星 ONVIF",
}

DEFAULT_AUTH: dict[str, Any] = {
    "username": security.DEFAULT_USERNAME,
    "passwordHash": "",
    "passwordSalt": "",
    "mustChangePassword": True,
    "sessionTtl": 86400,
    "requireLogin": True,
}

# COCO 类别 → 通用目标组
DEFAULT_CLASS_MAP: dict[str, str] = {
    "person": "person",
    "bicycle": "vehicle",
    "car": "vehicle",
    "motorcycle": "vehicle",
    "airplane": "vehicle",
    "bus": "vehicle",
    "train": "vehicle",
    "truck": "vehicle",
    "boat": "vehicle",
    "bird": "animal",
    "cat": "animal",
    "dog": "animal",
    "horse": "animal",
    "sheep": "animal",
    "cow": "animal",
    "elephant": "animal",
    "bear": "animal",
    "zebra": "animal",
    "giraffe": "animal",
    "backpack": "package",
    "umbrella": "package",
    "handbag": "package",
    "tie": "package",
    "suitcase": "package",
}


def _dict_factory(data: list[tuple[str, Any]]) -> dict[str, Any]:
    return {key: value for key, value in data}


# --------------------------------------------------------------------------------------
# 数据模型
# --------------------------------------------------------------------------------------


@dataclass
class SourceConfig:
    mainUrl: str = ""
    subUrl: str = ""
    mainWidth: int = 1920
    mainHeight: int = 1080
    mainFramerate: int = 25
    subWidth: int = 640
    subHeight: int = 480
    subFramerate: int = 15
    transport: str = "tcp"
    enabled: bool = True

    def url(self, stream: str = "main") -> str:
        if stream == "sub" and self.subUrl:
            return self.subUrl
        return self.mainUrl or self.subUrl


@dataclass
class StreamConfig:
    transcodeMain: bool = False
    transcodeSub: bool = False
    enableAudio: bool = False
    enableSubstream: bool = True
    useMainAsSubstream: bool = False
    record: bool = False


@dataclass
class Zone:
    id: str = ""
    name: str = ""
    type: str = "include"  # include | exclude | line
    points: list[list[float]] = field(default_factory=list)
    enabled: bool = True
    targets: list[str] = field(default_factory=list)  # 空 = 全部

    def normalized_points(self) -> list[tuple[float, float]]:
        result = []
        for point in self.points or []:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                result.append((float(point[0]), float(point[1])))
        return result


@dataclass
class DetectConfig:
    enabled: bool = True
    model: str = "yolo11n"
    backend: str = "auto"
    device: str = "auto"
    confidence: float = 0.45
    iou: float = 0.45
    fps: float = 5.0
    frameWidth: int = 960
    targets: list[str] = field(default_factory=lambda: ["person", "vehicle"])
    motionGate: bool = True
    motionSensitivity: int = 55
    cooldown: float = 5.0
    minBox: float = 0.0015
    tracker: bool = True
    saveSnapshot: bool = True
    maxDetections: int = 30
    classMap: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CLASS_MAP))
    zones: list[Zone] = field(default_factory=list)
    extraArgs: dict[str, Any] = field(default_factory=dict)


@dataclass
class OverlayConfig:
    enabled: bool = True
    width: int = 1280
    height: int = 720
    fps: float = 10.0
    encoder: str = "auto"
    bitrate: int = 2000
    showBoxes: bool = True
    showLabels: bool = True
    showConfidence: bool = True
    showZones: bool = False
    boxThickness: int = 2
    boxColor: str = "#00D68F"       # 主色（BGR 由渲染器转换）
    labelBgColor: str = "#0B1220"
    fontScale: float = 0.55
    drawTimestamp: bool = False
    extraText: str = ""
    paths: str = ""  # 自定义 MediaMTX 路径名，空 = <pathName>_overlay


@dataclass
class OnvifConfig:
    enabled: bool = True
    port: int = 0
    username: str = "admin"
    password: str = ""
    profile: str = "mercury"       # generic | mercury | tplink_vigi | hikvision | dahua | uniview | unifi | custom
    manufacturer: str = ""         # 空 = 使用 profile 默认值
    model: str = ""
    firmware: str = ""
    hardwareId: str = ""
    serial: str = ""
    scopes: list[str] = field(default_factory=list)
    eventTopics: dict[str, Any] = field(default_factory=dict)
    sendMotion: bool = True
    sendSmart: bool = True
    sendHeartbeat: bool = True
    wsDiscovery: bool = True
    authMode: str = "digest"       # digest | text | none
    snapshotEnabled: bool = True


@dataclass
class MercuryConfig:
    enabled: bool = True
    pushEnabled: bool = False
    pushUrl: str = ""
    pushFormat: str = "json"       # json | dahua | hikvision | tplink | form
    pushToken: str = ""
    pushTimeout: float = 5.0
    pushRetries: int = 2
    includeSnapshot: bool = True
    snapshotQuality: int = 70
    heartbeatInterval: float = 30.0
    eventCooldown: float = 2.0
    extraHeaders: dict[str, str] = field(default_factory=dict)


@dataclass
class CameraConfig:
    id: int = 0
    uuid: str = field(default_factory=new_uuid)
    name: str = ""
    enabled: bool = True
    autoStart: bool = True
    pathName: str = ""
    notes: str = ""
    createdAt: str = ""
    updatedAt: str = ""
    source: SourceConfig = field(default_factory=SourceConfig)
    stream: StreamConfig = field(default_factory=StreamConfig)
    onvif: OnvifConfig = field(default_factory=OnvifConfig)
    detect: DetectConfig = field(default_factory=DetectConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    mercury: MercuryConfig = field(default_factory=MercuryConfig)

    # ---- 便捷属性 ----
    @property
    def mainUrl(self) -> str:
        return self.source.url("main")

    @property
    def subUrl(self) -> str:
        return self.source.url("sub")

    @property
    def basePath(self) -> str:
        return self.pathName or f"cam{self.id}"

    @property
    def overlayPath(self) -> str:
        return self.overlay.paths or f"{self.basePath}_overlay"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self, dict_factory=_dict_factory)

    def public_dict(self) -> dict[str, Any]:
        """对外输出：隐藏敏感字段。"""
        data = self.to_dict()
        data["source"]["mainUrl"] = mask_url_password(data["source"].get("mainUrl", ""))
        data["source"]["subUrl"] = mask_url_password(data["source"].get("subUrl", ""))
        data["onvif"]["passwordSet"] = bool(data["onvif"].get("password"))
        data["onvif"]["password"] = ""
        data["mercury"]["pushToken"] = ""
        return data


@dataclass
class AuthSettings:
    username: str = security.DEFAULT_USERNAME
    passwordHash: str = ""
    passwordSalt: str = ""
    mustChangePassword: bool = True
    sessionTtl: int = 86400
    requireLogin: bool = True


@dataclass
class AppConfig:
    schemaVersion: int = CONFIG_SCHEMA_VERSION
    brand: str = "程星 ONVIF"
    settings: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_SETTINGS))
    auth: AuthSettings = field(default_factory=AuthSettings)
    cameras: list[CameraConfig] = field(default_factory=list)
    nextCameraId: int = 1


# --------------------------------------------------------------------------------------
# 序列化辅助
# --------------------------------------------------------------------------------------


def mask_url_password(url: str) -> str:
    if not url:
        return url
    try:
        scheme, rest = url.split("://", 1)
    except ValueError:
        return url
    if "@" not in rest:
        return url
    creds, host = rest.rsplit("@", 1)
    if ":" in creds:
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:****@{host}"
    return url


def _coerce(value: Any, annotation: Any) -> Any:
    """尽力把 JSON 值转换为注解类型。"""
    if value is None:
        return None
    origin = getattr(annotation, "__origin__", None)
    if annotation is bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if annotation is int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
    if annotation is float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    if annotation is str:
        return value if isinstance(value, str) else str(value)
    if origin is list and isinstance(value, list):
        return value
    if origin is dict and isinstance(value, dict):
        return value
    return value


def _build_dataclass(cls: type, data: Any):
    """递归构建 dataclass，容忍缺字段/多余字段。"""
    if not is_dataclass(cls):
        return data
    if not isinstance(data, dict):
        return cls()
    try:
        hints = get_type_hints(cls)
    except Exception:  # pragma: no cover - 类型注解损坏时退化为原始值
        hints = {}
    kwargs: dict[str, Any] = {}
    for item in fields(cls):
        if item.name in data:
            kwargs[item.name] = _build_value(hints.get(item.name, item.type), data[item.name])
    return cls(**kwargs)


def _build_value(annotation: Any, value: Any) -> Any:
    # 解析泛型简写（本项目仅用到 list[Zone]、dict[str, Any]）
    if isinstance(annotation, str):
        return value
    origin = getattr(annotation, "__origin__", None)
    if origin is list:
        args = getattr(annotation, "__args__", ())
        if args and hasattr(args[0], "__dataclass_fields__"):
            return [_build_dataclass(args[0], v) for v in value] if isinstance(value, list) else []
        return value if isinstance(value, list) else []
    if origin is dict:
        return value if isinstance(value, dict) else {}
    if hasattr(annotation, "__dataclass_fields__"):
        return _build_dataclass(annotation, value)
    return _coerce(value, annotation)


def _dataclass_to_dict(obj: Any) -> Any:
    if is_dataclass(obj):
        return {item.name: _dataclass_to_dict(getattr(obj, item.name)) for item in fields(obj)}
    if isinstance(obj, list):
        return [_dataclass_to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    return obj


# --------------------------------------------------------------------------------------
# 配置存储
# --------------------------------------------------------------------------------------


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or CONFIG_FILE)
        self._lock = threading.RLock()
        self.config = AppConfig()
        self.load()

    # ---- 读写 ----
    def load(self) -> AppConfig:
        with self._lock:
            raw = read_json(self.path, default=None)
            if not isinstance(raw, dict):
                self.config = AppConfig()
                self._ensure_auth()
                self.save()
                return self.config

            config = AppConfig()
            config.schemaVersion = int(raw.get("schemaVersion", CONFIG_SCHEMA_VERSION) or 1)
            settings = copy.deepcopy(DEFAULT_SETTINGS)
            settings.update(raw.get("settings") or {})
            config.settings = settings
            config.brand = raw.get("brand") or "程星 ONVIF"
            auth_data = dict(DEFAULT_AUTH)
            auth_data.update(raw.get("auth") or {})
            config.auth = _build_dataclass(AuthSettings, auth_data)
            config.cameras = [c for c in (_build_dataclass(CameraConfig, item) for item in raw.get("cameras") or []) if c.name]
            for camera in config.cameras:
                self._fix_camera(camera)
            config.nextCameraId = max(
                int(raw.get("nextCameraId") or 1),
                max((c.id for c in config.cameras), default=0) + 1,
            )
            self.config = config
            self._ensure_auth()
            self.save()
            return self.config

    def save(self) -> None:
        with self._lock:
            payload = _dataclass_to_dict(self.config)
            atomic_write_json(self.path, payload)

    def _ensure_auth(self) -> None:
        auth = self.config.auth
        if not auth.passwordHash or not auth.passwordSalt:
            password_hash, salt = security.hash_password(security.DEFAULT_PASSWORD)
            auth.passwordHash = password_hash
            auth.passwordSalt = salt
            auth.mustChangePassword = True
        settings = self.config.settings
        if not settings.get("rtspPassword"):
            settings["rtspPassword"] = security.random_token(9)

    # ---- 相机 CRUD ----
    @property
    def cameras(self) -> list[CameraConfig]:
        return self.config.cameras

    def get_camera(self, camera_id: int) -> CameraConfig | None:
        for camera in self.config.cameras:
            if camera.id == int(camera_id):
                return camera
        return None

    def add_camera(self, camera: CameraConfig) -> CameraConfig:
        with self._lock:
            camera.id = self.config.nextCameraId
            self.config.nextCameraId += 1
            camera.uuid = camera.uuid or new_uuid()
            self._fix_camera(camera)
            self.config.cameras.append(camera)
            self.save()
            return camera

    def update_camera(self, camera_id: int, data: dict[str, Any]) -> CameraConfig | None:
        with self._lock:
            camera = self.get_camera(camera_id)
            if not camera:
                return None
            merged = _dataclass_to_dict(camera)
            _deep_merge(merged, data)
            updated = _build_dataclass(CameraConfig, merged)
            updated.id = camera.id
            updated.uuid = camera.uuid or new_uuid()
            self._fix_camera(updated)
            index = self.config.cameras.index(camera)
            self.config.cameras[index] = updated
            self.save()
            return updated

    def delete_camera(self, camera_id: int) -> bool:
        with self._lock:
            camera = self.get_camera(camera_id)
            if not camera:
                return False
            self.config.cameras.remove(camera)
            self.save()
            return True

    def _fix_camera(self, camera: CameraConfig) -> None:
        import re

        camera.name = (camera.name or "未命名摄像机").strip()
        path = (camera.pathName or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", path):
            slug = slugify(camera.name, "")
            path = f"cam{camera.id}_{slug}" if slug else f"cam{camera.id}"
        camera.pathName = path.rstrip("_")
        if camera.onvif.port <= 0:
            camera.onvif.port = self.allocate_onvif_port(exclude_id=camera.id)
        if camera.onvif.username and not camera.onvif.password:
            camera.onvif.password = security.random_token(6).replace("-", "x").replace("_", "y")[:8]
        if not camera.mercury.pushUrl:
            camera.mercury.pushEnabled = False
        camera.detect.confidence = float(min(0.99, max(0.05, camera.detect.confidence)))
        camera.detect.fps = float(min(30, max(0.2, camera.detect.fps)))
        camera.overlay.width = max(2, int(camera.overlay.width) // 2 * 2)
        camera.overlay.height = max(2, int(camera.overlay.height) // 2 * 2)
        camera.overlay.fps = float(min(30, max(1, camera.overlay.fps)))

    def allocate_onvif_port(self, exclude_id: int | None = None) -> int:
        used = {c.onvif.port for c in self.config.cameras if c.id != exclude_id and c.onvif.port}
        settings = self.config.settings
        port = int(settings.get("onvifPortStart") or 8001)
        while port in used:
            port += 1
        return port

    # ---- 设置 ----
    def update_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            # 认证相关字段单独处理，避免被 DEFAULT_SETTINGS 过滤掉
            if "requireLogin" in data:
                self.config.auth.requireLogin = bool(data["requireLogin"])
            if "mustChangePassword" in data:
                self.config.auth.mustChangePassword = bool(data["mustChangePassword"])
            settings = copy.deepcopy(DEFAULT_SETTINGS)
            settings.update(self.config.settings)
            settings.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
            self.config.settings = settings
            self.save()
            return settings

    def set_password(self, new_password: str, *, must_change: bool = False) -> None:
        with self._lock:
            password_hash, salt = security.hash_password(new_password)
            self.config.auth.passwordHash = password_hash
            self.config.auth.passwordSalt = salt
            self.config.auth.mustChangePassword = must_change
            self.save()

    def verify_password(self, password: str) -> bool:
        auth = self.config.auth
        return security.verify_password(password, auth.passwordHash, auth.passwordSalt)

    # ---- 迁移 ----
    def import_legacy_config(self, path: Path) -> tuple[int, list[str]]:
        """导入旧版 Tonys-onvif 配置。返回 (导入数量, 警告)。"""
        raw = read_json(path)
        warnings: list[str] = []
        if not isinstance(raw, dict):
            return 0, ["配置文件无法解析"]

        legacy_settings = raw.get("settings") or {}
        settings_patch = {
            "webPort": legacy_settings.get("webPort", 5552),
            "rtspPort": legacy_settings.get("rtspPort", 8554),
            "rtspUsername": legacy_settings.get("globalUsername") or "cx",
            "rtspPassword": legacy_settings.get("globalPassword") or "",
            "openBrowser": bool(legacy_settings.get("openBrowser", False)),
            "logLevel": "DEBUG" if legacy_settings.get("debugMode") else "INFO",
        }
        self.update_settings({k: v for k, v in settings_patch.items() if v not in (None, "")})

        imported = 0
        for item in raw.get("cameras") or []:
            if not isinstance(item, dict) or not item.get("mainStreamUrl"):
                warnings.append(f"跳过无效摄像机: {item.get('name', '?')}")
                continue
            camera = CameraConfig(
                id=0,
                uuid=item.get("uuid") or new_uuid(),
                name=item.get("name") or "导入摄像机",
                source=SourceConfig(
                    mainUrl=item.get("mainStreamUrl", ""),
                    subUrl=item.get("subStreamUrl", "") or "",
                    mainWidth=int(item.get("mainWidth") or 1920),
                    mainHeight=int(item.get("mainHeight") or 1080),
                    mainFramerate=int(item.get("mainFramerate") or 25),
                    subWidth=int(item.get("subWidth") or 640),
                    subHeight=int(item.get("subHeight") or 480),
                    subFramerate=int(item.get("subFramerate") or 15),
                ),
                onvif=OnvifConfig(
                    port=0,
                    username=item.get("onvifUsername") or "admin",
                    password=item.get("onvifPassword") or "",
                    profile="mercury",
                ),
                detect=DetectConfig(
                    model=(item.get("aiModel") or "yolo11n").replace(".pt", ""),
                    targets=[t for t in (item.get("aiTargets") or ["person", "vehicle"]) if isinstance(t, str)],
                    confidence=float(item.get("aiConfidenceThreshold") or 45) / 100.0,
                    motionSensitivity=int(item.get("aiMotionSensitivity") or 55),
                    enabled=bool(item.get("aiDetectionEnabled", True)),
                ),
                autoStart=bool(item.get("autoStart", True)),
            )
            self.add_camera(camera)
            imported += 1
        return imported, warnings


def _deep_merge(base: dict, patch: dict) -> dict:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def camera_from_payload(payload: dict[str, Any]) -> CameraConfig:
    """从 API/JSON 载荷构建摄像机配置。"""
    return _build_dataclass(CameraConfig, payload)
