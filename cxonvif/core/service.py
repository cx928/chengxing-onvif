"""引擎运行器 / Engine runner（Web 版与桌面版共用）。"""

from __future__ import annotations

import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path

from ..api import create_app
from ..brand import BRAND_ZH, GITHUB_URL
from ..config import ConfigStore
from ..logbus import BUS, info, warn
from ..paths import HOME, PID_FILE, PROJECT_ROOT
from ..version import CURRENT_VERSION, version_string
from .manager import CameraManager

WEB_DIR = PROJECT_ROOT / "web"


def _write_pid() -> None:
    try:
        PID_FILE.write_text(str(__import__("os").getpid()), encoding="utf-8")
    except OSError:
        pass


def _clear_pid() -> None:
    PID_FILE.unlink(missing_ok=True)


def run_engine(
    store: ConfigStore | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    open_browser: bool | None = None,
) -> int:
    from werkzeug.serving import make_server

    store = store or ConfigStore()
    settings = store.config.settings
    host = host or str(settings.get("bind") or "0.0.0.0")
    port = int(port or settings.get("webPort") or 5552)
    if open_browser is None:
        open_browser = bool(settings.get("openBrowser", False))

    shutdown = threading.Event()

    def handle_signal(signum, frame):  # noqa: ANN001
        info(f"收到信号 {signum}，准备退出", "service")
        shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, handle_signal)
        except (ValueError, OSError):
            pass

    _write_pid()
    print(f"\n{BRAND_ZH}  v{CURRENT_VERSION}\n{'=' * 52}")
    print(f"数据目录: {HOME}")
    print(f"项目主页: {GITHUB_URL}\n")

    restart_requested = False
    try:
        while True:
            manager = CameraManager(store)
            manager.restart_requested = False
            manager.shutdown_requested = False
            media_ok, media_message = manager.start_mediamtx()
            if not media_ok:
                warn(f"MediaMTX 启动失败：{media_message}", "service")

            app = create_app(manager, web_dir=WEB_DIR)
            try:
                server = make_server(host, port, app, threaded=True)
                server.daemon_threads = True
            except OSError as exc:
                warn(f"Web 端口 {port} 启动失败：{exc}", "service")
                manager.stop()
                return 2

            web_thread = threading.Thread(target=server.serve_forever, name="web", daemon=True)
            web_thread.start()
            # Web 就绪后再启动摄像机：叠加推流需要 MediaMTX 回调本服务的鉴权接口
            manager.start_cameras()
            info(f"Web 控制台: http://{manager.local_ip}:{port}", "service")
            print(f"Web 控制台: http://127.0.0.1:{port}\n")

            if open_browser:
                try:
                    webbrowser.open(f"http://127.0.0.1:{port}")
                except Exception:
                    pass

            try:
                while not shutdown.is_set() and not manager.restart_requested and not manager.shutdown_requested:
                    if not web_thread.is_alive():
                        warn("Web 线程退出，服务即将重启", "service")
                        restart_requested = True
                        break
                    time.sleep(0.5)
            finally:
                try:
                    server.shutdown()
                finally:
                    try:
                        server.server_close()
                    except Exception:
                        pass
                # 清理可能卡住的线程/进程，最多等 20 秒，确保服务能真正退出
                stopper = threading.Thread(target=manager.stop, name="stop", daemon=True)
                stopper.start()
                stopper.join(timeout=20)
                if stopper.is_alive():
                    warn("停止超时，强制退出（残留子进程会随主进程结束）", "service")

            if manager.restart_requested:
                info("收到重启请求，正在重新加载…", "service")
                restart_requested = True
            if manager.shutdown_requested:
                shutdown.set()
            if not shutdown.is_set() and not restart_requested:
                break
            if shutdown.is_set():
                break
            time.sleep(0.3)
            restart_requested = False
        return 0
    finally:
        _clear_pid()
