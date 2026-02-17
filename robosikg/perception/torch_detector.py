from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import torch
import torchvision
from torchvision.transforms.functional import to_tensor

from .base import Detection, Detector


COCO_CLS = [
    "__background__","person","bicycle","car","motorcycle","airplane","bus","train","truck","boat",
    "traffic light","fire hydrant","N/A","stop sign","parking meter","bench","bird","cat","dog",
    "horse","sheep","cow","elephant","bear","zebra","giraffe","N/A","backpack","umbrella","N/A",
    "N/A","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball","kite","baseball bat",
    "baseball glove","skateboard","surfboard","tennis racket","bottle","N/A","wine glass","cup","fork",
    "knife","spoon","bowl","banana","apple","sandwich","orange","broccoli","carrot","hot dog","pizza",
    "donut","cake","chair","couch","potted plant","bed","N/A","dining table","N/A","N/A","toilet","N/A",
    "tv","laptop","mouse","remote","keyboard","cell phone","microwave","oven","toaster","sink","refrigerator",
    "N/A","book","clock","vase","scissors","teddy bear","hair drier","toothbrush"
]


@dataclass
class TorchVisionFRCNN(Detector):
    score_thresh: float = 0.5
    device: str = "cuda"
    pretrained: bool = True
    require_cuda: bool = True
    _model: Optional[torch.nn.Module] = None

    def __post_init__(self) -> None:
        if self.device not in {"cpu", "cuda"}:
            raise ValueError("device must be 'cpu' or 'cuda'")
        if self.device == "cuda" and not torch.cuda.is_available():
            if self.require_cuda:
                raise RuntimeError(
                    "CUDA device requested but not available. "
                    "Run with --device cpu or configure CUDA correctly."
                )
            self.device = "cpu"

    def _ensure(self) -> torch.nn.Module:
        if self._model is None:
            try:
                if self.pretrained:
                    model = torchvision.models.detection.fasterrcnn_resnet50_fpn(
                        weights=torchvision.models.detection.FasterRCNN_ResNet50_FPN_Weights.DEFAULT
                    )
                else:
                    model = torchvision.models.detection.fasterrcnn_resnet50_fpn(
                        weights=None,
                        weights_backbone=None,
                    )
            except Exception as exc:
                if self.pretrained:
                    raise RuntimeError(
                        "Failed to load pretrained FasterRCNN weights. "
                        "Ensure weights are cached or internet access is available. "
                        "Run with --no-pretrained for offline mode."
                    ) from exc
                raise
            model.eval()
            model.to(self.device)
            self._model = model
        return self._model

    @torch.inference_mode()
    def detect(self, bgr: np.ndarray) -> list[Detection]:
        model = self._ensure()
        rgb = bgr[..., ::-1].copy()
        x = to_tensor(rgb).to(self.device)
        out = model([x])[0]

        dets: list[Detection] = []
        boxes = out["boxes"].detach().cpu().numpy()
        scores = out["scores"].detach().cpu().numpy()
        labels = out["labels"].detach().cpu().numpy()

        h, w = bgr.shape[:2]
        for box, sc, lab in zip(boxes, scores, labels):
            if float(sc) < self.score_thresh:
                continue
            x1, y1, x2, y2 = box.tolist()
            x1 = int(max(0, min(w - 1, round(x1))))
            y1 = int(max(0, min(h - 1, round(y1))))
            x2 = int(max(0, min(w - 1, round(x2))))
            y2 = int(max(0, min(h - 1, round(y2))))
            cls = COCO_CLS[int(lab)] if int(lab) < len(COCO_CLS) else f"coco_{int(lab)}"
            dets.append(Detection(cls=cls, score=float(sc), bbox_xyxy=(x1, y1, x2, y2)))
        return dets
