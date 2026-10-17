"""日志总线：文件 + 内存环形缓冲 + 实时订阅。"""

from __future__ import annotations

import collections
import logging
import logging.handlers
import queue
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import LOG_FILE


@dataclass
class LogRecord:
    time: str
    level: str
    source: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"time": self.time, "level": self.level, "source": self.source, "message": self.message}


class LogBus:
    """线程安全的事件日志缓冲，供 Web UI / 桌面端实时读取。"""

    def __init__(self, capacity: int = 3000) -> None:
        self._records: collections.deque[LogRecord] = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []
        self._seq = 0

    @property
    def seq(self) -> int:
        return self._seq

    def append(self, level: str, source: str, message: str) -> None:
        from .util import local_iso

        record = LogRecord(local_iso(), level.upper(), source, message)
        with self._lock:
            self._records.append(record)
            self._seq += 1
            for sub in list(self._subscribers):
                try:
                    sub.put_nowait(record)
                except queue.Full:
                    pass

    def tail(self, limit: int = 200, level: str | None = None) -> list[dict[str, str]]:
        with self._lock:
            records = list(self._records)
        if level:
            allowed = _level_rank(level)
            records = [r for r in records if _level_rank(r.level) >= allowed]
        return [r.to_dict() for r in records[-limit:]]

    def subscribe(self) -> queue.Queue:
        sub: queue.Queue = queue.Queue(maxsize=500)
        with self._lock:
            self._subscribers.append(sub)
        return sub

    def unsubscribe(self, sub: queue.Queue) -> None:
        with self._lock:
            if sub in self._subscribers:
                self._subscribers.remove(sub)


_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


def _level_rank(level: str) -> int:
    return _LEVELS.get(level.upper(), 20)


BUS = LogBus()


class _BusHandler(logging.Handler):
    def __init__(self, source: str = "server") -> None:
        super().__init__()
        self.source = source

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            if record.exc_info:
                message += " | " + logging.Formatter().formatException(record.exc_info)
            BUS.append(record.levelname, self.source, message)
        except Exception:  # pragma: no cover - 日志本身不应抛出
            pass


def init_logging(level: str = "INFO", log_file: Path = LOG_FILE, silent: bool = False) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=4 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        pass

    if not silent and sys.stderr is not None:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        root.addHandler(stream)

    root.addHandler(_BusHandler())


def log(level: str, message: str, source: str = "app") -> None:
    """写入日志总线，同时交给标准 logging（落盘 + 控制台）。"""
    logging.getLogger("cxonvif").log(getattr(logging, level.upper(), logging.INFO), f"[{source}] {message}")


def info(message: str, source: str = "app") -> None:
    log("INFO", message, source)


def warn(message: str, source: str = "app") -> None:
    log("WARNING", message, source)


def error(message: str, source: str = "app") -> None:
    log("ERROR", message, source)
