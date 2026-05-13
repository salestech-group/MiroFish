# Step 1 — CLAUDE.md Conventions Decisions

Decisions made while updating `CLAUDE.md` (Step 1, PROMPT 2).

## Date: 2026-05-06

## Drivers
The recent merge `feat/graphiti-neo4j-migration` (commit `6264828`)
established **Neo4j + Graphiti** as the primary knowledge-graph store.
The previous CLAUDE.md was out of date.

## Section-by-Section Decisions

### Tech Stack
- **Memory/Graph (UPDATED):** Primary = **Neo4j + Graphiti** (`graphiti-core>=0.3`).
  All graph retrieval modules call into Graphiti via `GraphitiAdapter`.
- **Versions added:** Vue 3.5, Vite 7, axios 1.14, vue-router 4.6,
  vue-i18n 11, D3 7, camel-oasis 0.2.5, camel-ai 0.2.78.
- **i18n:** Documented `vue-i18n` + `/locales/{en,zh,languages}.json`.

### Required Environment Variables
Updated to reflect `app/config.py`:
- Added: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `EMBEDDING_MODEL`.
- Added: optional `LLM_BOOST_*` block (omit entirely if unused).

### Conventions (per user direction)
- **Follow the conventions already established in this project.**
- Don't impose external style guides on existing code.
- 4-space indent, snake_case in Python; comments/docstrings mix English
  and Chinese — both styles must continue to work.
- No enforced formatter or linter — match the surrounding file.
- New tooling decisions (Ruff, Prettier, etc.) require discussion before
  adoption.

### Architecture — Must-Respect Rules
Confirmed all architectural patterns drawn from the actual code:
1. Background tasks via `Task` model (status + progress polling).
2. Reasoning-model output stripping (`<think>` tags, code fences).
3. Simulation IPC via `simulation_ipc.py`.
4. Subprocess cleanup via `SimulationRunner.register_cleanup()`.
5. Startup recovery via `_recover_stuck_projects()`.
6. Per-project graph isolation via `group_id` (Neo4j-specific).
7. Chat prefix injection to suppress tool calls in user-visible
   responses.

### Commands
- Added a note that `npm run dev` requires Neo4j running.
- Added a note that no lint/format command is configured.
- Clarified that pytest currently has only one script-style test
  (`backend/scripts/test_profile_format.py`).

## What's Now in CLAUDE.md
- Project overview (unchanged).
- Commands (with Neo4j prerequisite note + lint disclaimer).
- Tech stack (Neo4j+Graphiti, full versions).
- Required env vars (Neo4j block, optional boost block).
- 5-step pipeline (rephrased to mention Graphiti+Neo4j).
- Backend / frontend structure (added i18n, locale, logger to utils).
- Key implementation conventions (the seven must-respect rules).
- Coding conventions (project-internal, no external imposition).

## Next
- **PROMPT 3:** Review / update `README.md`.
