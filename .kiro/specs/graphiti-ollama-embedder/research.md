# Research & Design Decisions — graphiti-ollama-embedder

## Summary
- **Feature**: `graphiti-ollama-embedder`
- **Discovery Scope**: Extension (small, narrowly scoped change to an existing adapter + supporting docs)
- **Key Findings**:
  - The Graphiti `OpenAIEmbedder` already accepts an arbitrary `base_url` and `api_key`. Pointing it at Ollama's OpenAI-compatible `/v1/embeddings` endpoint requires **no code change** — only documentation.
  - The silent placeholder-UUID fallback in `_GraphNamespace.add_batch` violates the project's existing background-task error-handling contract (`error-handling.md`: "Long-running tasks must always reach a terminal state"). The plumbing to surface a failure already exists in `_build_graph_worker`.
  - `mxbai-embed-large` is the only widely-available local embedder that matches Graphiti's hard-coded `EMBEDDING_DIM = 1024`. Smaller models (`nomic-embed-text` at 768) would silently mis-fit Neo4j vector indexes and are out of scope.

## Research Log

### Ollama's OpenAI-compatible embeddings API
- **Context**: Verify that no Ollama-specific Graphiti embedder class is required.
- **Sources Consulted**: Existing code at `backend/app/services/graphiti_adapter.py:92–115` (`OpenAIEmbedderConfig` accepts arbitrary `base_url`); ticket #18 description; Graphiti `embedder/client.py:22` (`EMBEDDING_DIM = 1024`).
- **Findings**:
  - Ollama exposes `POST /v1/embeddings` mirroring the OpenAI shape.
  - The current `_build_llm_and_embedder("openai")` branch already uses `EMBEDDING_API_KEY or LLM_API_KEY` and `EMBEDDING_BASE_URL or LLM_BASE_URL`, so any OpenAI-compatible endpoint just works.
  - Ollama ignores the auth header but `OpenAIEmbedderConfig` requires a non-empty `api_key`; the literal string `"ollama"` is the de-facto convention.
- **Implications**: This is a documentation-only ask for R1. No new provider literal, no new factory branch.

### Failure-propagation contract
- **Context**: Confirm that removing the broad `except` in `_GraphNamespace.add_batch` will result in `Task.status = FAILED` in the UI.
- **Sources Consulted**:
  - `.kiro/steering/error-handling.md` § Background Task Errors — outer `except Exception` in worker calls `fail_task(task_id, str(e))`.
  - `backend/app/services/graph_builder.py:289–308` — `add_text_batches` already wraps `client.graph.add_batch` in `try/except` and re-raises after a localized progress message.
  - `backend/app/services/graph_builder.py:231–234` — `_build_graph_worker` catches every exception and calls `self.task_manager.fail_task(task_id, error_msg)` with a full traceback.
- **Findings**: The chain `add_episode → _GraphNamespace.add_batch → add_text_batches → _build_graph_worker → fail_task` is intact except for the swallow at the adapter layer. Removing the swallow is sufficient; no caller-side change is required.
- **Implications**: R2.3 / R2.5 are realized for free as soon as R2.2 is implemented.

### Single vs. batch ingestion path
- **Context**: Determine whether the single-episode `_GraphNamespace.add(...)` (line 441) needs a parallel fix.
- **Sources Consulted**: `graphiti_adapter.py:441–453`. No `try/except`; exceptions bubble naturally.
- **Findings**: Only the batch path swallows. The single path already complies.
- **Implications**: Fix is local to `add_batch`. Do not introduce symmetric handling in `add(...)`.

### Logging level
- **Context**: Decide between `WARNING` and `ERROR` for the failure log line.
- **Sources Consulted**: `.kiro/steering/error-handling.md` § Logging:
  - `ERROR` — task failure, unrecoverable exception
  - `WARNING` — retry triggered, transient failure, recovered state
- **Findings**: A failure that terminates the surrounding task is unrecoverable from the task's perspective, so `ERROR` is correct. The current `WARNING` is mislabelled.
- **Implications**: R2.4 — change to `logger.exception(...)` (which logs at ERROR with traceback).

### Documentation surfaces
- **Context**: Decide which files need updating to satisfy R1.
- **Sources Consulted**: `.env.example` (canonical config), `CLAUDE.md` lines 60–82, `README.md` lines 148–165, `docker-compose.yml` lines 21–37.
- **Findings**: All four are appropriate. `README.md` already has a placeholder for "non-OpenAI provider" and is the natural home for the `curl` smoke test snippet. `docker-compose.yml` benefits from one additional comment about `host.docker.internal`.
- **Implications**: Update all four; keep edits minimal and additive.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A. Drop swallow + docs | Remove `except` block in `add_batch`; update four docs files | Smallest surface; honors steering rules; symmetric with `add()` | Loses (broken) "best effort" intent | Recommended |
| B. Narrow + retry | Catch only transient classes (`httpx.TimeoutException`, `openai.APIConnectionError`); use `retry_with_backoff` from `app/utils/retry.py`; raise everything else | Adds resilience to genuine network blips | More moving parts; would also need to update `add()` for symmetry | Defer to follow-up |
| C. New `ollama` provider literal | Extend `_build_llm_and_embedder` with a third branch | Symmetric with `openai`/`gemini` | Explicitly out of scope per ticket; duplicate code path (Ollama is OpenAI-SDK with custom `base_url`) | Rejected |

## Design Decisions

### Decision: Adopt Option A (drop the placeholder fallback entirely; documentation only for Ollama support)
- **Context**: R2 mandates that embedding failures during graph build surface as visible task failures. R1 mandates documentation for an Ollama embedder. The adapter already supports any OpenAI-compatible base URL.
- **Alternatives Considered**:
  1. **Option B (narrow + retry)** — keep a small `except` clause for transient errors and use the project's `retry_with_backoff`.
  2. **Option C (new provider literal)** — add an `ollama` branch in `_build_llm_and_embedder`.
- **Selected Approach**:
  - In `_GraphNamespace.add_batch`, replace the `try/except Exception` block with a straightforward call. Failures from `_run(self._g.add_episode(...))` propagate to the caller.
  - Use `logger.exception(...)` immediately before re-raise is unnecessary — `_build_graph_worker` already calls `logger.exception(f"task {task_id} failed")` per the error-handling steering. To honor R2.4 explicitly without double-logging, wrap the call in a narrow `try/except: logger.exception(...); raise` so the adapter-level context (`group_id`, episode index) is captured before bubbling.
  - Update `.env.example`, `CLAUDE.md`, `README.md`, and `docker-compose.yml` to document Ollama configuration (R1).
- **Rationale**:
  - The ticket explicitly lists transient-retry behavior and per-provider factory as out of scope.
  - Steering's error-handling chapter forbids catch-and-continue in service code.
  - Smaller surface = lower regression risk.
- **Trade-offs**:
  - +Visibility: real config errors now surface at the UI.
  - +Code symmetry: `add()` and `add_batch()` behave the same on failure.
  - −One-time noise: operators whose graph builds were "succeeding" only because of the silent fallback will now see a failed task. This is the intended correction; mention in PR body.
- **Follow-up**:
  - If transient blips become an operational issue, revisit Option B in a separate ticket using `retry_with_backoff` against `_g.add_episode`.

### Decision: Use `logger.exception(...)` not `logger.error(...)`
- **Context**: R2.4 requires ERROR-level logging of the underlying exception.
- **Alternatives Considered**: `logger.error(str(e))` (no traceback), `logger.warning(...)` (current behavior).
- **Selected Approach**: `logger.exception("Episode add failed (group_id=%s)", graph_id)` then `raise`.
- **Rationale**: `logger.exception` logs at ERROR with the full traceback, which is what the steering doc prescribes for unrecoverable adapter failures.
- **Trade-offs**: A small amount of duplication if `_build_graph_worker` also logs via `logger.exception`. Acceptable — the two log lines describe different layers (adapter vs. task) and have different identifying context.

### Decision: Document Ollama under the existing OpenAI provider, not as a separate provider literal
- **Context**: The ticket lists "per-provider embedder factory" as out of scope; Ollama is already reachable via the existing `openai` branch.
- **Selected Approach**: Document Ollama as a configuration *choice* of the existing `openai` Graphiti provider (set the three `EMBEDDING_*` env vars).
- **Rationale**: Avoids code duplication and matches the ticket's scope.

## Risks & Mitigations
- **Risk**: Operators currently relying on the silent fallback see new failed tasks. **Mitigation**: PR body calls this out explicitly with a "what changed" note pointing at the embedder env vars.
- **Risk**: The `except` is removed but a transient timeout intermittently fails the entire graph build. **Mitigation**: Documented as a known follow-up (Option B). Acceptable today because the alternative was an empty graph that *looked* successful.
- **Risk**: Documentation drifts between `.env.example`, `CLAUDE.md`, `README.md`. **Mitigation**: Keep all four edits in this PR and reference the same env-var triple verbatim.

## References
- Ticket #18 — `.ticket/18.md` (snapshot in this repo)
- Steering — `.kiro/steering/error-handling.md` § Background Task Errors and § Logging
- Steering — `.kiro/steering/tech.md` § Key Libraries (`graphiti-core` adapter rule)
- Code — `backend/app/services/graphiti_adapter.py:92–115, :441–475`
- Code — `backend/app/services/graph_builder.py:143–234, :256–310`
