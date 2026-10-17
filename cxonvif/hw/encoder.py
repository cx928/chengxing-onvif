"""编码器参数生成 / Encoder command-line arguments."""

from __future__ import annotations

from typing import Any

QUALITY_PRESETS = {
    "speed": {"libx264": "ultrafast", "libx265": "ultrafast", "qsv": "veryfast", "nvenc": "p1", "amf": "speed"},
    "balanced": {"libx264": "veryfast", "libx265": "veryfast", "qsv": "veryfast", "nvenc": "p4", "amf": "balanced"},
    "quality": {"libx264": "medium", "libx265": "medium", "qsv": "medium", "nvenc": "p6", "amf": "quality"},
}


def _preset(encoder: str, quality: str) -> str:
    family = "libx264"
    if encoder.startswith("libx265") or encoder.startswith("hevc"):
        family = "libx265"
    if "qsv" in encoder:
        family = "qsv"
    elif "nvenc" in encoder:
        family = "nvenc"
    elif "amf" in encoder:
        family = "amf"
    return QUALITY_PRESETS.get(quality, QUALITY_PRESETS["balanced"]).get(family, "veryfast")


def encoder_args(
    encoder: str,
    *,
    bitrate_kbps: int = 2000,
    fps: float = 10.0,
    codec: str = "h264",
    quality: str = "balanced",
    keyframe_seconds: float = 2.0,
    extra: dict[str, Any] | None = None,
) -> list[str]:
    """返回完整的编码参数（含 -c:v）。"""
    bitrate = max(128, int(bitrate_kbps))
    gop = max(1, int(round(fps * keyframe_seconds)))
    maxrate = int(bitrate * 1.2)
    bufsize = int(bitrate * 2)

    common = [
        "-c:v", encoder,
        "-b:v", f"{bitrate}k",
        "-maxrate", f"{maxrate}k",
        "-bufsize", f"{bufsize}k",
        "-g", str(gop),
        "-keyint_min", str(max(1, gop // 2)),
    ]

    if encoder.startswith("libx266") or encoder.startswith("libx264") or encoder.startswith("libx265"):
        common += ["-preset", _preset(encoder, quality), "-tune", "zerolatency", "-pix_fmt", "yuv420p"]
        if codec == "hevc":
            common += ["-tag:v", "hvc1"]
    elif encoder.endswith("_qsv"):
        common += ["-preset", _preset(encoder, quality), "-pix_fmt", "nv12", "-look_ahead", "0"]
    elif encoder.endswith("_nvenc"):
        common += [
            "-preset", _preset(encoder, quality),
            "-tune", "ll",
            "-rc", "cbr",
            "-zerolatency", "1",
            "-pix_fmt", "yuv420p",
        ]
        if codec == "hevc":
            common += ["-tag:v", "hvc1"]
    elif encoder.endswith("_amf"):
        common += ["-quality", _preset(encoder, quality), "-rc", "cbr", "-pix_fmt", "yuv420p"]
    elif encoder.endswith("_vaapi"):
        common += ["-pix_fmt", "nv12"]
    elif encoder.endswith("_videotoolbox"):
        common += ["-pix_fmt", "yuv420p", "-realtime", "1", "-allow_sw", "1"]
        if codec == "hevc":
            common += ["-tag:v", "hvc1"]
    elif encoder.endswith("_mf"):
        common += ["-pix_fmt", "nv12"]

    common += _extra_args(extra or {})
    return common


def _extra_args(extra: dict[str, Any]) -> list[str]:
    args: list[str] = []
    for key, value in extra.items():
        if value is None or value is False:
            continue
        flag = key if key.startswith("-") else f"-{key}"
        if value is True:
            args.append(flag)
        else:
            args.extend([flag, str(value)])
    return args


def decoder_args(mode: str = "auto", *, vendor: str = "") -> list[str]:
    """解码加速参数。mode: auto|software|cuda|qsv|d3d11va|dxva2|vaapi|videotoolbox。"""
    if mode in ("", "software", "none"):
        return []
    if mode == "auto":
        mode = {"nvidia": "cuda", "intel": "qsv", "amd": "d3d11va", "apple": "videotoolbox"}.get(vendor, "")
    if not mode:
        return []
    return ["-hwaccel", mode]


def needs_hwupload(encoder: str) -> bool:
    return encoder.endswith("_vaapi")
