from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Detection:
    cls: str
    score: float
    bbox_xyxy: tuple[int, int, int, int]  # pixel coords


class Detector(Protocol):
    def detect(self, bgr: np.ndarray) -> list[Detection]:
        ...
