"""开机自启与服务安装 / Autostart management.

Windows: 计划任务（SYSTEM，开机即启动，静默无窗口）或启动文件夹回退；
Linux: systemd 服务；
macOS: launchd。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..brand import SERVICE_NAME, SERVICE_NAME_LINUX
from ..logbus import info, warn
from ..paths import HOME
from ..util import IS_WINDOWS, platform_name, run_command

LAUNCHER = HOME / "start-silent.vbs"


def _pythonw() -> Path:
    executable = Path(sys.executable)
    if IS_WINDOWS:
        candidate = executable.with_name("pythonw.exe")
        if candidate.exists():
            return candidate
        candidate = executable.with_name("python.exe")
        if candidate.exists():
            return candidate
    return executable


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def is_admin() -> bool:
    if not IS_WINDOWS:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _write_launcher() -> str:
    """生成 VBS 静默启动器（无控制台窗口）。"""
    pythonw = _pythonw()
    root = _project_root()
    HOME.mkdir(parents=True, exist_ok=True)
    script = (
        'Set shell = CreateObject("WScript.Shell")\n'
        f'shell.CurrentDirectory = "{root}"\n'
        f'command = """{pythonw}"" -m cxonvif serve --silent"\n'
        'shell.Run command, 0, False\n'
    )
    LAUNCHER.write_text(script, encoding="utf-8")
    return str(LAUNCHER)


def _remove_login_run_key() -> None:
    """移除安装版写入的登录自启注册表项，避免与计划任务重复启动。"""
    if not IS_WINDOWS:
        return
    try:
        run_command(
            ["reg", "delete", r"HKLM\Software\Microsoft\Windows\CurrentVersion\Run", "/v", SERVICE_NAME, "/f"],
            timeout=15,
        )
    except Exception:
        pass


def _startup_dir() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


# --------------------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------------------


def _task_exists() -> bool:
    completed = run_command(["schtasks", "/Query", "/TN", SERVICE_NAME], timeout=15)
    return completed.returncode == 0


def windows_install(*, mode: str = "auto") -> tuple[bool, str]:
    launcher = _write_launcher()
    if mode in ("auto", "system") and is_admin():
        command = f'wscript.exe "{launcher}"'
        completed = run_command(
            [
                "schtasks", "/Create", "/F",
                "/TN", SERVICE_NAME,
                "/SC", "ONSTART",
                "/RU", "SYSTEM",
                "/RL", "HIGHEST",
                "/TR", command,
            ],
            timeout=30,
        )
        if completed.returncode == 0:
            _remove_login_run_key()
            info(f"已创建开机计划任务 {SERVICE_NAME}", "service")
            return True, "已安装开机自启（系统计划任务，SYSTEM 静默启动）"
        warn(f"计划任务创建失败：{completed.stderr}", "service")
        if mode == "system":
            return False, (completed.stderr or completed.stdout or "创建计划任务失败").strip()
    # 回退：当前用户启动文件夹（无需管理员）
    try:
        startup = _startup_dir()
        startup.mkdir(parents=True, exist_ok=True)
        target = startup / f"{SERVICE_NAME}.vbs"
        target.write_text(Path(launcher).read_text(encoding="utf-8"), encoding="utf-8")
        _remove_login_run_key()
        return True, "已加入当前用户启动文件夹（登录后静默启动；如需开机启动请以管理员身份安装）"
    except OSError as exc:
        return False, f"安装自启失败：{exc}"


def windows_uninstall() -> tuple[bool, str]:
    messages = []
    if _task_exists():
        completed = run_command(["schtasks", "/Delete", "/F", "/TN", SERVICE_NAME], timeout=20)
        messages.append("计划任务已删除" if completed.returncode == 0 else "计划任务删除失败")
    _remove_login_run_key()
    target = _startup_dir() / f"{SERVICE_NAME}.vbs"
    if target.exists():
        try:
            target.unlink()
            messages.append("启动文件夹已清理")
        except OSError:
            messages.append("启动文件夹清理失败")
    return True, "；".join(messages) or "未发现自启项"


def windows_status() -> dict[str, Any]:
    running = False
    detail = ""
    if _task_exists():
        completed = run_command(["schtasks", "/Query", "/TN", SERVICE_NAME, "/FO", "LIST", "/V"], timeout=20)
        detail = completed.stdout or ""
        running = "Ready" in detail or "就绪" in detail or "Running" in detail or "正在运行" in detail
    return {
        "platform": "windows",
        "installed": _task_exists() or ( _startup_dir() / f"{SERVICE_NAME}.vbs").exists(),
        "task": _task_exists(),
        "startupFolder": ( _startup_dir() / f"{SERVICE_NAME}.vbs").exists(),
        "admin": is_admin(),
        "detail": detail[:2000],
        "launcher": str(LAUNCHER),
    }


# --------------------------------------------------------------------------------------
# Linux / macOS
# --------------------------------------------------------------------------------------

UNIT_TEMPLATE = """[Unit]
Description=程星 ONVIF 服务 (ChengXing ONVIF)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={root}
ExecStart={python} -m cxonvif serve --silent
Environment=CXONVIF_HOME={home}
Restart=on-failure
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
"""

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.chengxing.onvif</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>cxonvif</string>
        <string>serve</string>
        <string>--silent</string>
    </array>
    <key>WorkingDirectory</key><string>{root}</string>
    <key>EnvironmentVariables</key>
    <dict><key>CXONVIF_HOME</key><string>{home}</string></dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>{log}</string>
    <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""


def linux_install() -> tuple[bool, str]:
    if not is_admin():
        return False, "需要 root 权限：sudo cxonvif autostart install"
    unit_path = Path(f"/etc/systemd/system/{SERVICE_NAME_LINUX}.service")
    content = UNIT_TEMPLATE.format(root=_project_root(), python=sys.executable, home=HOME)
    try:
        unit_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return False, f"写入 systemd 单元失败：{exc}"
    run_command(["systemctl", "daemon-reload"], timeout=30)
    completed = run_command(["systemctl", "enable", "--now", SERVICE_NAME_LINUX], timeout=60)
    if completed.returncode == 0:
        return True, f"已安装并启动 systemd 服务 {SERVICE_NAME_LINUX}"
    return False, (completed.stderr or completed.stdout or "systemctl 启动失败").strip()


def linux_uninstall() -> tuple[bool, str]:
    if not is_admin():
        return False, "需要 root 权限"
    run_command(["systemctl", "disable", "--now", SERVICE_NAME_LINUX], timeout=60)
    try:
        Path(f"/etc/systemd/system/{SERVICE_NAME_LINUX}.service").unlink(missing_ok=True)
        run_command(["systemctl", "daemon-reload"], timeout=30)
        return True, "已移除 systemd 服务"
    except OSError as exc:
        return False, str(exc)


def linux_status() -> dict[str, Any]:
    unit = Path(f"/etc/systemd/system/{SERVICE_NAME_LINUX}.service")
    completed = run_command(["systemctl", "is-active", SERVICE_NAME_LINUX], timeout=10)
    return {
        "platform": "linux",
        "installed": unit.exists(),
        "active": (completed.stdout or "").strip() == "active",
        "unit": str(unit),
    }


def macos_install() -> tuple[bool, str]:
    if not is_admin():
        return False, "需要 sudo 权限"
    plist_path = Path("/Library/LaunchDaemons/com.chengxing.onvif.plist")
    content = PLIST_TEMPLATE.format(
        python=sys.executable, root=_project_root(), home=HOME, log=HOME / "logs" / "service.log"
    )
    try:
        plist_path.write_text(content, encoding="utf-8")
        os.chmod(plist_path, 0o644)
    except OSError as exc:
        return False, f"写入 launchd 配置失败：{exc}"
    completed = run_command(["launchctl", "load", "-w", str(plist_path)], timeout=30)
    return completed.returncode == 0, "已安装 launchd 服务" if completed.returncode == 0 else (completed.stderr or "launchctl 失败")


def macos_uninstall() -> tuple[bool, str]:
    plist_path = Path("/Library/LaunchDaemons/com.chengxing.onvif.plist")
    run_command(["launchctl", "unload", "-w", str(plist_path)], timeout=30)
    try:
        plist_path.unlink(missing_ok=True)
        return True, "已移除 launchd 服务"
    except OSError as exc:
        return False, str(exc)


def macos_status() -> dict[str, Any]:
    plist_path = Path("/Library/LaunchDaemons/com.chengxing.onvif.plist")
    completed = run_command(["launchctl", "list", "com.chengxing.onvif"], timeout=10)
    return {
        "platform": "macos",
        "installed": plist_path.exists(),
        "active": completed.returncode == 0,
        "plist": str(plist_path),
    }


# --------------------------------------------------------------------------------------
# 统一入口
# --------------------------------------------------------------------------------------


def install(mode: str = "auto") -> tuple[bool, str]:
    platform = platform_name()
    if platform == "windows":
        return windows_install(mode=mode)
    if platform == "linux":
        return linux_install()
    return macos_install()


def uninstall() -> tuple[bool, str]:
    platform = platform_name()
    if platform == "windows":
        return windows_uninstall()
    if platform == "linux":
        return linux_uninstall()
    return macos_uninstall()


def status() -> dict[str, Any]:
    platform = platform_name()
    if platform == "windows":
        return windows_status()
    if platform == "linux":
        return linux_status()
    return macos_status()
