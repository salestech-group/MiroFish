# Research & Design Decisions

## Summary
- **Feature**: `graph-build-empty-fix`
- **Discovery Scope**: Extension
- **Key Findings**:
  - `_build_llm_and_embedder` (`backend/app/services/graphiti_adapter.py:92-139`) already supports any OpenAI-compatible `/v1/embeddings` endpoint through the existing `"openai"` branch — Ollama at `host:11434/v1` works without a new provider branch.
  - The empty-graph symptom is consistent with a **vector-dimension mismatch**: `Config.EMBEDDING_MODEL` defaults to OpenAI's `text-embedding-3-small` (1536-dim), but `graphiti-core` initialises the Neo4j vector index at 1024 dims. When `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` are unset, the embedder reuses `LLM_BASE_URL` / `LLM_API_KEY`, which on the documented Dashscope/Qwen default cannot serve OpenAI's embedding model and produces either a 4xx (since #18, raised to the worker) or a dim-mismatch write that graphiti-core does not validate.
  - The loud-failure plumbing from spec `graphiti-ollama-embedder` (issue #18) is intact: `_GraphNamespace.add_batch` re-raises with `logger.exception`, and `_build_graph_worker` calls `fail_task(...)`. Belt-and-braces: gate `complete_task` on a non-zero entity-node count so a "succeeded but empty" graph cannot reach `GRAPH_COMPLETED` if any silent path remains.
  - `_recover_stuck_projects` (`backend/app/__init__.py:88-109`) already gates recovery promotion on `count(:Entity {group_id}) > 0`, so Requirement 4 AC5's contract holds symmetrically on the startup side.

## Research Log

### Embedder construction path under current defaults
- **Context**: Determine the runtime configuration of the embedder when an operator runs `main` with the documented `.env` (Qwen via Dashscope for LLM, all `EMBEDDING_*` unset).
- **Sources Consulted**: `backend/app/services/graphiti_adapter.py:92-139`, `backend/app/config.py:32-54`, README.md L150-184.
- **Findings**:
  - Resolved values: `embedding_model = "text-embedding-3-small"` (1536-dim), `base_url = LLM_BASE_URL = https://dashscope.aliyuncs.com/compatible-mode/v1`, `api_key = LLM_API_KEY` (a Dashscope key).
  - Dashscope's OpenAI-compatible mode does not serve `text-embedding-3-small`. The call either 404s on the model name or returns an empty/incorrect response. Since spec #18, this failure path propagates to the worker — but operators reading the README's default config still trip it.
- **Implications**: Flipping the default `EMBEDDING_*` to a local Ollama embedder both (a) restores a self-hosted, free-by-default flow and (b) collapses the dim-mismatch class of empty-graph regressions because `mxbai-embed-large` is 1024-dim, matching graphiti-core's vector index.

### Graphiti-core vector index dimension
- **Context**: Confirm graphiti-core's expected embedding dimension and whether it is configurable from MiroFish.
- **Sources Consulted**: CLAUDE.md L78-80 (states the 1024-dim invariant), `.kiro/specs/graphiti-ollama-embedder/requirements.md` (Requirement 3 AC1), `_PassthroughReranker` in `graphiti_adapter.py:38-51` (precedent for working around upstream defaults).
- **Findings**:
  - `graphiti-core` ≥ 0.3 ships with `EMBEDDING_DIM = 1024`. It is not surfaced as an env knob in MiroFish today and is explicitly out of scope to change.
  - Therefore the embedder must produce 1024-dim vectors. `mxbai-embed-large` does; `text-embedding-3-small` (1536) and `nomic-embed-text` (768) do not.
- **Implications**: The only correct default model is one whose output is 1024-dim. Ollama's `mxbai-embed-large` is the project's already-documented choice (CLAUDE.md, README).

### Existing loud-failure contract
- **Context**: Verify that this spec inherits a working error-propagation contract rather than re-establishing one.
- **Sources Consulted**: `backend/app/services/graphiti_adapter.py:455-486` (`add_batch`), `backend/app/services/graph_builder.py:227-230` (worker `except`), `.kiro/steering/error-handling.md`.
- **Findings**:
  - `add_batch` calls `logger.exception(...)` and `raise` on the first failed episode (lines 478-483). No placeholder UUIDs.
  - The worker catches `Exception`, formats traceback, and calls `TaskManager().fail_task(task_id, error_msg)`.
- **Implications**: This spec must not weaken the contract. The only remaining silent surface is "the entire batch succeeds but produces no entities" — which the design handles by gating `complete_task` on a non-zero node count returned by `_get_graph_info(graph_id)`.

### Startup recovery contract
- **Context**: Confirm that `_recover_stuck_projects` already aligns with Requirement 4 AC5.
- **Sources Consulted**: `backend/app/__init__.py:88-109`.
- **Findings**: Recovery only promotes to `GRAPH_COMPLETED` when `count(:Entity {group_id}) > 0`. Gates on entities, not edges.
- **Implications**: No change needed in the recovery path. Symmetric gating in `complete_task` (this spec) yields a consistent "non-empty entities ⇒ COMPLETED" invariant on both startup recovery and live worker completion.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A — Defaults-only flip | Change `config.py` + `.env.example` + docs. No code logic change. | Smallest diff, fully reversible, leverages existing loud-failure plumbing. | Doesn't address the residual silent path of "Graphiti succeeded but produced no entities". | Sufficient if the dim-mismatch is the sole root cause. |
| B — Defaults flip + startup embedder probe | Plus a synchronous one-shot embedding ping during `_get_graphiti()` init, asserting dim match. | Surfaces dim/connectivity errors at boot. | Explicitly out of boundary per requirements (no startup probe). | Rejected. |
| C — Defaults flip + non-zero-count gate | Flip defaults; gate `complete_task` on `_get_graph_info(graph_id).node_count > 0`; if 0, call `fail_task` with a clear "graph build produced 0 entities" message. | Closes the "succeeded but empty" silent path symmetrically with `_recover_stuck_projects`. Stays within boundary. | Slightly larger diff (≈10 lines in `graph_builder.py`). | **Selected.** |

## Design Decisions

### Decision: Local Ollama (`mxbai-embed-large`) as the embedding default
- **Context**: Requirement 2 — local embedder is the default; remote providers stay as opt-in fallbacks.
- **Alternatives Considered**:
  1. Keep OpenAI default, document Ollama as the recommended path — rejected; doesn't satisfy R2 AC1/AC2.
  2. Switch default to a remote 1024-dim provider (e.g., Cohere `embed-english-light-v3.0`) — rejected; reintroduces a remote dependency in the hot path.
  3. Bundle Ollama in `docker-compose.yml` — rejected; explicitly out of boundary, operator-managed.
- **Selected Approach**: `Config.EMBEDDING_MODEL = 'mxbai-embed-large'`, `Config.EMBEDDING_BASE_URL = 'http://localhost:11434/v1'`, `Config.EMBEDDING_API_KEY = 'ollama'`. `.env.example` presents the Ollama block uncommented and the OpenAI/Gemini blocks commented out.
- **Rationale**: Matches the already-documented invariant (1024-dim, self-hosted), removes the dim-mismatch root cause, and removes the per-request remote cost.
- **Trade-offs**: New operators must `ollama pull mxbai-embed-large` before the first graph build. README and `.env.example` already cover this prerequisite, so the burden is small. Operators in pure-cloud deployments must explicitly opt in to a remote embedder, which is the desired direction.
- **Follow-up**: README setup section must mention the `ollama pull` prerequisite alongside Neo4j.

### Decision: Gate `complete_task` on a non-zero entity-node count
- **Context**: Requirement 4 AC5 — `GRAPH_COMPLETED` must not be reachable while Neo4j holds zero entities for the project's `group_id`.
- **Alternatives Considered**:
  1. Trust `add_batch`'s loud-failure contract entirely — rejected; if any future Graphiti call returns without raising but writes nothing, the symptom recurs silently.
  2. Add a separate "verify graph" task after build — rejected; over-engineering for a 5-line gate.
- **Selected Approach**: Inside `_build_graph_worker`, after `_get_graph_info(graph_id)`, if `node_count == 0`, call `TaskManager().fail_task(...)` with a localised message naming the failure (and skip `complete_task`).
- **Rationale**: Mirrors `_recover_stuck_projects`' "promote only when count > 0" rule; preserves the contract symmetrically on both completion paths.
- **Trade-offs**: Tiny additional code surface. Eliminates the regression vector for any future silent failure inside graphiti-core.
- **Follow-up**: Add the new failure message to `locales/en.json` and `locales/zh.json` keys consistent with the existing `progress.*` namespace.

### Decision: No new env var for `EMBEDDING_DIM`
- **Context**: Requirement 3 AC4 — keep dim fixed at 1024.
- **Selected Approach**: Continue to inherit graphiti-core's `EMBEDDING_DIM = 1024`. Document the constraint in CLAUDE.md.
- **Rationale**: Avoids surface-area creep; supporting 768/1536 dims is its own follow-up that would require a graphiti-core upgrade or fork.

### Decision: README documents the Ollama path as the active default; OpenAI/Gemini as commented fallbacks
- **Context**: Requirement 6 — the documented happy path must match the new behavior.
- **Selected Approach**: Swap the `# EMBEDDING_*=` comments in README's env block so the Ollama lines are uncommented and the OpenAI/Gemini lines move to a comment-only example.
- **Rationale**: Matches `.env.example`'s structure; minimises drift between the two files.

## Risks & Mitigations

- **Risk:** The actual root cause is upstream in `graphiti-core`, not the dim mismatch — defaults flip alone may not produce non-empty graphs.
  - **Mitigation:** R1 mandates a reproduction run on `main` before the fix; design includes the `complete_task` gate so a silent upstream failure is surfaced as a `fail_task` rather than an "empty graph, COMPLETED" outcome. PR description records the captured failure mode.
- **Risk:** Operators upgrade in place and discover their old project graphs (1536-dim OpenAI embeddings) are unreachable.
  - **Mitigation:** Requirement 5 AC3 — operators continue to set `EMBEDDING_MODEL` to their previous value; no auto-rebuild. Document in CLAUDE.md and README's migration note that switching embedder models invalidates existing project graphs (already a baseline rule from `database.md`).
- **Risk:** `.env.example` is hook-protected (the assistant cannot write to it).
  - **Mitigation:** Implementation will provide the required diff and a one-line `cat`-friendly snippet in the PR description / `HANDOFF.md`. Operator applies the change manually.

## Smoke Run

### 2026-05-11 — sandbox validation

- **Gate firing (Task 5.3 / negative path)**: validated in-process with the worker driven by a stubbed `_get_graph_info` that returns `node_count=0`. Result captured by the implementation script: `Task.status == FAILED`, `Task.error` starts with "Graph build produced 0 entities for this project. …", and the ERROR log line `graph build produced 0 entities for group_id=mirofish_test (task=…)` is emitted via the new `mirofish.graph_builder` logger. Symmetric happy path with `node_count=42` was also driven and `Task.status == COMPLETED` with `result.graph_info.node_count == 42`.
- **Config defaults (Task 2.1)**: validated in-process. With no `.env` override, `Config.EMBEDDING_MODEL = "mxbai-embed-large"`, `Config.EMBEDDING_BASE_URL = "http://localhost:11434/v1"`, `Config.EMBEDDING_API_KEY = "ollama"`, `Config.GRAPHITI_LLM_PROVIDER = "openai"`. Override semantics confirmed: explicit env vars still win over the new defaults.
- **End-to-end smoke (Task 5.1)**: deferred to operator validation — the sandbox lacks Neo4j, Ollama, and LLM credentials. The PR description will state explicitly that the smoke run was not executed in this environment and lists the steps an operator should run before tagging the PR ready: `ollama pull mxbai-embed-large` → `docker compose up -d neo4j` → `npm run dev` → upload a representative seed file → confirm `Task.result.graph_info.node_count > 0` → run Step 2 (Env Setup) → run Step 4 (Report) and confirm tool calls return non-empty results.
- **Backwards-compat (Task 5.2)**: deferred to operator validation under the same constraint. The PR description includes the operator runbook for the OpenAI override scenario (`.env` with `EMBEDDING_*` pointing at `https://api.openai.com/v1` and `text-embedding-3-small`) plus the Gemini provider scenario (`GRAPHITI_LLM_PROVIDER=gemini`, `EMBEDDING_MODEL=gemini-embedding-001`).

## Reproduction Log

### 2026-05-11 — sandbox run

- **Context**: Implementation phase Task 1.1 attempted live reproduction on `main`'s default `.env` (LLM via Dashscope, all `EMBEDDING_*` unset).
- **Result**: Reproduction could not be executed inside the Claude sandbox — no Neo4j daemon, no Ollama daemon, no LLM API key, no network egress to Dashscope. A live capture of the failing `Task` envelope and Neo4j node count is therefore deferred to operator validation (Task 5.1).
- **Working hypothesis (carried forward)**: Two compounding silent paths produce the empty-graph symptom on default config:
  1. With `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` unset, the embedder falls back to `LLM_API_KEY` / `LLM_BASE_URL`. On the documented default (Dashscope/Qwen for LLM), Dashscope's OpenAI-compatible surface does not serve `text-embedding-3-small` — calls either 404 or return non-conformant payloads. Post #18 this would propagate as a `Task.FAILED`, not an "empty graph, COMPLETED".
  2. If the embedder returns a payload (e.g., on an OpenAI key) the resulting 1536-dim vector mismatches Graphiti's 1024-dim vector index. Behaviour at this boundary is graphiti-core-dependent and may have surfaced historically as "wrote metadata, dropped entities".
- **Verdict**: **diverged-by-sandbox**. The fix is robust against either failure mode: flipping the defaults to a 1024-dim local embedder collapses both classes, and the `_get_graph_info(...).node_count == 0` gate (Task 3.1) converts any residual silent path into a `Task.FAILED` with `progress.emptyGraphFailure`.
- **Operator-side verification**: Task 5.1 captures the live Smoke Run; Task 5.3 forces the gate's negative path to confirm it surfaces the residual silent case as expected.


- `backend/app/services/graphiti_adapter.py` — embedder construction, loud-failure batch
- `backend/app/services/graph_builder.py` — graph-build worker
- `backend/app/__init__.py` — startup recovery
- `backend/app/config.py` — env-driven defaults
- `.kiro/specs/graphiti-ollama-embedder/requirements.md` — preceding loud-failure work (issue #18)
- `.kiro/specs/graphiti-neo4j-finalize/` — initial Zep → Graphiti migration
- `.kiro/steering/database.md`, `.kiro/steering/error-handling.md` — invariants relied upon
- `.ticket/37.md` — bug ticket source
