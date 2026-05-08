# Gap Analysis — graphiti-ollama-embedder

## 1. Current State Investigation

### Domain assets touched by this feature
- `backend/app/services/graphiti_adapter.py`
  - Lines 92–139 — `_build_llm_and_embedder(provider)`. Builds an `OpenAIEmbedder` (when `provider == "openai"`) using `EMBEDDING_API_KEY or LLM_API_KEY`, `EMBEDDING_BASE_URL or LLM_BASE_URL`, and `EMBEDDING_MODEL`. Already supports pointing the embedder at any OpenAI-compatible endpoint — no code change is needed for Ollama support. This is a **documentation gap, not a code gap**.
  - Lines 455–475 — `_GraphNamespace.add_batch`. Iterates episodes, calls `add_episode`, and on `except Exception as e` logs a one-line `WARNING` and substitutes a fresh placeholder UUID. This is the silent-swallow path.
  - Line 441–453 — `_GraphNamespace.add(...)`. Single-episode path. **Already raises naturally** because there is no `try/except`.
  - Lines 504–506 — `_GraphNamespace.search(...)`. Has its own `except Exception` that logs and returns empty results. Per `error-handling.md` ("for non-fatal search failures, log and return empty results") this is the documented contract; out of scope.
- `backend/app/services/graph_builder.py`
  - Lines 256–310 — `add_text_batches(...)`. Already wraps `client.graph.add_batch(...)` in `try/except Exception` and **re-raises** after a progress message. So if `_GraphNamespace.add_batch` raises, the exception propagates correctly.
  - Lines 143–234 — `_build_graph_worker`. Outer `try/except Exception` calls `self.task_manager.fail_task(task_id, error_msg)` with `f"{str(e)}\n{traceback.format_exc()}"`. This already implements the "task always terminates" rule from `error-handling.md`.
- `backend/app/config.py`
  - Lines 40, 50–51 — defines `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL`. No change required.
- `.env.example` (project root) — currently only documents the OpenAI/Gemini path with commented-out `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` lines.
- `CLAUDE.md` lines 60–82 — "Required Environment Variables" section lists `EMBEDDING_MODEL` with a note about Gemini overrides only.
- `README.md` lines 148–165 — "Required Environment Variables" section, mentions "uncomment if using a non-OpenAI provider, e.g. Gemini" but no Ollama example.
- `docker-compose.yml` lines 21–37 — `mirofish` service uses `env_file: .env` and overrides `NEO4J_URI`. No Ollama hint, but the standard `host.docker.internal` route works.

### Conventions extracted from steering
- `tech.md`: "All graph reads/writes go through the `graphiti_adapter`; do not call Neo4j drivers directly from feature code." — adapter is the right place for the fix.
- `error-handling.md`: "Long-running tasks must always reach a terminal state (`COMPLETED` or `FAILED`)" — silent placeholder UUID violates this.
- `error-handling.md`: "Don't catch `Exception` inside an API handler just to log and continue" — same anti-pattern in the adapter today.
- `error-handling.md` § Logging: `WARNING` is for "retry triggered, transient failure, recovered state"; `ERROR` is for "task failure, unrecoverable exception". The current `WARNING` mislabels what is actually an unrecoverable failure for the task.
- `tech.md`: Ollama is **not currently** an officially listed provider. CLAUDE.md only enumerates OpenAI and Gemini.
- `commits.md` / `dev-guidelines.md`: 4-space indent, max 120 chars/line, double-quoted Python strings, snake_case, conventional commits.

### Integration surfaces
- The `OpenAIEmbedder` from `graphiti_core.embedder.openai` already accepts an arbitrary `base_url`. Ollama exposes `/v1/embeddings` at `http://localhost:11434/v1`. No new client class is required.
- Background-task lifecycle: API handler → `GraphBuilderService.build_graph_async()` → background thread → `_build_graph_worker` → `fail_task(task_id, msg)`. Already in place; this feature just needs to stop short-circuiting it.

## 2. Requirements Feasibility Analysis

| Req | Need | Maps to | Gap |
| --- | --- | --- | --- |
| R1.1 | `.env.example` Ollama block | `.env.example` | **Missing** (docs) |
| R1.2 | `CLAUDE.md` lists OpenAI/Gemini/Ollama, dim constraint | `CLAUDE.md` | **Missing** (docs) |
| R1.3 | Docker-compose / README note about `host.docker.internal:11434` | `docker-compose.yml` comments / `README.md` | **Missing** (docs) |
| R1.4 | `curl` smoke-test snippet | `README.md` | **Missing** (docs) |
| R1.5 | Pipeline works end-to-end with mxbai-embed-large | adapter is already provider-agnostic via OpenAI-SDK | **No code gap** — already supported, just undocumented |
| R2.1 | Drop placeholder-UUID fallback | `graphiti_adapter.py:471–473` | **Constraint** — narrow change only |
| R2.2 | Propagate ingest exception | `graphiti_adapter.py:471–473` + caller | **Missing** — adapter swallows; caller re-raises if it sees an exception |
| R2.3 | `Task` transitions to `FAILED` with non-empty `error` | `graph_builder.py:231–234` | **Already implemented** — relies on R2.2 |
| R2.4 | Log at `ERROR` level | `graphiti_adapter.py:472` | **Missing** — currently `WARNING` |
| R2.5 | UI shows error, no fake-success placeholder | downstream of R2.3 | **Already implemented** via task polling |
| R2.6 | Preserve happy-path UUID contract | `graphiti_adapter.py:455–474` | **Constraint** — keep return shape on success |
| R3.1 | OpenAI/Gemini behavior unchanged | `_build_llm_and_embedder` | **No change needed** — branch untouched |
| R3.2 | No new env var | scope rule | **Constraint** |
| R3.3 | Document 1024-dim constraint | `CLAUDE.md` | **Missing** (docs) |

### Research needed
- None for this feature — `OpenAIEmbedder` already supports custom `base_url`, and Ollama's `/v1/embeddings` is OpenAI-compatible (well-known and used in many projects). The 1024-dim constraint comes from `graphiti_core/embedder/client.py:22` (`EMBEDDING_DIM = 1024`) and is documented in the ticket itself.
- One mild unknown: whether to narrow the `except` to a transient subset (e.g., `httpx.TimeoutException`, `httpx.NetworkError`) and retry, or simply drop the catch entirely. Decided in design phase, not blocking.

### Complexity signal
- Mostly documentation. The code change is **5 lines** in one method.

## 3. Implementation Approach Options

### Option A — Pure narrow fix in `_GraphNamespace.add_batch` + docs only (RECOMMENDED)
- **What**: delete the `except Exception` block in `add_batch` (or replace with `logger.exception(...)` + `raise`); update `.env.example`, `CLAUDE.md`, `README.md`, `docker-compose.yml` comments.
- **Files**: `backend/app/services/graphiti_adapter.py`, `.env.example`, `CLAUDE.md`, `README.md`, `docker-compose.yml`.
- **Trade-offs**:
  - ✅ Minimal blast radius — adapter behavior outside `add_batch` is untouched.
  - ✅ Existing background-task contract carries the failure to the UI for free.
  - ✅ Honors steering rules: don't catch `Exception` to log-and-continue; tasks must terminate; ERROR-level logging for unrecoverable failures.
  - ❌ Loses the (currently broken) "best effort, keep going on a partial failure" intent. In practice that intent never produced a usable graph anyway, so the loss is theoretical.

### Option B — Narrow the catch to transient errors and retry, fail loud on the rest
- **What**: keep a `try/except`, but only catch a small set of transient classes (`httpx.TimeoutException`, `httpx.NetworkError`, `openai.APIConnectionError`), wrap the whole `add_episode` call in `retry_with_backoff` from `app/utils/retry.py`, and re-raise everything else immediately.
- **Trade-offs**:
  - ✅ Adds small resilience for genuinely transient blips.
  - ✅ Aligns with the existing `retry_with_backoff` pattern.
  - ❌ More moving parts; broader change for a bug fix.
  - ❌ Single-episode `add()` would also need the same treatment to avoid two divergent retry semantics.
  - ❌ Out-of-scope creep: ticket is focused on stopping the silent swallow + documenting Ollama.

### Option C — Per-provider embedder factory + Option A
- **What**: extend `_build_llm_and_embedder` with a third provider literal (`"ollama"`) that uses `OpenAIEmbedder` under the hood with hardcoded sensible defaults.
- **Trade-offs**:
  - ✅ Symmetric with `openai`/`gemini`.
  - ❌ The ticket explicitly lists "per-provider embedder factory" as out of scope.
  - ❌ Duplicate code path — Ollama is just OpenAI-SDK with a different base URL.

## 4. Effort & Risk

- **Effort**: **S** (≤1 day). One file, one method, ~5 LOC delta plus 4 doc edits.
- **Risk**: **Low**. The change makes a previously-silent failure loud; it cannot break the happy path because the happy-path branch is the same return statement. Documentation changes are not load-bearing.

One non-zero risk: if there are real-world users today whose graph builds succeed only by accident (i.e., the fallback hides intermittent embedding failures), they will start seeing failed tasks instead of (broken) successful ones. This is the intended correction — but worth noting in the PR description so the operator can re-check their embedder credentials.

## 5. Recommendations for design phase

- **Preferred approach**: **Option A**. Smallest correct fix; documentation reflects the already-supported configuration; follows steering's error-handling philosophy literally.
- **Key decisions to lock in design**:
  1. Drop the `except` entirely, or narrow it? Default: drop. Rationale: the only retry path that matters is transient network blips, and those would also kill the surrounding `_run` loop today; addressing them would be a follow-up using the project's `retry_with_backoff` decorator on the underlying graph driver call, not a band-aid in `add_batch`.
  2. Which docs files mention Ollama? Default: `.env.example`, `CLAUDE.md`, `README.md`, `docker-compose.yml` comment. Two-file or three-file split?
- **Carry-forward research**: none.
