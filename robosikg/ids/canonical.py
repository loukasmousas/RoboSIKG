from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRef:
    source_id: str  # e.g., filename stem or ROS topic


def canon_frame(source: SourceRef, frame_index: int, t_ns: int) -> str:
    if frame_index < 0:
        raise ValueError("frame_index must be >= 0")
    if t_ns < 0:
        raise ValueError("t_ns must be >= 0")
    return f"frame:{source.source_id}:{frame_index}:{t_ns}"


def canon_region(frame_uri: str, bbox_xyxy: tuple[int, int, int, int], cls: str) -> str:
    x1, y1, x2, y2 = bbox_xyxy
    if x2 < x1 or y2 < y1:
        raise ValueError("bbox_xyxy must satisfy x2 >= x1 and y2 >= y1")
    return f"region:{frame_uri}:{cls}:{x1},{y1},{x2},{y2}"


def canon_track(source: SourceRef, track_id: int) -> str:
    if track_id < 0:
        raise ValueError("track_id must be >= 0")
    return f"track:{source.source_id}:{track_id}"


def canon_event(source: SourceRef, event_type: str, t0_ns: int, t1_ns: int, keys: list[str]) -> str:
    if t0_ns < 0 or t1_ns < 0:
        raise ValueError("event timestamps must be >= 0")
    if t1_ns < t0_ns:
        raise ValueError("t1_ns must be >= t0_ns")
    # keys are URIs (tracks/regions) included deterministically
    joined = ",".join(sorted(set(keys)))
    return f"event:{source.source_id}:{event_type}:{t0_ns}:{t1_ns}:{joined}"
