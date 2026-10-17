"""运行目录解析 / Runtime paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .brand import DATA_DIR_NAME

# 仓库根目录（源码运行时的基准目录）
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def app_home() -> Path:
    """返回可写的数据目录。

    优先级：CXONVIF_HOME > 平台标准目录 > 用户主目录回退。
    """
    env = os.environ.get("CXONVIF_HOME")
    if env:
        home = Path(env).expanduser().resolve()
        home.mkdir(parents=True, exist_ok=True)
        return home

    candidates: list[Path] = []
    if os.name == "nt":
        candidates.append(Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / DATA_DIR_NAME)
        candidates.append(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / DATA_DIR_NAME)
    elif sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Application Support" / DATA_DIR_NAME)
    else:
        if os.geteuid() == 0:
            candidates.append(Path("/var/lib/chengxing-onvif"))
        candidates.append(Path.home() / ".local" / "share" / DATA_DIR_NAME)

    for candidate in candidates:
        if _writable(candidate):
            return candidate
    fallback = Path.home() / ".cxonvif"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def ensure_layout(home: Path | None = None) -> dict[str, Path]:
    """创建并返回数据目录布局。"""
    home = home or app_home()
    layout = {
        "home": home,
        "models": home / "models",
        "snapshots": home / "snapshots",
        "logs": home / "logs",
        "cache": home / "cache",
        "recordings": home / "recordings",
        "vendor": home / "vendor",
    }
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    return layout


HOME = app_home()
LAYOUT = ensure_layout(HOME)
CONFIG_FILE = HOME / "config.json"
SECRET_FILE = HOME / "secret.key"
LOG_FILE = LAYOUT["logs"] / "cxonvif.log"
PID_FILE = HOME / "cxonvif.pid"
MODELS_DIR = LAYOUT["models"]
SNAPSHOT_DIR = LAYOUT["snapshots"]


def find_asset(*relative: str) -> Path | None:
    """在若干可能位置查找随附资源（ffmpeg/mediamtx 等）。"""
    roots = [
        PROJECT_ROOT,
        HOME,
        LAYOUT["vendor"],
        Path(sys.executable).parent,
        Path.cwd(),
    ]
    for root in roots:
        candidate = root.joinpath(*relative)
        if candidate.exists():
            return candidate
    return None
