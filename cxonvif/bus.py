"""事件总线 / In-process event bus."""

from __future__ import annotations

import queue
import threading
from collections import deque
from typing import Any, Callable

Listener = Callable[[dict], None]


class EventBus:
    """轻量发布订阅：检测事件、状态事件、日志事件均可复用。"""

    def __init__(self, history: int = 500) -> None:
        self._listeners: list[Listener] = []
        self._lock = threading.Lock()
        self.history: deque[dict] = deque(maxlen=history)
        self._seq = 0

    @property
    def seq(self) -> int:
        return self._seq

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            self.unsubscribe(listener)

        return unsubscribe

    def unsubscribe(self, listener: Listener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def publish(self, event: dict) -> None:
        with self._lock:
            self._seq += 1
            event.setdefault("seq", self._seq)
            self.history.append(event)
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:  # pragma: no cover - 订阅者异常不应影响发布
                pass

    def since(self, seq: int = 0, limit: int = 200) -> list[dict]:
        with self._lock:
            events = [e for e in self.history if e.get("seq", 0) > seq]
        return events[-limit:]
