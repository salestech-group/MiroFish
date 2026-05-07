# Database / Knowledge Graph Standards

The "database" in MiroFish is **Neo4j accessed via Graphiti**, not a
relational store. There is no SQL, no migrations file, no ORM. Generic
relational guidance does not apply — these are the project-specific
patterns.

## Architecture

- **Engine**: Neo4j 5.x Community over `bolt://`.
- **Graph layer**: `graphiti-core` ≥ 0.3 — handles node/edge writes,
  embeddings, hybrid search, reranking.
- **Adapter**: `backend/app/services/graphiti_adapter.py` is the **only**
  module that imports `graphiti_core` directly. Every other module talks
  to the graph through this adapter.

The adapter exposes a Zep-Cloud-shaped namespace
(`client.graph.add_episode(...)`, `client.graph.search(...)`, etc.) so
legacy `zep_*` services kept their existing call sites after the
migration. New code should use the same surface — do not introduce a
parallel API.

## Core Rule: `group_id` Isolation

**Every read or write to the graph must be scoped by the project's
`group_id`.** The graph is multi-tenant by construction; cross-project
access is not permitted and is grounds for rejecting a change in review.

- A project's `group_id` lives on its `Project` model and never changes
  after creation.
- When constructing search filters, episode adds, or node/edge fetches,
  always pass `group_id=project.group_id` (or the equivalent
  `group_ids=[...]`).
- If you need data spanning projects (e.g. an admin view), aggregate
  per-project at the API layer; do not query the graph without a
  `group_id` filter.

## Adapter Patterns That Must Stay Intact

These are non-obvious and break subtly when violated:

- **Single Graphiti singleton.** `_get_graphiti()` lazily constructs one
  `Graphiti` instance for the whole process. Do not instantiate
  `Graphiti` in services or tests.
- **Persistent event loop in a dedicated thread.** All async graph calls
  are dispatched through `_run(coro)` onto a single background event
  loop (see `graphiti-event-loop` thread). The Neo4j async driver is
  bound to whichever loop opened it; crossing loops corrupts the driver
  state. Never call `asyncio.run(...)` on a Graphiti coroutine, and
  never schedule one on a request thread's loop.
- **Indices and constraints on first init.** `build_indices_and_constraints()`
  runs once when the singleton is created. New required indexes go
  through Graphiti's mechanisms, not raw Cypher in services.

## What Belongs in the Graph

- **Entities** — Domain objects extracted by the ontology generator
  (people, organizations, concepts, events, etc.).
- **Edges** — Relationships between entities, typed per the project's
  generated ontology.
- **Episodes** — The raw text/units the entities were derived from;
  Graphiti owns chunking and embedding.

What does **not** belong in the graph:

- Project / task metadata (lives in in-memory `ProjectManager` and
  `TaskManager`).
- Simulation state (owned by OASIS subprocesses).
- User-uploaded files (filesystem only — paths, not contents, are
  passed through the API).

## Schema & Ontology

- Ontology (entity types + edge types) is **generated per project** by
  the LLM in step 1, stored on the `Project` model, and used to
  constrain extraction during graph build.
- There is no global, hand-maintained schema file. Don't add one — the
  ontology is intentionally per-project.
- Reasoning-model outputs from ontology generation are stripped of
  `<think>` blocks and code fences before JSON parsing (see
  `tech.md`'s "reasoning-model output stripping" decision).

## Embeddings

- `EMBEDDING_MODEL` is configurable per provider:
  - OpenAI default: `text-embedding-3-small`
  - Gemini: `text-embedding-004` / `gemini-embedding-001`
- Embedding model selection lives in `config.py`. Don't hard-code it in
  services.
- Switching embedding model **invalidates existing project graphs** —
  document this if you add an option that changes the default.

## Query Patterns

- Read via the adapter's search methods (hybrid RRF recipes are wired
  in `graphiti_adapter.py`); avoid raw Cypher in feature code.
- If a feature genuinely requires raw Cypher, add it as a method on the
  adapter, scoped by `group_id`, with a comment explaining why
  Graphiti's API is insufficient.
- Pagination over Graphiti results uses `utils/zep_paging.py` (legacy
  name, still applicable).

## Startup Recovery

`_recover_stuck_projects` runs on app boot and promotes any project
left in `GRAPH_BUILDING` to `GRAPH_COMPLETED` if the graph already has
that project's nodes — handling the case where the original task was
killed by a restart. **Any new long-running graph operation must
either:**

1. Be safe to re-run from the start, OR
2. Add an analogous recovery path so a restart mid-task doesn't strand
   the project.

## Backups

Graph data is treated as **regenerable from seed material**, not as
durable user data — there is no project-managed backup/restore. If a
deployment requires durability, that's an operator concern (Neo4j
backups), not a feature-code one.

---
_Focus on patterns and decisions. No environment-specific settings._
