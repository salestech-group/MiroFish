# Implementation Plan — graphiti-neo4j-finalize

> Two-phase ordering: Foundation tasks (Config, Compose, env example) unblock the core adapter rewrite. Core tasks rewrite the Graphiti adapter and clean up the misleading reranker kwarg in callers. Validation closes the loop with a structural review and a manual smoke test.

## 1. Foundation — runtime configuration and infrastructure wiring

- [x] 1.1 (P) Extend the central configuration module with the new provider switch and decoupled embedder credentials
  - Add a `GRAPHITI_LLM_PROVIDER` configuration knob with allowed values `openai` and `gemini`, defaulting to `openai` when the environment variable is unset.
  - Add optional `EMBEDDING_API_KEY` and `EMBEDDING_BASE_URL` fields that fall back to the existing chat-LLM credentials when unset.
  - Preserve every existing `Config` attribute exactly (no removals, no renames); existing Gemini deployments must keep reading the same env vars.
  - Observable completion: importing the configuration module exposes the three new attributes with documented defaults, and existing attributes report identical values to before.
  - _Requirements: 3.1, 3.2, 5.1, 5.2, 5.3, 5.5, 8.3_
  - _Boundary: Config_

- [x] 1.2 (P) Add a healthchecked Neo4j service to the Docker Compose stack
  - Declare a `neo4j` service using `neo4j:5-community`, exposing the HTTP browser and Bolt ports, mounting named volumes for data and logs, and reading its admin password from the same project env file.
  - Add a Bolt-level healthcheck (using `cypher-shell`) so dependent services start only after Neo4j accepts queries.
  - Wire the existing application service so that it depends on Neo4j being healthy and overrides the connection URI for the in-container case while leaving the host-mode default untouched.
  - Keep Compose v2 syntax: do not introduce a top-level `version:` key.
  - Observable completion: `docker compose config` parses cleanly, and `docker compose up -d` from a clean checkout brings both services up with Neo4j reporting `healthy` before the application starts.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.3_
  - _Boundary: docker-compose.yml_

- [x] 1.3 (P) Refresh the env example to mirror the README and the code's actual reads
  - Add the Neo4j connection variables, the embedding model, and the new optional provider/embedder variables alongside their fallback rules.
  - Drop the deprecated Zep variable (or keep a single commented "deprecated" line) and add a comment guiding Qwen/Dashscope users to point the embedder at OpenAI directly.
  - Ensure no real secret values are present.
  - If the environment-guard hook blocks editing the example file, document the same content in the README's environment section instead and note the discrepancy in the PR description.
  - Observable completion: copying the example to a fresh `.env` plus filling in only the LLM key is sufficient to boot the stack against the documented default provider; the variable set in the example matches the variable set in the README's environment section.
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_
  - _Boundary: .env.example, README_

## 2. Core — Graphiti adapter rewrite

- [x] 2.1 Replace the no-op Gemini reranker with a provider-agnostic passthrough
  - Remove the `_GeminiReranker` class that depends on a Gemini client and replace it with a renamed passthrough that returns its input list with synthetic descending scores and holds no provider-specific state.
  - Always inject this passthrough into the Graphiti constructor so the framework does not silently fall back to its OpenAI-only default reranker (which would 401 against Qwen/Dashscope keys).
  - Observable completion: the graph adapter module exposes a passthrough reranker with no Gemini dependency, and a grep for `_GeminiReranker` in `backend/app/services/` returns zero hits.
  - _Requirements: 7.1, 7.4_

- [x] 2.2 Implement the Graphiti provider switch inside the singleton factory
  - Read the new provider configuration once when constructing the singleton; branch between an OpenAI-compatible client/embedder pair and the existing Gemini client/embedder pair.
  - Lazy-import the provider-specific Graphiti classes inside their respective branches so a missing optional dependency for one provider does not break the other.
  - For the OpenAI-compatible branch, use the chat triple (`api_key`, `base_url`, `model`) for the LLM client and the embedder credentials with fallback to the chat triple for the embedder.
  - For the Gemini branch, preserve the current behaviour byte-for-byte.
  - When the provider value is unrecognised, raise an error that names the offending value and lists the allowed set, so misconfiguration is surfaced loudly rather than silently.
  - Preserve the existing singleton pattern, double-checked lock, persistent event-loop binding, and `build_indices_and_constraints()` call exactly.
  - Observable completion: with the documented default configuration plus a Qwen/Dashscope key, the adapter constructs a Graphiti instance whose internal LLM client targets the configured base URL; with `GRAPHITI_LLM_PROVIDER=gemini` and an existing Gemini setup, the constructed instance is functionally identical to the pre-change behaviour.
  - _Requirements: 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 5.4, 8.1, 8.2, 9.4_
  - _Depends: 1.1, 2.1_

- [x] 2.3 Make the search namespace honest about reranker support
  - Drop the `reranker` keyword argument from the adapter's search method since the adapter has never honoured it.
  - Observable completion: the adapter's search method signature contains no `reranker` parameter, and a grep for `reranker=` in `backend/app/services/graphiti_adapter.py` returns zero hits.
  - _Requirements: 7.2_
  - _Depends: 2.2_

## 3. Core — caller cleanup so the new signature stays consistent

- [x] 3.1 (P) Remove the misleading reranker keyword from the report-tool search call
  - Update the graph search invocation that asks for a `cross_encoder` reranker (which the adapter never honoured) so it no longer passes the keyword.
  - Leave behaviour unchanged otherwise; the reranker argument was already a no-op.
  - Observable completion: a grep for `reranker=` in `backend/app/services/zep_tools.py` returns zero hits, and report-tool search code paths still execute end-to-end without `TypeError`.
  - _Requirements: 7.3, 7.4_
  - _Boundary: zep_tools.py_
  - _Depends: 2.3_

- [x] 3.2 (P) Remove the misleading reranker keyword from the profile-generator search calls
  - Update both of the graph search invocations that ask for an `rrf` reranker (also a no-op in the adapter) so they no longer pass the keyword.
  - Observable completion: a grep for `reranker=` in `backend/app/services/oasis_profile_generator.py` returns zero hits, and profile-generation search code paths still execute end-to-end without `TypeError`.
  - _Requirements: 7.3, 7.4_
  - _Boundary: oasis_profile_generator.py_
  - _Depends: 2.3_

## 4. Validation — structural checks and manual smoke

- [x] 4.1 Static verification of the rewrite
  - Confirm that no references to `_GeminiReranker` remain anywhere under `backend/`.
  - Confirm that no `reranker=` keyword arguments remain anywhere under `backend/app/services/`.
  - Confirm that `docker compose config` parses the new compose file without warnings about deprecated keys.
  - Confirm that the host-mode default for the Neo4j URI in the configuration is `bolt://localhost:7687` (Requirement 2.1) and is not mutated by the Compose service-level override.
  - Observable completion: all four checks pass and their commands exit zero / produce empty greps; results captured in the PR description.
  - _Requirements: 1.8, 2.1, 7.1, 7.2, 7.3_
  - _Depends: 3.1, 3.2_

- [ ] 4.2 Compose stack smoke (no LLM keys required)
  - Boot the full stack via `docker compose up -d` from a clean state (volumes pruned).
  - Confirm Neo4j reaches `healthy` status before the application container starts (verifies the `depends_on` wiring).
  - Confirm `cypher-shell` against the running Neo4j accepts a trivial `RETURN 1` using the configured password.
  - Confirm the application's `/health` endpoint returns OK after Neo4j is healthy.
  - Observable completion: `docker compose ps` shows both services running with Neo4j healthy; `curl localhost:5001/health` returns the expected JSON.
  - _Requirements: 1.9, 2.2_
  - _Depends: 1.2, 4.1_

- [ ] 4.3 Provider misconfiguration smoke
  - Set `GRAPHITI_LLM_PROVIDER` to an unrecognised value with an LLM key configured and trigger a graph-build request.
  - Confirm the adapter raises an error that names the offending value and lists the allowed providers.
  - Observable completion: the application logs contain the expected named-and-allowed error message; the failure surface is the provider error itself, not a generic 500.
  - _Requirements: 3.5, 9.4_
  - _Depends: 2.2, 4.2_

- [ ]* 4.4 End-to-end pipeline smoke against the documented default provider
  - Run by the ticket reviewer using real keys (Qwen for chat, OpenAI for embeddings).
  - Configure `LLM_API_KEY` (Qwen), `EMBEDDING_API_KEY` (OpenAI), keep `GRAPHITI_LLM_PROVIDER` at its default (`openai`), then upload a small `.txt` and run ontology generation followed by graph build.
  - Verify the graph data endpoint returns a non-zero count of nodes and edges and that report tools (`InsightForge`, `Panorama`) return non-empty results.
  - Marked optional because it depends on real API keys not present in the implementation environment; required for ticket reviewer sign-off.
  - Observable completion: graph build completes within ~10 minutes; data and report endpoints return non-empty payloads.
  - _Requirements: 9.1, 9.2, 9.3_
  - _Depends: 2.2, 4.2_

- [ ]* 4.5 Backwards-compatibility smoke against Gemini
  - Run by a reviewer with a Gemini key.
  - Set `GRAPHITI_LLM_PROVIDER=gemini`, leave `LLM_API_KEY` as the Gemini key, and set `EMBEDDING_MODEL=text-embedding-004`.
  - Run the same upload + build flow and confirm completion.
  - Marked optional for the same reason as 4.4 (no Gemini key in implementation environment); required for ticket reviewer sign-off.
  - Observable completion: graph build completes successfully with no behavioural difference from the pre-change implementation.
  - _Requirements: 8.1_
  - _Depends: 2.2, 4.2_
