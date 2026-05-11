# Requirements Document

## Project Description (Input)
Fix Graphiti embedding integration with Ollama (mxbai-embed-large) and stop silently swallowing embedding failures. Two bugs: (1) No first-class support for local Ollama embedders — `EMBEDDING_MODEL` defaults to OpenAI's `text-embedding-3-small` and the embedder reuses `LLM_BASE_URL` when `EMBEDDING_BASE_URL` is unset, so Ollama users get 404s; `.env.example` and `CLAUDE.md` don't document Ollama. (2) `backend/app/services/graphiti_adapter.py:471-473` catches every exception during episode ingestion, logs a truncated `WARNING`, and substitutes a placeholder UUID, so a graph build appears to succeed but writes nothing. Tracked as GitHub issue #18.

## Introduction
This feature adds first-class documentation for using a local Ollama embedder
(`mxbai-embed-large`, 1024-dim) with the Graphiti adapter and removes the
silent placeholder-UUID fallback in `_GraphNamespace.add_batch` so that
embedding failures terminate the surrounding background `Task` with the
underlying error visible in the UI and logs.

The work spans two narrowly scoped changes:

1. **Documentation update** — `.env.example`, `CLAUDE.md`, and the README /
   docker-compose comments gain a short Ollama section that explains how to
   point the embedder at a local Ollama instance, why `mxbai-embed-large` is
   the recommended model (1024-dim, matches Graphiti's default
   `EMBEDDING_DIM`), and how to smoke-test connectivity with one `curl`
   command before kicking off a graph build.
2. **Loud failure** — the broad `except Exception` in
   `_GraphNamespace.add_batch` is removed (or narrowed to a small set of
   transient network errors). Episode ingestion failures now propagate to
   the calling background task, which marks itself `FAILED` with the
   underlying error message attached, rather than logging a `WARNING` and
   returning a fake UUID.

No new dependency, environment variable, or config flag is introduced.
All existing OpenAI/Gemini configurations continue to work unchanged.

## Boundary Context
- **In scope**: documenting Ollama as a third supported embedder provider
  in `.env.example`, `CLAUDE.md`, and the docker-compose / README comments;
  removing the silent placeholder-UUID fallback in
  `_GraphNamespace.add_batch`; surfacing the underlying ingestion error to
  the background `Task` so it terminates with `status=FAILED`; documenting
  a one-line `curl` smoke test for embedder connectivity.
- **Out of scope**: a startup-time embedder health probe that refuses to
  boot on dim/model mismatch; making `EMBEDDING_DIM` env-configurable so
  768-dim or 1536-dim embedders can be used; adding a per-provider
  embedder factory (today the adapter only branches on `openai` and
  `gemini`); generic retry/backoff policy changes elsewhere in the
  pipeline.
- **Adjacent expectations**: the existing background-task error-handling
  contract from `.kiro/steering/error-handling.md` already specifies that
  worker exceptions must call `fail_task(...)`. This feature relies on
  that contract — it does not introduce a new one. The single-episode
  `_GraphNamespace.add(...)` path is left untouched because it already
  re-raises naturally.

## Requirements

### Requirement 1: Ollama Embedder Documentation
**Objective:** As a self-hosting MiroFish operator, I want first-class
documentation for using a local Ollama embedder, so that I can run the
Graphiti pipeline without needing an OpenAI- or Gemini-compatible
embeddings endpoint.

#### Acceptance Criteria
1. The `.env.example` file shall contain a commented Ollama embedder block
   showing `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, and `EMBEDDING_MODEL`
   set to `http://host.docker.internal:11434/v1`, a non-empty placeholder
   string, and `mxbai-embed-large` respectively, with a comment noting the
   `ollama pull mxbai-embed-large` prerequisite.
2. The `CLAUDE.md` file shall list the three supported embedder providers
   (OpenAI, Gemini, Ollama) and shall state the 1024-dim constraint that
   forces `mxbai-embed-large` over `nomic-embed-text` (768-dim).
3. Where the user runs MiroFish in Docker, the docker-compose comments or
   README shall note that Ollama on the host is reached from the
   `mirofish` container via `host.docker.internal:11434`.
4. The documentation shall include a one-line `curl` example that calls
   `$EMBEDDING_BASE_URL/embeddings` with the configured model and confirms
   the response embedding length is 1024.
5. When the operator follows the documented Ollama configuration with
   `mxbai-embed-large` pulled in Ollama, the existing graph-build pipeline
   shall complete end-to-end and write real nodes and edges to Neo4j with
   no code changes beyond the env-var configuration.

### Requirement 2: Loud Embedding Failure
**Objective:** As a MiroFish operator, I want embedding failures during
graph build to surface as a visible task failure with the underlying
error, so that I can fix my embedder configuration instead of seeing an
"empty graph" with no diagnostic.

#### Acceptance Criteria
1. The `_GraphNamespace.add_batch` method shall not return a placeholder
   `_EpisodeResult` UUID when the underlying `add_episode` call raises an
   exception.
2. If `add_episode` raises any exception other than a narrowly defined set
   of transient network errors, then `_GraphNamespace.add_batch` shall
   propagate the exception to its caller.
3. When `_GraphNamespace.add_batch` propagates an exception, the
   surrounding graph-build background `Task` shall transition to
   `FAILED` with `Task.error` containing a non-empty message derived from
   the underlying exception (per the existing
   `.kiro/steering/error-handling.md` contract).
4. While a graph-build task is failing because of a misconfigured
   `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, or `EMBEDDING_API_KEY`, the
   adapter shall log the underlying `add_episode` error at `ERROR` level
   (not `WARNING`) before raising, so the root cause is visible in
   server logs.
5. Where the configured `EMBEDDING_MODEL` is invalid (e.g. a typo, or a
   model not pulled in Ollama), the user-facing project state shall move
   out of `GRAPH_BUILDING` and the task shall surface the underlying
   embedder error to the frontend without producing a placeholder-UUID
   "successful" episode.
6. The `_GraphNamespace.add_batch` method shall preserve its current
   contract for successful episodes: each successfully ingested episode
   shall still produce one `_EpisodeResult` whose `uuid_` matches the
   Graphiti-assigned episode UUID, in input order.

### Requirement 3: Backwards Compatibility
**Objective:** As an existing MiroFish operator already running with an
OpenAI- or Gemini-compatible embedder, I want this change to be invisible
on the happy path, so that no upgrade action is required.

#### Acceptance Criteria
1. Where `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, and `EMBEDDING_MODEL`
   are unset or set to OpenAI/Gemini-compatible values, the embedder
   construction in `_build_llm_and_embedder` shall behave identically to
   the current implementation.
2. The graph-build pipeline shall not require any new environment
   variable to function; Ollama support shall be enabled purely by
   setting the three existing `EMBEDDING_*` variables.
3. While Graphiti's default `EMBEDDING_DIM` is 1024, the documentation
   shall explicitly note that any embedder model with a different output
   dimension is unsupported by this change and is an explicit follow-up
   item.
