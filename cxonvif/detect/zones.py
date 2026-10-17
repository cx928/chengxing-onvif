"""区域规则 / Detection zones (include / exclude polygons)."""

from __future__ import annotations

from ..config import Zone
from .types import Detection


def point_in_polygon(x: float, y: float, points: list[tuple[float, float]]) -> bool:
    """射线法判断点是否在多边形内。"""
    if len(points) < 3:
        return False
    inside = False
    j = len(points) - 1
    for i in range(len(points)):
        xi, yi = points[i]
        xj, yj = points[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def zone_matches(zone: Zone, detection: Detection) -> bool:
    if not zone.enabled:
        return False
    if zone.targets and detection.group not in zone.targets:
        return False
    cx, cy = detection.center
    points = zone.normalized_points()
    if len(points) < 3:
        return False
    return point_in_polygon(cx, cy, points)


def filter_detections(detections: list[Detection], zones: list[Zone]) -> list[Detection]:
    """include 区域取并集，exclude 区域直接剔除；无 include 时全图生效。"""
    includes = [z for z in zones if z.enabled and z.type == "include"]
    excludes = [z for z in zones if z.enabled and z.type == "exclude"]

    result: list[Detection] = []
    for detection in detections:
        if any(zone_matches(zone, detection) for zone in excludes):
            continue
        if includes:
            applicable = [z for z in includes if not z.targets or detection.group in z.targets]
            if applicable and not any(zone_matches(zone, detection) for zone in applicable):
                continue
        result.append(detection)
    return result
