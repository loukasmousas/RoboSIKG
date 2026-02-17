from __future__ import annotations

import numpy as np


class KalmanBox:
    """
    Constant-velocity Kalman filter on bbox center + size: [cx, cy, w, h, vx, vy, vw, vh].
    This is a lightweight MOT baseline suitable for a Cookoff demo.
    """

    def __init__(self, xyxy: tuple[int, int, int, int]):
        x1, y1, x2, y2 = xyxy
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        w = max(1.0, (x2 - x1))
        h = max(1.0, (y2 - y1))

        self.x = np.array([cx, cy, w, h, 0, 0, 0, 0], dtype=np.float32)

        self.P = np.eye(8, dtype=np.float32) * 10.0
        self.F = np.eye(8, dtype=np.float32)
        for i in range(4):
            self.F[i, i + 4] = 1.0  # dt=1 frame

        self.Q = np.eye(8, dtype=np.float32) * 0.01
        self.R = np.eye(4, dtype=np.float32) * 1.0
        self.H = np.zeros((4, 8), dtype=np.float32)
        self.H[0, 0] = 1
        self.H[1, 1] = 1
        self.H[2, 2] = 1
        self.H[3, 3] = 1

    def predict(self) -> np.ndarray:
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.x.copy()

    def update(self, xyxy: tuple[int, int, int, int]) -> None:
        x1, y1, x2, y2 = xyxy
        z = np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0, max(1.0, x2 - x1), max(1.0, y2 - y1)], dtype=np.float32)

        y = z - (self.H @ self.x)
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)

        self.x = self.x + K @ y
        I = np.eye(8, dtype=np.float32)
        self.P = (I - K @ self.H) @ self.P

    def to_xyxy(self) -> tuple[int, int, int, int]:
        cx, cy, w, h = self.x[:4]
        x1 = int(round(cx - w / 2.0))
        y1 = int(round(cy - h / 2.0))
        x2 = int(round(cx + w / 2.0))
        y2 = int(round(cy + h / 2.0))
        return x1, y1, x2, y2
