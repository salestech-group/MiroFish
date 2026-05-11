# Requirements Document

## Project Description (Input)
Replace the no-op `_PassthroughReranker` in `backend/app/services/graphiti_adapter.py` with a real reranker that uses an Ollama-available model, so Graphiti search results are properly reranked for the SearchResult / InsightForge / Panorama / Interview report tools. Add `RERANKER_PROVIDER` / `RERANKER_MODEL` / `RERANKER_BASE_URL` env knobs (defaults: ollama / a small Ollama chat model / EMBEDDING_BASE_URL), keep `_PassthroughReranker` only when `RERANKER_PROVIDER=none`, and update `.env.example`, `CLAUDE.md`, and the README accordingly. Source ticket: #39 (.ticket/39.md).

## Introduction

The Graphiti adapter currently injects a `_PassthroughReranker` into the `Graphiti(...)` constructor to bypass the upstream default (`OpenAIRerankerClient` with a hard-coded `gpt-4.1-nano` and OpenAI-specific `logprobs`/`logit_bias`), which would 401 against Qwen/Dashscope keys and is unavailable through Ollama. The passthrough is a no-op: it returns passages in original order with synthetic descending scores, so search results consumed by the ReportAgent tools (`SearchResult`, `InsightForge`, `Panorama`, `Interview`) are not actually reranked.

This feature replaces the no-op with a real reranker backed by a model available through the local Ollama stack (matching the existing `EMBEDDING_MODEL=mxbai-embed-large` precedent). A small set of environment variables makes the provider, model, and endpoint overridable. An explicit `none` provider preserves the passthrough behavior for CI / lightweight setups that cannot pull the reranker model.

## Boundary Context

- **In scope**:
  - A new `CrossEncoderClient` implementation in `backend/app/services/` that scores passages against a query by calling an Ollama model through its OpenAI-compatible endpoint.
  - New `RERANKER_PROVIDER`, `RERANKER_MODEL`, `RERANKER_BASE_URL`, and `RERANKER_API_KEY` settings in `backend/app/config.py`, with sensible Ollama defaults.
  - Provider selection inside `_get_graphiti()` so `ollama` selects the new client and `none` keeps `_PassthroughReranker`.
  - Documentation updates in `.env.example`, `CLAUDE.md` (Required Environment Variables), and the project `README.md` (Ollama prerequisites).
  - Graceful failure when the configured reranker model is not pulled (clear error, no Flask crash; graph search either falls back to original order or surfaces a logged warning consistent with the existing `_GraphNamespace.search` exception path).
- **Out of scope**:
  - Changing `LLM_MODEL_NAME` or `EMBEDDING_MODEL` defaults.
  - Building OpenAI-only or Dashscope-only reranker clients; this spec is specifically the Ollama path (plus the `none` escape hatch).
  - Upstream changes to `graphiti-core`.
  - Adding any non-Python reranker library (e.g. `sentence-transformers`); the new client must reuse the OpenAI SDK already in the dependency set.
- **Adjacent expectations**:
  - `graphiti_adapter._get_graphiti()` continues to be the single Graphiti factory; the new reranker must be wired through it, not at call sites.
  - All Graphiti reads remain scoped by `group_id` — the reranker operates on passages already filtered per project; it does not change isolation rules.
  - The reranker integrates with `_GraphNamespace.search`, which is the path used by `SearchResult`, `InsightForge`, `Panorama`, and `Interview` tools; behavior changes propagate to those tools automatically and do not need per-tool code changes.

## Requirements

### Requirement 1: Default reranker is Ollama-backed, not the OpenAI default
**Objective:** As a backend developer running MiroFish against the default local Ollama stack, I want Graphiti to rerank search results without requiring an OpenAI key, so that report-tool relevance reflects a real model and not an arbitrary insertion order.

#### Acceptance Criteria
1. The Graphiti Adapter shall instantiate Graphiti with a non-passthrough `CrossEncoderClient` whenever `RERANKER_PROVIDER` resolves to `ollama` (the default).
2. The Graphiti Adapter shall not depend on `graphiti_core.cross_encoder.openai_reranker_client.OpenAIRerankerClient` for the default code path.
3. When `RERANKER_PROVIDER` is unset, the Graphiti Adapter shall behave as if `RERANKER_PROVIDER=ollama`.
4. The Graphiti Adapter shall not reference the model name `gpt-4.1-nano` in any reranker code path.

### Requirement 2: Ollama-backed reranker scores passages via an OpenAI-compatible chat endpoint
**Objective:** As a backend developer, I want a reranker that talks to a locally hosted model so that the local-first stack stays self-contained and no remote LLM key is required.

#### Acceptance Criteria
1. The Ollama Reranker shall expose a class that subclasses `graphiti_core.cross_encoder.client.CrossEncoderClient` and implements the asynchronous `rank(query, passages) -> list[tuple[passage, score]]` contract.
2. The Ollama Reranker shall call its configured chat-completions endpoint through the `openai` SDK using `RERANKER_BASE_URL` and `RERANKER_API_KEY`, so no second SDK is introduced.
3. The Ollama Reranker shall return passages sorted by descending score (highest relevance first) with one score per input passage.
4. When `passages` is empty, the Ollama Reranker shall return an empty list without issuing any model call.
5. The Ollama Reranker shall preserve passage strings byte-for-byte; it shall not rewrite, truncate, or reorder content within an individual passage.
6. If the model response cannot be parsed into a numeric score for a passage, the Ollama Reranker shall assign that passage a deterministic fallback score lower than every successfully-parsed score so the passage still appears in the output exactly once.

### Requirement 3: Reranker is configurable via environment variables
**Objective:** As an operator deploying MiroFish, I want to override the reranker provider, model, and endpoint via environment variables so that I can target a different Ollama host, a different model, or disable reranking entirely.

#### Acceptance Criteria
1. The Configuration module shall expose `RERANKER_PROVIDER` with default `ollama` and accept the values `ollama` and `none`.
2. The Configuration module shall expose `RERANKER_MODEL` whose default is a small Ollama-available chat model selected during design (e.g. `qwen2.5:3b` or `llama3.2:3b`).
3. The Configuration module shall expose `RERANKER_BASE_URL` whose default is the value of `EMBEDDING_BASE_URL` (so the same Ollama host is reused by default).
4. The Configuration module shall expose `RERANKER_API_KEY` whose default is the value of `EMBEDDING_API_KEY` (so Ollama's ignored-token default `ollama` works without explicit configuration).
5. If `RERANKER_PROVIDER` is set to a value other than `ollama` or `none`, the Graphiti Adapter shall raise a clear `ValueError` at startup naming the offending value and listing accepted values.
6. The Configuration module shall read all four reranker variables from the process environment via the same `os.environ.get` pattern used by the surrounding settings, with no additional dependencies.

### Requirement 4: `none` provider preserves the passthrough fallback for CI / lightweight setups
**Objective:** As a developer running tests or a slim container that cannot pull the reranker model, I want to disable reranking explicitly so the Flask app still boots and graph search still works.

#### Acceptance Criteria
1. Where `RERANKER_PROVIDER=none`, the Graphiti Adapter shall continue to inject `_PassthroughReranker` and shall not attempt any model call at startup.
2. While `RERANKER_PROVIDER=none`, graph search shall return results in the order Graphiti supplies them with the existing synthetic-descending-score behavior.
3. The Graphiti Adapter shall log at INFO level the selected reranker provider during initialization so operators can confirm whether reranking is active.

### Requirement 5: Graceful degradation when the configured Ollama model is unreachable
**Objective:** As an operator who forgot to run `ollama pull <model>` (or whose Ollama service is down), I want the Flask backend to keep serving requests with a clear log signal rather than crashing.

#### Acceptance Criteria
1. If the Ollama Reranker fails to score passages for a given query (e.g. connection refused, 404 model not found, timeout, or unparseable response), the Graphiti Adapter shall log a warning that names the failing model and the error class.
2. If the Ollama Reranker raises during a `rank` call, the calling `_GraphNamespace.search` shall not propagate the exception to HTTP callers; existing search-error handling already swallows reranker errors into a logged warning, and this behavior shall be preserved.
3. When the Ollama Reranker fails for a query, the rerank-failure path shall return the passages in their original Graphiti order so search remains functional.
4. The Ollama Reranker shall not raise during construction (i.e. `_get_graphiti()` must succeed even if the Ollama service is unavailable); failures are deferred until the first `rank` call.

### Requirement 6: Documentation reflects the new reranker configuration
**Objective:** As a new contributor reading the docs, I want the reranker env vars, defaults, and prerequisites documented in the same places the other LLM/embedder settings live so configuration is discoverable.

#### Acceptance Criteria
1. The Environment Example file (`.env.example`) shall include entries for `RERANKER_PROVIDER`, `RERANKER_MODEL`, `RERANKER_BASE_URL`, and `RERANKER_API_KEY`, each commented with its default and accepted values.
2. The CLAUDE.md document shall list the four reranker variables in its "Required Environment Variables" section with the same level of detail used for `EMBEDDING_MODEL`.
3. The README.md document shall mention the `ollama pull <reranker model>` prerequisite alongside the existing `ollama pull mxbai-embed-large` note (or wherever Ollama setup is documented).
4. Where the `.kiro/specs/graphiti-neo4j-finalize` documents state that the reranker is a passthrough no-op, those documents shall either be updated to point at this spec or left untouched (decided in design); the constraint is that no documentation shall continue to claim "a real per-provider reranker is a follow-up" once this spec is implemented.

### Requirement 7: Report-tool integration verifies reranked output reaches consumers
**Objective:** As a developer using the ReportAgent tools, I want `SearchResult`, `InsightForge`, `Panorama`, and `Interview` to receive properly reranked edges/nodes so their report output reflects model-judged relevance, not Graphiti's hybrid-search ordering alone.

#### Acceptance Criteria
1. When `RERANKER_PROVIDER=ollama` is active and the configured model is available, the `_GraphNamespace.search` shall return passages whose order is determined by the Ollama Reranker, not Graphiti's default RRF ordering.
2. The ReportAgent tools (`SearchResult`, `InsightForge`, `Panorama`, `Interview`) shall require no changes for this feature; the rerank improvement reaches them transparently through `_GraphNamespace.search`.
3. While the Ollama Reranker is active, the per-project `group_id` scoping of all Graphiti queries shall remain unchanged.
