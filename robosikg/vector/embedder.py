from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torchvision
from torchvision.transforms.functional import to_tensor
import torchvision.transforms as T

from .routing import RoutingEmbedding, RoutingStats, choose_topk


@dataclass
class EmbedResult:
    vec: np.ndarray              # float32 (D,)
    stats: RoutingStats
    logits_meta: dict            # model-readable metadata (topk, etc.)


class RegionEmbedder:
    """
    Baseline visual embedder:
    - crop region from frame
    - run ResNet18 backbone -> embedding
    - apply RoutingEmbedding -> routed embedding + logits metadata
    """

    def __init__(
        self,
        dim: int = 512,
        device: str = "cuda",
        centroid_k: int = 128,
        tau: float = 3.0,
        top_k: Optional[int] = None,
        pretrained: bool = True,
        require_cuda: bool = True,
        gamma_init: float = 0.0,
    ):
        if device not in {"cpu", "cuda"}:
            raise ValueError("device must be 'cpu' or 'cuda'")
        if device == "cuda" and not torch.cuda.is_available():
            if require_cuda:
                raise RuntimeError(
                    "CUDA device requested but not available. "
                    "Run with --device cpu or configure CUDA correctly."
                )
            device = "cpu"

        self.device = device
        self.pretrained = pretrained

        try:
            weights = torchvision.models.ResNet18_Weights.DEFAULT if pretrained else None
            self.backbone = torchvision.models.resnet18(weights=weights)
        except Exception as exc:
            if pretrained:
                raise RuntimeError(
                    "Failed to load pretrained ResNet18 weights. "
                    "Ensure weights are cached or internet access is available. "
                    "Run with --no-pretrained for offline mode."
                ) from exc
            raise

        self.backbone.fc = nn.Identity()
        self.backbone.eval().to(device)

        backbone_dim = 512
        self.proj = nn.Linear(backbone_dim, dim, bias=False).eval().to(device)

        if pretrained:
            self.preprocess = torchvision.models.ResNet18_Weights.DEFAULT.transforms()
        else:
            self.preprocess = T.Compose(
                [
                    T.Resize((224, 224)),
                    T.Normalize(
                        mean=(0.485, 0.456, 0.406),
                        std=(0.229, 0.224, 0.225),
                    ),
                ]
            )

        if top_k is None:
            top_k = choose_topk(centroid_k)
        self.router = (
            RoutingEmbedding(
                dim=dim,
                num_centroids=centroid_k,
                top_k=top_k,
                tau=tau,
                gamma_init=gamma_init,
            )
            .eval()
            .to(device)
        )

    @torch.inference_mode()
    def embed_region(self, bgr: np.ndarray, bbox_xyxy: tuple[int, int, int, int]) -> EmbedResult:
        x1, y1, x2, y2 = bbox_xyxy
        h, w = bgr.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w - 1, x2), min(h - 1, y2)

        crop = bgr[y1:y2, x1:x2]
        if crop.size == 0:
            # fall back: embed whole frame
            crop = bgr

        rgb = crop[..., ::-1].copy()
        x = to_tensor(rgb)  # (3,H,W)
        x = self.preprocess(x).unsqueeze(0).to(self.device)  # (1,3,H,W)

        feat = self.backbone(x)     # (1,512)
        vec = self.proj(feat)       # (1,D)
        vec = vec / (vec.norm(dim=-1, keepdim=True) + 1e-9)

        routed, stats, meta = self.router(vec)  # (1,D)
        routed = routed / (routed.norm(dim=-1, keepdim=True) + 1e-9)

        out = routed.squeeze(0).detach().cpu().float().numpy()
        return EmbedResult(vec=out, stats=stats, logits_meta=meta)
