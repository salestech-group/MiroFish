# API Standards

These are the conventions for the **Flask backend** consumed by the
Vue frontend. Generic REST guidance is secondary to the patterns
already established in `backend/app/api/`.

## Philosophy

- The frontend is the only consumer; we optimize for *that* contract,
  not for a hypothetical public API.
- Long-running work returns immediately with a `task_id`; clients
  poll. There are no streaming responses or websockets.
- The backend is stateless across restarts of `Project`/`Task` data
  (in-memory), with deterministic recovery on boot.

## URL Pattern

Routes live under `/api/<domain>/<action>` where domain matches the
Flask blueprint:

- `/api/graph/...` — `graph_bp` (`api/graph.py`)
- `/api/simulation/...` — `simulation_bp` (`api/simulation.py`)
- `/api/report/...` — `report_bp` (`api/report.py`)

Within a blueprint, resource sub-paths are accepted but **action-style
endpoints are equally common** (`/ontology/generate`,
`/project/<id>/reset`). Don't force REST verbs onto operations that
aren't naturally CRUD — match the surrounding file.

The Vite dev server proxies `/api/*` from `:3000` to `:5001`. Don't
hard-code the backend host in frontend code.

## Response Envelope

Every response uses this shape — do **not** invent a new one:

```json
// Success
{ "success": true, "data": { ... } }

// Failure
{ "success": false, "error": "Human-readable message" }
```

- `success` is always present and boolean.
- Successful responses put the payload under `data`. List endpoints may
  also include sibling fields (`count`, etc.) — see
  `/project/list` for the precedent.
- Error responses use `error: <string>`. There is no error-code enum.
  Messages may be in English or Chinese to match the rest of the
  module — keep both styles working.
- HTTP status follows the outcome: `200` on success, `400` for client
  validation, `404` for missing entities, `500` for unhandled
  exceptions.

## Long-Running Operations: The Task Polling Contract

This is the defining backend pattern. Anything that takes more than a
few seconds (ontology generation, graph build, profile generation,
simulation, report generation) **must** use it.

### Submit endpoint

- Validates input synchronously.
- Creates a `Task` via `TaskManager().create_task(task_type, metadata)`.
- Spawns a background `threading.Thread` that runs the work and
  updates the task as it progresses.
- Returns immediately:

```json
{ "success": true, "data": { "task_id": "...", "project_id": "..." } }
```

### Background worker

- Calls `TaskManager().update_task(task_id, progress=…, message=…, progress_detail=…)`
  at meaningful checkpoints (not every loop iteration).
- On success: `complete_task(task_id, result_dict)`.
- On failure: `fail_task(task_id, error_string)` — never let the
  exception escape the thread; tasks must always reach a terminal
  state.

### Status endpoint

- A polling endpoint (typically `/api/<domain>/task/<task_id>` or
  similar) returns the current `Task.to_dict()`.
- The frontend service layer (`frontend/src/api/*.js`) handles
  exponential backoff + a 5-min timeout; new endpoints don't need
  custom retry logic on the client.

### Task lifecycle

`PENDING → PROCESSING → COMPLETED | FAILED`. Other status fields
(`progress` 0–100, `progress_detail` dict) are advisory — the frontend
decides how to render them. Don't add new statuses without a
frontend-side change.

## Where Logic Belongs

- **`api/` (handlers)**: validate input, look up `Project`/`Task`,
  dispatch to a service, format the envelope. No graph access, no LLM
  calls, no `subprocess`.
- **`services/`**: all business logic, including spawning the
  background thread for long-running work.
- **`models/`**: state shape only.

If a handler is doing more than a few lines of orchestration, the work
belongs in a service.

## Authentication

There is no user-level authentication today. Endpoints assume a
trusted operator on the same network (dev, Docker, internal
deployment). **Do not add ad-hoc auth checks scattered through
handlers** — if/when auth is needed, it goes through Flask middleware
and is documented in a new steering file. Until then, treat all
endpoints as authenticated by deployment.

## Versioning

No version prefix in URLs. The frontend ships with the backend in a
single repo, so backwards compatibility for the API is not a concern.
If that ever changes (public API, multiple frontend versions), version
the affected blueprint, not the whole API.

## Pagination

- `/project/list` accepts `?limit=<n>` (default 50). Match this
  pattern for new list endpoints.
- Graph queries use `utils/graph_paging.py` for cursor-style paging.

## What Not to Do

- Don't return raw exceptions or stack traces in `error`.
- Don't bypass `TaskManager` for long-running work (e.g. with a custom
  status field on `Project`).
- Don't add new response envelope shapes — extend `data`.
- Don't introduce streaming (SSE, websockets) without a steering-level
  discussion; the polling model is intentional.

---
_Focus on patterns and decisions, not endpoint catalogs._
