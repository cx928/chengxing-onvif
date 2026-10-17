"""硬件画像：GPU、编码器、推理设备与加速建议。

探测结果带缓存（data/cache/hw_profile.json），避免每次启动都执行编码器实测。
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..logbus import info, warn
from ..paths import LAYOUT
from ..util import read_json, run_command
from .ffmpeg import FFmpegTool, list_encoders, list_hwaccels, resolve_ffmpeg

CACHE_FILE = LAYOUT["cache"] / "hw_profile.json"
CACHE_TTL = 3600.0

# 编码器候选：名称 → (编码, 厂商, 说明)
ENCODER_CANDIDATES: dict[str, tuple[str, str, str]] = {
    "h264_nvenc": ("h264", "nvidia", "NVIDIA NVENC"),
    "hevc_nvenc": ("hevc", "nvidia", "NVIDIA NVENC (H.265)"),
    "av1_nvenc": ("av1", "nvidia", "NVIDIA NVENC (AV1)"),
    "h264_qsv": ("h264", "intel", "Intel Quick Sync"),
    "hevc_qsv": ("hevc", "intel", "Intel Quick Sync (H.265)"),
    "av1_qsv": ("av1", "intel", "Intel Quick Sync (AV1)"),
    "h264_amf": ("h264", "amd", "AMD AMF"),
    "hevc_amf": ("hevc", "amd", "AMD AMF (H.265)"),
    "av1_amf": ("av1", "amd", "AMD AMF (AV1)"),
    "h264_vaapi": ("h264", "vaapi", "VAAPI (Linux)"),
    "hevc_vaapi": ("hevc", "vaapi", "VAAPI (H.265)"),
    "h264_videotoolbox": ("h264", "apple", "VideoToolbox"),
    "hevc_videotoolbox": ("hevc", "apple", "VideoToolbox (H.265)"),
    "h264_mf": ("h264", "windows", "Media Foundation"),
    "h264_d3d12va": ("h264", "windows", "D3D12VA"),
    "libx264": ("h264", "cpu", "软件编码 (libx264)"),
    "libx265": ("hevc", "cpu", "软件编码 (libx265)"),
}

# 按 GPU 厂商排序的编码器优先级
VENDOR_PRIORITY = {
    "nvidia": ["h264_nvenc", "hevc_nvenc"],
    "intel": ["h264_qsv", "hevc_qsv"],
    "amd": ["h264_amf", "hevc_amf"],
    "apple": ["h264_videotoolbox", "hevc_videotoolbox"],
    "vaapi": ["h264_vaapi", "hevc_vaapi"],
    "windows": ["h264_mf", "h264_d3d12va"],
    "cpu": ["libx264", "libx265"],
}


@dataclass
class GpuInfo:
    name: str
    vendor: str
    kind: str = "dGPU"          # iGPU | dGPU | virtual | unknown
    memoryMb: int = 0
    driver: str = ""
    index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EncoderInfo:
    name: str
    codec: str
    vendor: str
    description: str
    present: bool = False
    available: bool = False
    testError: str = ""


@dataclass
class InferenceBackend:
    key: str
    name: str
    installed: bool
    devices: list[str] = field(default_factory=list)
    version: str = ""
    note: str = ""


@dataclass
class HardwareProfile:
    generatedAt: float = 0.0
    os: str = ""
    osVersion: str = ""
    cpu: str = ""
    cpuCores: int = 0
    cpuThreads: int = 0
    ramMb: int = 0
    machine: str = ""
    ffmpegPath: str = ""
    ffmpegVersion: str = ""
    gpus: list[GpuInfo] = field(default_factory=list)
    encoders: list[EncoderInfo] = field(default_factory=list)
    hwaccels: list[str] = field(default_factory=list)
    inference: list[InferenceBackend] = field(default_factory=list)
    recommendedEncoder: str = "libx264"
    recommendedDecoder: str = ""
    recommendedInference: str = "cpu"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    def available_encoders(self, codec: str = "h264") -> list[str]:
        return [enc.name for enc in self.encoders if enc.codec == codec and enc.available]

    def encoder(self, name: str) -> EncoderInfo | None:
        for enc in self.encoders:
            if enc.name == name:
                return enc
        return None


_lock = threading.Lock()
_cache: HardwareProfile | None = None


# --------------------------------------------------------------------------------------
# GPU 探测
# --------------------------------------------------------------------------------------


class _DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("DeviceName", ctypes.c_wchar * 32),
        ("DeviceString", ctypes.c_wchar * 128),
        ("StateFlags", ctypes.c_ulong),
        ("DeviceID", ctypes.c_wchar * 128),
        ("DeviceKey", ctypes.c_wchar * 128),
    ]


_VIRTUAL_HINTS = (
    "oray", "idd", "virtual", "remote", "parsec", "basic display", "basic render",
    "mirage", "spacedesk", "usb display", "meta", "citrix", "vmware", "hyper-v",
)


def _classify_gpu(name: str, index: int) -> GpuInfo:
    lowered = name.lower()
    if any(hint in lowered for hint in _VIRTUAL_HINTS):
        return GpuInfo(name=name, vendor="virtual", kind="virtual", index=index)
    if "nvidia" in lowered or "geforce" in lowered or "quadro" in lowered or "rtx" in lowered or "tesla" in lowered:
        return GpuInfo(name=name, vendor="nvidia", kind="dGPU", index=index)
    if "amd" in lowered or "radeon" in lowered or "ati " in lowered:
        kind = "iGPU" if "vega" in lowered and "graphics" in lowered else "dGPU"
        return GpuInfo(name=name, vendor="amd", kind=kind, index=index)
    if "intel" in lowered or "arc" in lowered or "iris" in lowered or "uhd" in lowered or "hd graphics" in lowered:
        kind = "dGPU" if ("arc" in lowered and "graphics" not in lowered) else "iGPU"
        return GpuInfo(name=name, vendor="intel", kind=kind, index=index)
    if "apple" in lowered or "m1" in lowered or "m2" in lowered or "m3" in lowered or "m4" in lowered:
        return GpuInfo(name=name, vendor="apple", kind="iGPU", index=index)
    return GpuInfo(name=name, vendor="unknown", kind="unknown", index=index)


def _windows_gpus() -> list[GpuInfo]:
    gpus: list[GpuInfo] = []
    try:
        user32 = ctypes.windll.user32
        enum = user32.EnumDisplayDevicesW
        enum.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.POINTER(_DISPLAY_DEVICEW), ctypes.c_ulong]
        index = 0
        while index < 16:
            device = _DISPLAY_DEVICEW()
            device.cb = ctypes.sizeof(_DISPLAY_DEVICEW)
            if not enum(None, index, ctypes.byref(device), 0):
                break
            name = device.DeviceString.strip()
            flags = device.StateFlags
            # 只保留真实显示适配器（已附加到桌面或主适配器）
            if name and (flags & 0x1 or flags & 0x4):
                gpu = _classify_gpu(name, len(gpus))
                if gpu.vendor != "virtual":
                    gpus.append(gpu)
            index += 1
    except Exception as exc:  # pragma: no cover - 非 Windows
        warn(f"GPU 探测失败: {exc}", "hw")
    return gpus


def _nvidia_details(gpus: list[GpuInfo]) -> None:
    try:
        completed = run_command(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            timeout=8,
        )
    except (OSError, Exception):
        return
    if completed.returncode != 0:
        return
    for line in (completed.stdout or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        matched = next((g for g in gpus if g.vendor == "nvidia"), None)
        if matched:
            matched.memoryMb = int(float(parts[1])) if parts[1].replace(".", "").isdigit() else 0
            matched.driver = parts[2] if len(parts) > 2 else ""


def _linux_gpus() -> list[GpuInfo]:
    gpus: list[GpuInfo] = []
    try:
        completed = run_command(["lspci"], timeout=8)
        for line in (completed.stdout or "").splitlines():
            lowered = line.lower()
            if any(key in lowered for key in ("vga compatible", "3d controller", "display controller")):
                name = line.split(":", 2)[-1].strip()
                gpu = _classify_gpu(name, len(gpus))
                if gpu.vendor != "virtual":
                    gpus.append(gpu)
    except (OSError, Exception):
        pass
    return gpus


def _macos_gpus() -> list[GpuInfo]:
    try:
        completed = run_command(["system_profiler", "SPDisplaysDataType", "-json"], timeout=15)
        payload = json.loads(completed.stdout or "{}")
        result = []
        for item in payload.get("SPDisplaysDataType", []):
            name = item.get("sppci_model") or item.get("_name") or "GPU"
            gpu = _classify_gpu(name, len(result))
            result.append(gpu)
        return result
    except Exception:
        return []


def detect_gpus() -> list[GpuInfo]:
    if sys.platform == "win32":
        gpus = _windows_gpus()
    elif sys.platform == "darwin":
        gpus = _macos_gpus()
    else:
        gpus = _linux_gpus()
    if any(g.vendor == "nvidia" for g in gpus):
        _nvidia_details(gpus)
    return gpus


# --------------------------------------------------------------------------------------
# 编码器实测
# --------------------------------------------------------------------------------------


def _test_encoder(ffmpeg: FFmpegTool, encoder: str) -> tuple[bool, str]:
    """用 2 帧黑场实测编码器是否真的可用。"""
    args = [
        str(ffmpeg.path), "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=black:s=256x256:r=5",
        "-frames:v", "2", "-c:v", encoder, "-f", "null", "-",
    ]
    if encoder.endswith("_vaapi"):
        args = [
            str(ffmpeg.path), "-hide_banner", "-loglevel", "error",
            "-vaapi_device", "/dev/dri/renderD128",
            "-f", "lavfi", "-i", "color=black:s=256x256:r=5",
            "-vf", "format=nv12,hwupload", "-frames:v", "2", "-c:v", encoder, "-f", "null", "-",
        ]
    try:
        completed = run_command(args, timeout=25)
    except Exception as exc:
        return False, str(exc)[:200]
    if completed.returncode == 0:
        return True, ""
    stderr = (completed.stderr or "").strip().splitlines()
    return False, (stderr[-1] if stderr else f"exit {completed.returncode}")[:200]


def _probe_encoders(ffmpeg: FFmpegTool | None) -> list[EncoderInfo]:
    if not ffmpeg:
        return [
            EncoderInfo(name=name, codec=codec, vendor=vendor, description=desc)
            for name, (codec, vendor, desc) in ENCODER_CANDIDATES.items()
        ]
    present = list_encoders(ffmpeg.path)
    results: list[EncoderInfo] = []
    for name, (codec, vendor, desc) in ENCODER_CANDIDATES.items():
        info = EncoderInfo(name=name, codec=codec, vendor=vendor, description=desc, present=name in present)
        platform_note = _platform_unsupported(name)
        if platform_note:
            info.present = False
            info.testError = platform_note
        elif info.present:
            ok, error = _test_encoder(ffmpeg, name)
            info.available = ok
            info.testError = error
        results.append(info)
    return results


def _platform_unsupported(name: str) -> str:
    if name.endswith("_vaapi") and sys.platform != "linux":
        return "仅 Linux 可用"
    if name.endswith("_videotoolbox") and sys.platform != "darwin":
        return "仅 macOS 可用"
    if name.endswith("_mf") and sys.platform != "win32":
        return "仅 Windows 可用"
    return ""


# --------------------------------------------------------------------------------------
# 推理后端探测（可选依赖）
# --------------------------------------------------------------------------------------


def _probe_inference() -> list[InferenceBackend]:
    backends: list[InferenceBackend] = []

    try:
        import onnxruntime  # type: ignore

        providers = list(onnxruntime.get_available_providers())
        backends.append(
            InferenceBackend(
                key="onnxruntime",
                name="ONNX Runtime",
                installed=True,
                devices=providers,
                version=getattr(onnxruntime, "__version__", ""),
                note="支持 CPU / CUDA / DirectML / OpenVINO / TensorRT",
            )
        )
    except Exception:
        backends.append(
            InferenceBackend(
                key="onnxruntime",
                name="ONNX Runtime",
                installed=False,
                note="安装 onnxruntime / onnxruntime-gpu / onnxruntime-directml 后可用",
            )
        )

    try:
        import openvino as ov  # type: ignore

        devices: list[str] = []
        try:
            core = ov.Core()
            devices = [str(d) for d in core.available_devices]
        except Exception:
            pass
        backends.append(
            InferenceBackend(
                key="openvino",
                name="Intel OpenVINO",
                installed=True,
                devices=devices,
                version=getattr(ov, "__version__", ""),
                note="Intel 核显 / 独显 / NPU 最佳选择",
            )
        )
    except Exception:
        backends.append(
            InferenceBackend(
                key="openvino",
                name="Intel OpenVINO",
                installed=False,
                note="pip install openvino 后可用",
            )
        )

    try:
        import torch  # type: ignore

        devices = ["cpu"]
        note = ""
        if torch.cuda.is_available():
            devices.append("cuda:0")
            note = f"CUDA {torch.version.cuda}"
        try:
            import torch_directml  # type: ignore

            devices.append("dml")
            note = (note + " · DirectML").strip(" ·")
        except Exception:
            pass
        if hasattr(torch, "xpu") and getattr(torch, "xpu", None) and torch.xpu.is_available():  # type: ignore
            devices.append("xpu")
            note = (note + " · Intel XPU").strip(" ·")
        backends.append(
            InferenceBackend(
                key="ultralytics",
                name="Ultralytics (PyTorch)",
                installed=True,
                devices=devices,
                version=getattr(torch, "__version__", ""),
                note=note or "CPU 推理",
            )
        )
    except Exception:
        backends.append(
            InferenceBackend(
                key="ultralytics",
                name="Ultralytics (PyTorch)",
                installed=False,
                note="pip install ultralytics 后可用（支持 .pt 模型）",
            )
        )
    return backends


# --------------------------------------------------------------------------------------
# 组合画像
# --------------------------------------------------------------------------------------


def _pick_encoder(encoders: list[EncoderInfo], gpus: list[GpuInfo], preferred: str = "auto") -> str:
    available = {e.name for e in encoders if e.available}
    if preferred and preferred != "auto" and preferred in available:
        return preferred
    vendor_order: list[str] = []
    for gpu in gpus:
        if gpu.vendor in VENDOR_PRIORITY and gpu.vendor not in vendor_order:
            vendor_order.append(gpu.vendor)
    # Intel 核显常常也可用 QSV；若同时有 NVIDIA，优先独显
    for vendor in ("nvidia", "intel", "amd", "apple"):
        if vendor in vendor_order:
            for candidate in VENDOR_PRIORITY[vendor]:
                if candidate in available:
                    return candidate
    for candidate in ("h264_qsv", "h264_nvenc", "h264_amf", "h264_vaapi", "h264_videotoolbox", "h264_mf", "libx264"):
        if candidate in available:
            return candidate
    return "libx264"


def _pick_decoder(hwaccels: list[str], gpus: list[GpuInfo]) -> str:
    vendors = {g.vendor for g in gpus}
    if "nvidia" in vendors and "cuda" in hwaccels:
        return "cuda"
    if "intel" in vendors and "qsv" in hwaccels:
        return "qsv"
    if "amd" in vendors and "d3d11va" in hwaccels:
        return "d3d11va"
    if "vaapi" in hwaccels:
        return "vaapi"
    if "d3d11va" in hwaccels:
        return "d3d11va"
    return ""


def _pick_inference(backends: list[InferenceBackend], gpus: list[GpuInfo]) -> str:
    by_key = {b.key: b for b in backends}
    vendors = {g.vendor for g in gpus}
    onnx = by_key.get("onnxruntime")
    if onnx and onnx.installed:
        providers = set(onnx.devices)
        if "nvidia" in vendors and "CUDAExecutionProvider" in providers:
            return "onnxruntime:cuda"
        if "DmlExecutionProvider" in providers:
            return "onnxruntime:dml"
        if "OpenVINOExecutionProvider" in providers:
            return "onnxruntime:openvino"
        if "TensorrtExecutionProvider" in providers:
            return "onnxruntime:tensorrt"
    ov = by_key.get("openvino")
    if ov and ov.installed and any(d.startswith("GPU") for d in ov.devices):
        return "openvino:gpu"
    ultra = by_key.get("ultralytics")
    if ultra and ultra.installed:
        if "cuda:0" in ultra.devices:
            return "ultralytics:cuda"
        if "dml" in ultra.devices:
            return "ultralytics:dml"
    if ov and ov.installed:
        return "openvino:cpu"
    if onnx and onnx.installed:
        return "onnxruntime:cpu"
    return "ultralytics:cpu"


def _cpu_info() -> tuple[str, int, int, int]:
    name = ""
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            name = " ".join(str(value).split())
        except Exception:
            name = ""
    if not name:
        name = platform.processor() or platform.machine()
    cores = threads = 0
    ram_mb = 0
    try:
        import psutil  # type: ignore

        cores = psutil.cpu_count(logical=False) or 0
        threads = psutil.cpu_count(logical=True) or 0
        ram_mb = int(psutil.virtual_memory().total / (1024 * 1024))
    except Exception:
        cores = os.cpu_count() or 0
        threads = cores
    return name, cores, threads, ram_mb


def build_profile(settings: dict[str, Any] | None = None) -> HardwareProfile:
    settings = settings or {}
    ffmpeg = resolve_ffmpeg(settings.get("ffmpegPath", ""))
    gpus = detect_gpus()
    cpu_name, cores, threads, ram_mb = _cpu_info()
    encoders = _probe_encoders(ffmpeg)
    hwaccels = sorted(list_hwaccels(ffmpeg.path)) if ffmpeg else []
    backends = _probe_inference()

    profile = HardwareProfile(
        generatedAt=time.time(),
        os=sys.platform,
        osVersion=platform.version(),
        cpu=cpu_name,
        cpuCores=cores,
        cpuThreads=threads,
        ramMb=ram_mb,
        machine=platform.machine(),
        ffmpegPath=str(ffmpeg.path) if ffmpeg else "",
        ffmpegVersion=ffmpeg.version if ffmpeg else "",
        gpus=gpus,
        encoders=encoders,
        hwaccels=hwaccels,
        inference=backends,
    )
    preferred_encoder = settings.get("encoder", "auto") or "auto"
    profile.recommendedEncoder = _pick_encoder(encoders, gpus, preferred_encoder)
    profile.recommendedDecoder = _pick_decoder(hwaccels, gpus)
    profile.recommendedInference = _pick_inference(backends, gpus)

    if not ffmpeg:
        profile.notes.append("未找到 FFmpeg，请运行安装脚本或设置 ffmpegPath")
    if not any(e.available for e in encoders if e.vendor != "cpu"):
        profile.notes.append("没有可用的硬件编码器，将使用 libx264 软件编码")
    if not any(g.vendor != "virtual" for g in gpus):
        profile.notes.append("未检测到独立/集成显卡，AI 推理将使用 CPU")
    for gpu in gpus:
        if gpu.vendor == "nvidia" and not any(e.available for e in encoders if e.vendor == "nvidia"):
            profile.notes.append("检测到 NVIDIA 显卡，但 NVENC 不可用（请更新驱动或使用含 NVENC 的 FFmpeg）")
    return profile


def get_profile(settings: dict[str, Any] | None = None, *, refresh: bool = False) -> HardwareProfile:
    global _cache
    with _lock:
        if _cache and not refresh:
            return _cache
        if not refresh:
            cached = read_json(CACHE_FILE)
            if isinstance(cached, dict) and time.time() - float(cached.get("generatedAt") or 0) < CACHE_TTL:
                try:
                    profile = _profile_from_dict(cached)
                    _cache = profile
                    return profile
                except Exception:
                    pass
        profile = build_profile(settings)
        _cache = profile
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        info(f"硬件画像：{len(profile.gpus)} 个 GPU · 推荐编码器 {profile.recommendedEncoder} · 推荐推理 {profile.recommendedInference}", "hw")
        return profile


def refresh_profile(settings: dict[str, Any] | None = None) -> HardwareProfile:
    global _cache
    with _lock:
        _cache = None
    try:
        CACHE_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    return get_profile(settings, refresh=True)


def _profile_from_dict(data: dict[str, Any]) -> HardwareProfile:
    profile = HardwareProfile(**{k: v for k, v in data.items() if k in HardwareProfile.__dataclass_fields__})
    profile.gpus = [GpuInfo(**g) for g in data.get("gpus", [])]
    profile.encoders = [EncoderInfo(**e) for e in data.get("encoders", [])]
    profile.inference = [InferenceBackend(**b) for b in data.get("inference", [])]
    return profile
