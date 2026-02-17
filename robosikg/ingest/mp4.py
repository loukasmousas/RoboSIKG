from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterator, Optional

import cv2
import numpy as np


@dataclass(frozen=True)
class Frame:
    index: int
    t_ns: int
    bgr: np.ndarray  # uint8 HxWx3


def frame_timestamp_ns(frame_index: int, src_fps: float, timestamp_origin_ns: int = 0) -> int:
    if frame_index < 0:
        raise ValueError("frame_index must be >= 0")
    if src_fps <= 0:
        raise ValueError("src_fps must be > 0")
    return int(timestamp_origin_ns + round((frame_index / src_fps) * 1e9))


def iter_mp4(
    path: str,
    sample_fps: float = 5.0,
    max_frames: Optional[int] = None,
    timestamp_origin_ns: int = 0,
) -> Iterator[Frame]:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if sample_fps <= 0:
        raise ValueError("sample_fps must be > 0")

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(1, int(round(src_fps / sample_fps)))

    i = 0
    emitted = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if i % stride == 0:
            t_ns = frame_timestamp_ns(i, src_fps, timestamp_origin_ns=timestamp_origin_ns)
            yield Frame(index=i, t_ns=t_ns, bgr=frame)
            emitted += 1
            if max_frames is not None and emitted >= max_frames:
                break
        i += 1

    cap.release()
