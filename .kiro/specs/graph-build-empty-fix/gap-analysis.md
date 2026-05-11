# Gap Analysis: graph-build-empty-fix

## Scope Snapshot

The fix is small in code surface (config defaults, embedder construction, docs) but research-heavy on root cause (why does Graphiti `add_episode` appear to succeed yet leave Neo4j empty?). The Ollama documentation, OpenAI-compatible embedder support, and loud `add_batch` failure already exist from spec `graphiti-ollama-embedder` (issue #18). What's still missing: flipping the active default to Ollama and confirming the dimension-mismatch hypothesis that drives the empty-graph symptom.

## Current State

### Relevant Assets

- `backend/app/services/graphiti_adapter.py:92–139` — `_build_llm_and_embedder` constructs OpenAI or Gemini providers. The OpenAI branch reads `Config.EMBEDDING_BASE_URL or Config.LLM_BASE_URL` and `Config.EMBEDDING_API_KEY or Config.LLM_API_KEY`. This branch is already Ollama-compatible (Ollama exposes an OpenAI-shaped `/v1/embeddings`).
- `backend/app/services/graphiti_adapter.py:466–486` — `_GraphNamespace.add_batch` re-raises on episode-ingestion failures (spec #18). No placeholder UUIDs. Logger is `ERROR` with traceback.
- `backend/app/services/graph_builder.py:227–230` — `_build_graph_worker` catches `Exception`, captures traceback, calls `TaskManager().fail_task(task_id, error_msg)`.
- `backend/app/__init__.py:88–109` — `_recover_stuck_projects` gates promotion to `GRAPH_COMPLETED` on `count(n:Entity {group_id}) > 0`. Matches Req 4 AC5 already.
- `backend/app/config.py:42, 52–53` — current defaults:
  - `EMBEDDING_MODEL = 'text-embedding-3-small'` (OpenAI, 1536-dim)
  - `EMBEDDING_BASE_URL = None` → falls back to `LLM_BASE_URL`
  - `EMBEDDING_API_KEY = None` → falls back to `LLM_API_KEY`
- `README.md:163–183` — Ollama section present but commented out; OpenAI defaults are still the active path.
- `CLAUDE.md:72–80` — already names `mxbai-embed-large` (1024-dim) and explicitly rules out 768-dim `nomic-embed-text`. Documentation framing already treats Ollama as a supported provider.
- `docker-compose.yml:31–33` — already notes the `host.docker.internal:11434` reach-through for Ollama.

### Conventions in Play

- All Neo4j/Graphiti access goes through `services/graphiti_adapter.py` (per `.kiro/steering/database.md`).
- Configuration is centralized in `backend/app/config.py` — env-driven, single file.
- Background-task error handling: worker `try/except` → `fail_task(task_id, str(e))` (per `.kiro/steering/error-handling.md`).
- Graph is multi-tenant by `group_id`; every read/write must be scoped.

### Integration Surfaces Out of This Repo

- `graphiti-core` package — owns `EMBEDDING_DIM = 1024`, Neo4j vector index DDL, and `add_episode` LLM-extraction → embedding → write pipeline. Not vendored here; behavior must be inferred from runtime + their public API.
- Local Ollama daemon (operator-managed) — out of scope to bundle, in scope to assume runs at `host:11434`.

## Requirement-to-Asset Map

| Requirement | Asset / Touchpoint | Gap |
| --- | --- | --- |
| **R1 Root cause** | `_build_llm_and_embedder`, `add_batch`, `add_episode` runtime behavior, Neo4j vector-index dim | **Unknown** — need a reproduction run on default `main` config to capture the exact failure surface (dimension mismatch vs. embedder 404 vs. silent LLM-extraction-returns-empty). |
| **R2 Local-default** | `config.py:42, 52–53`, `.env.example` (protected — operator will reload), `README.md:163–183` | **Missing** — defaults still point to OpenAI; need to flip to Ollama (`mxbai-embed-large` @ `http://localhost:11434/v1`) and demote OpenAI/Gemini to commented fallbacks. |
| **R3 Dimension consistency** | `graphiti-core`'s `EMBEDDING_DIM = 1024` (external constant); `CLAUDE.md:72–80` documentation | **Constraint** — keep dim at 1024, don't expose a tunable. The Ollama default `mxbai-embed-large` is 1024-dim, so the defaults align. |
| **R4 Loud failure on every silent path** | `add_batch` (already loud), `_build_llm_and_embedder` (no pre-flight), `graph_builder._wait_for_episodes` (polls a no-op `episode.get`) | **Constraint** + possibly **Missing** — if R1 turns up an additional silent-failure call site (likely candidates: graphiti `add_episode` swallowing extraction failures, or a dim-mismatch returning soft errors), add a remediation there. |
| **R5 Backwards compatibility** | `_build_llm_and_embedder` OpenAI/Gemini branches | **Constraint** — no logic change required; only defaults change. Operator's explicit `EMBEDDING_*` settings continue to win. |
| **R6 Documentation** | `README.md:163–183`, `CLAUDE.md:72–80`, `docker-compose.yml:31–33`, `.env.example` (protected) | **Missing** — flip the README from "Ollama as commented option" to "Ollama as active default, OpenAI/Gemini commented fallback"; CLAUDE.md needs a small wording tweak; `.env.example` requires operator-coordinated edit (file is hook-protected). |
| **R7 End-to-end smoke** | Graph build → env setup (`profile_generator`) → report agent tools — not directly modified, just exercised | **Constraint** — requires a representative seed file. PR description documents whether the smoke test ran. |

## Implementation Approach Options

### Option A — Defaults-Only Flip (extend existing)

Change `backend/app/config.py` defaults and `.env.example` + README/CLAUDE.md/docker-compose comments. No code-path changes to `_build_llm_and_embedder` (the "openai" branch already serves Ollama). Optionally add a one-line ERROR log in `graphiti_adapter._build_llm_and_embedder` when `EMBEDDING_BASE_URL` is unset, warning that the LLM base URL is being reused (which is a known dim/model mismatch trap with Dashscope/Qwen).

**Trade-offs**
- ✅ Tiny, reversible, matches conventions.
- ✅ Fully relies on existing loud-failure plumbing.
- ❌ If R1 turns up a silent path inside `add_episode` itself (graphiti-core), defaults-only does not fix it.

### Option B — Defaults Flip + Pre-flight Embedder Probe (extend existing + small new helper)

Same as A, plus a one-shot embedder ping during `_get_graphiti()` initialization: synchronously call the configured embedder on a known string and assert the response length matches Graphiti's `EMBEDDING_DIM`. On mismatch or connectivity failure, raise so the first `Project` creation surfaces the error rather than the first graph-build worker.

**Trade-offs**
- ✅ Surfaces dimension/connectivity bugs before a long graph build runs.
- ✅ Avoids per-batch "is this even reachable?" guessing.
- ❌ Requirements explicitly call out "no startup-time embedder health probe that refuses to boot" (Boundary Context, out of scope). This option contradicts that boundary.

### Option C — Defaults Flip + First-Batch Failure Surfacing (hybrid, recommended)

Option A, plus targeted hardening based on what R1 reveals. Likely candidates if root cause is a graphiti-core silent path:
- Wrap the first `add_episode` call with an explicit dimension-check on the produced embedding (compare against `EMBEDDING_DIM`) and raise a clear `ValueError("embedding dim mismatch")` from `add_batch` before the Neo4j write, so the worker fails the task with an actionable message.
- Tighten `_get_graph_info` such that `complete_task` is gated on a non-zero node count (Req 4 AC5), so a "succeeded but empty" graph never reaches `GRAPH_COMPLETED`.

**Trade-offs**
- ✅ Targets the actual failure mode identified by R1 instead of speculating.
- ✅ Stays within the boundary (no startup probe, no new env var, no new provider).
- ✅ Matches existing conventions: a small `if not nodes: raise` inside the worker, propagated to `fail_task`.
- ❌ Slightly larger PR than A; the dim-check helper is new code (10–20 lines).

## Effort & Risk

- **Effort:** **S (1–3 days)** — code change is small; majority of the work is the root-cause repro + smoke-testing the end-to-end pipeline with a local Ollama instance.
- **Risk:** **Medium** — relies on a Graphiti-core/Neo4j interaction that we don't fully control. If the root cause is upstream and only fixable via a graphiti-core version bump, scope creeps. Mitigation: if upstream fix is required, capture it in the PR description and ship the defaults-flip + first-batch dim check now; the loud failure ensures operators see the real error rather than an empty graph.

## Research Items for Design Phase

1. **Confirm the exact silent-failure call site.** Run a fresh build on `main`'s default `.env` and trace where the entity-extraction-or-write disappears: graphiti-core LLM extraction stage, the embedder call, or the Neo4j vector-index write. Log/instrument as needed.
2. **Verify the embedder-output dimension at runtime.** With `mxbai-embed-large` via Ollama, confirm `len(embedding) == 1024`. With `text-embedding-3-small`, confirm 1536, and observe what Neo4j (or graphiti-core's vector-index check) does with the mismatch.
3. **Decide whether `_get_graph_info` gating belongs in this PR.** If R1 root cause is fully addressed by the defaults flip, the `node_count > 0` gate in `complete_task` is belt-and-braces. If R1 reveals a residual silent path, the gate becomes essential.

## Recommendations for Design Phase

- **Preferred approach: Option C** — flip defaults, instrument the first batch enough to capture R1 evidence, gate `complete_task` on a non-zero node count.
- **Key decisions to lock in design:**
  - Concrete default values for `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY` in `backend/app/config.py`.
  - Whether `_get_graph_info(graph_id)` returning `node_count == 0` should raise inside the worker (Req 4 AC5) or only when `add_batch` succeeded — the latter is the right semantics.
  - Wording for the README / CLAUDE.md flip: keep both providers documented; only change the *active* line.
- **Carry forward to implementation:**
  - `.env.example` is hook-protected; either coordinate with the developer to update it manually, or document the required diff in `HANDOFF.md`.
  - The end-to-end smoke test (graph build → profile generation → report query) needs a representative seed file; if unavailable, mark that explicitly in the PR.
