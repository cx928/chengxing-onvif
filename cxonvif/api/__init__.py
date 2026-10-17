"""Web 应用工厂 / Flask app factory."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from flask import Flask, Response, jsonify, request, send_from_directory

from ..api.auth import AuthManager
from ..api.jobs import JobRegistry
from ..api.routes import bp as api_bp
from ..brand import BRAND_ZH, COPYRIGHT
from ..core.manager import CameraManager
from ..logbus import BUS
from ..paths import HOME
from ..version import CURRENT_VERSION


def _json_error(message: str, code: int) -> Response:
    return jsonify({"ok": False, "error": message}), code


def create_app(
    manager: CameraManager,
    *,
    web_dir: Path,
    on_restart: Callable[[], None] | None = None,
    on_shutdown: Callable[[], None] | None = None,
) -> Flask:
    app = Flask(
        "cxonvif",
        static_folder=str(web_dir),
        static_url_path="/assets",
    )
    app.config["JSON_AS_ASCII"] = False
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

    auth_manager = AuthManager(manager.store)
    job_registry = JobRegistry()
    app.extensions["manager"] = manager
    app.extensions["auth"] = auth_manager
    app.extensions["jobs"] = job_registry
    app.extensions["on_restart"] = on_restart
    app.extensions["on_shutdown"] = on_shutdown

    if not hasattr(manager, "restart_requested"):
        manager.restart_requested = False
    if not hasattr(manager, "shutdown_requested"):
        manager.shutdown_requested = False

    # ------------------------------------------------------------------ 鉴权
    PUBLIC_PREFIXES = (
        "/api/v2/auth/",
        "/api/v2/health",
        "/api/internal/",
        "/assets/",
        "/favicon.ico",
    )

    @app.before_request
    def _guard():
        path = request.path
        if not path.startswith("/api/"):
            return None
        if any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
            return None
        if not manager.store.config.auth.requireLogin:
            return None
        if auth_manager.current_session():
            return None
        return _json_error("未登录", 401)

    @app.after_request
    def _cors(response):
        response.headers.setdefault("Access-Control-Allow-Origin", "*")
        response.headers.setdefault("Access-Control-Allow-Headers", "Authorization, Content-Type, X-CX-Token")
        response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        response.headers.setdefault("X-CX-Version", CURRENT_VERSION)
        if request.method == "OPTIONS":
            response.status_code = 200
        return response

    app.register_blueprint(api_bp)

    # ------------------------------------------------------------------ MediaMTX 鉴权回调
    @app.post("/api/internal/mediamtx/auth")
    def mediamtx_auth():
        payload = request.get_json(silent=True) or {}
        allowed, reason = manager.mediamtx_auth(payload)
        if allowed:
            return Response("ok", status=200, mimetype="text/plain")
        BUS.append("WARNING", "mediamtx", f"拒绝 {payload.get('action')} {payload.get('path')} from {payload.get('ip')}: {reason}")
        return Response(reason, status=401, mimetype="text/plain")

    @app.get("/api/internal/ping")
    def internal_ping():
        return jsonify({"ok": True, "brand": BRAND_ZH, "version": CURRENT_VERSION, "uptime": time.time()})

    # ------------------------------------------------------------------ 首页与静态资源
    @app.get("/")
    def index():
        if (web_dir / "index.html").exists():
            return send_from_directory(web_dir, "index.html")
        return Response(
            f"<h1>{BRAND_ZH}</h1><p>Web 控制台资源缺失，请检查 web/ 目录。</p>",
            mimetype="text/html",
        )

    @app.get("/favicon.ico")
    def favicon():
        icon = web_dir / "favicon.svg"
        if icon.exists():
            return send_from_directory(icon.parent, icon.name, mimetype="image/svg+xml")
        return Response(status=204)

    @app.get("/<path:filename>")
    def spa_fallback(filename: str):
        candidate = web_dir / filename
        if candidate.is_file():
            return send_from_directory(web_dir, filename)
        if (web_dir / "index.html").exists():
            return send_from_directory(web_dir, "index.html")
        return _json_error("Not found", 404)

    # ------------------------------------------------------------------ 错误处理
    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return _json_error("接口不存在", 404)
        return send_from_directory(web_dir, "index.html") if (web_dir / "index.html").exists() else _json_error("Not found", 404)

    @app.errorhandler(500)
    def server_error(error):  # pragma: no cover
        BUS.append("ERROR", "api", f"500: {error}")
        return _json_error("服务器内部错误", 500)

    @app.errorhandler(Exception)
    def unhandled(error):  # pragma: no cover
        import traceback

        traceback.print_exc()
        BUS.append("ERROR", "api", f"{type(error).__name__}: {error}")
        return _json_error(f"服务器异常: {error}", 500)

    BUS.append("INFO", "api", f"Web 控制台已就绪 · 数据目录 {HOME}")
    return app
