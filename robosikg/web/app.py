from __future__ import annotations

import asyncio
import re
import secrets
import threading
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from rdflib import Graph, Literal as RDFLiteral
from rdflib.namespace import RDF
from rdflib.term import URIRef

from robosikg.agent.orchestrator import Orchestrator
from robosikg.config import DemoConfig
from robosikg.ids.source_id import derive_source_id as derive_source_id_from_path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
SCRATCH_DIR = PROJECT_ROOT / "data" / "scratch"
SAFE_RUN_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,120}$")
KG_BASE_IRI = "https://example.org/robosikg#"
EXPORTS_DIR = PROJECT_ROOT / "out_web_exports"
RECORDINGS_DIR = PROJECT_ROOT / "out_web_recordings"


def _utc_now_iso() -> str:
    """Return UTC timestamp in ISO-8601 format without microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sanitize_filename(name: str) -> str:
    """Normalize uploaded names to safe local mp4 filenames."""
    base = Path(name).name
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(base).stem).strip("._")
    if not stem:
        stem = "upload"
    return f"{stem}.mp4"


def _derive_source_id(raw: str | None, mp4_path: Path) -> str:
    """Resolve source id from request value and mp4 path."""
    return derive_source_id_from_path(raw, mp4_path, fallback="web_demo")


def _short_label(uri: str) -> str:
    if uri.startswith("urn:sha256:"):
        return uri.removeprefix("urn:sha256:")[:10]
    if "#" in uri:
        return uri.rsplit("#", 1)[-1][:42]
    tail = uri.rstrip("/").rsplit("/", 1)[-1]
    return (tail or uri)[:42]


def _local_name(uri: str) -> str:
    if "#" in uri:
        return uri.rsplit("#", 1)[-1]
    return uri.rstrip("/").rsplit("/", 1)[-1]


def _node_display_label(uri: str, group: str, cls_value: str | None, frame_index: int | None) -> str:
    short_id = _short_label(uri)
    if not uri.startswith("urn:sha256:"):
        return _local_name(uri)[:42]

    parts: list[str] = []
    if group and group != "Entity":
        parts.append(group)
    if cls_value:
        parts.append(cls_value)
    if frame_index is not None:
        parts.append(f"f{frame_index}")

    prefix = " ".join(parts).strip()
    if prefix:
        return f"{prefix} #{short_id}"[:52]
    return f"id #{short_id}"


def _resolve_run_dir(run_name: str) -> Path:
    if not SAFE_RUN_NAME_RE.match(run_name):
        raise HTTPException(status_code=400, detail="Invalid run id")
    run_dir = PROJECT_ROOT / run_name
    if not run_dir.exists() or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="Run directory not found")
    return run_dir


def _summary_path_for_run(run_name: str) -> Path:
    run_dir = _resolve_run_dir(run_name)
    summary_path = run_dir / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found")
    return summary_path


def _read_summary(summary_path: Path) -> dict[str, Any]:
    import json

    try:
        with summary_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Run summary not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse run summary: {exc}") from exc


def _discover_runs(limit: int = 30) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_dir in PROJECT_ROOT.iterdir():
        if not run_dir.is_dir() or not run_dir.name.startswith("out_"):
            continue
        summary_path = run_dir / "run_summary.json"
        if not summary_path.exists():
            continue
        try:
            summary = _read_summary(summary_path)
            mtime = summary_path.stat().st_mtime
            rows.append(
                {
                    "run_id": run_dir.name,
                    "updated_at": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                    "source_id": summary.get("source_id"),
                    "reasoning_backend": summary.get("reasoning_backend"),
                    "reasoning_fallbacks": summary.get("reasoning_fallbacks"),
                    "counts": summary.get("counts", {}),
                    "timing": summary.get("timing", {}),
                }
            )
        except HTTPException:
            continue

    rows.sort(key=lambda x: x["updated_at"], reverse=True)
    return rows[:limit]


def _resolve_artifact_path(path_str: str | None) -> Path | None:
    if not path_str:
        return None
    p = Path(path_str)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists():
        return None
    return p


def _graph_for_run(run_name: str) -> Graph:
    summary_path = _summary_path_for_run(run_name)
    summary = _read_summary(summary_path)
    artifacts = summary.get("artifacts", {})
    nt_path = _resolve_artifact_path(artifacts.get("ntriples_sorted"))
    if nt_path is None:
        raise HTTPException(status_code=404, detail="graph.nt not found for this run")
    g = Graph()
    try:
        g.parse(nt_path, format="nt")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse graph.nt: {exc}") from exc
    return g


def _export_run_bundle(run_name: str) -> dict[str, Any]:
    run_dir = _resolve_run_dir(run_name)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = EXPORTS_DIR / f"{run_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    selected: list[Path] = []
    for filename in ("run_summary.json", "graph.nt", "graph.ttl", "reasoning_debug.jsonl", "eval_report.json"):
        p = run_dir / filename
        if p.exists():
            selected.append(p)

    if not selected:
        raise HTTPException(status_code=404, detail="No exportable artifacts found for this run")

    with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src in selected:
            zf.write(src, arcname=f"{run_name}/{src.name}")

    return {
        "run_id": run_name,
        "archive_path": archive_path.relative_to(PROJECT_ROOT).as_posix(),
        "size_bytes": archive_path.stat().st_size,
        "files": [p.name for p in selected],
    }


def _build_graph_payload(summary: dict[str, Any]) -> dict[str, Any]:
    artifacts = summary.get("artifacts", {})
    nt_path = _resolve_artifact_path(artifacts.get("ntriples_sorted"))
    if nt_path is None:
        return {"nodes": [], "edges": [], "stats": {"nodes": 0, "edges": 0}}

    g = Graph()
    try:
        g.parse(nt_path, format="nt")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse graph.nt: {exc}") from exc

    pred_cls = URIRef(f"{KG_BASE_IRI}cls")
    pred_frame_index = URIRef(f"{KG_BASE_IRI}frameIndex")

    type_map: dict[str, str] = {}
    cls_map: dict[str, str] = {}
    frame_map: dict[str, int] = {}
    for subj, _pred, obj in g.triples((None, RDF.type, None)):
        if isinstance(subj, URIRef) and isinstance(obj, URIRef):
            type_map[str(subj)] = _short_label(str(obj))
    for subj, _pred, obj in g.triples((None, pred_cls, None)):
        if isinstance(subj, URIRef) and isinstance(obj, RDFLiteral):
            cls_map[str(subj)] = str(obj)[:32]
    for subj, _pred, obj in g.triples((None, pred_frame_index, None)):
        if isinstance(subj, URIRef) and isinstance(obj, RDFLiteral):
            try:
                frame_map[str(subj)] = int(obj)
            except Exception:
                continue

    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, str]] = []
    max_edges = 800

    def ensure_node(uri: str) -> None:
        if uri in nodes:
            return
        group = type_map.get(uri, "Entity")
        nodes[uri] = {
            "id": uri,
            "label": _node_display_label(uri, group, cls_map.get(uri), frame_map.get(uri)),
            "short_id": _short_label(uri),
            "group": group,
            "cls": cls_map.get(uri),
        }

    for subj, pred, obj in g:
        if not isinstance(subj, URIRef):
            continue
        s = str(subj)
        ensure_node(s)
        if isinstance(obj, URIRef):
            o = str(obj)
            ensure_node(o)
            edges.append({"source": s, "target": o, "predicate": _short_label(str(pred))})
            if len(edges) >= max_edges:
                break

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
        },
    }


def _build_overlay_payload(summary: dict[str, Any]) -> dict[str, Any]:
    artifacts = summary.get("artifacts", {})
    nt_path = _resolve_artifact_path(artifacts.get("ntriples_sorted"))
    if nt_path is None:
        return {"frames": {}, "frame_count": 0}

    g = Graph()
    try:
        g.parse(nt_path, format="nt")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse graph.nt: {exc}") from exc

    pred_seen_in = URIRef(f"{KG_BASE_IRI}seenIn")
    pred_cls = URIRef(f"{KG_BASE_IRI}cls")
    pred_score = URIRef(f"{KG_BASE_IRI}score")
    pred_bbox_x1 = URIRef(f"{KG_BASE_IRI}bboxX1")
    pred_bbox_y1 = URIRef(f"{KG_BASE_IRI}bboxY1")
    pred_bbox_x2 = URIRef(f"{KG_BASE_IRI}bboxX2")
    pred_bbox_y2 = URIRef(f"{KG_BASE_IRI}bboxY2")
    pred_track_of = URIRef(f"{KG_BASE_IRI}trackOf")
    pred_frame_index = URIRef(f"{KG_BASE_IRI}frameIndex")

    frame_index_by_uri: dict[str, int] = {}
    for subj, _pred, obj in g.triples((None, pred_frame_index, None)):
        if not isinstance(subj, URIRef) or not isinstance(obj, RDFLiteral):
            continue
        try:
            frame_index_by_uri[str(subj)] = int(obj)
        except Exception:
            continue

    track_cls_by_uri: dict[str, str] = {}
    for subj, _pred, obj in g.triples((None, pred_cls, None)):
        if isinstance(subj, URIRef) and isinstance(obj, RDFLiteral):
            track_cls_by_uri[str(subj)] = str(obj)[:32]

    def _literal_float(subject: URIRef, predicate: URIRef) -> float | None:
        for obj in g.objects(subject, predicate):
            if isinstance(obj, RDFLiteral):
                try:
                    return float(obj)
                except Exception:
                    return None
        return None

    def _literal_str(subject: URIRef, predicate: URIRef) -> str | None:
        for obj in g.objects(subject, predicate):
            if isinstance(obj, RDFLiteral):
                return str(obj)
        return None

    def _uri_obj(subject: URIRef, predicate: URIRef) -> str | None:
        for obj in g.objects(subject, predicate):
            if isinstance(obj, URIRef):
                return str(obj)
        return None

    by_frame: dict[int, dict[str, Any]] = {}

    for subj, _pred, frame_obj in g.triples((None, pred_seen_in, None)):
        if not isinstance(subj, URIRef) or not isinstance(frame_obj, URIRef):
            continue
        frame_index = frame_index_by_uri.get(str(frame_obj))
        if frame_index is None:
            continue

        x1 = _literal_float(subj, pred_bbox_x1)
        y1 = _literal_float(subj, pred_bbox_y1)
        x2 = _literal_float(subj, pred_bbox_x2)
        y2 = _literal_float(subj, pred_bbox_y2)
        if None in {x1, y1, x2, y2}:
            continue
        cls = _literal_str(subj, pred_cls) or "obj"
        score = _literal_float(subj, pred_score)

        frame_row = by_frame.setdefault(frame_index, {"boxes": [], "tracks": []})
        frame_row["boxes"].append(
            {
                "bbox": [x1, y1, x2, y2],
                "cls": cls,
                "score": float(score) if score is not None else None,
            }
        )

        track_uri = _uri_obj(subj, pred_track_of)
        if track_uri:
            frame_row["tracks"].append(
                {
                    "track_id": _short_label(track_uri),
                    "bbox": [x1, y1, x2, y2],
                    "cls": track_cls_by_uri.get(track_uri, cls),
                }
            )

    return {
        "frames": {str(k): by_frame[k] for k in sorted(by_frame)},
        "frame_count": len(by_frame),
    }


class RunRequest(BaseModel):
    mp4_path: str = Field(default="data/scratch/traffic.mp4", min_length=1)
    source_id: str = Field(default="auto", min_length=1, max_length=120)
    reasoning_mode: Literal["auto", "nim", "mock"] = "nim"
    device: Literal["cuda", "cpu"] = "cuda"
    pretrained: bool = True
    score_thresh: float = Field(default=0.5, ge=0.0, le=1.0)
    max_frames: int = Field(default=300, ge=1, le=5000)
    sample_fps: float = Field(default=5.0, gt=0.0, le=120.0)
    reason_every_n_frames: int = Field(default=25, ge=0, le=10000)
    reasoning_debug: bool = False
    nim_base_url: str | None = None
    model_name: str | None = None

    model_config = {"extra": "forbid", "protected_namespaces": ()}


class ConsoleActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class SparqlQueryRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=120)
    query: str = Field(min_length=1, max_length=20000)
    limit: int = Field(default=50, ge=1, le=500)

    model_config = {"extra": "forbid"}


class LiveHub:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: set[WebSocket] = set()
        self._record_path: Path | None = None
        self._state_snapshot: dict[str, Any] = {
            "type": "run_state",
            "state": "idle",
            "ts": _utc_now_iso(),
        }

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        await ws.send_json({"type": "hello", "ts": _utc_now_iso(), "snapshot": self._state_snapshot})

    async def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        if payload.get("type") == "run_state":
            self._state_snapshot = payload
        if self._record_path is not None:
            try:
                import json

                with self._record_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(payload, sort_keys=True) + "\n")
            except Exception:
                pass
        stale: list[WebSocket] = []
        for ws in self._clients:
            try:
                await ws.send_json(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._clients.discard(ws)

    def publish_from_thread(self, payload: dict[str, Any]) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(payload), self._loop)

    @property
    def recording_path(self) -> str | None:
        if self._record_path is None:
            return None
        return self._record_path.relative_to(PROJECT_ROOT).as_posix()

    def start_recording(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8"):
            pass
        self._record_path = path

    def stop_recording(self) -> None:
        self._record_path = None


class PipelineService:
    def __init__(self, hub: LiveHub):
        self.hub = hub
        self._task: asyncio.Task[None] | None = None
        self._run_id: str | None = None
        self._paused = False
        self._pause_gate = threading.Event()
        self._pause_gate.set()
        self._stop_requested = threading.Event()
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def current_run_id(self) -> str | None:
        return self._run_id

    @property
    def paused(self) -> bool:
        return self.running and self._paused

    def pause(self) -> bool:
        if not self.running:
            return False
        self._paused = True
        self._pause_gate.clear()
        return True

    def resume(self) -> bool:
        if not self.running:
            return False
        self._paused = False
        self._pause_gate.set()
        return True

    def stop(self) -> bool:
        if not self.running:
            return False
        self._stop_requested.set()
        self._paused = False
        self._pause_gate.set()
        return True

    def _resolve_mp4(self, mp4_path: str) -> Path:
        p = Path(mp4_path)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p

    def _build_config(self, req: RunRequest) -> DemoConfig:
        cfg = DemoConfig()
        ingest_cfg = replace(cfg.ingest, sample_fps=req.sample_fps, max_frames=req.max_frames)
        perception_cfg = replace(
            cfg.perception,
            device=req.device,
            pretrained=req.pretrained,
            score_thresh=req.score_thresh,
            require_cuda=(req.device == "cuda"),
        )
        reasoning_cfg = replace(
            cfg.reasoning,
            mode=req.reasoning_mode,
            reason_every_n_frames=req.reason_every_n_frames,
            debug_capture=req.reasoning_debug,
            nim_base_url=req.nim_base_url or cfg.reasoning.nim_base_url,
            model_name=req.model_name or cfg.reasoning.model_name,
        )
        return replace(cfg, ingest=ingest_cfg, perception=perception_cfg, reasoning=reasoning_cfg)

    async def start(self, req: RunRequest) -> dict[str, Any]:
        mp4_path = self._resolve_mp4(req.mp4_path)
        if not mp4_path.exists():
            raise HTTPException(status_code=400, detail=f"MP4 file not found: {mp4_path}")

        async with self._lock:
            if self.running:
                raise HTTPException(status_code=409, detail="A run is already in progress")

            self._stop_requested.clear()
            self._paused = False
            self._pause_gate.set()
            run_id = f"out_web_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(2)}"
            run_dir = PROJECT_ROOT / run_id
            self._run_id = run_id
            self._task = asyncio.create_task(self._run_in_background(run_id=run_id, run_dir=run_dir, req=req))
            return {"run_id": run_id, "run_dir": str(run_dir.relative_to(PROJECT_ROOT))}

    async def _run_in_background(self, run_id: str, run_dir: Path, req: RunRequest) -> None:
        await self.hub.broadcast({"type": "run_state", "state": "starting", "run_id": run_id, "ts": _utc_now_iso()})

        try:
            summary = await asyncio.to_thread(self._run_sync, run_id, run_dir, req)
            stopped_early = bool(summary.get("counts", {}).get("stopped_early"))
            await self.hub.broadcast(
                {
                    "type": "run_state",
                    "state": "stopped" if stopped_early else "completed",
                    "run_id": run_id,
                    "summary_path": summary.get("artifacts", {}).get("summary"),
                    "counts": summary.get("counts", {}),
                    "reasoning_backend": summary.get("reasoning_backend"),
                    "reasoning_fallbacks": summary.get("reasoning_fallbacks"),
                    "ts": _utc_now_iso(),
                }
            )
        except Exception as exc:
            await self.hub.broadcast(
                {
                    "type": "run_state",
                    "state": "failed",
                    "run_id": run_id,
                    "detail": f"{type(exc).__name__}: {exc}",
                    "ts": _utc_now_iso(),
                }
            )
        finally:
            async with self._lock:
                self._run_id = None
                self._paused = False
                self._pause_gate.set()
                self._stop_requested.clear()

    def _run_sync(self, run_id: str, run_dir: Path, req: RunRequest) -> dict[str, Any]:
        cfg = self._build_config(req)
        mp4_path = self._resolve_mp4(req.mp4_path)
        source_id = _derive_source_id(req.source_id, mp4_path)
        run_dir.mkdir(parents=True, exist_ok=True)

        def emit(payload: dict[str, Any]) -> None:
            self.hub.publish_from_thread(
                {
                    "type": "run_event",
                    "run_id": run_id,
                    "event": payload,
                    "ts": _utc_now_iso(),
                }
            )

        def wait_if_paused() -> None:
            if self._pause_gate.is_set():
                return
            while not self._stop_requested.is_set():
                if self._pause_gate.wait(timeout=0.2):
                    return

        def should_stop() -> bool:
            return self._stop_requested.is_set()

        self.hub.publish_from_thread(
            {
                "type": "run_state",
                "state": "running",
                "run_id": run_id,
                "config": {
                    "source_id": source_id,
                    "reasoning_mode": req.reasoning_mode,
                    "device": req.device,
                    "pretrained": req.pretrained,
                    "sample_fps": req.sample_fps,
                    "max_frames": req.max_frames,
                },
                "ts": _utc_now_iso(),
            }
        )

        orch = Orchestrator(cfg=cfg, source_id=source_id, out_dir=str(run_dir))
        return orch.run_mp4(
            str(mp4_path),
            progress_cb=emit,
            should_stop=should_stop,
            wait_if_paused=wait_if_paused,
        )


class ConsoleState:
    def __init__(self) -> None:
        self.workspace = "default"
        self.rail = "Perception"
        self.instruction = "Inspect the next 10 seconds. Build scene graph. Identify hazards. Suggest safe action."
        self.overlays_visible = True
        self.layers = {
            "timeline": True,
            "boxes": False,
            "masks": False,
            "tracks": False,
            "labels": False,
        }
        self.modules = {"vision": True, "slam": True, "llm": True}
        self.menu_open = False
        self.last_action = "init"

    def snapshot(self, service: PipelineService, hub: LiveHub) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "rail": self.rail,
            "instruction": self.instruction,
            "overlays_visible": self.overlays_visible,
            "layers": self.layers,
            "modules": self.modules,
            "menu_open": self.menu_open,
            "run_running": service.running,
            "run_paused": service.paused,
            "run_id": service.current_run_id,
            "recording": hub.recording_path is not None,
            "recording_path": hub.recording_path,
            "last_action": self.last_action,
            "ts": _utc_now_iso(),
        }


def create_app() -> FastAPI:
    app = FastAPI(title="RoboSIKG Ops Console", version="0.1.0")
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.mount("/media", StaticFiles(directory=str(SCRATCH_DIR)), name="media")
    app.mount("/exports", StaticFiles(directory=str(EXPORTS_DIR)), name="exports")

    hub = LiveHub()
    service = PipelineService(hub=hub)
    console = ConsoleState()
    app.state.hub = hub
    app.state.service = service
    app.state.console = console

    @app.on_event("startup")
    async def _startup() -> None:
        await hub.start()

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "time": _utc_now_iso(),
            "running": service.running,
            "paused": service.paused,
            "current_run_id": service.current_run_id,
            "recording": hub.recording_path is not None,
        }

    @app.get("/api/console/state")
    async def get_console_state() -> dict[str, Any]:
        return console.snapshot(service, hub)

    @app.post("/api/console/action")
    async def post_console_action(req: ConsoleActionRequest) -> dict[str, Any]:
        action = req.action.strip().lower()
        payload = req.payload
        message = ""

        if action == "select_workspace":
            workspace = str(payload.get("workspace", "")).strip().lower()
            if workspace not in {"default", "warehouse", "traffic"}:
                raise HTTPException(status_code=400, detail="Invalid workspace")
            console.workspace = workspace
            message = f"Workspace set to {workspace}"
        elif action == "select_rail":
            rail = str(payload.get("rail", "")).strip()
            if rail not in {"Perception", "Reasoning", "Warehouse", "Graph", "Policy", "Settings"}:
                raise HTTPException(status_code=400, detail="Invalid rail section")
            console.rail = rail
            message = f"Rail focus set to {rail}"
        elif action == "toggle_overlays":
            console.overlays_visible = not console.overlays_visible
            message = "Overlays enabled" if console.overlays_visible else "Overlays hidden"
        elif action == "toggle_layer":
            layer = str(payload.get("layer", "")).strip().lower()
            if layer not in console.layers:
                raise HTTPException(status_code=400, detail="Invalid layer toggle")
            console.layers[layer] = not console.layers[layer]
            message = f"{layer.title()} {'enabled' if console.layers[layer] else 'disabled'}"
        elif action == "toggle_module":
            module = str(payload.get("module", "")).strip().lower()
            if module not in console.modules:
                raise HTTPException(status_code=400, detail="Invalid module toggle")
            console.modules[module] = not console.modules[module]
            message = f"{module.upper()} {'enabled' if console.modules[module] else 'disabled'}"
        elif action == "toggle_menu":
            console.menu_open = not console.menu_open
            message = "Menu opened" if console.menu_open else "Menu closed"
        elif action == "timeline_play":
            message = "Timeline playback toggled"
        elif action == "timeline_step":
            message = "Timeline stepped"
        elif action == "layout_graph":
            message = "Graph relayout requested"
        elif action == "refresh_graph":
            message = "Graph refresh requested"
        elif action == "set_instruction":
            text = str(payload.get("text", "")).strip()
            if not text:
                raise HTTPException(status_code=400, detail="Instruction cannot be empty")
            console.instruction = text[:1000]
            message = "Instruction updated"
        elif action == "toggle_pause":
            if not service.running:
                raise HTTPException(status_code=409, detail="No run in progress")
            if service.paused:
                service.resume()
                message = "Run resumed"
            else:
                service.pause()
                message = "Run paused"
            await hub.broadcast(
                {
                    "type": "run_state",
                    "state": "paused" if service.paused else "running",
                    "run_id": service.current_run_id,
                    "ts": _utc_now_iso(),
                }
            )
        elif action == "reset_console":
            stopped = service.stop()
            if hub.recording_path is not None:
                hub.stop_recording()
            console.menu_open = False
            console.overlays_visible = True
            console.layers = {
                "timeline": True,
                "boxes": False,
                "masks": False,
                "tracks": False,
                "labels": False,
            }
            console.modules = {"vision": True, "slam": True, "llm": True}
            message = "Run stop requested and console reset" if stopped else "Console reset"
            if stopped:
                await hub.broadcast(
                    {
                        "type": "run_state",
                        "state": "stopped",
                        "run_id": service.current_run_id,
                        "detail": "Stop requested by operator",
                        "ts": _utc_now_iso(),
                    }
                )
        elif action == "toggle_record":
            if hub.recording_path is None:
                rec_path = RECORDINGS_DIR / f"console_record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
                hub.start_recording(rec_path)
                message = f"Recording started: {rec_path.relative_to(PROJECT_ROOT).as_posix()}"
            else:
                current = hub.recording_path
                hub.stop_recording()
                message = f"Recording stopped: {current}"
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

        console.last_action = action
        snapshot = console.snapshot(service, hub)
        await hub.broadcast({"type": "console_state", "state": snapshot, "message": message, "ts": _utc_now_iso()})
        return {"ok": True, "message": message, "state": snapshot}

    @app.get("/api/runs")
    async def list_runs() -> dict[str, Any]:
        return {"items": _discover_runs(limit=40)}

    @app.get("/api/runs/{run_name}")
    async def get_run_summary(run_name: str) -> dict[str, Any]:
        summary_path = _summary_path_for_run(run_name)
        return _read_summary(summary_path)

    @app.get("/api/runs/{run_name}/graph")
    async def get_run_graph(run_name: str) -> dict[str, Any]:
        summary_path = _summary_path_for_run(run_name)
        summary = _read_summary(summary_path)
        return _build_graph_payload(summary)

    @app.get("/api/runs/{run_name}/overlays")
    async def get_run_overlays(run_name: str) -> dict[str, Any]:
        summary_path = _summary_path_for_run(run_name)
        summary = _read_summary(summary_path)
        out = _build_overlay_payload(summary)
        out["run_id"] = run_name
        return out

    @app.post("/api/runs/{run_name}/export")
    async def export_run_bundle(run_name: str) -> dict[str, Any]:
        out = _export_run_bundle(run_name)
        out["download_url"] = f"/exports/{Path(out['archive_path']).name}"
        return out

    @app.post("/api/sparql/query")
    async def run_sparql_query(req: SparqlQueryRequest) -> dict[str, Any]:
        _resolve_run_dir(req.run_id)
        g = _graph_for_run(req.run_id)
        try:
            result = g.query(req.query)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"SPARQL query failed: {exc}") from exc

        columns = [str(v) for v in result.vars]
        rows: list[list[str]] = []
        truncated = False
        for idx, row in enumerate(result):
            if idx >= req.limit:
                truncated = True
                break
            rows.append([str(v) if v is not None else "" for v in row])
        return {
            "run_id": req.run_id,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }

    @app.post("/api/run")
    async def start_run(req: RunRequest) -> dict[str, Any]:
        return await service.start(req)

    @app.post("/api/upload")
    async def upload_mp4(file: UploadFile = File(...)) -> dict[str, Any]:
        filename = file.filename or ""
        if not filename.lower().endswith(".mp4"):
            raise HTTPException(status_code=400, detail="Only .mp4 uploads are supported")

        safe_filename = _sanitize_filename(filename)
        stamped = f"{Path(safe_filename).stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        target = SCRATCH_DIR / stamped

        try:
            with target.open("wb") as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
        finally:
            await file.close()

        rel = target.relative_to(PROJECT_ROOT).as_posix()
        return {"path": rel, "size_bytes": target.stat().st_size}

    @app.websocket("/ws/live")
    async def ws_live(ws: WebSocket) -> None:
        await hub.connect(ws)
        try:
            while True:
                # Keep the socket open and allow optional ping messages from client.
                await ws.receive_text()
        except WebSocketDisconnect:
            await hub.disconnect(ws)
        except Exception:
            await hub.disconnect(ws)

    return app
