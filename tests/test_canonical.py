import pytest

from robosikg.ids.canonical import SourceRef, canon_event, canon_frame, canon_track


def test_canon_event_sorted_and_deduped_keys():
    src = SourceRef(source_id="demo")
    a = "urn:sha256:" + "a" * 64
    b = "urn:sha256:" + "b" * 64
    c1 = canon_event(src, "near", 100, 200, [b, a, b])
    c2 = canon_event(src, "near", 100, 200, [a, b])
    assert c1 == c2


def test_canon_frame_rejects_negative_index():
    src = SourceRef(source_id="demo")
    with pytest.raises(ValueError):
        canon_frame(src, -1, 0)


def test_canon_track_rejects_negative_track_id():
    src = SourceRef(source_id="demo")
    with pytest.raises(ValueError):
        canon_track(src, -1)
