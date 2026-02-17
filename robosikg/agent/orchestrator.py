from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional, Protocol

import numpy as np

from robosikg.config import DemoConfig
from robosikg.ids.canonical import SourceRef, canon_frame, canon_region, canon_track
from robosikg.ids.hashing import hash_uri
from robosikg.ingest.mp4 import iter_mp4
from robosikg.kg.store import GraphStore
from robosikg.perception.torch_detector import TorchVisionFRCNN
from robosikg.reasoning.cosmos_reason2 import CosmosReason2Client
from robosikg.reasoning.mock_reasoner import MockReasoner
from robosikg.reasoning.schemas import ReasoningInput, ReasoningOutput
from robosikg.tracking.mot import MultiObjectTracker
from robosikg.vector.embedder import RegionEmbedder
from robosikg.vector.faiss_store import FaissVectorStore


class Reasoner(Protocol):
    def reason(self, rin: ReasoningInput) -> ReasoningOutput:
        ...


@dataclass
class RunArtifacts:
    out_dir: str
    ttl_path: str
    nt_path: str
    summary_path: str


class Orchestrator:
    def __init__(self, cfg: DemoConfig, source_id: str, out_dir: str):
        self.cfg = cfg
        self.source = SourceRef(source_id=source_id)
        os.makedirs(out_dir, exist_ok=True)
        self.art = RunArtifacts(
            out_dir=out_dir,
            ttl_path=os.path.join(out_dir, "graph.ttl"),
            nt_path=os.path.join(out_dir, "graph.nt"),
            summary_path=os.path.join(out_dir, "run_summary.json"),
        )

        self.kg = GraphStore(base_iri=cfg.kg.base_iri)
        self.detector = TorchVisionFRCNN(
            score_thresh=cfg.perception.score_thresh,
            device=cfg.perception.device,
            pretrained=cfg.perception.pretrained,
            require_cuda=cfg.perception.require_cuda,
        )
        self.tracker = MultiObjectTracker(
            iou_match_thresh=cfg.tracking.iou_match_thresh,
            max_age_frames=cfg.tracking.max_age_frames,
            min_hits=cfg.tracking.min_hits,
        )
        self.embedder = RegionEmbedder(
            dim=cfg.vector.dim,
            device=cfg.perception.device,
            centroid_k=cfg.vector.centroid_k,
            tau=cfg.vector.route_tau,
            top_k=cfg.vector.route_top_k,
            pretrained=cfg.perception.pretrained,
            require_cuda=cfg.perception.require_cuda,
            gamma_init=cfg.vector.route_gamma_init,
        )
        self.vstore = FaissVectorStore(dim=cfg.vector.dim, use_gpu=cfg.vector.faiss_use_gpu)

        self._mock_reasoner: Reasoner = MockReasoner()
        self._nim_reasoner: Reasoner = CosmosReason2Client(
            base_url=cfg.reasoning.nim_base_url,
            model=cfg.reasoning.model_name,
            timeout_s=cfg.reasoning.timeout_s,
        )

        if cfg.reasoning.mode not in {"auto", "nim", "mock"}:
            raise ValueError("reasoning.mode must be one of: auto, nim, mock")

        self._auto_force_mock = False
        self.reasoning_fallbacks = 0
        self.reasoning_invocations = 0
        self.events: list[dict[str, Any]] = []
        self.errors: list[dict[str, str]] = []

    def _final_reasoning_backend(self) -> str:
        if self.cfg.reasoning.mode == "auto":
            return "mock(auto-fallback)" if self._auto_force_mock else "nim"
        return self.cfg.reasoning.mode

    def _reason(self, rin: ReasoningInput) -> tuple[ReasoningOutput, str]:
        mode = self.cfg.reasoning.mode

        if mode == "mock":
            return self._mock_reasoner.reason(rin), "mock"
        if mode == "nim":
            return self._nim_reasoner.reason(rin), "nim"

        if self._auto_force_mock:
            return self._mock_reasoner.reason(rin), "mock"

        try:
            return self._nim_reasoner.reason(rin), "nim"
        except Exception as exc:
            self._auto_force_mock = True
            self.reasoning_fallbacks += 1
            detail = f"{type(exc).__name__}: {exc}"
            self.errors.append(
                {
                    "type": "reasoning_fallback",
                    "mode": "auto",
                    "detail": detail,
                }
            )
            self.events.append(
                {
                    "type": "reasoning_fallback",
                    "frame_uri": rin.frame_uri,
                    "detail": detail,
                }
            )
            return self._mock_reasoner.reason(rin), "mock"

    def run_mp4(self, mp4_path: str) -> dict[str, Any]:
        started_ns = time.time_ns()
        t_start = time.perf_counter()

        frames_seen = 0
        regions_added = 0
        tracks_added: set[int] = set()
        last_query_vec: Optional[np.ndarray] = None

        for fr in iter_mp4(
            mp4_path,
            sample_fps=self.cfg.ingest.sample_fps,
            max_frames=self.cfg.ingest.max_frames,
            timestamp_origin_ns=self.cfg.ingest.timestamp_origin_ns,
        ):
            frames_seen += 1

            c_frame = canon_frame(self.source, fr.index, fr.t_ns)
            frame_uri = hash_uri(c_frame).uri()
            self.kg.add_frame(frame_uri, self.source.source_id, fr.index, fr.t_ns)

            dets = self.detector.detect(fr.bgr)
            _removed, confirmed = self.tracker.step(dets)

            for tr in confirmed:
                if tr.track_id in tracks_added:
                    continue
                c_tr = canon_track(self.source, tr.track_id)
                tr_uri = hash_uri(c_tr).uri()
                self.kg.add_track(tr_uri, self.source.source_id, tr.track_id, tr.cls)
                tracks_added.add(tr.track_id)

            for det in dets:
                c_reg = canon_region(frame_uri, det.bbox_xyxy, det.cls)
                reg_uri = hash_uri(c_reg).uri()
                self.kg.add_region(reg_uri, frame_uri, det.cls, det.score, det.bbox_xyxy, track_uri=None)

                emb = self.embedder.embed_region(fr.bgr, det.bbox_xyxy)
                last_query_vec = emb.vec
                self.vstore.add(
                    uri=reg_uri,
                    vec=emb.vec,
                    meta={
                        "cls": det.cls,
                        "score": det.score,
                        "bbox": det.bbox_xyxy,
                        "routing": {
                            "entropy": emb.stats.entropy,
                            "max_prob": emb.stats.max_prob,
                            "eff_k": emb.stats.eff_k,
                            "gamma": emb.stats.gamma,
                        },
                        "logits_meta": emb.logits_meta,
                        "frame_uri": frame_uri,
                    },
                )
                regions_added += 1

            reason_every = self.cfg.reasoning.reason_every_n_frames
            if reason_every > 0 and frames_seen % reason_every == 0:
                ann = self.vstore.search(query=last_query_vec, k=5) if last_query_vec is not None else []
                sparql_tracks = self.kg.query(
                    """
                    PREFIX kg: <https://example.org/robosikg#>
                    SELECT ?t ?cls WHERE { ?t a kg:Track ; kg:cls ?cls } LIMIT 20
                    """
                )

                rin = ReasoningInput(
                    source_id=self.source.source_id,
                    frame_uri=frame_uri,
                    recent_events=self.events[-20:],
                    sparql_snippets={"tracks": sparql_tracks},
                    ann_neighbors=ann,
                )

                rout, backend = self._reason(rin)
                self.reasoning_invocations += 1

                ordered_claims = sorted(
                    rout.claims,
                    key=lambda c: (c.subject_uri, c.predicate_iri, c.object_uri, c.type, c.confidence),
                )
                for cl in ordered_claims:
                    edge_uri = self.kg.add_edge(
                        s_uri=cl.subject_uri,
                        p_iri=cl.predicate_iri,
                        o_uri=cl.object_uri,
                        confidence=float(cl.confidence),
                    )
                    self.events.append(
                        {
                            "type": "claim",
                            "backend": backend,
                            "edge": edge_uri,
                            "summary": cl.type,
                            "confidence": float(cl.confidence),
                        }
                    )

                self.events.append(
                    {
                        "type": "reasoning_summary",
                        "backend": backend,
                        "frame": frame_uri,
                        "summary": rout.summary,
                        "trajectory_points": 0
                        if rout.trajectory_2d_norm_0_1000 is None
                        else len(rout.trajectory_2d_norm_0_1000),
                    }
                )

        if self.cfg.kg.persist_ttl:
            with open(self.art.ttl_path, "w", encoding="utf-8") as f:
                f.write(self.kg.serialize_ttl())
            with open(self.art.nt_path, "w", encoding="utf-8") as f:
                f.write(self.kg.serialize_ntriples_sorted())

        finished_ns = time.time_ns()
        elapsed_s = max(0.0, time.perf_counter() - t_start)
        summary = {
            "source_id": self.source.source_id,
            "config": asdict(self.cfg),
            "reasoning_backend": self._final_reasoning_backend(),
            "reasoning_fallbacks": self.reasoning_fallbacks,
            "errors": self.errors,
            "timing": {
                "started_ns": started_ns,
                "finished_ns": finished_ns,
                "elapsed_s": elapsed_s,
                "effective_fps": 0.0 if elapsed_s <= 0 else (frames_seen / elapsed_s),
            },
            "counts": {
                "frames_seen": frames_seen,
                "regions_added": regions_added,
                "tracks_seen": len(tracks_added),
                "events_total": len(self.events),
                "reasoning_invocations": self.reasoning_invocations,
                "kg_triples": self.kg.triple_count(),
                "vector_items": self.vstore.count(),
            },
            "events": self.events[-200:],
            "artifacts": {
                "ttl": self.art.ttl_path if self.cfg.kg.persist_ttl else None,
                "ntriples_sorted": self.art.nt_path if self.cfg.kg.persist_ttl else None,
                "summary": self.art.summary_path,
            },
        }
        with open(self.art.summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, sort_keys=True)

        return summary
