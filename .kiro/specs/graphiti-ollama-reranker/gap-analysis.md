# Implementation Gap Analysis — graphiti-ollama-reranker

## 1. Current State Investigation

### Domain Assets

| Asset | Location | Current behavior |
|-------|----------|------------------|
| `_PassthroughReranker` | `backend/app/services/graphiti_adapter.py:38-51` | Subclass of `graphiti_core.cross_encoder.client.CrossEncoderClient`. `rank(query, passages)` returns `(passage, 1.0 - 0.01 * i)` tuples in input order — no model call. |
| Graphiti factory | `backend/app/services/graphiti_adapter.py:142-162` (`_get_graphiti`) | Double-checked-locking singleton. Branches on `Config.GRAPHITI_LLM_PROVIDER` (`openai` / `gemini`). Always injects `_PassthroughReranker()` as `cross_encoder`. Runs `g.build_indices_and_constraints()` on the persistent event loop. |
| LLM/embedder builder | `backend/app/services/graphiti_adapter.py:92-139` (`_build_llm_and_embedder`) | Lazy-imports provider-specific Graphiti classes. Reads `Config.LLM_*` and `Config.EMBEDDING_*`. |
| Config surface | `backend/app/config.py:33-53` | Single class with class attrs; each is `os.environ.get('KEY', 'default')`. Has `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY` defaults aligned with local Ollama. |
| Graph-search callers | `_GraphNamespace.search` at `graphiti_adapter.py:488-517`; consumed by `zep_tools.py:491` (`ZepToolsService.search_graph`) and `oasis_profile_generator.py:313, 337`. | All call sites already dropped the misleading `reranker=` kwarg in `graphiti-neo4j-finalize`. They invoke `client.graph.search(graph_id, query, limit, scope)` only. |
| Existing LLM wrapper | `backend/app/utils/llm_client.py` | Uses synchronous `OpenAI()` client. Includes reasoning-model `<think>` stripping and a JSON-mode retry. Not directly relevant to the reranker but documents the in-house OpenAI-SDK pattern. |
| Async-loop helper | `graphiti_adapter.py:54-79` (`_get_loop`, `_run`) | Persistent dedicated event-loop thread used for all Graphiti async calls. The reranker's `rank` is **already** awaited by Graphiti itself, not by `_run`, so the new client can use plain `await` on `openai.AsyncOpenAI`. |

### Conventions Observed

- 4-space indent, snake_case, double quotes; English + Chinese mixed in comments — preserve both styles.
- New env vars go into `backend/app/config.py` as class attrs reading from `os.environ.get` with a sensible default. Validation is centralized in `Config.validate()`.
- New backend modules live under `backend/app/services/` with module-level `logger = get_logger('mirofish.<topic>')`.
- The OpenAI SDK is the only LLM client. New providers do not add a second SDK — they add a base-URL + model knob.
- No tests for graph code beyond `scripts/test_profile_format.py`; the project explicitly discourages adding a heavy test harness.

### Integration Surfaces

- **Upstream contract**: `CrossEncoderClient` is consumed by `graphiti_core` during `Graphiti.search()` execution; the framework calls `await reranker.rank(query, passages)` on whatever event loop the caller is using.
- **Inbound integration**: only one wire point — the `cross_encoder=` kwarg on `Graphiti(...)` in `_get_graphiti()` (`graphiti_adapter.py:156`).
- **Outbound integration**: the reranker calls Ollama via `http://localhost:11434/v1/chat/completions` (OpenAI-compatible). Already proven by `EMBEDDING_BASE_URL` for embeddings; Ollama's chat endpoint follows the same surface.

## 2. Requirements Feasibility Analysis

### Requirement-to-Asset Map

| Requirement | Existing assets | New assets needed | Gap tag |
|-------------|-----------------|-------------------|---------|
| R1: Default is Ollama, not OpenAI default | `_get_graphiti()` already injects an explicit reranker (no default fallthrough). | Switch the injected client class based on `RERANKER_PROVIDER`. | Missing (selection logic). |
| R2: Real `CrossEncoderClient` calling Ollama via OpenAI SDK | Pattern proven in `llm_client.py`; `openai` already in `pyproject.toml`. | New `OllamaReranker` class — subclass of `CrossEncoderClient`, uses `openai.AsyncOpenAI` for `rank()`. | Missing. |
| R3: Env knobs (`RERANKER_PROVIDER/MODEL/BASE_URL/API_KEY`) | Config pattern is established (`EMBEDDING_*` etc.). | Four new `Config` attrs, with defaults falling back to embedding settings where stated. | Missing. |
| R4: `none` provider preserves passthrough | `_PassthroughReranker` already exists. | Branch in `_get_graphiti()` to pick passthrough when provider == `none`. | Missing (small). |
| R5: Graceful degradation when Ollama is down | `_GraphNamespace.search` (lines 515-517) already catches all exceptions and returns empty results with a warning log. | Reranker `rank` must catch its own network/parse errors, log them, and return the original passages with synthetic scores so search still returns *something*. | Missing (within new class). |
| R6: Docs (`.env.example`, `CLAUDE.md`, README) | Existing docs already document `EMBEDDING_*` in three places — pattern is clear. | Add 4 new env lines + Ollama pull note. | Missing (text). |
| R7: Report tools get reranked output transparently | `_GraphNamespace.search` is the single chokepoint already used by all 4 tools (`SearchResult`, `InsightForge`, `Panorama`, `Interview`). | None — wiring change in factory propagates automatically. | None (verification only). |

### Constraints

- **Async contract**: `CrossEncoderClient.rank` is `async def`. The new client must be async. The OpenAI SDK provides `openai.AsyncOpenAI` for this.
- **Ollama model output shape**: A small chat model (`qwen2.5:3b`, `llama3.2:3b`) can be prompted to emit a numeric score; we cannot rely on `logprobs` because Ollama's OpenAI-compatible surface does not always expose `logprobs`/`logit_bias` consistently. Therefore the scoring strategy is "ask the model for a 0–10 (or 0–1) relevance score per passage and parse it from the text response."
- **No new dependency** allowed. Reranker must reuse `openai` SDK (already installed) — confirmed in `backend/.venv/lib/python3.13/site-packages/openai-2.35.1.dist-info/`.
- **Boot must not fail** when Ollama is unreachable (R5.4). Construction is cheap (build an `AsyncOpenAI` client; no network call). The model availability check happens lazily on first `rank()`.

### Complexity Signals

- Mostly a **single file plus config plus docs** change. Algorithmic logic is local to the new class (prompt + parse). No data model changes, no API surface changes, no UI changes.

### Research Needed (Carry into Design)

- **Model choice**: pick a small Ollama chat model that (a) is widely pulled, (b) reliably emits a numeric score in a 1–2 token answer, (c) is small enough to run on a typical dev machine. Candidates: `qwen2.5:3b`, `llama3.2:3b`, `phi3:3.8b`. Design phase will fix the default.
- **Scoring strategy**: per-passage call (N calls per query, simple to parse) vs. batched single-call (one prompt with all passages, harder to align). The per-passage approach is simpler and parallelizable via `asyncio.gather`; latency is bounded by the slowest passage. Design will fix the strategy.
- **Output parsing**: prefer JSON output (`{"score": 0.83}`) with markdown-fence stripping (project convention from `llm_client.chat_json`); fall back to regex-extract first float on parse failure.

## 3. Implementation Approach Options

### Option A — Extend `graphiti_adapter.py` In Place
Add the `OllamaReranker` class directly to `graphiti_adapter.py` next to `_PassthroughReranker`, and branch in `_get_graphiti()`.

- **Trade-offs**:
  - ✅ Same module owns all reranker wiring and the singleton; one file to read.
  - ✅ Smallest diff; matches the file's existing role as "everything Graphiti".
  - ❌ Adds prompt/parse logic to an already long (≈545-line) adapter module.
  - ❌ Harder to reuse the reranker outside Graphiti (unlikely, but precludes it).

### Option B — Separate Module `backend/app/services/ollama_reranker.py`
New module owns the class and its prompt/parse helpers; `graphiti_adapter.py` imports it and selects it in `_get_graphiti()`.

- **Trade-offs**:
  - ✅ Clear single-responsibility module; mirrors the structure suggested in the source ticket #39.
  - ✅ Adapter file stays focused on wiring; reranker can be unit-tested in isolation if testing is later added.
  - ❌ Slightly more navigation; one extra file in `services/`.
  - ❌ The provider-selection branch still lives in the adapter, so two files must agree on the provider string.

### Option C — Hybrid: Provider Registry
Introduce a small `_RERANKER_PROVIDERS` map (`"ollama" -> _build_ollama_reranker`, `"none" -> _PassthroughReranker`) inside `graphiti_adapter.py`, with the actual class still living in a separate `ollama_reranker.py`.

- **Trade-offs**:
  - ✅ Adding a future provider (e.g. `sentence_transformers`) is a one-line registry change.
  - ✅ Keeps reranker class out of the adapter.
  - ❌ Slight over-engineering for two providers (`ollama` + `none`); ticket #39 explicitly scopes only the Ollama path.

## 4. Implementation Complexity & Risk

- **Effort**: **S (1–3 days)**
  - One new class (~80–120 lines), four new config attrs (~10 lines), one factory branch (~10 lines), three doc updates (~30 lines). No schema or API changes.
- **Risk**: **Low**
  - Established patterns (config, OpenAI SDK, logger).
  - `_PassthroughReranker` is preserved exactly for the `none` fallback, so the worst-case behavior is identical to today.
  - The graceful-failure path (R5) requires care, but the existing `_GraphNamespace.search` exception handling already insulates HTTP callers from reranker errors.

## 5. Recommendations for Design Phase

- **Preferred approach**: **Option B (separate `ollama_reranker.py` module)**. Best alignment with #39's "implement in `backend/app/services/`", keeps `graphiti_adapter.py` focused on Graphiti wiring, and matches the project's "one concern per module" pattern in `services/`.
- **Key decisions to lock in design**:
  1. Default `RERANKER_MODEL` value (recommend `qwen2.5:3b` — small, broadly available on Ollama, reliable at structured short outputs).
  2. Per-passage scoring strategy with `asyncio.gather` parallelism (simpler, deterministic).
  3. Prompt + parse format: ask for JSON `{"score": <0.0..1.0>}`, strip fences, regex-fallback to first float.
  4. Failure mode for a single passage: assign deterministic low score (e.g. `0.0 - 0.001 * i`) so passage still appears once.
  5. Failure mode for whole `rank()` call: log warning, return original-order tuples with passthrough scores (no exception bubbles up).
  6. Update `.kiro/specs/graphiti-neo4j-finalize/research.md` "follow-up" note to point at this spec (R6.4).
- **Research items carried forward**:
  - Confirm `qwen2.5:3b` produces stable JSON scores in benchmark prompts (or pick alternative).
  - Decide whether to expose `RERANKER_MAX_PARALLEL` for concurrency limit (default `len(passages)` — likely small, ≤10).
