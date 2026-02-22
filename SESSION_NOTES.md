# Session Notes (Feb 22, 2026)

No git commits were created in this session.

## What Was Changed

### 1) Reasoning output recovery and normalization
- File: `robosikg/reasoning/cosmos_reason2.py`
- Added normalization for common claim formats so structured claims are less likely to be dropped:
  - Predicate alias normalization (for example `near`, `kg:inside`, `overlap` -> canonical KG IRIs).
  - Hash URI normalization from common variants (raw digest, uppercase digest, embedded digest).
  - Alternate key support (`subject`/`object`/`relation`, `score`).
  - Claim deduplication and subject!=object guard.
- Prompt instructions were tightened to encourage concise, frame-specific summaries and structured claims.

### 2) Run quality counters for reasoning
- File: `robosikg/agent/orchestrator.py`
- Added reasoning quality metrics in `run_summary.json`:
  - `reasoning_claims_total`
  - `reasoning_zero_claim_invocations`
  - `reasoning_invocations_with_claims`
  - `reasoning_avg_claims_per_invocation`
  - `trajectory_points_total`
- Added `claims` count to each `reasoning_summary` event.

### 3) Evaluation report enhancements
- File: `scripts/evaluate.py`
- Included the new reasoning quality counters in `eval_report.json`.

### 4) Generic detector filtering control (video-agnostic)
- Files:
  - `scripts/run_demo.py`
  - `robosikg/web/app.py`
  - `README.md`
- Added `score_thresh` plumbing:
  - CLI flag: `--score-thresh` (0.0-1.0)
  - Web API request field: `score_thresh`

### 5) Documentation update
- File: `docs/run_summary_schema.md`
- Documented the new summary `counts` fields.

### 6) Tests added/updated
- File: `tests/test_cosmos_reason2.py`
- Added tests for:
  - Predicate/hash normalization behavior.
  - Alternate claim key acceptance.

## Validation Status
- Test command run: `pytest -q`
- Result: `19 passed` (warnings only; no failures).

## Modified Files
- `README.md`
- `docs/run_summary_schema.md`
- `robosikg/agent/orchestrator.py`
- `robosikg/reasoning/cosmos_reason2.py`
- `robosikg/web/app.py`
- `scripts/evaluate.py`
- `scripts/run_demo.py`
- `tests/test_cosmos_reason2.py`

## Next Run Baseline
Use the command below to exercise the new settings and metrics:

```bash
python3 scripts/run_demo.py \
  --mp4 data/scratch/traffic.mp4 \
  --out out_demo_next \
  --source-id traffic_video \
  --reasoning-mode nim \
  --sample-fps 4 \
  --reason-every-n-frames 10 \
  --score-thresh 0.6 \
  --max-frames 500 \
  --device cuda \
  --pretrained \
  --nim-base-url http://160.211.46.122:8000/v1 \
  --model-name nvidia/cosmos-reason2-8b
```

## Update: Reasoning Debug Trace (Feb 22, 2026)

Added end-to-end debug trace support for NIM reasoning calls.

### New controls
- CLI flag: `--reasoning-debug / --no-reasoning-debug` (default: off)
- Web request field: `reasoning_debug` (default: false)

### New artifacts/counters
- `run_summary.json.artifacts.reasoning_debug` points to `reasoning_debug.jsonl` when enabled.
- `run_summary.json.counts.reasoning_debug_entries` counts logged reasoning invocations.

### What debug trace includes per invocation
- URL/model/frame URI
- Context counts (`allowed_entity_uris`, `ann_neighbors`, `recent_events`, etc.)
- ANN preview (top neighbors with URI, score, class/frame metadata)
- Raw NIM response content (trimmed if needed)
- Parse mode (`strict` or `lenient_coerce`)
- Raw/coerced/final claim counts

### Verification run
- Output dir: `out_debug_check/`
- Result: 4 debug entries were produced and recorded.
- Finding: model responses had `claims: []` directly from NIM (`raw_claims_count=0`), so zero-claim outcome is model output, not parser filtering.

## Update: Structured-Claim Recovery + Web Console Fix (Feb 22, 2026)

### Added/changed
- `robosikg/reasoning/schemas.py`
  - Added optional `no_claim_reason` to reasoning output schema.
- `robosikg/reasoning/cosmos_reason2.py`
  - Prompt now explicitly requests `no_claim_reason` when claims are empty.
  - `PROMPT_SCHEMA` now accepts `no_claim_reason`.
  - Coercion preserves/sets `no_claim_reason` and narrows observed class extraction to relevant context keys.
  - Debug now records `raw_no_claim_reason` and `final_no_claim_reason`.
- `robosikg/agent/orchestrator.py`
  - Added motion context (`track_motion`) into reasoning input.
  - Added deterministic fallback claims when model returns none:
    - geometry-based (`near` / `inside` / `overlaps`) from current detections
    - retrieval-based (`near`) from ANN neighbors
  - Added counters:
    - `reasoning_model_claims_total`
    - `reasoning_deterministic_fallback_invocations`
    - `reasoning_deterministic_fallback_claims_total`
  - `reasoning_summary` events now include `no_claim_reason` and `claim_source`.
- `scripts/evaluate.py` / `docs/run_summary_schema.md`
  - Included new deterministic-fallback/model-claim counters.
- `scripts/run_web_console.py`
  - Added repo-root path bootstrap so `python3 scripts/run_web_console.py` no longer fails with `ModuleNotFoundError: robosikg`.

### Validation
- Test suite: `pytest -q` -> `21 passed`.
- Web console startup command now works and serves on `http://0.0.0.0:8080`.
- Verification run: `out_fix_check2/`
  - `reasoning_model_claims_total = 0`
  - `reasoning_deterministic_fallback_claims_total = 16`
  - `reasoning_claims_total = 16`
  - `Edge` instances present in `graph.nt` (non-zero relation edges now written).

## Update: Web Console Controls + WebSocket Runtime (Feb 22, 2026)

### Added/changed
- `requirements.txt`
  - Added `websockets==13.1` so Uvicorn can run WebSocket protocol handlers for `/ws/live`.
- `robosikg/web/static/app.js`
  - Wired previously dead controls (`Pause`, `Reset`, `Record`, `Menu`, `Play`, `Step`, `Layout`).
  - Added generic placeholder wiring so any remaining unimplemented buttons now report clearly in the event feed instead of appearing dead.
  - Added helper actions:
    - video play/pause toggle
    - timeline step
    - graph relayout
    - dashboard selection reset
- `README.md`
  - Added note that live updates require WebSocket support from `requirements.txt`.

### Validation
- `pytest -q` -> `21 passed`.
- Web console boot check: `timeout 6 python3 scripts/run_web_console.py` starts successfully.
- Runtime check after install: `AutoWebSocketsProtocol is None` -> `False` (WebSocket support active).

## Update: Full Console Backend Wiring + Graph Labels (Feb 22, 2026)

### Added/changed
- `robosikg/web/app.py`
  - Added backend console state + action APIs:
    - `GET /api/console/state`
    - `POST /api/console/action`
  - Added action handlers for workspace/rail/layers/modules/menu/pause/reset/record/instruction and graph/timeline action logging.
  - Added cooperative run control hooks (pause/resume/stop) via `PipelineService` flags.
  - Added run export endpoint:
    - `POST /api/runs/{run_id}/export` -> zip bundle under `out_web_exports/`.
  - Added SPARQL query endpoint:
    - `POST /api/sparql/query`.
  - Added export static mount at `/exports`.
  - Added optional websocket recording to `out_web_recordings/*.jsonl`.
  - Improved graph node labels to combine semantic context + short hash; node payload now also includes `short_id` and `cls`.
- `robosikg/agent/orchestrator.py`
  - Added optional `should_stop` / `wait_if_paused` callbacks to `run_mp4`.
  - Added `counts.stopped_early`.
- `robosikg/web/static/index.html`
  - Added IDs for all control buttons for deterministic wiring.
- `robosikg/web/static/app.js`
  - Wired all visible control buttons to backend actions/endpoints.
  - Added SPARQL query execution UI path and run export integration.
  - Synced UI state from backend console snapshot + websocket `console_state` events.
  - Added pause/resume and recording state UI updates.
- `robosikg/web/static/styles.css`
  - Added badge styles for `paused` and `stopped`.
- `docs/web_console_controls.md`
  - Added full button-by-button operator guide with backend endpoint mapping.
- `README.md`
  - Linked controls guide and documented new console/export/query APIs and label behavior.
- `docs/run_summary_schema.md`
  - Documented `counts.stopped_early`.

### Validation
- `pytest -q` -> `21 passed`.
- `python3 -m py_compile robosikg/web/app.py robosikg/agent/orchestrator.py` -> success.
- Web console boot check: `timeout 6 python3 scripts/run_web_console.py` -> startup success.
- Endpoint smoke tests via `fastapi.testclient`:
  - `/api/console/state`, `/api/console/action`, `/api/runs/{id}/export`, `/api/sparql/query` all returned `200`.
