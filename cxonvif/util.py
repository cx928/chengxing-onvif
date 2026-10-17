"""通用工具函数 / Small shared helpers."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

IS_WINDOWS = os.name == "nt"
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

_write_lock = threading.Lock()


def now_iso() -> str:
    """UTC 时间戳，带 Z 后缀（ONVIF 使用）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def local_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_uuid() -> str:
    return str(uuid.uuid4())


def atomic_write_json(path: Path, data: Any, *, backup: bool = True) -> None:
    """原子写入 JSON，避免断电/崩溃导致配置损坏。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        if backup and path.exists():
            try:
                shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
            except OSError:
                pass
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def run_command(
    args: list[str],
    *,
    timeout: float = 20.0,
    check: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """静默执行命令（Windows 下不弹窗）。"""
    creationflags = CREATE_NO_WINDOW if IS_WINDOWS else 0
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
        creationflags=creationflags,
        env=env,
    )


def popen_hidden(args: list[str], **kwargs) -> subprocess.Popen:
    """启动后台进程，Windows 下隐藏控制台窗口。"""
    creationflags = kwargs.pop("creationflags", 0)
    if IS_WINDOWS:
        creationflags |= CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(args, creationflags=creationflags, **kwargs)


def local_ip() -> str:
    """获取本机局域网 IPv4 地址（不产生真实流量）。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def port_free(port: int, host: str = "0.0.0.0") -> bool:
    """检查端口是否可用（同时检查 IPv4 与 IPv6，避免漏判双栈监听）。"""
    targets: list[tuple[int, str]] = []
    if host in ("0.0.0.0", "", None):
        targets.append((socket.AF_INET, "0.0.0.0"))
        if socket.has_ipv6:
            targets.append((socket.AF_INET6, "::"))
    else:
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        targets.append((family, host))

    for family, address in targets:
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            # 不使用 SO_REUSEADDR：Windows 下它允许"抢占"已被监听的端口，导致误判
            if family == socket.AF_INET6:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            sock.bind((address, port))
        except OSError:
            return False
        finally:
            sock.close()
    return True


def port_owner_pid(port: int, kind: str = "tcp") -> int | None:
    """返回监听指定端口的进程 PID（需要 psutil，失败时返回 None）。"""
    try:
        import psutil

        for conn in psutil.net_connections(kind=kind):
            if not conn.laddr or getattr(conn.laddr, "port", None) != port:
                continue
            if conn.status == psutil.CONN_LISTEN and conn.pid:
                return int(conn.pid)
    except Exception:
        return None
    return None



def find_free_port(start: int, end: int = 65535, host: str = "0.0.0.0") -> int | None:
    for port in range(start, min(end, start + 500)):
        if port_free(port, host):
            return port
    return None


def human_bytes(value: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def slugify(value: str, fallback: str = "camera") -> str:
    """生成 ASCII 路径片段（MediaMTX 路径 / URL 安全）。"""
    cleaned = []
    for ch in value.strip():
        if ch.isascii() and (ch.isalnum() or ch in "-_"):
            cleaned.append(ch)
        elif ch in " .":
            cleaned.append("_")
    result = "".join(cleaned).strip("_-")
    while "__" in result:
        result = result.replace("__", "_")
    return (result or fallback)[:40]


def mask_secret(value: str, keep: int = 2) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return value[:keep] + "*" * (len(value) - keep * 2) + value[-keep:]


def sleep_until_next(interval: float, started: float) -> None:
    delay = interval - (time.monotonic() - started)
    if delay > 0:
        time.sleep(delay)


def platform_name() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"
