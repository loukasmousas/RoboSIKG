from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass(frozen=True)
class VideoIngestConfig:
    sample_fps: float = 5.0          # demo default: lightweight
    max_frames: Optional[int] = 500  # cap for cookoff demo reproducibility
    timestamp_origin_ns: int = 0     # deterministic origin for timestamp computation


@dataclass(frozen=True)
class PerceptionConfig:
    detector_name: str = "torchvision_frcnn"  # baseline, no TRT required
    score_thresh: float = 0.5
    device: str = "cuda"  # "cuda" or "cpu"
    pretrained: bool = True
    require_cuda: bool = True


@dataclass(frozen=True)
class TrackingConfig:
    iou_match_thresh: float = 0.3
    max_age_frames: int = 15
    min_hits: int = 2


@dataclass(frozen=True)
class KGConfig:
    base_iri: str = "https://example.org/robosikg#"
    persist_ttl: bool = True


@dataclass(frozen=True)
class VectorConfig:
    dim: int = 512
    faiss_use_gpu: bool = False  # starter uses faiss-cpu by default
    centroid_k: int = 128
    route_tau: float = 3.0
    route_top_k: int | None = None
    route_gamma_init: float = 0.0


@dataclass(frozen=True)
class ReasoningConfig:
    mode: Literal["auto", "nim", "mock"] = "auto"
    reason_every_n_frames: int = 50
    nim_base_url: str = "http://160.211.47.74:8000/v1"
    model_name: str = "nvidia/cosmos-reason2-8b"
    timeout_s: float = 60.0
    debug_capture: bool = False


@dataclass(frozen=True)
class DemoConfig:
    ingest: VideoIngestConfig = field(default_factory=VideoIngestConfig)
    perception: PerceptionConfig = field(default_factory=PerceptionConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    kg: KGConfig = field(default_factory=KGConfig)
    vector: VectorConfig = field(default_factory=VectorConfig)
    reasoning: ReasoningConfig = field(default_factory=ReasoningConfig)
