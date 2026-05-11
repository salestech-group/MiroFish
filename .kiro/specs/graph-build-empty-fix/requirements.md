# Requirements Document

## Project Description (Input)
Fix neo4j migration leaves graph empty (metadata written but no entities/edges) and migrate the embedding pipeline to a local model by default. See `.ticket/37.md` for the full brief.

## Introduction

After the Zep Cloud → Graphiti + local Neo4j migration, a fresh graph build connects to Neo4j and writes some bookkeeping/metadata but never persists the entity and edge data extracted from uploaded source material. Downstream pipeline steps (env setup, profile generation, report agent) consequently have no graph to read, so the end-to-end flow is effectively broken.

This feature has two coupled deliverables:

1. **Restore non-empty graph builds.** Identify the failure path that lets a graph build appear successful while leaving `(:Entity {group_id})` and `RELATES_TO` edges empty, fix it, and ensure that any remaining silent-failure surfaces are converted into a `Task.status = FAILED` with a useful error message — extending the existing loud-failure work from spec `graphiti-ollama-embedder`.
2. **Default to a local embedder.** Move the configured embedder defaults off OpenAI's `text-embedding-3-small` (1536-dim, remote, paid) and onto a local 1024-dim model (Ollama `mxbai-embed-large`) so a clean checkout runs end-to-end without remote embedding credentials and so the configured dimension matches Graphiti's `EMBEDDING_DIM=1024` vector-index dimension.

The bug ticket explicitly couples these two changes because dimension mismatch between the embedder output (1536-dim with the current default) and Graphiti's Neo4j vector index (1024-dim) is one of the likely root causes of the silent empty-graph behavior, and aligning on a local 1024-dim default fixes both at once while removing the remote dependency from the graph-build hot path.

This work explicitly preserves backwards compatibility for operators who already point the `EMBEDDING_*` variables at OpenAI- or Gemini-compatible endpoints.

## Boundary Context
- **In scope**: diagnosing and fixing the path that produces an empty graph; making local embeddings (1024-dim Ollama `mxbai-embed-large`) the configured default in `backend/app/config.py` and `.env.example`; aligning the embedder output dimension with Graphiti's `EMBEDDING_DIM` end-to-end so vector writes land in Neo4j; surfacing any remaining silent failure path on the graph-build worker as a `Task.status = FAILED` with a useful error; updating `README.md`, `CLAUDE.md`, and `docker-compose.yaml` comments to reflect that local embeddings are the default and remote providers are configurable fallbacks; verifying that profile generation and the report agent can read the resulting graph after a fresh build.
- **Out of scope**: rewriting the Graphiti adapter's provider factory beyond what is needed to make Ollama the default; introducing a startup-time embedder health probe that refuses to boot on dim/model mismatch (logging + first-batch failure are sufficient); supporting embedding dimensions other than 1024 (changing `EMBEDDING_DIM` is an explicit follow-up); migrating LLM defaults — only embedding defaults change; bundling Ollama or any local-model binary into the Docker stack; backfilling or auto-rebuilding the graphs of projects created before this change.
- **Adjacent expectations**: relies on the loud-failure contract for `_GraphNamespace.add_batch` introduced in spec `graphiti-ollama-embedder` (issue #18) — episode-ingestion exceptions already propagate to the worker; this spec must not weaken that contract. Relies on the background-task error-handling contract in `.kiro/steering/error-handling.md` — worker exceptions reach `fail_task(...)` and the task moves out of `PROCESSING`. Relies on the `group_id` isolation rule in `.kiro/steering/database.md` — every graph read/write must remain scoped by `group_id`.

## Requirements

### Requirement 1: Root Cause Identification for Empty Graph Builds
**Objective:** As a MiroFish maintainer, I want the failure path that produces empty graphs on the post-migration default configuration to be diagnosed and documented, so that the resulting fix is justified by evidence and the regression cannot reappear unnoticed.

#### Acceptance Criteria

1. When a fresh graph build is run on the pre-fix `main` branch with the documented default `.env` (no `EMBEDDING_*` overrides), the maintainer shall reproduce the empty-graph symptom and capture the underlying failure mode (server-side rejection, swallowed exception, dimension mismatch, etc.) before any code change is applied.
2. The pull request description and `.kiro/specs/graph-build-empty-fix/design.md` shall document the identified root cause(s) in 2–5 sentences, including which file(s) and which call sites surface or mask the failure.
3. If the root cause is a dimension mismatch between the configured embedder and Graphiti's Neo4j vector index, then the design document shall record both dimensions (configured embedder, Graphiti `EMBEDDING_DIM`) and the resulting Neo4j error class.
4. If the root cause is a silently swallowed exception path outside the already-hardened `_GraphNamespace.add_batch`, then the design document shall identify the call site(s) and Requirement 4 shall cover the loud-failure remediation.
5. The MiroFish system shall not be considered "fixed" by this spec unless a reproduction run on the post-fix default configuration writes a non-zero count of `(:Entity {group_id})` nodes and `RELATES_TO` edges to Neo4j for the project's `group_id` for a seed file that previously produced an empty graph.

### Requirement 2: Local Embeddings as the Default Provider
**Objective:** As a new MiroFish operator with a fresh checkout, I want the embedding pipeline to default to a local model, so that I can run a clean end-to-end graph build without configuring a remote embedding provider or paying per-request.

#### Acceptance Criteria

1. The `backend/app/config.py` defaults shall set `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, and `EMBEDDING_API_KEY` such that, in the absence of any `EMBEDDING_*` override in `.env`, the embedder targets a local Ollama instance with the `mxbai-embed-large` model.
2. The `.env.example` file shall present the local-Ollama embedder configuration as the active, uncommented default, and shall present the OpenAI- and Gemini-compatible embedder configurations as commented-out fallbacks with one-line guidance on when to use each.
3. When the operator runs `npm run dev` (or `docker compose up`) with the default configuration and a running local Ollama instance that has `mxbai-embed-large` pulled, the graph-build pipeline shall complete end-to-end and write non-empty entity nodes and edges to Neo4j for the project's `group_id`.
4. If the operator runs the default configuration without a reachable Ollama instance, then the graph-build `Task` shall transition to `FAILED` with `Task.error` containing a non-empty message naming the connectivity failure (per `.kiro/steering/error-handling.md`).
5. The Ollama embedder integration shall continue to be constructed through the existing `_build_llm_and_embedder` factory in `backend/app/services/graphiti_adapter.py` rather than via a new provider-specific code path.

### Requirement 3: Embedding Dimension Consistency
**Objective:** As a MiroFish maintainer, I want the configured embedder's output dimension to match Graphiti's Neo4j vector index dimension end-to-end, so that vector writes are accepted by Neo4j and the empty-graph failure mode cannot recur through a dimension drift.

#### Acceptance Criteria

1. The MiroFish system shall keep Graphiti's default `EMBEDDING_DIM = 1024` and shall configure the default embedder (`mxbai-embed-large`) so its output vectors are 1024-dimensional, matching the Neo4j vector index.
2. The `CLAUDE.md` documentation shall explicitly state the 1024-dim constraint and shall name `mxbai-embed-large` (Ollama, 1024-dim) as a supported default while explicitly ruling out 768-dim models such as `nomic-embed-text`.
3. Where an operator overrides `EMBEDDING_MODEL` to a model whose output dimension does not match Graphiti's `EMBEDDING_DIM`, the graph-build `Task` shall fail loudly with the underlying Neo4j dimension-mismatch error surfaced to the frontend, rather than producing an empty graph silently.
4. The system shall not introduce a separately tunable embedding-dimension environment variable in this spec; changing the dimension end-to-end is explicitly out of scope.

### Requirement 4: Loud Failure on Every Silent Empty-Graph Path
**Objective:** As a MiroFish operator, I want any graph-build failure that previously left Neo4j empty to instead terminate the background task with a visible error, so that the empty-graph regression cannot return unnoticed.

#### Acceptance Criteria

1. The `_GraphNamespace.add_batch` loud-failure contract from spec `graphiti-ollama-embedder` (episode-ingestion exceptions propagate, no placeholder UUIDs) shall remain intact; this spec shall not reintroduce a silent fallback.
2. If the root-cause investigation under Requirement 1 identifies any additional silent-failure call site in `graphiti_adapter.py` or `graph_builder.py` that contributes to the empty-graph symptom, then that call site shall be remediated so its failure propagates to the worker and reaches `TaskManager().fail_task(...)`.
3. When the embedder construction in `_build_llm_and_embedder` fails (e.g., unreachable base URL), then the first call that triggers a Graphiti operation requiring the embedder shall raise to the worker and the graph-build task shall transition to `FAILED` with `Task.error` containing the underlying error message.
4. The graph-build worker in `graph_builder.py` shall log the propagated failure at `ERROR` level (not `WARNING`) before calling `fail_task(...)`, and the user-facing project state shall move out of `GRAPH_BUILDING` per the existing recovery contract.
5. While a graph-build task is processing, the system shall not transition the surrounding `Project` to `GRAPH_COMPLETED` unless `_get_graph_info(graph_id)` confirms a non-zero entity-node count for the project's `group_id`.

### Requirement 5: Backwards Compatibility for Existing Remote Embedder Configurations
**Objective:** As an existing MiroFish operator who has already configured `EMBEDDING_*` to point at an OpenAI- or Gemini-compatible endpoint, I want this change to be invisible on the happy path, so that no upgrade action is required.

#### Acceptance Criteria

1. Where `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, and `EMBEDDING_API_KEY` are set to OpenAI- or Gemini-compatible values in `.env`, the embedder construction in `_build_llm_and_embedder` shall behave identically to the pre-change implementation for those providers.
2. The MiroFish system shall not require any new environment variable to function; local-Ollama support shall remain enabled purely by the existing `EMBEDDING_*` variables and `GRAPHITI_LLM_PROVIDER`.
3. When an operator has previously built a project graph with a 1536-dim OpenAI embedder, the system shall continue to read that graph after the default change, provided the operator continues to set `EMBEDDING_MODEL` to the same value they used before; the spec shall not auto-rebuild or invalidate pre-existing project graphs.
4. The `GRAPHITI_LLM_PROVIDER` default shall remain `openai` (since "openai" already encompasses any OpenAI-SDK-compatible endpoint, including Ollama at `host:11434/v1`); only the `EMBEDDING_*` defaults change.

### Requirement 6: Documentation Reflects the New Default
**Objective:** As a new operator reading the README or CLAUDE.md, I want the documented happy path to match the new local-by-default behavior, so that I can run a clean graph build by following the docs without discovering the OpenAI default after the fact.

#### Acceptance Criteria

1. The `CLAUDE.md` "Required Environment Variables" section shall describe local Ollama (`mxbai-embed-large`, 1024-dim) as the default `EMBEDDING_MODEL` and shall list OpenAI- and Gemini-compatible embedders as supported alternatives.
2. The `README.md` setup section shall mention that a local Ollama instance with `mxbai-embed-large` pulled is part of the default prerequisite stack (alongside Neo4j), and shall include the one-line `ollama pull mxbai-embed-large` command needed before the first graph build.
3. The `docker-compose.yaml` comments or the README's Docker section shall note that, when running MiroFish in Docker, Ollama on the host is reached via `host.docker.internal:11434` and shall reference the existing `.env.example` snippet rather than duplicating the env values.
4. The documentation shall include a one-line `curl` smoke test that calls the configured `$EMBEDDING_BASE_URL/embeddings` with the configured model and confirms the response embedding length is 1024, so operators can diagnose embedder connectivity before running a graph build.

### Requirement 7: End-to-End Verification Across Downstream Steps
**Objective:** As a MiroFish operator, I want a fresh graph build under the new defaults to produce a graph that the downstream profile-generation and report-agent steps can actually read, so that the fix delivers a working pipeline and not just a non-empty Neo4j.

#### Acceptance Criteria

1. When a fresh graph build under the new defaults completes, the env-setup step (profile generation) shall successfully read entities from the project's `group_id` and produce a non-empty list of OASIS agent profiles.
2. When the report agent runs against a graph built under the new defaults, its `SearchResult` / `InsightForge` / `Panorama` / `Interview` tools shall return non-empty results for queries that previously returned empty (because the graph was empty).
3. The pull request description shall document the end-to-end smoke-test path (graph build → profile generation → report-agent query) the maintainer ran on a representative seed file before requesting review.
4. If the end-to-end smoke test cannot be run by the maintainer (e.g., no representative seed material at hand), then the maintainer shall state that explicitly in the PR description rather than implicitly claiming downstream success.
