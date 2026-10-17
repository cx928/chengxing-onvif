"""命令行入口 / CLI."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

from . import brand
from .paths import HOME
from .version import CURRENT_VERSION, version_string


def _redirect_output() -> None:
    """静默模式：把 stdout/stderr 重定向到日志文件（pythonw 下也没有窗口）。"""
    from .paths import LOG_FILE

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stream = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = stream
    sys.stderr = stream


def cmd_serve(args: argparse.Namespace) -> int:
    from .config import ConfigStore
    from .core.service import run_engine
    from .logbus import init_logging

    if args.silent:
        _redirect_output()
    init_logging(level="DEBUG" if args.debug else "INFO", silent=args.silent)

    store = ConfigStore()
    if args.port:
        store.update_settings({"webPort": int(args.port)})
    if args.browser:
        open_browser = True
    elif args.no_browser:
        open_browser = False
    else:
        open_browser = None
    return run_engine(store, host=args.host, port=args.port, open_browser=open_browser)


def cmd_password(args: argparse.Namespace) -> int:
    from .config import ConfigStore

    store = ConfigStore()
    if args.password:
        store.set_password(args.password, must_change=False)
        print("密码已更新")
        return 0
    new_password = args.generate or f"cx{secrets.token_hex(4)}"
    store.set_password(new_password, must_change=True)
    print(f"管理员账号: {store.config.auth.username}")
    print(f"新密码: {new_password}")
    print("请登录 Web 控制台后立即修改。")
    return 0


def cmd_autostart(args: argparse.Namespace) -> int:
    from .core import autostart

    if args.action == "install":
        ok, message = autostart.install(mode="user" if args.user else "auto")
    elif args.action == "uninstall":
        ok, message = autostart.uninstall()
    else:
        status = autostart.status()
        print(f"平台: {status.get('platform')}")
        print(f"已安装: {status.get('installed')}")
        if status.get("detail"):
            print(status["detail"])
        return 0
    print(message)
    return 0 if ok else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    from .detect.models import list_models
    from .hw.ffmpeg import resolve_ffmpeg
    from .hw.probe import get_profile
    from .stream.mediamtx import find_binary

    config = __import__("cxonvif.config", fromlist=["ConfigStore"]).ConfigStore()
    settings = config.config.settings
    print(f"{brand.BRAND_ZH} 自检 / doctor  v{CURRENT_VERSION}")
    print(f"数据目录: {HOME}")
    print(f"Python: {sys.version.split()[0]}")
    ffmpeg = resolve_ffmpeg(settings.get("ffmpegPath", ""))
    print(f"FFmpeg: {ffmpeg.path if ffmpeg else '未找到'} {('v' + ffmpeg.version) if ffmpeg else ''}")
    mediamtx = find_binary(settings.get("mediamtxPath", ""))
    print(f"MediaMTX: {mediamtx or '未找到（将尝试自动下载）'}")
    profile = get_profile(settings, refresh=args.refresh)
    print(f"GPU: {', '.join(f'{g.vendor}:{g.name}' for g in profile.gpus) or '未检测到'}")
    print(f"推荐编码器: {profile.recommendedEncoder}")
    print(f"推荐解码加速: {profile.recommendedDecoder or '软件'}")
    print(f"推荐推理设备: {profile.recommendedInference}")
    print("可用硬件编码器: " + (", ".join(e.name for e in profile.encoders if e.available) or "无"))
    print("推理后端: " + "; ".join(f"{b.name}{'(已安装)' if b.installed else '(未安装)'}" for b in profile.inference))
    installed = [m["key"] for m in list_models() if m["installed"]]
    print(f"已下载模型: {', '.join(installed) or '无'}")
    print(f"摄像机: {len(config.config.cameras)} 台")
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    from .detect.models import download_model, list_models

    if args.action == "download":
        ok, message = download_model(args.key)
        print(message)
        return 0 if ok else 1
    for model in list_models():
        flag = "✔" if model["installed"] else " "
        print(f"[{flag}] {model['key']:<16} {model['name']:<22} {model['family']:<9} {model['description']}")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    from .hw.ffmpeg import probe_media, resolve_ffmpeg

    ffmpeg = resolve_ffmpeg("")
    result = probe_media(args.url, ffmpeg.ffprobe if ffmpeg else None)
    print(result)
    return 0 if result.get("ok") else 1


def cmd_version(args: argparse.Namespace) -> int:
    print(f"{brand.BRAND_ZH} {version_string()}")
    print(f"{brand.TAGLINE}")
    print(f"GitHub: {brand.GITHUB_URL}")
    print(f"B站: {brand.BILIBILI}")
    print(f"邮箱: {brand.EMAIL}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cxonvif",
        description=f"{brand.BRAND_ZH} —— 多模型 ONVIF 虚拟摄像机服务器",
    )
    parser.add_argument("--version", action="store_true", help="显示版本")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="启动服务（Web 版）")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--silent", action="store_true", help="静默模式（不输出到控制台，适合开机自启）")
    serve.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    serve.add_argument("--browser", action="store_true", help="启动后自动打开浏览器（安装版快捷方式使用）")
    serve.add_argument("--debug", action="store_true")
    serve.set_defaults(func=cmd_serve)

    password = sub.add_parser("password", help="设置管理员密码")
    password.add_argument("password", nargs="?", help="新密码")
    password.add_argument("--generate", action="store_true", help="生成随机密码")
    password.set_defaults(func=cmd_password)

    autostart = sub.add_parser("autostart", help="开机自启管理")
    autostart.add_argument("action", choices=["install", "uninstall", "status"])
    autostart.add_argument("--user", action="store_true", help="仅当前用户（Windows 启动文件夹）")
    autostart.set_defaults(func=cmd_autostart)

    doctor = sub.add_parser("doctor", help="环境自检")
    doctor.add_argument("--refresh", action="store_true", help="重新探测硬件")
    doctor.set_defaults(func=cmd_doctor)

    models = sub.add_parser("models", help="模型管理")
    models.add_argument("action", choices=["list", "download"], nargs="?", default="list")
    models.add_argument("key", nargs="?", default="yolo11n")
    models.set_defaults(func=cmd_models)

    probe = sub.add_parser("probe", help="探测视频流")
    probe.add_argument("url")
    probe.set_defaults(func=cmd_probe)

    version = sub.add_parser("version", help="显示版本信息")
    version.set_defaults(func=cmd_version)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "version", False):
        return cmd_version(args)
    if not getattr(args, "command", None):
        args = parser.parse_args(["serve", *(argv or [])])
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
