from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from robosikg.ingest.mp4 import frame_timestamp_ns, iter_mp4


class _FakeCapture:
    def __init__(self, frames: list[np.ndarray], fps: float):
        self._frames = frames
        self._fps = fps
        self._idx = 0

    def isOpened(self) -> bool:  # noqa: N802 - OpenCV API compatibility
        return True

    def get(self, prop: int) -> float:
        if prop == cv2.CAP_PROP_FPS:
            return self._fps
        return 0.0

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._idx >= len(self._frames):
            return False, None
        frame = self._frames[self._idx]
        self._idx += 1
        return True, frame

    def release(self) -> None:
        return None


def test_frame_timestamp_ns_is_deterministic():
    t1 = frame_timestamp_ns(frame_index=30, src_fps=30.0, timestamp_origin_ns=100)
    t2 = frame_timestamp_ns(frame_index=30, src_fps=30.0, timestamp_origin_ns=100)
    assert t1 == t2 == 1_000_000_100


def test_iter_mp4_reproducible_timestamps(monkeypatch, tmp_path: Path):
    path = tmp_path / "dummy.mp4"
    path.write_bytes(b"")

    frames = [np.zeros((4, 4, 3), dtype=np.uint8) for _ in range(6)]

    def _cap_factory(_path: str):
        return _FakeCapture(frames=list(frames), fps=30.0)

    monkeypatch.setattr(cv2, "VideoCapture", _cap_factory)

    first = list(
        iter_mp4(
            str(path),
            sample_fps=10.0,
            max_frames=None,
            timestamp_origin_ns=42,
        )
    )
    second = list(
        iter_mp4(
            str(path),
            sample_fps=10.0,
            max_frames=None,
            timestamp_origin_ns=42,
        )
    )
    assert [f.index for f in first] == [0, 3]
    assert [f.index for f in second] == [0, 3]
    assert [f.t_ns for f in first] == [f.t_ns for f in second]
    assert [f.t_ns for f in first] == [42, 100_000_042]
