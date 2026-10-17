"""模型注册表 / Model zoo.

支持四类模型来源：
* ultralytics 权重（.pt）：YOLOv5/v8/v10/v11/v12/v26、RT-DETR、YOLO-World；
* ONNX（.onnx）：任意 YOLO 系或自定义检测模型，走 ONNX Runtime（CPU/CUDA/DirectML/OpenVINO/TensorRT）；
* OpenVINO IR（.xml/.bin）：Intel 核显/独显/NPU 原生加速；
* 自定义路径：用户自备模型。
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..logbus import info, warn
from ..paths import MODELS_DIR, PROJECT_ROOT

ASSET_BASE = "https://github.com/ultralytics/assets/releases/download/v8.4.0"

COCO_LABELS: tuple[str, ...] = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
    "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
)
PERSON_LABELS: tuple[str, ...] = ("person",)


@dataclass(frozen=True)
class ModelSpec:
    key: str
    name: str
    family: str                 # pt | onnx | openvino | custom
    task: str = "detect"        # detect | segment | pose | obb
    filename: str = ""
    url: str = ""
    sizeMb: float = 0.0
    labels: tuple[str, ...] = COCO_LABELS
    description: str = ""
    inputSize: int = 640
    outputFormat: str = "auto"  # auto | yolo_v8 | yolo_v5 | end2end | rtdetr
    license: str = "AGPL-3.0 (Ultralytics)"
    tags: tuple[str, ...] = ()

    def to_dict(self, *, installed: bool = False, path: str = "") -> dict[str, Any]:
        data = asdict(self)
        data["labels"] = len(self.labels)
        data["labelNames"] = list(self.labels[:12])
        data["installed"] = installed
        data["path"] = path
        return data


MODELS: dict[str, ModelSpec] = {}


def _register(spec: ModelSpec) -> None:
    MODELS[spec.key] = spec


def _pt(key: str, name: str, filename: str, size: float, desc: str, **kwargs: Any) -> None:
    _register(
        ModelSpec(
            key=key,
            name=name,
            family="pt",
            filename=filename,
            url=f"{ASSET_BASE}/{filename}",
            sizeMb=size,
            description=desc,
            **kwargs,
        )
    )


# ---- YOLO26：最新一代，端到端无 NMS，速度/精度均衡 ----
_pt("yolo26n", "YOLO26n", "yolo26n.pt", 5.3, "最新一代轻量模型，适合 4 路以上并发", tags=("推荐", "轻量"))
_pt("yolo26s", "YOLO26s", "yolo26s.pt", 20.0, "新一代小模型，精度更高", tags=("推荐",))
_pt("yolo26m", "YOLO26m", "yolo26m.pt", 42.0, "新一代中模型，适合人车检测", tags=())
# ---- YOLO11 ----
_pt("yolo11n", "YOLO11n", "yolo11n.pt", 5.4, "成熟稳定的轻量模型（默认）", tags=("推荐", "轻量"))
_pt("yolo11s", "YOLO11s", "yolo11s.pt", 18.4, "小模型，精度与速度均衡")
_pt("yolo11m", "YOLO11m", "yolo11m.pt", 38.8, "中模型，适合复杂场景")
# ---- YOLOv8 ----
_pt("yolov8n", "YOLOv8n", "yolov8n.pt", 6.2, "经典轻量模型，兼容性最好", tags=("兼容",))
_pt("yolov8s", "YOLOv8s", "yolov8s.pt", 21.5, "经典小模型")
_pt("yolov8n-human", "YOLOv8n-human", "yolov8n-human.pt", 6.2, "纯人形检测专用模型，误报更低", tags=("人形专用",), labels=PERSON_LABELS)
# ---- YOLOv10 / YOLO12 ----
_pt("yolov10n", "YOLOv10n", "yolov10n.pt", 5.8, "端到端无 NMS 模型")
_pt("yolo12n", "YOLO12n", "yolo12n.pt", 5.6, "注意力机制模型，小目标更准")
# ---- RT-DETR：Transformer 检测器，非 YOLO ----
_pt("rtdetr-l", "RT-DETR-L", "rtdetr-l.pt", 63.0, "Transformer 检测器（非 YOLO），遮挡场景更稳", tags=("非YOLO",), outputFormat="rtdetr")
# ---- 开放词汇 ----
_pt("yolov8s-worldv2", "YOLO-World v2 S", "yolov8s-worldv2.pt", 24.0, "开放词汇检测，可自定义要检测的目标", tags=("开放词汇",))

# ---- 官方预导出 ONNX（无需本机导出，直接可跑 ONNX Runtime） ----
_ONNX_PRESETS = [
    ("yolo26n-onnx", "YOLO26n (ONNX)", "yolo26n.onnx", 10.0, "ONNX Runtime / DirectML 通用", "end2end"),
    ("yolo11n-onnx", "YOLO11n (ONNX)", "yolo11n.onnx", 10.4, "ONNX Runtime / DirectML 通用", "auto"),
    ("yolo11s-onnx", "YOLO11s (ONNX)", "yolo11s.onnx", 36.0, "ONNX Runtime 小模型", "auto"),
    ("yolov8n-onnx", "YOLOv8n (ONNX)", "yolov8n.onnx", 12.0, "ONNX Runtime 兼容性最好", "auto"),
]
for key, name, filename, size, desc, fmt in _ONNX_PRESETS:
    _register(
        ModelSpec(
            key=key,
            name=name,
            family="onnx",
            filename=filename,
            url=f"{ASSET_BASE}/{filename}",
            sizeMb=size,
            description=desc,
            outputFormat=fmt,
            tags=("ONNX",),
        )
    )

# ---- 自定义模型占位 ----
_register(
    ModelSpec(
        key="custom",
        name="自定义模型",
        family="custom",
        filename="",
        description="填写本机 .pt / .onnx / .xml 模型路径，或上传到 models 目录",
        license="取决于模型来源",
        tags=("自定义",),
    )
)

MODEL_ALIASES = {
    "yolov8m": "yolov8n",
    "yolov8l": "yolov8n",
    "yolov8x": "yolov8n",
    "yolo11x": "yolo11n",
    "yolov5": "yolo11n",
}


def resolve_model(key: str) -> ModelSpec | None:
    if not key:
        return None
    if key in MODELS:
        return MODELS[key]
    if key in MODEL_ALIASES:
        return MODELS.get(MODEL_ALIASES[key])
    stem = Path(key).stem
    if stem in MODELS:
        return MODELS[stem]
    return None


def model_path(spec: ModelSpec | None) -> Path | None:
    if not spec or not spec.filename:
        return None
    candidate = MODELS_DIR / spec.filename
    return candidate if candidate.exists() else None


def list_models() -> list[dict[str, Any]]:
    result = []
    for spec in MODELS.values():
        path = model_path(spec)
        result.append(spec.to_dict(installed=bool(path), path=str(path) if path else ""))
    return result


def list_custom_models() -> list[dict[str, Any]]:
    """扫描 models 目录中的自定义模型。"""
    found: list[dict[str, Any]] = []
    if not MODELS_DIR.exists():
        return found
    for path in sorted(MODELS_DIR.glob("*")):
        if path.suffix.lower() not in {".pt", ".onnx", ".xml", ".engine", ".plan"}:
            continue
        if any(spec.filename == path.name for spec in MODELS.values()):
            continue
        family = "onnx" if path.suffix.lower() == ".onnx" else "openvino" if path.suffix.lower() == ".xml" else "pt"
        found.append(
            {
                "key": path.stem,
                "name": path.stem,
                "family": family,
                "file": path.name,
                "path": str(path),
                "sizeMb": round(path.stat().st_size / 1024 / 1024, 1),
                "labels": len(COCO_LABELS),
                "license": "自定义",
                "tags": ["本机"],
                "installed": True,
            }
        )
    return found


def install_bundled_models() -> int:
    """把安装包内置的模型复制到数据目录（首次运行/升级时）。"""
    source = PROJECT_ROOT / "models"
    if not source.is_dir():
        return 0
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in source.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".pt", ".onnx", ".xml", ".bin", ".engine", ".plan"}:
            continue
        target = MODELS_DIR / path.name
        if target.exists():
            continue
        try:
            import shutil

            shutil.copy2(path, target)
            copied += 1
        except OSError as exc:
            warn(f"内置模型复制失败 {path.name}: {exc}", "models")
    if copied:
        info(f"已安装 {copied} 个内置模型到 {MODELS_DIR}", "models")
    return copied


_download_lock = threading.Lock()


def download_model(key: str, *, progress=None) -> tuple[bool, str]:
    """下载官方模型到 models 目录。"""
    spec = resolve_model(key)
    if not spec or not spec.url:
        return False, "该模型没有可下载的官方地址"
    target = MODELS_DIR / spec.filename
    if target.exists():
        return True, "模型已存在"
    with _download_lock:
        if target.exists():
            return True, "模型已存在"
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        info(f"开始下载模型 {spec.name} → {target}", "models")
        try:
            import requests

            with requests.get(spec.url, stream=True, timeout=60) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length") or 0)
                temp = target.with_suffix(target.suffix + ".part")
                downloaded = 0
                last_report = 0.0
                with open(temp, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 20):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if progress:
                            import time

                            now = time.time()
                            if now - last_report > 0.5 or downloaded == total:
                                last_report = now
                                progress(downloaded, total)
                temp.replace(target)
            info(f"模型下载完成：{target.name}", "models")
            return True, "下载完成"
        except Exception as exc:
            warn(f"模型下载失败：{exc}", "models")
            return False, f"下载失败: {exc}"


def delete_model(key: str) -> tuple[bool, str]:
    spec = resolve_model(key)
    if not spec:
        return False, "未知模型"
    path = MODELS_DIR / spec.filename
    if not path.exists():
        return False, "模型文件不存在"
    try:
        path.unlink()
        return True, "已删除"
    except OSError as exc:
        return False, f"删除失败: {exc}"
