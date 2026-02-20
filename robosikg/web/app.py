from __future__ import annotations

import asyncio
import re
import secrets
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from rdflib import Graph
from rdflib.namespace import RDF
from rdflib.term import URIRef

from robosikg.agent.orchestrator import Orchestrator
from robosikg.config import DemoConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
SCRATCH_DIR = PROJECT_ROOT / "data" / "scratch"
SAFE_RUN_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,120}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sanitize_filename(name: str) -> str:
    base = Path(name).name
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(base).stem).strip("._")
    if not stem:
        stem = "upload"
    return f"{stem}.mp4"


def _short_label(uri: str) -> str:
    if uri.startswith("urn:sha256:"):
        return uri.removeprefix("urn:sha256:")[:10]
    if "#" in uri:
        return uri.rsplit("#", 1)[-1][:42]
    tail = uri.rstrip("/").rsplit("/", 1)[-1]
    return (tail or uri)[:42]


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

    type_map: dict[str, str] = {}
    for subj, _pred, obj in g.triples((None, RDF.type, None)):
        if isinstance(subj, URIRef) and isinstance(obj, URIRef):
            type_map[str(subj)] = _short_label(str(obj))

    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, str]] = []
    max_edges = 800

    def ensure_node(uri: str) -> None:
        if uri in nodes:
            return
        group = type_map.get(uri, "Entity")
        nodes[uri] = {
            "id": uri,
            "label": _short_label(uri),
            "group": group,
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


class RunRequest(BaseModel):
    mp4_path: str = Field(default="data/scratch/traffic.mp4", min_length=1)
    source_id: str = Field(default="web_demo", min_length=1, max_length=120)
    reasoning_mode: Literal["auto", "nim", "mock"] = "nim"
    device: Literal["cuda", "cpu"] = "cuda"
    pretrained: bool = True
    max_frames: int = Field(default=300, ge=1, le=5000)
    sample_fps: float = Field(default=5.0, gt=0.0, le=120.0)
    reason_every_n_frames: int = Field(default=25, ge=0, le=10000)
    nim_base_url: str | None = None
    model_name: str | None = None

    model_config = {"extra": "forbid"}


class LiveHub:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: set[WebSocket] = set()
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


class PipelineService:
    def __init__(self, hub: LiveHub):
        self.hub = hub
        self._task: asyncio.Task[None] | None = None
        self._run_id: str | None = None
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def current_run_id(self) -> str | None:
        return self._run_id

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
            require_cuda=(req.device == "cuda"),
        )
        reasoning_cfg = replace(
            cfg.reasoning,
            mode=req.reasoning_mode,
            reason_every_n_frames=req.reason_every_n_frames,
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

            run_id = f"out_web_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(2)}"
            run_dir = PROJECT_ROOT / run_id
            self._run_id = run_id
            self._task = asyncio.create_task(self._run_in_background(run_id=run_id, run_dir=run_dir, req=req))
            return {"run_id": run_id, "run_dir": str(run_dir.relative_to(PROJECT_ROOT))}

    async def _run_in_background(self, run_id: str, run_dir: Path, req: RunRequest) -> None:
        await self.hub.broadcast({"type": "run_state", "state": "starting", "run_id": run_id, "ts": _utc_now_iso()})

        try:
            summary = await asyncio.to_thread(self._run_sync, run_id, run_dir, req)
            await self.hub.broadcast(
                {
                    "type": "run_state",
                    "state": "completed",
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

    def _run_sync(self, run_id: str, run_dir: Path, req: RunRequest) -> dict[str, Any]:
        cfg = self._build_config(req)
        mp4_path = self._resolve_mp4(req.mp4_path)
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

        self.hub.publish_from_thread(
            {
                "type": "run_state",
                "state": "running",
                "run_id": run_id,
                "config": {
                    "reasoning_mode": req.reasoning_mode,
                    "device": req.device,
                    "pretrained": req.pretrained,
                    "sample_fps": req.sample_fps,
                    "max_frames": req.max_frames,
                },
                "ts": _utc_now_iso(),
            }
        )

        orch = Orchestrator(cfg=cfg, source_id=req.source_id, out_dir=str(run_dir))
        return orch.run_mp4(str(mp4_path), progress_cb=emit)


def create_app() -> FastAPI:
    app = FastAPI(title="RoboSIKG Ops Console", version="0.1.0")
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.mount("/media", StaticFiles(directory=str(SCRATCH_DIR)), name="media")

    hub = LiveHub()
    service = PipelineService(hub=hub)
    app.state.hub = hub
    app.state.service = service

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
            "current_run_id": service.current_run_id,
        }

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
