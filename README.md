# RoboSIKG

RoboSIKG is a reproducible robotics memory pipeline for video-based physical AI:
- deterministic hashed URIs for frames/tracks/regions/events
- RDF/SPARQL-style spatiotemporal knowledge graph (RDFLib)
- vector memory (FAISS) with routing-embedding diagnostics metadata
- Cosmos Reason 2 integration via NVIDIA NIM (OpenAI-compatible endpoint)

The baseline demo is **GPU-first** (`--device cuda` by default) with **auto fallback** to mock reasoning when NIM is unavailable.

## Repository Layout

```text
robosikg/
  config.py
  ids/
  ingest/
  perception/
  tracking/
  kg/
  vector/
  reasoning/
  agent/
scripts/
  run_demo.py
  evaluate.py
tests/
docker/
  nim_reason2_run.sh
docs/
  run_summary_schema.md
  cookoff_checklist.md
```

## Quickstart

### 1) Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]" --no-build-isolation
```

### 2) Run tests

```bash
pytest -q
```

### 3) Run demo on MP4

```bash
python scripts/run_demo.py \
  --mp4 /path/to/input.mp4 \
  --out out_demo \
  --source-id demo_video \
  --reasoning-mode auto \
  --device cuda \
  --pretrained
```

Key flags:
- `--reasoning-mode {auto,nim,mock}`
- `--device {cuda,cpu}`
- `--pretrained / --no-pretrained`
- `--sample-fps`, `--max-frames`, `--reason-every-n-frames`
- `--nim-base-url`, `--model-name`

If CUDA is unavailable in `--device cuda` mode, startup fails fast with an actionable error.

### 4) Evaluate output

```bash
python scripts/evaluate.py --run out_demo/run_summary.json
```

## NIM (Optional)

Run local Cosmos Reason 2 NIM:

```bash
export NGC_API_KEY=...
bash docker/nim_reason2_run.sh
```

Default NIM endpoint used by demo:
- `http://127.0.0.1:8000/v1/chat/completions`

In `--reasoning-mode auto`, the orchestrator attempts NIM first and switches to mock reasoner if NIM fails.

## Reproducibility Notes

- Frame timestamps are deterministic from media timeline and configured origin (`timestamp_origin_ns`), not wall-clock time.
- Canonical IDs are hashed as `urn:sha256:<hex>`.
- Artifacts:
  - `graph.ttl`
  - `graph.nt` (sorted n-triples for deterministic diffing)
  - `run_summary.json`
  - `eval_report.json`

See `docs/run_summary_schema.md` for summary fields.

## Docker

Build image:

```bash
docker build -t robosikg:latest .
```

Then run with NVIDIA runtime and mounted input/output paths as needed.

## Deferred (Post-MVP)

- Figma push automation (`scripts/figma_push.py`)
- ROS2 live ingest implementation
- Isaac Sim / Replicator path
- TensorRT production inference path

## Cookoff Submission Checklist

See `docs/cookoff_checklist.md`.
