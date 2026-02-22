# `run_summary.json` Schema

Top-level fields:

- `source_id` (`string`): deterministic source identifier from CLI.
- `config` (`object`): resolved runtime config used for the run.
- `reasoning_backend` (`string`): final backend used (`nim`, `mock`, or `mock(auto-fallback)`).
- `reasoning_fallbacks` (`integer`): count of fallback transitions from NIM to mock in auto mode.
- `errors` (`array<object>`): structured non-fatal errors recorded during run.
- `timing` (`object`):
  - `started_ns` (`integer`)
  - `finished_ns` (`integer`)
  - `elapsed_s` (`number`)
  - `effective_fps` (`number`)
- `counts` (`object`):
  - `frames_seen` (`integer`)
  - `regions_added` (`integer`)
  - `tracks_seen` (`integer`)
  - `events_total` (`integer`)
  - `reasoning_invocations` (`integer`)
  - `reasoning_model_claims_total` (`integer`)
  - `reasoning_claims_total` (`integer`)
  - `reasoning_zero_claim_invocations` (`integer`)
  - `reasoning_invocations_with_claims` (`integer`)
  - `reasoning_avg_claims_per_invocation` (`number`)
  - `reasoning_deterministic_fallback_invocations` (`integer`)
  - `reasoning_deterministic_fallback_claims_total` (`integer`)
  - `trajectory_points_total` (`integer`)
  - `reasoning_debug_entries` (`integer`)
  - `kg_triples` (`integer`)
  - `vector_items` (`integer`)
- `events` (`array<object>`): recent run events (claims, summaries, fallbacks).
- `artifacts` (`object`):
  - `ttl` (`string|null`)
  - `ntriples_sorted` (`string|null`)
  - `summary` (`string`)
  - `reasoning_debug` (`string|null`)
