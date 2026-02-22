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
  - Also drives section visibility/focus in the UI (contextual workspace view).

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
- `Full`:
  - Requests fullscreen on the video stage container (video + overlay canvas).
  - This is the reliable fullscreen path when overlays are enabled.
  - Double-click on video also routes to this fullscreen path.
- Layer pills:
  - `Timeline`, `Boxes`, `Masks`, `Tracks`, `Labels` toggle backend layer state (`toggle_layer`).
  - `Boxes`, `Masks`, `Tracks`, `Labels` are rendered client-side on top of video.
  - `Tracks` also draws trajectory polylines when reasoning payload includes trajectory points.

### Overlay Data Behavior

- During a live run:
  - Frame events include `boxes` and `tracks`, so overlays update from websocket stream.
- When loading a historical run:
  - UI fetches `GET /api/runs/{run_id}/overlays` and maps video time to nearest available source-frame index.
  - This avoids periodic overlay dropouts when sampled frame indices are sparse (for example `0, 8, 16, ...`).

### Native Video Fullscreen Notes

- Browser-native fullscreen controls (inside the `<video>` element) are browser-managed.
- The app performs best-effort promotion from native video fullscreen to stage fullscreen so overlays remain visible.
- Native fullscreen control clicks are additionally bridged via pointer/click heuristics to request stage fullscreen directly.
- Browser policy may still prevent retargeting in some environments; when that happens, use `Full` in the timeline controls for guaranteed overlay fullscreen.

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
