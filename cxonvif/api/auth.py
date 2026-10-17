"""API 鉴权 / Bearer token authentication."""

from __future__ import annotations

from functools import wraps

from flask import jsonify, request

from ..config import ConfigStore
from ..security import LoginThrottle, SessionStore


class AuthManager:
    def __init__(self, store: ConfigStore) -> None:
        self.store = store
        self.sessions = SessionStore(ttl=int(store.config.auth.sessionTtl or 86400))
        self.throttle = LoginThrottle()

    # ------------------------------------------------------------------ 登录
    def login(self, username: str, password: str, remote_addr: str) -> tuple[dict, int]:
        locked, remaining = self.throttle.is_locked(remote_addr)
        if locked:
            return {"ok": False, "error": f"尝试次数过多，请 {int(remaining)} 秒后再试"}, 429
        auth = self.store.config.auth
        if username != auth.username:
            self.throttle.record_failure(remote_addr)
            return {"ok": False, "error": "用户名或密码错误"}, 401
        if not self.store.verify_password(password):
            self.throttle.record_failure(remote_addr)
            return {"ok": False, "error": "用户名或密码错误"}, 401
        self.throttle.reset(remote_addr)
        token, expires = self.sessions.create(auth.username)
        return {
            "ok": True,
            "token": token,
            "expires": expires,
            "username": auth.username,
            "mustChangePassword": auth.mustChangePassword,
        }, 200

    # ------------------------------------------------------------------ 校验
    def token_from_request(self) -> str | None:
        header = request.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            return header[7:].strip()
        return request.headers.get("X-CX-Token") or request.args.get("token")

    def current_session(self) -> dict | None:
        return self.sessions.validate(self.token_from_request())

    def require(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not self.store.config.auth.requireLogin:
                return func(*args, **kwargs)
            session = self.current_session()
            if not session:
                return jsonify({"ok": False, "error": "未登录", "code": "unauthorized"}), 401
            return func(*args, **kwargs)

        return wrapper

    # ------------------------------------------------------------------ 改密
    def change_password(self, current: str, new_password: str) -> tuple[dict, int]:
        if not self.store.verify_password(current):
            return {"ok": False, "error": "当前密码不正确"}, 400
        if len(new_password) < 8:
            return {"ok": False, "error": "新密码至少 8 位"}, 400
        if new_password == current:
            return {"ok": False, "error": "新密码不能与旧密码相同"}, 400
        self.store.set_password(new_password, must_change=False)
        self.sessions.revoke_user(self.store.config.auth.username)
        return {"ok": True, "message": "密码已更新，请重新登录"}, 200
