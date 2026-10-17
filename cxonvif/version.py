"""版本信息 / Version information."""

from __future__ import annotations

CURRENT_VERSION = "1.0.1"
VERSION_TUPLE = (1, 0, 1)
BUILD = "2026.10"
CODENAME = "启明"

# 配置结构版本，用于数据迁移
CONFIG_SCHEMA_VERSION = 1


def version_string() -> str:
    return f"{CURRENT_VERSION} ({BUILD})"


def parse_version(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in value.lstrip("vV").split(".")[:3])
    except (ValueError, AttributeError):
        return (0, 0, 0)


def is_newer(current: str, latest: str) -> bool:
    return parse_version(latest) > parse_version(current)
