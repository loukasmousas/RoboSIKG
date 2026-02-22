from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Optional, Protocol

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
    reasoning_debug_path: str


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
            reasoning_debug_path=os.path.join(out_dir, "reasoning_debug.jsonl"),
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
            debug_capture=cfg.reasoning.debug_capture,
        )

        if cfg.reasoning.mode not in {"auto", "nim", "mock"}:
            raise ValueError("reasoning.mode must be one of: auto, nim, mock")

        self._auto_force_mock = False
        self.reasoning_fallbacks = 0
        self.reasoning_invocations = 0
        self.reasoning_model_claims_total = 0
        self.reasoning_claims_total = 0
        self.reasoning_zero_claim_invocations = 0
        self.reasoning_trajectory_points_total = 0
        self.reasoning_deterministic_fallback_invocations = 0
        self.reasoning_deterministic_fallback_claims_total = 0
        self.reasoning_debug_entries = 0
        self.events: list[dict[str, Any]] = []
        self.errors: list[dict[str, str]] = []

    def _track_motion_context(self, confirmed_tracks: list[Any]) -> list[dict[str, Any]]:
        motion: list[dict[str, Any]] = []
        for tr in confirmed_tracks[:20]:
            tr_uri = hash_uri(canon_track(self.source, tr.track_id)).uri()
            bbox = tr.bbox()
            vx = float(tr.kf.x[4])
            vy = float(tr.kf.x[5])
            motion.append(
                {
                    "track_uri": tr_uri,
                    "cls": tr.cls,
                    "bbox_xyxy": [int(v) for v in bbox],
                    "velocity_xy_px_per_frame": [vx, vy],
                    "speed_px_per_frame": float(np.hypot(vx, vy)),
                    "age": int(tr.age),
                    "hits": int(tr.hits),
                    "time_since_update": int(tr.time_since_update),
                }
            )
        return motion

    @staticmethod
    def _bbox_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
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

    @staticmethod
    def _bbox_inside(inner: tuple[int, int, int, int], outer: tuple[int, int, int, int]) -> bool:
        ix1, iy1, ix2, iy2 = inner
        ox1, oy1, ox2, oy2 = outer
        return ix1 >= ox1 and iy1 >= oy1 and ix2 <= ox2 and iy2 <= oy2

    def _heuristic_relation_claims(self, regions: list[dict[str, Any]], max_claims: int = 8) -> list[dict[str, Any]]:
        if len(regions) < 2:
            return []
        top = sorted(regions, key=lambda r: float(r["score"]), reverse=True)[:10]
        claims: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        def _add(subject_uri: str, predicate_iri: str, object_uri: str, claim_type: str, confidence: float) -> None:
            if len(claims) >= max_claims:
                return
            key = (subject_uri, predicate_iri, object_uri)
            if key in seen:
                return
            seen.add(key)
            claims.append(
                {
                    "type": claim_type,
                    "subject_uri": subject_uri,
                    "predicate_iri": predicate_iri,
                    "object_uri": object_uri,
                    "confidence": float(max(0.0, min(1.0, confidence))),
                }
            )

        for i in range(len(top)):
            if len(claims) >= max_claims:
                break
            a = top[i]
            ax1, ay1, ax2, ay2 = a["bbox"]
            acx = (ax1 + ax2) / 2.0
            acy = (ay1 + ay2) / 2.0
            for j in range(i + 1, len(top)):
                if len(claims) >= max_claims:
                    break
                b = top[j]
                bx1, by1, bx2, by2 = b["bbox"]
                bcx = (bx1 + bx2) / 2.0
                bcy = (by1 + by2) / 2.0

                iou = self._bbox_iou(a["bbox"], b["bbox"])
                if iou >= 0.25:
                    _add(
                        a["uri"],
                        "https://example.org/robosikg#overlaps",
                        b["uri"],
                        "geometry_overlaps",
                        0.5 + min(0.5, iou),
                    )
                    continue

                if self._bbox_inside(a["bbox"], b["bbox"]):
                    _add(
                        a["uri"],
                        "https://example.org/robosikg#inside",
                        b["uri"],
                        "geometry_inside",
                        0.9,
                    )
                    continue
                if self._bbox_inside(b["bbox"], a["bbox"]):
                    _add(
                        b["uri"],
                        "https://example.org/robosikg#inside",
                        a["uri"],
                        "geometry_inside",
                        0.9,
                    )
                    continue

                span_x = max(ax2, bx2) - min(ax1, bx1)
                span_y = max(ay2, by2) - min(ay1, by1)
                span_diag = float(np.hypot(span_x, span_y))
                if span_diag <= 1e-6:
                    continue
                center_dist = float(np.hypot(acx - bcx, acy - bcy))
                d_norm = center_dist / span_diag
                if d_norm <= 0.18:
                    _add(
                        a["uri"],
                        "https://example.org/robosikg#near",
                        b["uri"],
                        "geometry_near",
                        max(0.55, 1.0 - d_norm),
                    )
        return claims

    @staticmethod
    def _ann_relation_claims(ann_neighbors: list[dict[str, Any]], max_claims: int = 4) -> list[dict[str, Any]]:
        rows = [row for row in ann_neighbors if isinstance(row, dict) and isinstance(row.get("uri"), str)]
        if len(rows) < 2:
            return []
        anchor = rows[0].get("uri")
        if not isinstance(anchor, str):
            return []
        claims: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows[1 : 1 + max_claims]:
            other = row.get("uri")
            if not isinstance(other, str) or other == anchor:
                continue
            key = (anchor, "https://example.org/robosikg#near", other)
            if key in seen:
                continue
            seen.add(key)
            raw_score = row.get("score")
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                score = 0.0
            confidence = max(0.55, min(0.95, 0.55 + 0.2 * score))
            claims.append(
                {
                    "type": "retrieval_near",
                    "subject_uri": anchor,
                    "predicate_iri": "https://example.org/robosikg#near",
                    "object_uri": other,
                    "confidence": confidence,
                }
            )
        return claims

    @staticmethod
    def _trajectory_payload(points: Any) -> list[dict[str, Any]]:
        if points is None:
            return []
        out: list[dict[str, Any]] = []
        for idx, item in enumerate(points):
            row: dict[str, Any] | None = None
            if hasattr(item, "model_dump"):
                try:
                    row = item.model_dump()  # pydantic model
                except Exception:
                    row = None
            elif isinstance(item, dict):
                row = item
            if row is None:
                continue
            pt = row.get("point_2d")
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                continue
            try:
                x = float(pt[0])
                y = float(pt[1])
            except (TypeError, ValueError):
                continue
            x = max(0.0, min(1000.0, x))
            y = max(0.0, min(1000.0, y))
            label = str(row.get("label") or f"p{idx}")
            out.append({"point_2d": [x, y], "label": label})
        return out

    @staticmethod
    def _deterministic_trajectory_from_track_motion(
        track_motion: list[dict[str, Any]],
        frame_hw: tuple[int, int],
        horizon_points: int = 5,
    ) -> list[dict[str, Any]]:
        if not track_motion:
            return []
        frame_h, frame_w = int(frame_hw[0]), int(frame_hw[1])
        if frame_h <= 1 or frame_w <= 1:
            return []

        def _speed(row: dict[str, Any]) -> float:
            try:
                return float(row.get("speed_px_per_frame", 0.0))
            except (TypeError, ValueError):
                return 0.0

        top = max(track_motion, key=_speed)
        bbox = top.get("bbox_xyxy")
        if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
            return []
        try:
            x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
        except (TypeError, ValueError):
            return []

        vel = top.get("velocity_xy_px_per_frame")
        vx, vy = 0.0, 0.0
        if isinstance(vel, (list, tuple)) and len(vel) >= 2:
            try:
                vx = float(vel[0])
                vy = float(vel[1])
            except (TypeError, ValueError):
                vx, vy = 0.0, 0.0

        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        pts: list[dict[str, Any]] = []
        steps = max(2, int(horizon_points))
        for step in range(steps):
            px = max(0.0, min(float(frame_w - 1), cx + vx * step))
            py = max(0.0, min(float(frame_h - 1), cy + vy * step))
            nx = max(0.0, min(1000.0, (px / float(frame_w)) * 1000.0))
            ny = max(0.0, min(1000.0, (py / float(frame_h)) * 1000.0))
            pts.append({"point_2d": [nx, ny], "label": "now" if step == 0 else f"t+{step}"})
        return pts

    @staticmethod
    def _emit_progress(progress_cb: Optional[Callable[[dict[str, Any]], None]], payload: dict[str, Any]) -> None:
        if progress_cb is None:
            return
        try:
            progress_cb(payload)
        except Exception:
            # Progress callbacks are best-effort and should never break pipeline execution.
            return

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

    def run_mp4(
        self,
        mp4_path: str,
        progress_cb: Optional[Callable[[dict[str, Any]], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
        wait_if_paused: Optional[Callable[[], None]] = None,
    ) -> dict[str, Any]:
        started_ns = time.time_ns()
        t_start = time.perf_counter()

        if self.cfg.reasoning.debug_capture:
            # Truncate debug log at run start to avoid mixing runs when reusing out_dir.
            with open(self.art.reasoning_debug_path, "w", encoding="utf-8"):
                pass

        frames_seen = 0
        regions_added = 0
        tracks_added: set[int] = set()
        last_query_vec: Optional[np.ndarray] = None
        stopped_early = False

        for fr in iter_mp4(
            mp4_path,
            sample_fps=self.cfg.ingest.sample_fps,
            max_frames=self.cfg.ingest.max_frames,
            timestamp_origin_ns=self.cfg.ingest.timestamp_origin_ns,
        ):
            if should_stop is not None and should_stop():
                stopped_early = True
                break
            if wait_if_paused is not None:
                wait_if_paused()
                if should_stop is not None and should_stop():
                    stopped_early = True
                    break

            frames_seen += 1
            current_regions: list[dict[str, Any]] = []

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
                current_regions.append(
                    {
                        "uri": reg_uri,
                        "bbox": det.bbox_xyxy,
                        "cls": det.cls,
                        "score": float(det.score),
                    }
                )

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

            self._emit_progress(
                progress_cb,
                {
                    "type": "frame",
                    "frame_index": fr.index,
                    "frame_uri": frame_uri,
                    "frame_width": int(fr.bgr.shape[1]),
                    "frame_height": int(fr.bgr.shape[0]),
                    "t_ns": fr.t_ns,
                    "frames_seen": frames_seen,
                    "detections": len(dets),
                    "tracks_confirmed": len(confirmed),
                    "boxes": [
                        {
                            "bbox": [float(x) for x in det.bbox_xyxy],
                            "cls": det.cls,
                            "score": float(det.score),
                        }
                        for det in dets
                    ],
                    "tracks": [
                        {
                            "track_id": int(tr.track_id),
                            "bbox": [float(x) for x in tr.bbox_xyxy],
                            "cls": tr.cls,
                        }
                        for tr in confirmed
                    ],
                    "regions_added": regions_added,
                    "vector_items": self.vstore.count(),
                },
            )

            reason_every = self.cfg.reasoning.reason_every_n_frames
            if reason_every > 0 and frames_seen % reason_every == 0:
                ann = self.vstore.search(query=last_query_vec, k=5) if last_query_vec is not None else []
                sparql_tracks = self.kg.query(
                    """
                    PREFIX kg: <https://example.org/robosikg#>
                    SELECT ?t ?cls WHERE { ?t a kg:Track ; kg:cls ?cls } LIMIT 20
                    """
                )
                track_motion = self._track_motion_context(confirmed)

                rin = ReasoningInput(
                    source_id=self.source.source_id,
                    frame_uri=frame_uri,
                    recent_events=self.events[-20:],
                    sparql_snippets={
                        "tracks": sparql_tracks,
                        "track_motion": track_motion,
                        "frame_hw": [int(fr.bgr.shape[0]), int(fr.bgr.shape[1])],
                    },
                    ann_neighbors=ann,
                )

                rout, backend = self._reason(rin)
                self.reasoning_invocations += 1

                if self.cfg.reasoning.debug_capture and backend == "nim":
                    nim_debug = getattr(self._nim_reasoner, "last_debug", None)
                    if isinstance(nim_debug, dict):
                        payload = {
                            "invocation": self.reasoning_invocations,
                            "frame_uri": frame_uri,
                            "source_id": self.source.source_id,
                            **nim_debug,
                        }
                        with open(self.art.reasoning_debug_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps(payload, sort_keys=True) + "\n")
                        self.reasoning_debug_entries += 1

                ordered_claims = sorted(
                    rout.claims,
                    key=lambda c: (c.subject_uri, c.predicate_iri, c.object_uri, c.type, c.confidence),
                )
                model_claim_count = len(ordered_claims)
                self.reasoning_model_claims_total += model_claim_count
                claims_out = [
                    {
                        "type": c.type,
                        "subject_uri": c.subject_uri,
                        "predicate_iri": c.predicate_iri,
                        "object_uri": c.object_uri,
                        "confidence": float(c.confidence),
                    }
                    for c in ordered_claims
                ]
                claim_source = "nim"
                if not claims_out:
                    fallback_claims = self._heuristic_relation_claims(current_regions, max_claims=8)
                    if not fallback_claims:
                        fallback_claims = self._ann_relation_claims(ann, max_claims=4)
                    if fallback_claims:
                        claims_out = fallback_claims
                        claim_source = "geometric_fallback" if "geometry_" in fallback_claims[0]["type"] else "retrieval_fallback"
                        self.reasoning_deterministic_fallback_invocations += 1
                        self.reasoning_deterministic_fallback_claims_total += len(fallback_claims)

                claim_count = len(claims_out)
                self.reasoning_claims_total += claim_count
                if claim_count == 0:
                    self.reasoning_zero_claim_invocations += 1

                for cl in claims_out:
                    edge_uri = self.kg.add_edge(
                        s_uri=cl["subject_uri"],
                        p_iri=cl["predicate_iri"],
                        o_uri=cl["object_uri"],
                        confidence=float(cl["confidence"]),
                    )
                    self.events.append(
                        {
                            "type": "claim",
                            "backend": backend,
                            "claim_source": claim_source,
                            "edge": edge_uri,
                            "summary": cl["type"],
                            "confidence": float(cl["confidence"]),
                        }
                    )

                trajectory_payload = self._trajectory_payload(rout.trajectory_2d_norm_0_1000)
                trajectory_source = "nim"
                if not trajectory_payload:
                    trajectory_payload = self._deterministic_trajectory_from_track_motion(
                        track_motion=track_motion,
                        frame_hw=(int(fr.bgr.shape[0]), int(fr.bgr.shape[1])),
                        horizon_points=5,
                    )
                    if trajectory_payload:
                        trajectory_source = "track_motion_fallback"

                trajectory_points = len(trajectory_payload)
                self.reasoning_trajectory_points_total += trajectory_points
                self.events.append(
                    {
                        "type": "reasoning_summary",
                        "backend": backend,
                        "frame": frame_uri,
                        "summary": rout.summary,
                        "no_claim_reason": rout.no_claim_reason,
                        "claim_source": claim_source,
                        "claims": claim_count,
                        "trajectory_points": trajectory_points,
                        "trajectory_source": trajectory_source,
                    }
                )
                self._emit_progress(
                    progress_cb,
                    {
                        "type": "reasoning",
                        "backend": backend,
                        "frame_uri": frame_uri,
                        "summary": rout.summary,
                        "claims": claim_count,
                        "reasoning_invocations": self.reasoning_invocations,
                        "trajectory_points": trajectory_points,
                        "trajectory_source": trajectory_source,
                        "trajectory_2d_norm_0_1000": trajectory_payload,
                    },
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
                "reasoning_model_claims_total": self.reasoning_model_claims_total,
                "reasoning_claims_total": self.reasoning_claims_total,
                "reasoning_zero_claim_invocations": self.reasoning_zero_claim_invocations,
                "reasoning_invocations_with_claims": max(
                    0, self.reasoning_invocations - self.reasoning_zero_claim_invocations
                ),
                "reasoning_avg_claims_per_invocation": 0.0
                if self.reasoning_invocations == 0
                else (self.reasoning_claims_total / self.reasoning_invocations),
                "reasoning_deterministic_fallback_invocations": self.reasoning_deterministic_fallback_invocations,
                "reasoning_deterministic_fallback_claims_total": self.reasoning_deterministic_fallback_claims_total,
                "trajectory_points_total": self.reasoning_trajectory_points_total,
                "reasoning_debug_entries": self.reasoning_debug_entries,
                "kg_triples": self.kg.triple_count(),
                "vector_items": self.vstore.count(),
                "stopped_early": stopped_early,
            },
            "events": self.events[-200:],
            "artifacts": {
                "ttl": self.art.ttl_path if self.cfg.kg.persist_ttl else None,
                "ntriples_sorted": self.art.nt_path if self.cfg.kg.persist_ttl else None,
                "summary": self.art.summary_path,
                "reasoning_debug": self.art.reasoning_debug_path
                if self.cfg.reasoning.debug_capture and self.reasoning_debug_entries > 0
                else None,
            },
        }
        with open(self.art.summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, sort_keys=True)

        self._emit_progress(
            progress_cb,
            {
                "type": "complete",
                "summary_path": self.art.summary_path,
                "counts": summary["counts"],
                "reasoning_backend": summary["reasoning_backend"],
                "reasoning_fallbacks": summary["reasoning_fallbacks"],
                "stopped_early": stopped_early,
            },
        )

        return summary
