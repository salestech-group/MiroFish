# Technology Stack

## Architecture

A two-tier web app with a long-running **background-task** core:

- **Frontend** (Vue 3 + Vite) — Single-page UI orchestrating the 5-step
  workflow. Polls the backend for task progress; renders the knowledge
  graph with D3.
- **Backend** (Flask + `uv`) — Stateless HTTP API on top of in-memory
  `Project` and `Task` models. Heavy work (ontology extraction, graph
  build, profile generation, simulation, report) runs as background
  tasks tracked through `Task` and exposed via polling endpoints.
- **Knowledge graph** — Neo4j is the durable store; Graphiti is the
  write/read layer. All queries are scoped by per-project `group_id`.
- **Simulation** — CAMEL-OASIS executes in subprocesses; the Flask app
  communicates with them only through `services/simulation_ipc.py`.

The system favors **process isolation** for the simulator and **in-memory
state with restart recovery** for project/task tracking, rather than a
classic job queue + persistent DB.

## Core Technologies

- **Backend language**: Python ≥3.11, ≤3.12
- **Backend framework**: Flask 3.0 + flask-cors
- **Backend tooling**: `uv` for dependency management
- **Frontend framework**: Vue 3.5 + Vue Router 4 + `vue-i18n` 11
- **Frontend tooling**: Vite 7
- **Graph DB**: Neo4j 5.x (Community) via `bolt://`
- **Graph layer**: `graphiti-core` ≥ 0.3
- **Simulation**: `camel-oasis` 0.2.5 + `camel-ai` 0.2.78
- **LLM access**: OpenAI SDK against any OpenAI-compatible endpoint

## Key Libraries

Only the libraries that shape how new code is written:

- **`openai`** — Sole LLM client; new providers are integrated by changing
  `LLM_BASE_URL`/`LLM_MODEL_NAME`, **not** by adding a second SDK.
- **`graphiti-core`** — All graph reads/writes go through the
  `graphiti_adapter`; do not call Neo4j drivers directly from feature
  code.
- **`camel-oasis` / `camel-ai`** — Pinned versions; upgrading either
  requires re-validating the simulation pipeline end-to-end.
- **`PyMuPDF`, `charset-normalizer`, `chardet`** — File ingestion;
  encoding detection is mandatory because seed material is frequently
  non-UTF-8 (notably mixed Chinese/English).
- **`pydantic` v2** — Used for structured LLM output / validation.
- **`axios`** (frontend) — All API calls go through `src/api/*.js`
  services with a 5-min timeout and exponential retry; components must
  not call `fetch`/`axios` directly.
- **`d3` v7** — Knowledge-graph visualization in `GraphPanel.vue`.

## Development Standards

### Type Safety
- Python: type hints where the surrounding file uses them. Don't retrofit
  hints into untyped modules just for consistency.
- Frontend: plain JavaScript, not TypeScript. Use JSDoc only when it
  improves clarity.

### Code Quality
- **No enforced linter or formatter** in this repo by design. Match the
  surrounding file's style. Discuss with the user before introducing
  ESLint/Prettier/Ruff/Black.
- 4-space indentation everywhere.
- Python: `snake_case`. Existing files mix English and Chinese in
  comments/docstrings — preserve both; do not translate one into the
  other unless asked.

### Testing
- pytest is wired (`backend/scripts/test_profile_format.py`) but coverage
  is intentionally minimal. Don't add a heavy test harness without
  discussing scope.
- For UI changes, run `npm run dev` and exercise the feature in a
  browser; type-check/test passes do not prove feature correctness here.

### Internationalization
- User-visible strings live in repo-root `/locales/*.json` (`en.json`,
  `zh.json`, `languages.json`). The `frontend/vite.config.js` aliases
  `@locales` to that root folder so the backend logger and frontend share
  the same keys.
- Backend logger messages are part of the i18n surface — translate keys,
  not raw log lines, when adding new logs that surface to users.

## Development Environment

### Required Tools

| Tool      | Version       |
| --------- | ------------- |
| Node.js   | ≥18           |
| Python    | ≥3.11, ≤3.12  |
| `uv`      | latest        |
| Neo4j     | 5.x Community |
| Docker    | optional      |

### Common Commands

```bash
# Setup (one-shot)
npm run setup:all

# Dev (backend on :5001, frontend on :3000 with /api proxy)
npm run dev

# Run individually
npm run backend
npm run frontend

# Build frontend
npm run build

# Backend tests
cd backend && uv run python -m pytest

# Full stack (incl. Neo4j)
docker compose up
```

## Key Technical Decisions

- **Neo4j + Graphiti replaces Zep Cloud.** Several services still carry
  the legacy `zep_*` filename prefix (`zep_tools.py`,
  `zep_entity_reader.py`, `zep_graph_memory_updater.py`). New code must
  not depend on Zep Cloud. The `ZEP_API_KEY` env var is kept (empty
  string is fine) only for backwards compatibility.
- **Per-project graph isolation via `group_id`.** Every Graphiti read or
  write must filter by the project's `group_id`. There is no
  cross-project graph access.
- **Reasoning-model output stripping.** Models like MiniMax and GLM emit
  `<think>` blocks and markdown fences; outputs are stripped before JSON
  parsing (see commit `985f89f`). New LLM-output parsers must do the
  same.
- **Background tasks via `Task` model, not a queue.** Anything taking
  more than a few seconds returns immediately and tracks progress on a
  `Task` object the frontend polls. There is no Celery/RQ/etc.
- **Startup recovery for stuck projects.** On boot,
  `_recover_stuck_projects` promotes projects in `GRAPH_BUILDING` to
  `GRAPH_COMPLETED` if Neo4j already has their nodes. New long-running
  task types should follow the same recovery pattern.
- **Subprocess cleanup is centralized.** `SimulationRunner.register_cleanup()`
  registers a shutdown hook so simulation subprocesses die with the app.
  Don't spawn subprocesses outside this path.
- **Configuration is a single Python file.** `backend/app/config.py`
  holds LLM, Neo4j, embedding, chunking, OASIS, and ReportAgent
  settings. Prefer extending it over scattering env-var reads through
  the codebase.
- **Default simulation parameters.** Max 10 rounds. Twitter actions:
  `CREATE_POST`, `LIKE_POST`, `REPOST`, `FOLLOW`, `QUOTE_POST`,
  `DO_NOTHING`. Reddit additionally: `CREATE_COMMENT`, `LIKE_COMMENT`,
  `DISLIKE_*`, `SEARCH_*`, `TREND`, `REFRESH`, `MUTE`. Changes go in
  `config.py`, not per-call.

---
_Document standards and patterns, not every dependency_
