"""轻量 IoU 跟踪器 / Lightweight IoU tracker.

用于给检测框分配稳定 ID，并在事件里去重（同一目标不会反复触发）。
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from .types import Detection


@dataclass
class Track:
    track_id: int
    label: str
    group: str
    box: tuple[float, float, float, float]
    hits: int = 1
    age: int = 0
    missing: int = 0
    history: list[tuple[float, float]] = field(default_factory=list)


class IoUTracker:
    def __init__(self, iou_threshold: float = 0.25, max_missing: int = 8) -> None:
        self.iou_threshold = iou_threshold
        self.max_missing = max_missing
        self._ids = itertools.count(1)
        self.tracks: list[Track] = []

    def reset(self) -> None:
        self.tracks.clear()

    def update(self, detections: list[Detection]) -> list[Detection]:
        for track in self.tracks:
            track.age += 1
            track.missing += 1

        unmatched = list(detections)
        matched_tracks: list[Track] = []

        for track in sorted(self.tracks, key=lambda t: -t.hits):
            best_index = -1
            best_iou = self.iou_threshold
            probe = Detection(label=track.label, confidence=1.0, box=track.box, group=track.group)
            for index, detection in enumerate(unmatched):
                if detection.group != track.group:
                    continue
                iou = probe.iou(detection)
                if iou > best_iou:
                    best_iou = iou
                    best_index = index
            if best_index >= 0:
                detection = unmatched.pop(best_index)
                detection.track_id = track.track_id
                track.box = detection.box
                track.label = detection.label
                track.hits += 1
                track.missing = 0
                track.history.append(detection.center)
                if len(track.history) > 30:
                    track.history.pop(0)
                matched_tracks.append(track)

        for detection in unmatched:
            track = Track(
                track_id=next(self._ids),
                label=detection.label,
                group=detection.group,
                box=detection.box,
                history=[detection.center],
            )
            detection.track_id = track.track_id
            self.tracks.append(track)
            matched_tracks.append(track)

        self.tracks = [t for t in self.tracks if t.missing <= self.max_missing]
        return detections
