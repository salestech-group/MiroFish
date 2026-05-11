# Implementation Plan

> Foundation tasks introduce the four `RERANKER_*` configuration knobs.
> Core tasks add the new `OllamaReranker` and the factory selection branch.
> Integration tasks wire documentation parity.
> Validation closes the loop with a structural sweep.

## Foundation

- [x] 1. Add reranker configuration surface
- [x] 1.1 Introduce four `RERANKER_*` settings on the `Config` class
  - Add `RERANKER_PROVIDER` with default `ollama`, read via `os.environ.get('RERANKER_PROVIDER', 'ollama')`.
  - Add `RERANKER_MODEL` with default `qwen2.5:3b`, read via `os.environ.get('RERANKER_MODEL', 'qwen2.5:3b')`.
  - Add `RERANKER_BASE_URL` with default that chains to the embedding host: `os.environ.get('RERANKER_BASE_URL', os.environ.get('EMBEDDING_BASE_URL', 'http://localhost:11434/v1'))`. Do not reference `Config.EMBEDDING_BASE_URL` directly; use the env-lookup form so behaviour stays consistent under reload patterns.
  - Add `RERANKER_API_KEY` with default that chains to the embedding key the same way (`os.environ.get('RERANKER_API_KEY', os.environ.get('EMBEDDING_API_KEY', 'ollama'))`).
  - Do not add the reranker to `Config.validate()`; the provider has no mandatory credentials.
  - Observable completion: a Python REPL that imports `Config` shows the four attributes with the documented defaults, and overriding `EMBEDDING_BASE_URL` in the environment is visible on `Config.RERANKER_BASE_URL` too.
  - _Requirements: 1.3, 3.1, 3.2, 3.3, 3.4, 3.6_

## Core

- [x] 2. Implement the Ollama-backed reranker
- [x] 2.1 Create the new reranker module with the `CrossEncoderClient` subclass
  - Define a new module under `backend/app/services/` that hosts the reranker class. The class subclasses `graphiti_core.cross_encoder.client.CrossEncoderClient` and implements only the async `rank` method.
  - Constructor accepts `model`, `base_url`, `api_key` as keyword arguments; it instantiates `openai.AsyncOpenAI(base_url=..., api_key=...)` but performs no network I/O so the Flask app can boot when Ollama is unreachable.
  - `rank(query, passages)` short-circuits on empty `passages` and returns `[]` without any model call.
  - For each passage, send a single chat-completion request with `temperature=0.0` and a deterministic system prompt asking for a JSON object `{"score": <0.0..1.0>}` describing the passage's relevance to the query. Use `asyncio.gather` to run all per-passage requests concurrently.
  - Parse each model response defensively: strip any `<think>...</think>` block, strip markdown code fences, attempt `json.loads`, fall back to regex-extract the first floating-point number, clip the value to `[0.0, 1.0]`. On any per-passage failure, assign a deterministic fallback score of `-0.001 * passage_index` and log at DEBUG once per failure naming the model and error class. The passage string is echoed byte-for-byte regardless of parse outcome.
  - Wrap the whole call in a `try/except`. On a whole-call failure (connection refused, 404, timeout, etc.), log a single WARNING naming the model and error class, then return `[(p, 1.0 - 0.01 * i) for i, p in enumerate(passages)]` so search remains functional. The method must not raise.
  - Sort the returned list by score descending before returning.
  - Observable completion: instantiating the new class with a deliberately bad `base_url` does not raise; an async call to `rank("q", [])` returns `[]`; an async call with two non-empty passages against a reachable Ollama returns two `(passage, float)` tuples in descending-score order, with every input passage byte-identical in the output.
  - _Requirements: 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 5.1, 5.2, 5.3, 5.4, 7.1_
  - _Boundary: OllamaReranker module_

## Integration

- [x] 3. Wire the new reranker into the Graphiti factory
- [x] 3.1 Select the reranker inside `_get_graphiti()` based on `Config.RERANKER_PROVIDER`
  - Introduce a small allow-list constant alongside `_ALLOWED_GRAPHITI_PROVIDERS` enumerating `("ollama", "none")`.
  - Read `Config.RERANKER_PROVIDER`, lowercase it, and validate against the allow-list. If the value is not in the allow-list, raise `ValueError` with a message that names the offending value and lists the accepted values — same shape as the existing `GRAPHITI_LLM_PROVIDER` validation.
  - For `ollama`, construct the new `OllamaReranker(model=Config.RERANKER_MODEL, base_url=Config.RERANKER_BASE_URL, api_key=Config.RERANKER_API_KEY)` and pass it as the `cross_encoder=` argument to `Graphiti(...)`.
  - For `none`, continue to pass `_PassthroughReranker()` as today; do not change the passthrough class.
  - Add one INFO log line at construction time that announces the selected reranker provider (sibling of the existing "Initializing Graphiti client (provider=...)" log).
  - Preserve the double-checked locking and singleton pattern exactly. The provider is read once at first construction; do not re-read at runtime.
  - Observable completion: with `RERANKER_PROVIDER` unset, app startup logs `Initializing Graphiti reranker (provider=ollama)...` and Graphiti is constructed with the `OllamaReranker`. With `RERANKER_PROVIDER=none`, the log reports `none` and Graphiti uses `_PassthroughReranker`. With `RERANKER_PROVIDER=banana`, `_get_graphiti()` raises `ValueError` listing `('ollama', 'none')`.
  - _Requirements: 1.1, 1.2, 3.5, 4.1, 4.2, 4.3_
  - _Depends: 1.1, 2.1_

- [ ] 4. Update operator-facing documentation
- [ ] 4.1 (P) Add the new env knobs to `.env.example`  *(deferred — sandbox hook blocks all `.env*` access; see HANDOFF.md)*
  - Insert a four-line `RERANKER_*` block adjacent to the existing `EMBEDDING_*` block, mirroring the comment style (default, accepted values, and a one-line note that `RERANKER_PROVIDER=none` disables reranking).
  - Observable completion: opening `.env.example` shows the four new variables with documented defaults, positioned next to the embedding block.
  - _Requirements: 6.1_
  - _Boundary: .env.example_
  - _Depends: 1.1_

- [x] 4.2 (P) Extend the `Required Environment Variables` snippet in `CLAUDE.md`
  - Add the four `RERANKER_*` variables to the existing fenced code block under "Required Environment Variables" in `CLAUDE.md`, keeping the same comment style used for the `EMBEDDING_*` block.
  - Observable completion: `CLAUDE.md` documents the four reranker variables next to the embedding block and includes a note that `RERANKER_PROVIDER=none` keeps the previous passthrough behaviour.
  - _Requirements: 6.2_
  - _Boundary: CLAUDE.md_
  - _Depends: 1.1_

- [x] 4.3 (P) Document the Ollama pull prerequisite and env block in `README.md`
  - In the existing "Install Ollama and pull the default embedding model" section, add a parallel `ollama pull qwen2.5:3b` step (or note that the model used for reranking must be pulled, using the documented default).
  - In the `.env` snippet under "Configure Environment Variables", add the four `RERANKER_*` lines with brief comments mirroring the embedding-block style.
  - Treat `README-EN.md` and `README-ZH.md` translations as out of scope for this ticket — translation belongs to the active i18n workstream and would otherwise drift.
  - Observable completion: `README.md` shows the `ollama pull qwen2.5:3b` step and the four reranker env lines in the `.env` snippet.
  - _Requirements: 6.3_
  - _Boundary: README.md_
  - _Depends: 1.1_

- [x] 4.4 (P) Update the stale follow-up claim in the prior spec
  - In `.kiro/specs/graphiti-neo4j-finalize/research.md`, find the "A real per-provider reranker is a follow-up" text and either replace it with a pointer to this spec or note that follow-up has shipped under `graphiti-ollama-reranker`. The constraint is that no remaining documentation continues to claim the reranker remains a deferred passthrough.
  - Observable completion: a grep for "real per-provider reranker is a follow-up" across `.kiro/specs/` returns either zero hits or a pointer note to `graphiti-ollama-reranker`.
  - _Requirements: 6.4_
  - _Boundary: .kiro/specs/graphiti-neo4j-finalize/research.md_

## Validation

- [x] 5. Structural verification sweep
- [x] 5.1 Grep for legacy reranker references and verify the new wiring is reachable
  - Grep `backend/app/services/` for `gpt-4.1-nano` and `OpenAIRerankerClient`; both must return zero hits in code paths owned by this spec.
  - Grep `backend/app/services/graphiti_adapter.py` for the symbol of the new reranker class; confirm there is exactly one import site and one use site (the `_get_graphiti()` branch).
  - Confirm the four ReportAgent tools (`SearchResult`, `InsightForge`, `Panorama`, `Interview`) require no source changes by grepping for `client.graph.search(` call sites and verifying the kwarg shape is unchanged.
  - Confirm `_GraphNamespace.search` still filters by `group_id` (no regression to project isolation).
  - Observable completion: a short verification summary captured during implementation lists each grep outcome with the expected zero / single hit, and the report-tool call sites are unchanged.
  - _Requirements: 1.4, 7.1, 7.2, 7.3_
  - _Depends: 3.1_
