# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MiroFish is a multi-agent swarm intelligence prediction engine. It builds knowledge graphs from seed data, simulates thousands of AI agents interacting on virtual Twitter/Reddit platforms (via CAMEL-OASIS), and generates analytical reports — all to predict outcomes of real-world scenarios.

## Commands

### Setup
```bash
npm run setup:all        # Install all dependencies (frontend + backend)
npm run setup            # Frontend npm install only
npm run setup:backend    # Backend: uv sync (Python deps)
```

### Development
```bash
npm run dev              # Run backend + frontend concurrently
npm run backend          # Backend only: Flask on port 5001
npm run frontend         # Frontend only: Vite on port 3000
```

> **Prerequisite:** Neo4j must be running (default `bolt://localhost:7687`).
> The Graphiti-based knowledge graph requires it. Use `docker-compose up`
> for the full stack including Neo4j.

### Build
```bash
npm run build            # Build frontend (Vite)
```

### Backend (Python)
```bash
cd backend && uv run python run.py          # Start Flask server
cd backend && uv run python -m pytest       # Run tests (currently scripts/test_profile_format.py only)
```

### Docker
```bash
docker-compose up        # Full stack via Docker
```

> **Lint/format:** No linter or formatter is configured in this project.
> Match the existing style of the file you're editing.

## Architecture

### Stack
- **Backend**: Python ≥3.11, Flask 3.0, managed by `uv`
- **Frontend**: Vue 3.5 + Vite 7, port 3000; proxies `/api` → port 5001
- **LLM**: OpenAI SDK-compatible (default: Qwen via `dashscope`; also works with GLM, OpenAI, Gemini)
- **Memory/Graph**: **Neo4j + Graphiti** (`graphiti-core>=0.3`) — primary store for the knowledge graph (entities/edges scoped by `group_id` per project)
- **Simulation**: CAMEL-OASIS 0.2.5 + camel-ai 0.2.78 (multi-agent Twitter + Reddit simulation)
- **Visualization**: D3.js 7
- **i18n**: `vue-i18n` (frontend) + per-locale JSON in `/locales/` (`en.json`, `zh.json`, `languages.json`); backend logger messages translated as part of the i18n initiative

### Required Environment Variables
Copy `.env.example` to `.env`:
```
# LLM (OpenAI SDK-compatible)
LLM_API_KEY              # Required
LLM_BASE_URL             # Default: https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME           # Default: qwen-plus

# Neo4j + Graphiti (knowledge graph)
NEO4J_URI                # Default: bolt://localhost:7687
NEO4J_USER               # Default: neo4j
NEO4J_PASSWORD           # Default: mirofish123 (override in real env)
EMBEDDING_MODEL          # Default: mxbai-embed-large  (local Ollama, 1024-dim)
EMBEDDING_BASE_URL       # Default: http://localhost:11434/v1
EMBEDDING_API_KEY        # Default: "ollama"  (Ollama ignores the value)
                         # Other supported configurations:
                         #   • OpenAI:  text-embedding-3-small  (only if you accept
                         #             a remote dependency; set EMBEDDING_BASE_URL
                         #             to https://api.openai.com/v1 and
                         #             EMBEDDING_API_KEY to your OpenAI key)
                         #   • Gemini:  text-embedding-004 / gemini-embedding-001
                         #             (set GRAPHITI_LLM_PROVIDER=gemini)
                         # Constraint: model must produce 1024-dim vectors to match
                         # Graphiti's default EMBEDDING_DIM. 768-dim models such as
                         # nomic-embed-text are not supported.
                         # Prerequisite for the default: `ollama pull mxbai-embed-large`.

# Reranker (cross-encoder for Graphiti search results)
RERANKER_PROVIDER        # Default: ollama  (allowed: "ollama", "none")
                         # "none" keeps the legacy passthrough — useful for CI /
                         # slim containers that cannot pull a reranker model.
RERANKER_MODEL           # Default: qwen2.5:3b  (local Ollama chat model)
                         # Prerequisite for the default: `ollama pull qwen2.5:3b`.
RERANKER_BASE_URL        # Default: value of EMBEDDING_BASE_URL
                         # (typically http://localhost:11434/v1)
RERANKER_API_KEY         # Default: value of EMBEDDING_API_KEY
                         # (Ollama ignores the value)

# Optional — Accelerated LLM (omit entirely if not used)
LLM_BOOST_API_KEY
LLM_BOOST_BASE_URL
LLM_BOOST_MODEL_NAME
```

### 5-Step Pipeline
The core workflow is a sequential async pipeline:
1. **Graph Build** — Upload files → LLM extracts ontology → Graphiti writes nodes/edges to Neo4j (scoped by per-project `group_id`)
2. **Env Setup** — Read entities from Neo4j → Generate OASIS agent profiles (AI personalities)
3. **Simulation** — CAMEL-OASIS runs agents on dual platforms (Twitter + Reddit) in parallel
4. **Report** — `ReportAgent` (ReACT loop) queries the graph with tools: `SearchResult`, `InsightForge`, `Panorama`, `Interview`
5. **Interaction** — Chat with simulated agents or the `ReportAgent`

### Backend Structure (`backend/app/`)
- `api/` — Flask blueprints: `graph_bp`, `simulation_bp`, `report_bp`
- `services/` — Core logic: graph building, simulation runner, report agent, Graphiti adapter, graph retrieval tools
- `models/` — `Project` and `Task` state objects (in-memory, JSON-serializable)
- `utils/` — LLM client wrapper, file parser, retry logic, graph pagination, locale helpers, logger
- `config.py` — All configuration (LLM, Neo4j, embedding, chunking, OASIS, ReportAgent params)

Long-running operations (ontology generation, graph build, profile generation, report generation) run as background tasks tracked via `Task` objects with progress polling.

### Frontend Structure (`frontend/src/`)
- `views/` — Page components mapped to routes; `Process.vue` is the main 50KB workflow orchestrator
- `components/` — `Step1-5` step components + `GraphPanel.vue` (D3 graph visualization)
- `api/` — Axios services (`graph.js`, `simulation.js`, `report.js`) with 5-min timeout and exponential retry
- `i18n/` — Locale loader; messages in repo-root `/locales/`
- `router/`, `store/`, `assets/`

### Key Implementation Conventions

These are conventions **established by this project**. Match them when adding new code.

- **Background tasks via `Task` model** — Any operation that takes more than a few seconds (ontology gen, graph build, profile gen, simulation, report) must be tracked through `Task` with status + progress fields and exposed via a polling endpoint.
- **Reasoning-model output stripping** — Reasoning-model outputs (e.g. MiniMax/GLM with `<think>` tags or markdown code fences) must be stripped before JSON parsing. See the fix in commit `985f89f`.
- **Simulation IPC via `simulation_ipc.py`** — Inter-process communication between the Flask app and simulation subprocesses goes through this module; do not call subprocess primitives directly elsewhere.
- **Subprocess cleanup** — `SimulationRunner.register_cleanup()` is invoked at app start so simulation subprocesses are terminated on shutdown. Don't bypass it.
- **Startup recovery (`_recover_stuck_projects`)** — On boot, projects stuck in `GRAPH_BUILDING` are auto-recovered to `GRAPH_COMPLETED` if Neo4j already has their nodes (the original task was killed by a restart). New code paths that introduce long-running tasks should follow the same recovery pattern.
- **Per-project graph isolation** — All Neo4j/Graphiti queries must filter by the project's `group_id`. Cross-project graph access is not permitted.
- **Interview / chat prefix injection** — Agent chat suppresses tool calls in user-visible responses via prefix injection. Preserve this when extending chat behavior.
- **Default simulation parameters** — Max 10 rounds. Twitter actions: `CREATE_POST`, `LIKE_POST`, `REPOST`, `FOLLOW`, `QUOTE_POST`, `DO_NOTHING`. Reddit adds `CREATE_COMMENT`, `LIKE_COMMENT`, `DISLIKE_*`, `SEARCH_*`, `TREND`, `REFRESH`, `MUTE`. Configured in `app/config.py`.

### Coding Conventions
- Follow the conventions already established in this project — match the surrounding file's style.
- 4-space indentation, snake_case in Python; existing code mixes English and Chinese in comments/docstrings — keep both styles working.
- Use type hints where the surrounding code uses them; otherwise match local style.
- For new tooling decisions (lint, format, test runners), discuss before adding — the project intentionally has no enforced formatter at present.
