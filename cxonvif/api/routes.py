"""REST API v2 路由。"""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request, send_file, stream_with_context

from ..config import DEFAULT_SETTINGS, CameraConfig, camera_from_payload
from ..core.manager import CameraManager
from ..detect.models import MODELS, list_custom_models, list_models, resolve_model
from ..hw.ffmpeg import capture_jpeg, probe_media
from ..hw.probe import refresh_profile
from ..logbus import BUS
from ..onvif.profiles import list_profiles
from ..paths import HOME, MODELS_DIR
from ..security import password_strength
from ..stream.source import guess_stream_urls
from ..util import now_iso
from ..version import CURRENT_VERSION

bp = Blueprint("api_v2", __name__, url_prefix="/api/v2")


# --------------------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------------------


def manager() -> CameraManager:
    return current_app.extensions["manager"]


def auth():
    return current_app.extensions["auth"]


def jobs():
    return current_app.extensions["jobs"]


def ok(data: Any = None, **extra) -> Response:
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload)


def fail(message: str, code: int = 400, **extra) -> Response:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return jsonify(payload), code


def login_required(func):
    """请求时解析登录状态（不能在导入期访问 current_app）。"""

    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not manager().store.config.auth.requireLogin:
            return func(*args, **kwargs)
        if not auth().current_session():
            return fail("未登录", 401)
        return func(*args, **kwargs)

    return wrapper


# --------------------------------------------------------------------------------------
# 认证
# --------------------------------------------------------------------------------------


@bp.get("/auth/state")
def auth_state():
    config = manager().store.config
    return ok(
        {
            "requireLogin": config.auth.requireLogin,
            "username": config.auth.username,
            "mustChangePassword": config.auth.mustChangePassword,
            "brand": config.brand,
        }
    )


@bp.post("/auth/login")
def auth_login():
    body = request.get_json(silent=True) or {}
    result, code = auth().login(
        str(body.get("username") or "admin"),
        str(body.get("password") or ""),
        request.remote_addr or "unknown",
    )
    return jsonify(result), code


@bp.post("/auth/logout")
def auth_logout():
    token = auth().token_from_request()
    if token:
        auth().sessions.revoke(token)
    return ok()


@bp.get("/auth/session")
@login_required
def auth_session():
    session = auth().current_session() or {}
    return ok({"username": session.get("username"), "expires": session.get("expires")})


@bp.post("/auth/password")
@login_required
def auth_password():
    body = request.get_json(silent=True) or {}
    result, code = auth().change_password(str(body.get("currentPassword") or ""), str(body.get("newPassword") or ""))
    return jsonify(result), code


@bp.get("/auth/password/strength")
@login_required
def auth_password_strength():
    value = request.args.get("password", "")
    score, hints = password_strength(value)
    return ok({"score": score, "hints": hints})


# --------------------------------------------------------------------------------------
# 系统
# --------------------------------------------------------------------------------------


@bp.get("/health")
def health():
    engine = manager()
    return jsonify(
        {
            "status": "ok",
            "brand": "程星 ONVIF",
            "version": CURRENT_VERSION,
            "uptime": int(time.time() - engine.started_at) if engine.started_at else 0,
            "cameras": len(engine.store.cameras),
            "running": sum(1 for c in engine.cameras.values() if c.status == "running"),
        }
    )


@bp.get("/system/info")
@login_required
def system_info():
    return ok(manager().system_info())


@bp.get("/system/status")
@login_required
def system_status():
    return ok(manager().status())


@bp.get("/system/settings")
@login_required
def system_settings_get():
    engine = manager()
    config = engine.store.config
    return ok(
        {
            "settings": engine.settings,
            "auth": {
                "username": config.auth.username,
                "requireLogin": config.auth.requireLogin,
                "mustChangePassword": config.auth.mustChangePassword,
            },
            "defaults": DEFAULT_SETTINGS,
            "paths": {"home": str(HOME), "models": str(MODELS_DIR)},
        }
    )


@bp.put("/system/settings")
@login_required
def system_settings_put():
    body = request.get_json(silent=True) or {}
    result = manager().apply_settings(body)
    return ok(result)


@bp.get("/system/logs")
@login_required
def system_logs():
    limit = min(int(request.args.get("limit", 300)), 2000)
    level = request.args.get("level") or None
    return ok(BUS.tail(limit=limit, level=level))


@bp.get("/system/events")
@login_required
def system_events():
    since = int(request.args.get("since", 0))
    return ok({"events": manager().events_since(since), "seq": manager().events.seq})


@bp.get("/system/events/stream")
def system_events_stream():
    token = request.args.get("token")
    if manager().store.config.auth.requireLogin and not auth().sessions.validate(token):
        return fail("未登录", 401)
    engine = manager()
    bus = engine.events

    def generate():
        last_seq = int(request.args.get("since", 0))
        yield "retry: 3000\n\n"
        pending = bus.since(last_seq)
        for event in pending:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        import queue

        channel: queue.Queue = queue.Queue(maxsize=200)
        unsubscribe = bus.subscribe(lambda event: channel.put(event) if not channel.full() else None)
        try:
            last_ping = time.time()
            while True:
                try:
                    event = channel.get(timeout=5)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except queue.Empty:
                    pass
                if time.time() - last_ping > 15:
                    last_ping = time.time()
                    yield ": ping\n\n"
        finally:
            unsubscribe()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@bp.post("/system/restart")
@login_required
def system_restart():
    manager().restart_requested = True
    return ok({"message": "服务将在 1 秒内重启"})


@bp.post("/system/shutdown")
@login_required
def system_shutdown():
    manager().shutdown_requested = True
    return ok({"message": "服务即将停止"})


@bp.get("/system/config/export")
@login_required
def system_config_export():
    payload = manager().store.config
    from ..config import _dataclass_to_dict

    content = json.dumps(_dataclass_to_dict(payload), ensure_ascii=False, indent=2)
    return Response(
        content,
        mimetype="application/json",
        headers={"Content-Disposition": 'attachment; filename="chengxing-onvif-backup.json"'},
    )


# --------------------------------------------------------------------------------------
# 开机自启 / 服务
# --------------------------------------------------------------------------------------


@bp.get("/service/autostart")
@login_required
def service_autostart_status():
    from ..core import autostart

    return ok(autostart.status())


@bp.post("/service/autostart")
@login_required
def service_autostart_set():
    from ..core import autostart

    body = request.get_json(silent=True) or {}
    enabled = bool(body.get("enabled", True))
    mode = str(body.get("mode") or "auto")
    success, message = autostart.install(mode=mode) if enabled else autostart.uninstall()
    return ok({"message": message, "status": autostart.status()}) if success else fail(message)


@bp.post("/service/launch")
@login_required
def service_launch():
    """供桌面端/脚本调用：返回静默启动命令提示（不实际执行）。"""
    from ..core import autostart

    return ok({"launcher": str(autostart.LAUNCHER), "pythonw": str(autostart._pythonw())})


@bp.post("/import/tonys")
@login_required
def import_tonys():
    body = request.get_json(silent=True) or {}
    path = Path(str(body.get("path") or "")).expanduser()
    if not path.exists():
        return fail("配置文件不存在")
    count, warnings = manager().store.import_legacy_config(path)
    return ok({"imported": count, "warnings": warnings})


# --------------------------------------------------------------------------------------
# 硬件与模型
# --------------------------------------------------------------------------------------


@bp.get("/hardware")
@login_required
def hardware():
    engine = manager()
    return ok(engine.hardware.to_dict())


@bp.post("/hardware/refresh")
@login_required
def hardware_refresh():
    engine = manager()

    def work(progress):
        progress(0.1, "正在检测显卡与编码器…")
        engine.hardware = refresh_profile(engine.settings)
        progress(1.0, "完成")
        return engine.hardware.to_dict()

    job = jobs().start("刷新硬件画像", work)
    return ok(job.to_dict())


@bp.get("/models")
@login_required
def models():
    custom = list_custom_models()
    return ok(
        {
            "registry": list_models(),
            "custom": custom,
            "backends": manager().hardware.inference,
        }
    )


@bp.post("/models/<key>/download")
@login_required
def model_download(key: str):
    spec = resolve_model(key)
    if not spec or not spec.url:
        return fail("该模型没有可下载地址")

    def work(progress):
        from ..detect.models import download_model

        def report(done: int, total: int) -> None:
            progress(done / total if total else 0.0, f"下载中 {done // 1048576}MB")

        success, message = download_model(key, progress=report)
        if not success:
            raise RuntimeError(message)
        return {"key": key, "message": message}

    job = jobs().start(f"下载模型 {spec.name}", work)
    return ok(job.to_dict())


@bp.delete("/models/<key>")
@login_required
def model_delete(key: str):
    from ..detect.models import delete_model

    success, message = delete_model(key)
    return ok({"message": message}) if success else fail(message)


@bp.post("/models/<key>/export")
@login_required
def model_export(key: str):
    body = request.get_json(silent=True) or {}
    fmt = str(body.get("format") or "onnx").lower()
    if fmt not in ("onnx", "openvino"):
        return fail("仅支持导出 onnx / openvino")
    spec = resolve_model(key)
    if not spec:
        return fail("未知模型")
    if spec.family != "pt":
        return fail("仅 .pt 模型可导出")

    def work(progress):
        from ultralytics import YOLO

        from ..detect.models import model_path

        path = model_path(spec)
        if not path:
            from ..detect.models import download_model

            success, message = download_model(key)
            if not success:
                raise RuntimeError(message)
            path = model_path(spec)
        progress(0.1, "加载模型…")
        model = YOLO(str(path))
        progress(0.2, f"导出 {fmt}（可能需要数分钟）…")
        exported = model.export(format="openvino" if fmt == "openvino" else "onnx", imgsz=spec.inputSize)
        progress(1.0, "导出完成")
        return {"format": fmt, "path": str(exported)}

    job = jobs().start(f"导出 {spec.name} → {fmt}", work)
    return ok(job.to_dict())


@bp.get("/jobs")
@login_required
def jobs_list():
    return ok(jobs().list())


@bp.get("/jobs/<job_id>")
@login_required
def job_get(job_id: str):
    job = jobs().get(job_id)
    return ok(job.to_dict()) if job else fail("任务不存在", 404)


@bp.get("/onvif/profiles")
@login_required
def onvif_profiles():
    return ok(list_profiles())


# --------------------------------------------------------------------------------------
# 摄像机
# --------------------------------------------------------------------------------------


@bp.get("/cameras")
@login_required
def cameras_list():
    engine = manager()
    return ok(
        {
            "cameras": [engine.cameras[c.id].state() if c.id in engine.cameras else {
                "id": c.id,
                "name": c.name,
                "status": "stopped",
                "config": c.public_dict(),
            } for c in engine.store.cameras]
        }
    )


@bp.post("/cameras")
@login_required
def cameras_create():
    body = request.get_json(silent=True) or {}
    if not body.get("name"):
        return fail("请填写摄像机名称")
    if not (body.get("source") or {}).get("mainUrl"):
        return fail("请填写主码流地址")
    config = camera_from_payload(body)
    runtime = manager().add_camera(config)
    return ok(runtime.state())


@bp.get("/cameras/<int:camera_id>")
@login_required
def cameras_get(camera_id: int):
    engine = manager()
    runtime = engine.cameras.get(camera_id)
    if runtime:
        return ok(runtime.state())
    config = engine.store.get_camera(camera_id)
    if not config:
        return fail("摄像机不存在", 404)
    return ok({"id": config.id, "name": config.name, "status": "stopped", "config": config.public_dict()})


@bp.put("/cameras/<int:camera_id>")
@login_required
def cameras_update(camera_id: int):
    body = request.get_json(silent=True) or {}
    runtime = manager().update_camera(camera_id, body)
    if not runtime:
        return fail("摄像机不存在", 404)
    return ok(runtime.state())


@bp.delete("/cameras/<int:camera_id>")
@login_required
def cameras_delete(camera_id: int):
    ok_delete = manager().delete_camera(camera_id)
    return ok() if ok_delete else fail("摄像机不存在", 404)


@bp.post("/cameras/<int:camera_id>/start")
@login_required
def cameras_start(camera_id: int):
    success, message = manager().start_camera(camera_id)
    return ok({"message": message}) if success else fail(message)


@bp.post("/cameras/<int:camera_id>/stop")
@login_required
def cameras_stop(camera_id: int):
    success, message = manager().stop_camera(camera_id)
    return ok({"message": message}) if success else fail(message)


@bp.post("/cameras/<int:camera_id>/restart")
@login_required
def cameras_restart(camera_id: int):
    success, message = manager().restart_camera(camera_id)
    return ok({"message": message}) if success else fail(message)


@bp.post("/cameras/<int:camera_id>/test-event")
@login_required
def cameras_test_event(camera_id: int):
    runtime = manager().cameras.get(camera_id)
    if not runtime:
        return fail("摄像机未运行")
    runtime.trigger_test()
    return ok({"message": "测试事件已发送（ONVIF + 推送）"})


@bp.post("/cameras/<int:camera_id>/push-test")
@login_required
def cameras_push_test(camera_id: int):
    success, message = manager().test_push(camera_id)
    return ok({"message": message}) if success else fail(message)


@bp.get("/cameras/<int:camera_id>/snapshot")
@login_required
def cameras_snapshot(camera_id: int):
    runtime = manager().cameras.get(camera_id)
    if not runtime:
        return fail("摄像机未运行", 404)
    data = runtime.snapshot_jpeg()
    if not data:
        return fail("暂时没有可用画面", 404)
    return Response(
        data,
        mimetype="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@bp.get("/cameras/<int:camera_id>/events")
@login_required
def cameras_events(camera_id: int):
    runtime = manager().cameras.get(camera_id)
    if not runtime:
        return fail("摄像机未运行", 404)
    return ok({"events": list(runtime.event_logs)})


@bp.post("/cameras/<int:camera_id>/snapshot/test")
@login_required
def cameras_snapshot_test(camera_id: int):
    engine = manager()
    body = request.get_json(silent=True) or {}
    config = engine.store.get_camera(camera_id)
    url = str(body.get("url") or (config.source.url("main") if config else ""))
    if not url:
        return fail("请填写视频地址")
    data = capture_jpeg(engine.ffmpeg, url)
    if not data:
        return fail("抓拍失败，请检查地址与网络")
    return Response(data, mimetype="image/jpeg")


@bp.post("/probe")
@login_required
def probe():
    body = request.get_json(silent=True) or {}
    url = str(body.get("url") or "")
    if not url:
        return fail("请填写视频地址")
    engine = manager()
    ffprobe = engine.ffmpeg.ffprobe if engine.ffmpeg else None
    result = probe_media(url, ffprobe)
    return ok(result) if result.get("ok") else fail(result.get("error") or "探测失败", 400, detail=result)


@bp.get("/probe/templates")
@login_required
def probe_templates():
    host = request.args.get("host") or "192.168.1.64"
    return ok(guess_stream_urls(host, "admin", ""))

