# Research & Design Decisions — graphiti-ollama-reranker

## Summary
- **Feature**: `graphiti-ollama-reranker`
- **Discovery Scope**: Extension (one new service module + factory branch + config + docs).
- **Key Findings**:
  - `CrossEncoderClient.rank(query, passages) -> list[tuple[str, float]]` is the only abstract contract Graphiti requires of the reranker. The existing `_PassthroughReranker` already exercises this contract correctly.
  - Ollama's OpenAI-compatible `/v1/chat/completions` endpoint does not reliably expose `logprobs` / `logit_bias`, so Graphiti's default OpenAI scoring approach (binary YES/NO over token logits) cannot be ported. The reranker must use **prompted numeric scoring** with text-output parsing.
  - The `openai` SDK already shipped in `backend/.venv` (v2.35.1) exposes `AsyncOpenAI`, which is the right client for the async `rank()` method without introducing any new dependency.

## Research Log

### Graphiti's `CrossEncoderClient` contract
- **Context**: Need to confirm the precise shape of the `rank` interface and any other abstract members.
- **Sources Consulted**: `backend/app/services/graphiti_adapter.py:38-51` (`_PassthroughReranker`); `.kiro/specs/graphiti-neo4j-finalize/research.md` and `gap-analysis.md` (which captured the upstream contract on first integration); ticket #39 narrative.
- **Findings**:
  - `_PassthroughReranker` subclasses `CrossEncoderClient` and only overrides `async def rank(query: str, passages: list[str]) -> list[tuple[str, float]]`.
  - Graphiti's internal call site (`graphiti_core/graphiti.py:154`) constructs the reranker once and calls `rank` per search. There is no separate batch interface to satisfy.
  - Passages are short text snippets (entity-edge facts / node summaries). Typical N per search ≤ 10 (limit defaulted in `_GraphNamespace.search`).
- **Implications**: A drop-in subclass that implements `rank` is sufficient. No additional abstract methods to wire.

### Ollama OpenAI-compatible scoring surface
- **Context**: Decide how to obtain a relevance score per passage from a small Ollama-served chat model.
- **Sources Consulted**: Project-internal `backend/app/utils/llm_client.py` (uses `openai.OpenAI` + `chat.completions.create` against Dashscope / OpenAI / Ollama uniformly); ticket #39 "Proposed approach" section enumerating Ollama chat-model scoring vs. embedding cosine.
- **Findings**:
  - Ollama supports `/v1/chat/completions` for chat models like `qwen2.5:3b`, `llama3.2:3b`, `phi3:3.8b`. Pulling a model is required (`ollama pull <model>`).
  - JSON-mode (`response_format={"type": "json_object"}`) is honored by recent Ollama versions but not universally; project convention is to fall back gracefully (cf. `LLMClient.chat_json`).
  - Embedding-cosine reranker is feasible (re-embed query and passages with `mxbai-embed-large`) but produces a weaker ordering signal than an LLM that can reason about the question. Picking LLM scoring matches the ticket's preferred path.
- **Implications**:
  - Use a chat-completion call per passage with a deterministic temperature (0.0) and a tight system prompt asking for a JSON score in [0.0, 1.0].
  - Parse with the same defensive strategy used elsewhere: strip `<think>` blocks, strip markdown fences, attempt `json.loads`, regex-fallback to first float, deterministic low score on hard failure.

### Concurrency strategy
- **Context**: Decide between per-passage parallel calls vs. one batched call.
- **Findings**:
  - Per-passage with `asyncio.gather` is simpler to align outputs and resilient — a single bad output only loses one passage's score.
  - Single batched prompt requires the model to emit aligned scores (often by index); LLMs occasionally drop entries or misorder them, demanding additional validation.
  - With typical `limit ≤ 10`, parallel per-passage calls hit Ollama briefly; on a 3B model this is < 5s for 10 passages.
- **Implications**: Default to per-passage `asyncio.gather`. Expose no extra concurrency knob initially (avoid premature configuration surface; YAGNI per project guidelines).

### Failure semantics
- **Context**: Required by R5 — Flask must keep serving on Ollama outage, and graph search should remain functional.
- **Sources Consulted**: `backend/app/services/graphiti_adapter.py:515-517` (`_GraphNamespace.search` swallows all exceptions and logs a warning); `_get_graphiti()` runs once at first call.
- **Findings**:
  - Construction of an `openai.AsyncOpenAI` client does not perform any network I/O. Therefore `OllamaReranker.__init__` can be safe at startup even when Ollama is down.
  - If `rank()` itself raises, the upstream `Graphiti.search` may surface the exception. The new reranker should therefore catch its own errors and degrade to passthrough behavior in-method rather than relying on the outer `try/except` in `_GraphNamespace.search`.
- **Implications**: `OllamaReranker.rank` should never raise. On exception or unparseable output it returns the input passages in the original order with passthrough-style synthetic scores and emits a single WARNING log per failure (rate-limited by intent: one log per rank() call).

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A: Add class to `graphiti_adapter.py` | Define `OllamaReranker` next to `_PassthroughReranker` in the same file. | Minimal diff; single file to read. | Bloats an already-long adapter; mixes wiring with provider-specific logic. | — |
| B: New `services/ollama_reranker.py` module | Dedicated module owns prompt + parse + async client; adapter only selects it. | Single-responsibility module; matches ticket suggestion; reusable in isolation. | One extra import in adapter. | **Selected.** Aligns with project pattern of one concern per `services/*` file. |
| C: Hybrid provider registry | Map `RERANKER_PROVIDER → builder` in adapter; class still in B's module. | Future providers are a one-line registry change. | Over-engineering for two providers (`ollama` + `none`). | Deferred until a third provider is needed. |

## Design Decisions

### Decision: Provider selected via env var, branch lives in `_get_graphiti()`
- **Context**: R3 requires env-driven provider selection; only two values supported by this spec (`ollama` and `none`).
- **Alternatives Considered**:
  1. Function-pointer registry (Option C).
  2. Inline `if/else` in the factory selecting one of two classes.
- **Selected Approach**: Inline branch in `_get_graphiti()` reads `Config.RERANKER_PROVIDER`, picks `_build_ollama_reranker()` or `_PassthroughReranker()`, validates unknown values with a `ValueError` matching the existing `_ALLOWED_GRAPHITI_PROVIDERS` convention.
- **Rationale**: Mirrors the established `GRAPHITI_LLM_PROVIDER` validation pattern (`_ALLOWED_GRAPHITI_PROVIDERS`) without adding speculative abstraction. Two values, two branches.
- **Trade-offs**: Adding a third provider later costs one more `elif`; acceptable.
- **Follow-up**: Surface the selected provider in the INFO startup log so operators can confirm.

### Decision: Per-passage scoring with `asyncio.gather`, no concurrency knob
- **Context**: R2.3 requires one score per passage in descending order; R5 requires graceful per-call failure.
- **Alternatives Considered**:
  1. Single batched prompt with index-aligned output.
  2. Per-passage call with bounded `Semaphore`.
- **Selected Approach**: Per-passage `asyncio.gather` with no explicit limit; rely on default `limit ≤ 10` in `_GraphNamespace.search`.
- **Rationale**: Simple, deterministic, isolates per-passage failures. Avoids premature configuration knob.
- **Trade-offs**: If a future caller asks for `limit=100`, Ollama may queue 100 requests; acceptable for now because no caller does this.
- **Follow-up**: If real-world rerank latency becomes a concern, add `RERANKER_MAX_PARALLEL` then.

### Decision: Default model = `qwen2.5:3b`
- **Context**: Need a small, broadly-available Ollama chat model that reliably emits a numeric score in 1–2 tokens.
- **Alternatives Considered**:
  1. `qwen2.5:3b` (Apache-2.0, 3B params, strong instruction following).
  2. `llama3.2:3b` (Llama community license, 3B).
  3. `phi3:3.8b` (MIT, 3.8B).
- **Selected Approach**: `qwen2.5:3b`.
- **Rationale**: Matches the Qwen-family alignment of the rest of the project (`qwen-plus` is the documented LLM default). Apache-2.0 license is permissive. Small enough for typical dev machines.
- **Trade-offs**: Operators on systems without `qwen2.5:3b` must `ollama pull qwen2.5:3b` or override `RERANKER_MODEL`.
- **Follow-up**: README will document `ollama pull qwen2.5:3b` alongside the existing `ollama pull mxbai-embed-large` step.

### Decision: Defensive output parsing (`json.loads` → regex float → deterministic low score)
- **Context**: R2.6 requires deterministic handling of unparseable model responses.
- **Selected Approach**:
  1. Strip `<think>...</think>` blocks (project convention from `llm_client.py:64`).
  2. Strip markdown fences (project convention from `llm_client.chat_json`).
  3. `json.loads` and read `score` (float in `[0, 1]`, clipped on out-of-range).
  4. On JSON failure, regex-extract the first float token; clip to `[0, 1]`.
  5. On total failure, assign `0.0 - 0.001 * passage_index` (deterministic and below any successfully-parsed score).
- **Rationale**: Reuses patterns already in the codebase. Keeps every passage in the output (R2.6).
- **Trade-offs**: One failed parse silently downranks a passage; logged at DEBUG (not WARNING) to avoid log spam.

## Risks & Mitigations
- **Risk**: Ollama service is not running on startup → boot must not fail. **Mitigation**: Construct only `AsyncOpenAI` (no network call) during `__init__`. Defer connectivity to first `rank()`. R5.4.
- **Risk**: Model is not pulled → `rank()` raises 404 from Ollama. **Mitigation**: Catch within `rank()`, log WARNING naming model + error class, return passthrough-ordered tuples so search still works. R5.1, R5.3.
- **Risk**: Operator misconfigures `RERANKER_PROVIDER` to an unknown value → silent fallthrough to wrong reranker. **Mitigation**: `_get_graphiti()` raises `ValueError` listing allowed values, mirroring `_ALLOWED_GRAPHITI_PROVIDERS`. R3.5.
- **Risk**: Multiple concurrent `rank()` calls overwhelm a small local Ollama daemon. **Mitigation**: Accept default Graphiti `limit ≤ 10`; document `RERANKER_MAX_PARALLEL` as a future follow-up if needed.

## References
- `backend/app/services/graphiti_adapter.py:38-51` — current passthrough reranker contract.
- `backend/app/services/graphiti_adapter.py:142-162` — current `_get_graphiti()` wiring point.
- `backend/app/utils/llm_client.py` — project pattern for OpenAI-SDK chat + JSON parsing + reasoning-block stripping.
- `.kiro/specs/graphiti-neo4j-finalize/research.md` — historical context for why the passthrough was introduced.
- Ticket `#39` in `.ticket/39.md` — feature brief and acceptance criteria.
