# Cosmos Cookoff Submission Checklist

## Required Artifacts

1. Public code repository URL with reproducible deployment instructions.
2. Demo video under 3 minutes.
3. Written description of what was built and how it works.

## Repo Readiness

1. `README.md` includes install, run, and evaluate commands.
2. `scripts/run_demo.py` produces `graph.ttl`, `graph.nt`, and `run_summary.json`.
3. `scripts/evaluate.py` produces `eval_report.json`.
4. CI runs tests on push/PR.
5. Optional NIM integration steps are documented.
6. `docs/sparql_query_playbook.md` includes presentation-ready SPARQL examples.

## Demo Readiness

1. Prepare input MP4 and fixed run command.
   - For this repo, `data/scratch/traffic.mp4` and `data/scratch/balloons.mp4` are tracked for reproducibility.
2. Capture one successful run with deterministic outputs.
3. Highlight:
   - deterministic hashed IDs
   - KG + SPARQL retrieval
   - vector retrieval with routing diagnostics
   - reasoning output + fallback/consultant behavior

## Final Submission Pass

1. Confirm code is public and dependencies are installable.
2. Verify video length < 3:00.
3. Include direct instructions for judging reproducibility.
