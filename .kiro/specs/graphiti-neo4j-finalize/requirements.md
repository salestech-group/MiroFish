# Requirements Document

## Project Description (Input)
Complete Zep → Neo4j/Graphiti migration: add Neo4j to docker-compose.yml (Part 1) and fix the data-processing pipeline so the documented default LLM provider (Qwen via Dashscope) works end-to-end (Part 2). Tracked by GitHub issue #1.

## Introduction

Commit `6264828` replaced Zep Cloud with Graphiti + Neo4j as the knowledge-graph backend, but the migration left two functional gaps that block first-time setup and the documented default LLM provider:

1. `docker-compose.yml` does not include Neo4j, so `docker compose up -d` from a clean checkout cannot bring up the stack as advertised in the README.
2. Graphiti is hard-wired to Gemini for both LLM and embeddings, so the documented default provider (Qwen via Dashscope) — which is OpenAI-SDK-compatible — fails Step 1 of the pipeline (Graph Build) with a 401.

Adjacent issues block the same path: the env example file is stale (still references `ZEP_API_KEY`, missing Neo4j and embedding vars), the embedder credentials are coupled to the chat LLM credentials, and a no-op reranker stub silently degrades search quality while the call site at `backend/app/services/zep_tools.py:504` requests a `cross_encoder` reranker that the adapter accepts and ignores.

This spec finalises the migration so a fresh checkout with a Qwen `LLM_API_KEY` works end-to-end via Docker, without regressing the existing Gemini path.

## Boundary Context

- **In scope**:
  - Adding a Neo4j service to `docker-compose.yml`, wired with healthcheck and `depends_on`.
  - Making the Graphiti LLM client and embedder configurable (OpenAI-compatible vs Gemini).
  - Decoupling embedding credentials from chat LLM credentials.
  - Refreshing `.env.example` to mirror the README and the code's actual env reads.
  - Cleaning up the reranker situation (no-op stub + ignored kwarg + misleading caller).
  - Verifying the host-mode `npm run dev` path still works against a host-installed Neo4j.

- **Out of scope**:
  - Renaming `zep_*` files (legacy prefix) — tracked separately.
  - Migrating data from existing Zep deployments.
  - Frontend changes.
  - Adding a real cross-encoder reranker implementation (we choose to remove rather than reimplement; future ticket may add one).
  - Pagination cleanup of `_NodeNamespace.get_by_graph_id` / `_EdgeNamespace.get_by_graph_id` (low priority, deferred).

- **Adjacent expectations**:
  - `_recover_stuck_projects` (`backend/app/__init__.py`) talks to Neo4j at startup and must continue to function once Neo4j is reachable inside Docker.
  - All Graphiti reads/writes remain scoped by per-project `group_id` (no change to isolation semantics).
  - The single-source-of-truth config remains `backend/app/config.py`; new knobs are added there, not scattered.

## Requirements

### Requirement 1: Dockerised Neo4j Service
**Objective:** As a new contributor, I want `docker compose up -d` from a clean checkout to bring up Neo4j alongside the application, so that I can follow the README's "Quick Deploy via Docker" path without installing Neo4j manually.

#### Acceptance Criteria
1. The `docker-compose.yml` shall declare a service named `neo4j` using image `neo4j:5-community`.
2. The `neo4j` service shall expose ports `7474` (HTTP browser) and `7687` (Bolt) to the host.
3. The `neo4j` service shall authenticate with `neo4j/${NEO4J_PASSWORD:-mirofish123}` sourced from the project env file.
4. The `neo4j` service shall mount named Docker volumes for `/data` and `/logs` so graph state persists across container restarts.
5. The `neo4j` service shall declare a healthcheck that succeeds only when Bolt is ready (e.g. via `cypher-shell`).
6. The `mirofish` application service shall declare `depends_on: { neo4j: { condition: service_healthy } }` so the app starts only after Neo4j is ready.
7. While running inside the Docker network, the `mirofish` service shall use `NEO4J_URI=bolt://neo4j:7687` (overriding the host-mode default of `bolt://localhost:7687`).
8. The `docker-compose.yml` shall not include the obsolete top-level `version:` key (Compose v2 syntax).
9. When `docker compose up -d` is run on a clean checkout, the system shall start both services and `POST /api/graph/build` shall succeed end-to-end against the in-stack Neo4j.

### Requirement 2: Host-Mode Compatibility (No Regression)
**Objective:** As a developer running `npm run dev` against a host-installed Neo4j, I want my workflow to keep working unchanged, so that the Docker addition does not regress the host-mode dev loop.

#### Acceptance Criteria
1. When `NEO4J_URI` is unset, the application shall default to `bolt://localhost:7687`.
2. When `npm run dev` is run with a host-installed Neo4j on the default port, the application shall connect successfully without any new configuration steps compared to before this change.
3. The Docker-only `NEO4J_URI=bolt://neo4j:7687` override shall not appear in any non-Docker code path.

### Requirement 3: Configurable Graphiti LLM Provider
**Objective:** As an operator using the documented default LLM provider (Qwen via Dashscope), I want Graphiti to use the same OpenAI-SDK-compatible endpoint as the rest of the app, so that Step 1 of the pipeline succeeds without my key being sent to Google.

#### Acceptance Criteria
1. The system shall read a configuration value `Config.GRAPHITI_LLM_PROVIDER` with allowed values `openai` and `gemini`.
2. When `GRAPHITI_LLM_PROVIDER` is unset, the system shall default to `openai`.
3. When `GRAPHITI_LLM_PROVIDER=openai`, the Graphiti adapter shall instantiate an OpenAI-compatible LLM client using `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL_NAME` (the same triple consumed by `LLMClient`).
4. When `GRAPHITI_LLM_PROVIDER=gemini`, the Graphiti adapter shall instantiate `GeminiClient` with the existing configuration (preserving today's behaviour).
5. If `GRAPHITI_LLM_PROVIDER` is set to an unrecognised value, the Graphiti adapter shall raise a configuration error at startup with a message naming the offending value and the allowed set.
6. When the provider is `openai` and `LLM_API_KEY` is a Qwen/Dashscope key, the system shall complete a graph build for a small `.txt` document end-to-end without hitting Gemini endpoints.

### Requirement 4: Configurable Graphiti Embedder
**Objective:** As an operator, I want the embedder to follow the same provider switch as the LLM client, so that I can run a fully OpenAI-compatible stack or a fully Gemini stack without code edits.

#### Acceptance Criteria
1. When `GRAPHITI_LLM_PROVIDER=openai`, the Graphiti adapter shall instantiate an OpenAI-compatible embedder using the embedding-specific credentials (see Requirement 5) and `EMBEDDING_MODEL`.
2. When `GRAPHITI_LLM_PROVIDER=gemini`, the Graphiti adapter shall instantiate `GeminiEmbedder` using `LLM_API_KEY` and `EMBEDDING_MODEL` (preserving today's behaviour).
3. The Graphiti adapter shall not import provider-specific embedder classes that are unused at runtime for the selected provider (lazy import or guarded selection).

### Requirement 5: Decoupled Embedding Credentials
**Objective:** As an operator running Qwen for chat (which does not expose `text-embedding-3-small`), I want to point the embedder at a separate provider/key, so that embeddings work without forcing me to use a single provider for everything.

#### Acceptance Criteria
1. The system shall read optional configuration values `EMBEDDING_API_KEY` and `EMBEDDING_BASE_URL`.
2. When `EMBEDDING_API_KEY` is unset, the system shall fall back to `LLM_API_KEY`.
3. When `EMBEDDING_BASE_URL` is unset, the system shall fall back to `LLM_BASE_URL`.
4. When `EMBEDDING_API_KEY` is set, the embedder shall use the embedding key for embedding calls and the chat LLM key shall be untouched for chat calls.
5. The embedder shall use `EMBEDDING_MODEL` for the model name independently of `LLM_MODEL_NAME`.

### Requirement 6: Refreshed Env Example
**Objective:** As a new contributor copying `.env.example` to `.env`, I want the example to reflect what the code actually reads, so that following the README produces a working configuration.

#### Acceptance Criteria
1. The `.env.example` file shall include `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` with sensible defaults matching `backend/app/config.py`.
2. The `.env.example` file shall include `EMBEDDING_MODEL` with a default consistent with `Config.EMBEDDING_MODEL`.
3. The `.env.example` file shall include the optional `GRAPHITI_LLM_PROVIDER`, `EMBEDDING_API_KEY`, and `EMBEDDING_BASE_URL` keys with comments explaining their fallback behaviour.
4. The `.env.example` file shall annotate that Dashscope/Qwen does not expose OpenAI-compatible embeddings and shall recommend pointing the embedder at OpenAI directly when chat is Dashscope/Qwen.
5. The `.env.example` file shall either drop `ZEP_API_KEY` entirely or keep it as a single commented line marked deprecated for users with old setups.
6. The `.env.example` file shall not contain any real secret values.
7. Where `.env.example` lists an env var, the README's environment-variable section shall list the same var (no drift between the two surfaces).

### Requirement 7: Reranker Cleanup
**Objective:** As a developer reading the search code path, I want the reranker situation to be honest, so that I am not misled into believing search results are reranked when they are not.

#### Acceptance Criteria
1. The `_GeminiReranker` no-op stub shall be removed from `backend/app/services/graphiti_adapter.py`.
2. The `_GraphNamespace.search` method shall not accept a `reranker` keyword argument it silently ignores; the parameter shall either be removed or honoured.
3. The `ZepToolsService.search_graph` call site in `backend/app/services/zep_tools.py` shall not pass `reranker="cross_encoder"` if the adapter cannot honour it.
4. After cleanup, every search code path (`InsightForge`, `PanoramaSearch`, `QuickSearch`, the report-agent tools) shall return Graphiti's default-ranked results without the misleading no-op layer.

### Requirement 8: Provider Backwards Compatibility
**Objective:** As an existing operator running with Gemini, I want my deployment to keep working without changes after this migration is finalised, so that I am not forced to migrate providers.

#### Acceptance Criteria
1. When `GRAPHITI_LLM_PROVIDER=gemini` and the existing `LLM_API_KEY`/`EMBEDDING_MODEL` are unchanged, the Graphiti adapter shall behave identically to the pre-change implementation for graph build, search, and report.
2. When the env file does not declare `GRAPHITI_LLM_PROVIDER`, the system shall pick `openai` (matching the documented default provider) and shall not silently switch existing Gemini deployments.
3. The migration shall not remove any env var an existing Gemini deployment relies on (`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL_NAME`, `EMBEDDING_MODEL`, `NEO4J_*`).

### Requirement 9: End-to-End Acceptance via Qwen
**Objective:** As a reviewer of this migration, I want a smoke test that a fresh checkout with the documented default provider can complete the pipeline, so that I have confidence the fix actually unblocks the README path.

#### Acceptance Criteria
1. When a fresh checkout is configured with a Qwen `LLM_API_KEY`, an OpenAI `EMBEDDING_API_KEY`, and `GRAPHITI_LLM_PROVIDER=openai` (default), uploading a small `.txt` and calling `/api/graph/build` shall complete successfully.
2. After a successful graph build, querying the graph data endpoint shall return a non-zero count of nodes and edges.
3. After a successful graph build, generating a report with `InsightForge`/`Panorama` shall return non-empty results.
4. If the smoke test fails, the system shall surface the underlying provider error (not a 500) so the operator can correct configuration.
