from robosikg.perception.base import Detection
from robosikg.tracking.mot import iou
from robosikg.tracking.mot import MultiObjectTracker

def test_iou_basic():
    a = (0, 0, 10, 10)
    b = (5, 5, 15, 15)
    assert 0 < iou(a, b) < 1


def test_tracker_class_mismatch_and_expiration():
    tracker = MultiObjectTracker(iou_match_thresh=0.3, max_age_frames=1, min_hits=1)

    det_person = Detection(cls="person", score=0.9, bbox_xyxy=(0, 0, 10, 10))
    _removed, confirmed = tracker.step([det_person])
    assert len(confirmed) == 1
    assert confirmed[0].track_id == 0

    det_car = Detection(cls="car", score=0.8, bbox_xyxy=(0, 0, 10, 10))
    removed, confirmed = tracker.step([det_car])
    assert len(removed) == 0
    assert {t.cls for t in confirmed} == {"person", "car"}

    removed, _confirmed = tracker.step([])
    removed_ids = {t.track_id for t in removed}
    assert 0 in removed_ids
