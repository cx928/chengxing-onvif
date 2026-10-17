"""密码与令牌安全 / Password hashing and session tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
import time

PBKDF2_ITERATIONS = 260_000
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "cx123456"


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """返回 (hash_b64, salt_b64)。"""
    salt_bytes = base64.b64decode(salt) if salt else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, PBKDF2_ITERATIONS)
    return base64.b64encode(digest).decode("ascii"), base64.b64encode(salt_bytes).decode("ascii")


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    if not password_hash or not salt:
        return False
    try:
        candidate, _ = hash_password(password, salt)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, password_hash)


def password_strength(password: str) -> tuple[int, list[str]]:
    """返回 (0-4 分数, 提示列表)。"""
    score = 0
    hints: list[str] = []
    if len(password) >= 8:
        score += 1
    else:
        hints.append("至少 8 个字符")
    if len(password) >= 12:
        score += 1
    if any(ch.isdigit() for ch in password):
        score += 1
    else:
        hints.append("包含数字")
    if any(ch.isupper() for ch in password) and any(ch.islower() for ch in password):
        score += 1
    else:
        hints.append("包含大小写字母")
    if any(not ch.isalnum() for ch in password):
        score = min(4, score + 1)
    else:
        hints.append("包含符号更安全")
    return min(4, score), hints


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


class SessionStore:
    """内存会话存储（Bearer Token）。"""

    def __init__(self, ttl: int = 86400) -> None:
        self.ttl = ttl
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, username: str, *, ttl: int | None = None) -> tuple[str, float]:
        token = random_token(32)
        expires = time.time() + (ttl or self.ttl)
        with self._lock:
            self._sessions[token] = {"username": username, "expires": expires, "created": time.time()}
        return token, expires

    def validate(self, token: str | None) -> dict | None:
        if not token:
            return None
        with self._lock:
            session = self._sessions.get(token)
            if not session:
                return None
            if session["expires"] < time.time():
                self._sessions.pop(token, None)
                return None
            return dict(session)

    def revoke(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)

    def revoke_user(self, username: str) -> None:
        with self._lock:
            for token in [t for t, s in self._sessions.items() if s["username"] == username]:
                self._sessions.pop(token, None)

    def cleanup(self) -> None:
        now = time.time()
        with self._lock:
            for token in [t for t, s in self._sessions.items() if s["expires"] < now]:
                self._sessions.pop(token, None)


class LoginThrottle:
    """简单的登录失败限速，防止暴力破解。"""

    def __init__(self, max_attempts: int = 8, window: float = 300.0, lock_for: float = 120.0) -> None:
        self.max_attempts = max_attempts
        self.window = window
        self.lock_for = lock_for
        self._failures: dict[str, list[float]] = {}
        self._locked: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_locked(self, key: str) -> tuple[bool, float]:
        with self._lock:
            until = self._locked.get(key, 0)
            if until > time.time():
                return True, until - time.time()
            return False, 0.0

    def record_failure(self, key: str) -> None:
        now = time.time()
        with self._lock:
            attempts = [t for t in self._failures.get(key, []) if now - t < self.window]
            attempts.append(now)
            self._failures[key] = attempts
            if len(attempts) >= self.max_attempts:
                self._locked[key] = now + self.lock_for
                self._failures[key] = []

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked.pop(key, None)
