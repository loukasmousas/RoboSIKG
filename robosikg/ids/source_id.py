from __future__ import annotations

import re
from pathlib import Path

_AUTO_SOURCE_IDS = {"auto", "default", "demo_video", "web_demo"}


def derive_source_id(raw: str | None, mp4_path: str | Path, fallback: str = "demo_video") -> str:
    """Return a stable source id, deriving from mp4 filename for generic/empty values.

    Args:
        raw: User-provided source id (can be empty/"auto"/generic).
        mp4_path: Input video path used for deterministic fallback naming.
        fallback: Final fallback if filename normalization yields empty.
    """
    source = (raw or "").strip()
    if source and source.lower() not in _AUTO_SOURCE_IDS:
        return source

    stem = Path(mp4_path).stem.strip() or fallback
    sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "_", stem).strip("._")
    return sanitized or fallback

