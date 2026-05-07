# Implementation Tasks — graphiti-ollama-embedder

> Source spec: `.kiro/specs/graphiti-ollama-embedder/`
> Ticket: #18

## Plan

This feature has two narrowly scoped deliverables:

1. **Code change** — remove the silent placeholder-UUID fallback in `_GraphNamespace.add_batch` so embedding failures propagate and the surrounding graph-build `Task` ends in `FAILED`.
2. **Configuration documentation** — describe the existing-but-undocumented Ollama embedder configuration in `.env.example`, `CLAUDE.md`, `README.md`, and `docker-compose.yml`.

The code change is self-contained in one method. The configuration-file edits do not depend on the code change and can run in parallel with each other.

## Tasks

- [x] 1. Make embedding-batch failures loud (adapter fix)
- [x] 1.1 Replace the silent placeholder-UUID fallback in `_GraphNamespace.add_batch` with ERROR-level logging plus exception propagation
  - Open the per-episode `try/except Exception` around the synchronous `add_episode` call in the batch ingestion path of the Graphiti adapter and remove the placeholder-UUID branch entirely.
  - Replace the existing `WARNING`-level log line with a `logger.exception(...)` call that captures the `graph_id` and the index of the failing episode in its message; do not include the episode body, API keys, or full traceback duplication beyond what `logger.exception` emits.
  - Re-raise the original exception so it bubbles up to `GraphBuilderService.add_text_batches` (which already re-raises) and on to `_build_graph_worker` (which already calls `fail_task`).
  - Preserve the happy-path contract: a successful episode still produces exactly one `_EpisodeResult` whose `uuid_` matches the Graphiti-assigned episode UUID, and the returned list keeps input order.
  - Leave the single-episode `add(...)` method untouched (it already raises naturally) and leave `_GraphNamespace.search(...)` untouched (its log-and-return-empty contract is documented in steering and out of scope).
  - Observable completion: when the embedder is misconfigured (e.g. `EMBEDDING_MODEL` set to an unknown model on the configured base URL), starting a graph build through the UI causes the `Task` to transition to `FAILED` with `Task.error` populated by the underlying Graphiti exception message, and the backend log includes an ERROR-level entry from the Graphiti adapter naming the failing `graph_id`.
  - _Requirements: 2.1, 2.2, 2.4, 2.6_
  - _Boundary: graphiti_adapter._GraphNamespace.add_batch_

- [x] 2. Document the Ollama embedder configuration
- [x] 2.1 (P) Add a commented Ollama embedder block to `.env.example`
  - Append three commented environment-variable lines configuring the existing `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, and `EMBEDDING_MODEL` for an Ollama deployment with `mxbai-embed-large`.
  - Include a short comment explaining the prerequisite step (`ollama pull mxbai-embed-large`) and the rationale for `mxbai-embed-large` over `nomic-embed-text` (1024-dim vs 768-dim, must match Graphiti's default `EMBEDDING_DIM`).
  - Use `http://host.docker.internal:11434/v1` as the base URL example so the snippet works from inside the `mirofish` container; mention that host-mode (`npm run dev`) operators can substitute `http://localhost:11434/v1`.
  - Set the example `EMBEDDING_API_KEY` to a non-empty placeholder string (Ollama ignores the value but `OpenAIEmbedderConfig` requires it to be non-empty).
  - Leave the existing OpenAI/Gemini commented examples untouched — the Ollama block is additive.
  - Observable completion: a fresh `cp .env.example .env` followed by uncommenting only the three Ollama lines and pulling the model in Ollama is sufficient to point the existing `openai`-provider Graphiti embedder at the local Ollama daemon.
  - _Requirements: 1.1_
  - _Boundary: .env.example_

- [x] 2.2 (P) Extend the "Required Environment Variables" section in `CLAUDE.md`
  - Update the `EMBEDDING_MODEL` notes to enumerate the three supported embedder configurations: OpenAI (`text-embedding-3-small`), Gemini (`text-embedding-004`), and Ollama (`mxbai-embed-large`).
  - Document the 1024-dim constraint imposed by Graphiti's default `EMBEDDING_DIM` and explicitly note that 768-dim models such as `nomic-embed-text` are unsupported until `EMBEDDING_DIM` is made configurable.
  - Cross-reference `.env.example` for the Ollama-specific `EMBEDDING_BASE_URL`/`EMBEDDING_API_KEY` triple instead of duplicating the values inline.
  - Observable completion: a new contributor reading only `CLAUDE.md` § "Required Environment Variables" can identify all three supported embedder providers and the dim constraint without consulting external sources.
  - _Requirements: 1.2, 3.3_
  - _Boundary: CLAUDE.md_

- [x] 2.3 (P) Add an Ollama section and `curl` smoke test to `README.md`
  - In the "Required Environment Variables" block, add an Ollama example alongside the existing Gemini hint covering `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, and `EMBEDDING_MODEL`.
  - Append a one-line `curl` snippet that POSTs to `$EMBEDDING_BASE_URL/embeddings` with the configured model and a trivial input, then pipes through `jq '.data[0].embedding | length'` to verify a `1024` response — explicitly framed as a pre-build smoke test.
  - Use the same `host.docker.internal:11434` convention as `.env.example` and `docker-compose.yml`, with a short note on the `localhost` substitution for host-mode operators.
  - Keep the existing copy/install steps untouched; this edit is additive within the same `## Configure Environment Variables` (or equivalent) subsection.
  - Observable completion: an operator running the new `curl` snippet against a correctly configured Ollama daemon sees `1024` printed to stdout and can use that as a go/no-go signal before kicking off the graph build.
  - _Requirements: 1.3, 1.4_
  - _Boundary: README.md_

- [x] 2.4 (P) Add a `host.docker.internal` comment to the `mirofish` service in `docker-compose.yml`
  - Add a single comment line above (or alongside) the existing `NEO4J_URI` override in the `mirofish` service noting that an Ollama daemon running on the host is reachable from this container via `host.docker.internal:11434` and that this is the value to use for `EMBEDDING_BASE_URL` when running the Compose stack.
  - Do not introduce any new service, environment variable, or volume; the change is comment-only.
  - Observable completion: a reader of `docker-compose.yml` who sets up Ollama on the host can derive the correct `EMBEDDING_BASE_URL` value without consulting external Docker networking documentation.
  - _Requirements: 1.3_
  - _Boundary: docker-compose.yml_

- [ ] 3. Manual end-to-end verification (deferred to reviewer — requires running Neo4j + LLM stack)
- [ ] 3.1 Verify the happy and failure paths through the graph-build pipeline (deferred to reviewer)
  - Run `npm run dev` against the existing OpenAI/Qwen-style embedder configuration to confirm the graph-build flow still completes with real nodes/edges in Neo4j (regression check for R3.1).
  - Set `EMBEDDING_MODEL` to a deliberately invalid value (e.g. `text-embedding-3-small-typo`) against the same base URL, trigger a graph build through the UI, and confirm the project exits `GRAPH_BUILDING`, the backing `Task` reaches `status = FAILED`, and `Task.error` carries the underlying 404/unknown-model message (R2.3, R2.5). Inspect the backend logs for the new ERROR-level entry from the Graphiti adapter (R2.4).
  - If an Ollama daemon with `mxbai-embed-large` is available, follow the documented `.env.example` snippet plus the `curl` smoke test, then run a full graph build and confirm Neo4j has nodes/edges scoped to the project's `group_id` (R1.5).
  - Note in the PR body that, on a partial-batch failure, episodes successfully written before the failure remain committed in Neo4j (post-condition documented in design.md); a re-run appends rather than overwrites because Graphiti episode UUIDs are unique.
  - Observable completion: PR description records the three scenarios (OpenAI happy path, deliberate-typo failure path, optional Ollama happy path) with the resulting `Task` status, an excerpt of `Task.error` for the failure case, and a link to (or extract from) the ERROR-level adapter log.
  - _Depends: 1.1, 2.1, 2.2, 2.3, 2.4_
  - _Requirements: 1.5, 2.3, 2.4, 2.5, 3.1, 3.2_
  - _Boundary: end-to-end pipeline (verification only, no code change)_

## Requirements Coverage

| Requirement | Tasks |
|-------------|-------|
| 1.1 | 2.1 |
| 1.2 | 2.2 |
| 1.3 | 2.3, 2.4 |
| 1.4 | 2.3 |
| 1.5 | 3.1 |
| 2.1 | 1.1 |
| 2.2 | 1.1 |
| 2.3 | 3.1 (verification — already implemented in `_build_graph_worker`) |
| 2.4 | 1.1, 3.1 |
| 2.5 | 3.1 (verification — already implemented in frontend task polling) |
| 2.6 | 1.1 |
| 3.1 | 3.1 |
| 3.2 | 3.1 |
| 3.3 | 2.2 |
