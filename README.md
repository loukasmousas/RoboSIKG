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
compose.yaml
docs/
  run_summary_schema.md
  cookoff_checklist.md
```

## Quickstart

### 1) Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -r requirements.txt
```

### 2) Run tests

```bash
python3 -m pytest -q
```

### 3) Run demo on MP4

```bash
python3 scripts/run_demo.py \
  --mp4 data/scratch/input.mp4 \
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
For meaningful scene semantics, keep `--pretrained` enabled. `--no-pretrained` uses untrained detector/embedding weights and can produce irrelevant reasoning context.

### 4) Evaluate output

```bash
python3 scripts/evaluate.py --run out_demo/run_summary.json
```

## NIM (Optional)

Run local Cosmos Reason 2 NIM:

```bash
export NVIDIA_API_KEY=...
docker compose --profile cosmos-reason2-8b up -d
```

The compose profile exposes:
- `http://127.0.0.1:8000/v1/chat/completions`

Default NIM endpoint used by demo:
- `http://160.211.46.134:8000/v1/chat/completions`

Default model used by demo:
- `nvidia/cosmos-reason2-8b`

Optional overrides:
- `ROBOSIKG_NIM_BASE_URL`
- `ROBOSIKG_MODEL_NAME`

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

## CUDA Runtime Notes

- `--device cuda` requires a runtime with visible GPU devices.
- If `nvidia-smi` works but PyTorch reports CUDA Error 304, run outside restricted sandboxing and ensure the container/host exposes NVIDIA compute devices.

## Deferred (Post-MVP)

- Figma push automation
- ROS2 live ingest implementation
- Isaac Sim / Replicator path
- TensorRT production inference path

## Cookoff Submission Checklist

See `docs/cookoff_checklist.md`.
