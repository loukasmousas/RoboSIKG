from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


def choose_topk(num_centroids: int, dense_threshold: int = 256) -> Optional[int]:
    # Same policy intent as your TensorFlow implementation: dense for small K, top-k for large K.
    return None if num_centroids <= dense_threshold else 4


@dataclass
class RoutingStats:
    entropy: float
    max_prob: float
    eff_k: float
    gamma: float


class RoutingEmbedding(nn.Module):
    """
    PyTorch port of the centroid-routing + gated residual pattern.

    Stores "model-readable logits metadata" as top-k indices + weights (optional).
    """

    def __init__(
        self,
        dim: int,
        num_centroids: int,
        top_k: Optional[int] = None,
        tau: float = 3.0,
        gamma_init: float = 0.0,
        entropy_weight: float = 1e-3,
        diversity_weight: float = 1e-3,
    ) -> None:
        super().__init__()
        self.dim = dim
        self.num_centroids = num_centroids
        self.top_k = top_k
        self.tau = tau
        self.entropy_weight = entropy_weight
        self.diversity_weight = diversity_weight

        self.centroids = nn.Parameter(torch.empty(num_centroids, dim))
        nn.init.xavier_uniform_(self.centroids)
        self.gamma = nn.Parameter(torch.tensor(float(gamma_init), dtype=torch.float32))

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, RoutingStats, dict]:
        """
        x: (N, D)
        returns:
          y: (N, D)
          stats: routing diagnostics
          meta: {"scores_topk":..., "idx_topk":...} or dense score summary
        """
        x32 = x.float()
        c32 = self.centroids.float()

        x_norm = F.normalize(x32, dim=-1)
        c_norm = F.normalize(c32, dim=-1)

        sims = x_norm @ c_norm.T  # (N,K)
        logits = float(self.tau) * sims
        scores = F.softmax(logits, dim=-1)  # (N,K)

        # diagnostics
        p = torch.clamp(scores, 1e-8, 1.0)
        ent = (-p * torch.log(p)).sum(dim=-1).mean()
        max_prob = scores.max(dim=-1).values.mean()
        eff_k = (scores > 0.01).float().sum(dim=-1).mean()

        # regularizers (optional) – returned as meta-loss for training loops
        loss_reg = torch.tensor(0.0, device=x.device)
        if self.entropy_weight > 0:
            loss_reg = loss_reg + float(self.entropy_weight) * (ent - 1.0).pow(2)
        if self.diversity_weight > 0:
            gram = c_norm @ c_norm.T
            off_diag = gram - torch.diag(torch.diag(gram))
            loss_reg = loss_reg + float(self.diversity_weight) * (off_diag.pow(2).mean())

        # compute side vector
        meta: dict = {"loss_reg": float(loss_reg.detach().cpu().item())}
        if self.top_k is not None and self.top_k > 0:
            k = min(self.top_k, self.num_centroids)
            vals, idx = torch.topk(scores, k=k, dim=-1)
            w = vals / (vals.sum(dim=-1, keepdim=True) + 1e-9)
            side = (w.unsqueeze(-1) * c32[idx]).sum(dim=-2)
            meta.update({"idx_topk": idx.detach().cpu().tolist(), "w_topk": w.detach().cpu().tolist()})
        else:
            side = scores @ c32
            # store only a cheap summary to avoid huge payloads
            meta.update({"scores_mean": scores.mean(dim=0).detach().cpu().tolist()})

        y = x + self.gamma.to(x.dtype) * side.to(x.dtype)
        stats = RoutingStats(
            entropy=float(ent.detach().cpu().item()),
            max_prob=float(max_prob.detach().cpu().item()),
            eff_k=float(eff_k.detach().cpu().item()),
            gamma=float(self.gamma.detach().cpu().item()),
        )
        return y, stats, meta
