from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from robosikg.perception.base import Detection
from .kalman import KalmanBox


def iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1, ax2 - ax1) * max(1, ay2 - ay1)
    area_b = max(1, bx2 - bx1) * max(1, by2 - by1)
    return float(inter / (area_a + area_b - inter))


@dataclass
class Track:
    track_id: int
    cls: str
    kf: KalmanBox
    age: int = 0
    hits: int = 0
    time_since_update: int = 0
    last_score: float = 0.0

    def predict(self) -> None:
        self.kf.predict()
        self.age += 1
        self.time_since_update += 1

    def update(self, det: Detection) -> None:
        self.kf.update(det.bbox_xyxy)
        self.hits += 1
        self.time_since_update = 0
        self.last_score = det.score

    def bbox(self) -> tuple[int, int, int, int]:
        return self.kf.to_xyxy()


class MultiObjectTracker:
    def __init__(self, iou_match_thresh: float = 0.3, max_age_frames: int = 15, min_hits: int = 2):
        self.iou_match_thresh = iou_match_thresh
        self.max_age_frames = max_age_frames
        self.min_hits = min_hits
        self._next_id = 0
        self.tracks: list[Track] = []

    def step(self, detections: list[Detection]) -> tuple[list[Track], list[Track]]:
        # predict
        for tr in self.tracks:
            tr.predict()

        if len(self.tracks) == 0:
            for det in detections:
                self._start_track(det)
            return [], self._confirmed()

        # cost matrix (1 - IoU), only same class matches
        cost = np.ones((len(self.tracks), len(detections)), dtype=np.float32)
        for i, tr in enumerate(self.tracks):
            for j, det in enumerate(detections):
                if tr.cls != det.cls:
                    continue
                cost[i, j] = 1.0 - iou(tr.bbox(), det.bbox_xyxy)

        row_ind, col_ind = linear_sum_assignment(cost)
        matched_tracks = set()
        matched_dets = set()

        for i, j in zip(row_ind.tolist(), col_ind.tolist()):
            if cost[i, j] > (1.0 - self.iou_match_thresh):
                continue
            self.tracks[i].update(detections[j])
            matched_tracks.add(i)
            matched_dets.add(j)

        # start new tracks for unmatched dets
        for j, det in enumerate(detections):
            if j not in matched_dets:
                self._start_track(det)

        # retire dead tracks
        survivors: list[Track] = []
        removed: list[Track] = []
        for tr in self.tracks:
            if tr.time_since_update > self.max_age_frames:
                removed.append(tr)
            else:
                survivors.append(tr)
        self.tracks = survivors

        return removed, self._confirmed()

    def _start_track(self, det: Detection) -> None:
        tr = Track(track_id=self._next_id, cls=det.cls, kf=KalmanBox(det.bbox_xyxy), hits=1, last_score=det.score)
        self._next_id += 1
        self.tracks.append(tr)

    def _confirmed(self) -> list[Track]:
        return [t for t in self.tracks if t.hits >= self.min_hits]
