# Web Console Controls

This guide documents every control in the Ops Console and what each one does.

## Top Bar

- `Workspace` selector:
  - `Demo Workspace`, `Warehouse Ops`, `Traffic Ops`.
  - Persists console workspace state via `POST /api/console/action` (`select_workspace`).
- `Run` selector:
  - Chooses which prior run is loaded in graph/metrics/chat.
- `Pause` / `Resume`:
  - Pauses or resumes the active pipeline run (`toggle_pause`).
  - Pause is cooperative and takes effect between processed frames.
- `Reset`:
  - Requests stop for active run and resets console toggles (`reset_console`).
- `Record` / `Stop Rec`:
  - Starts/stops recording live websocket payloads to `out_web_recordings/*.jsonl` (`toggle_record`).
- `•••` (`Menu`):
  - Toggles backend menu state (`toggle_menu`).

## Left Rail

- `Perception`, `Reasoning`, `Warehouse`, `Graph`, `Policy`, `Settings`:
  - Sets active rail focus state in backend (`select_rail`).
  - Used for operator context persistence.

## Perception / Video Panel

- `Export`:
  - Creates a zip bundle for selected run at `out_web_exports/*.zip`.
  - Endpoint: `POST /api/runs/{run_id}/export`.
- `Overlays`:
  - Shows/hides overlay chips (`toggle_overlays`).
- `Play`:
  - Toggles video preview playback and logs backend action (`timeline_play`).
- `Step`:
  - Steps preview forward by 0.25s and logs backend action (`timeline_step`).
- Layer pills:
  - `Timeline`, `Boxes`, `Masks`, `Tracks`, `Labels` toggle backend layer state (`toggle_layer`).

## Graph Panel

- `Layout`:
  - Recomputes graph layout and logs backend action (`layout_graph`).
- `Refresh`:
  - Reloads selected run summary+graph from backend and logs action (`refresh_graph`).
- `Graph Filters` checkboxes:
  - Client-side filtering by node group.

## Operator Panel

- `Upload`:
  - Uploads `.mp4` to `data/scratch` (`POST /api/upload`).
- `Run Pipeline`:
  - Starts a new run (`POST /api/run`) with panel settings.
- Module pills:
  - `Vision`, `SLAM`, `LLM` toggle backend module state (`toggle_module`).
- `Operator Instruction` textarea:
  - Persists instruction text in backend (`set_instruction`).

## Query Panel

- `Copy`:
  - Copies SPARQL editor text to clipboard.
- `Run`:
  - Executes SPARQL against selected run graph (`POST /api/sparql/query`).
  - Returns tabular rows rendered in chat preview.

## Graph Labels

Graph node IDs stay stable (`id` is full URI), but display labels now combine meaning and identity:
- Example: `Region car #006711e9db`
- Example: `Frame f12 #a1b2c3d4e5`

This makes nodes readable without losing deterministic hashed identifiers.
