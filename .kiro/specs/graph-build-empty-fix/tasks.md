# Implementation Plan

- [x] 1. Foundation: reproduce the empty-graph symptom on `main` defaults
- [x] 1.1 Reproduce the empty-graph failure mode on the pre-fix `main` configuration
  - Stand up a local Neo4j (per `docker compose up neo4j` or an existing host instance) and an unmodified backend on the current `main` branch with the documented default `.env` (LLM via Dashscope/Qwen, no `EMBEDDING_*` overrides).
  - Upload a small representative seed file, kick off a graph build, and observe the worker until it terminates.
  - Capture (a) the resulting `Task` envelope (`status`, `error`), (b) the underlying `mirofish.*` logs (ERROR/WARNING lines from `graphiti_adapter` and `graph_builder`), and (c) the result of `MATCH (n:Entity {group_id: $gid}) RETURN count(n)` in Neo4j.
  - Observable completion: the captured failure-mode notes (Task envelope + log excerpt + node count) are appended under a new "Reproduction Log" section in `.kiro/specs/graph-build-empty-fix/research.md`, identifying which call site surfaces the failure (or which call site silently swallows it).
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 1.2 Reconcile reproduction findings with the design hypothesis
  - Compare the Reproduction Log against the dim-mismatch / Dashscope-can't-serve-OpenAI-embeddings hypothesis recorded in `research.md`.
  - If findings match, mark the hypothesis "confirmed" in `research.md` and proceed to Task 2.
  - If findings diverge (root cause is elsewhere — e.g., a different silent path in graphiti-core or `graphiti_adapter`), append a one-paragraph design revision to `design.md` under "Overview" and add or rescope tasks before proceeding to Task 2.
  - Observable completion: `research.md` has an explicit "confirmed" or "diverged" verdict with one-line rationale; if diverged, `design.md` has the matching revision paragraph dated to the implementation run.
  - _Requirements: 1.2, 1.4_

- [x] 2. Core: flip embedding defaults to local Ollama
- [x] 2.1 (P) Update embedding defaults in backend configuration
  - In `backend/app/config.py`, change the three `EMBEDDING_*` defaults so that, with no `.env` override, the embedder resolves to a local Ollama instance with `mxbai-embed-large`: model `mxbai-embed-large`, base URL `http://localhost:11434/v1`, API key `ollama`.
  - Do not introduce a new env var, rename any existing one, or change `GRAPHITI_LLM_PROVIDER` (which stays `openai`).
  - Observable completion: importing `Config` in a fresh Python shell with an empty `.env` returns the three new default values; setting any of the three in `.env` continues to override them (override semantics unchanged).
  - _Requirements: 2.1, 5.4_
  - _Boundary: Config_

- [x] 2.2 (P) Add `progress.emptyGraphFailure` locale key in English and Chinese
  - Add a new entry under the existing `progress.*` namespace in `locales/en.json` and `locales/zh.json` whose value names the failure (graph build produced 0 entities for the project's `group_id`).
  - Wording must remain readable in both locale switches via `utils.locale.t` and `vue-i18n` without templated arguments (no placeholders).
  - Observable completion: `t('progress.emptyGraphFailure')` resolves to a non-empty, locale-appropriate string under `set_locale('en')` and `set_locale('zh')`.
  - _Requirements: 4.4, 4.5_
  - _Boundary: locales_

- [x] 3. Core: gate graph-build completion on a non-zero entity-node count
- [x] 3.1 Insert non-zero-count gate into the graph-build worker
  - In `backend/app/services/graph_builder.py`, immediately after `_get_graph_info(graph_id)` returns and before `complete_task(...)` is called inside `_build_graph_worker`, branch on `graph_info.node_count == 0`.
  - On zero: log at ERROR level via `mirofish.graph_builder`'s existing logger naming `graph_id`, then call `TaskManager().fail_task(task_id, t('progress.emptyGraphFailure'))` and return without invoking `complete_task`.
  - On non-zero: proceed with the existing `complete_task` path unchanged.
  - Do not weaken or touch the existing `except Exception` branch in the worker — the gate is additional.
  - Observable completion: a graph build whose `add_batch` returned cleanly but produced 0 `(:Entity {group_id})` rows in Neo4j surfaces in the UI as a `FAILED` task with `Task.error == t('progress.emptyGraphFailure')`, and the corresponding ERROR log line is present in the backend logs; `Project.status` no longer rests in `GRAPH_BUILDING` for the affected project.
  - _Requirements: 1.4, 3.3, 4.2, 4.4, 4.5_
  - _Depends: 2.2_

- [x] 4. Core: documentation updates for the new default
- [x] 4.1 (P) Flip the README env block to Ollama-active, OpenAI/Gemini commented
  - In `README.md`, edit the env-block code fence (around the existing embedding section) so the three Ollama lines are uncommented and the OpenAI/Gemini examples become commented-out fallback blocks beneath, with one-line guidance on when to use each.
  - In the surrounding setup prose, list `ollama pull mxbai-embed-large` as a prerequisite alongside Neo4j; keep the existing one-line `curl` smoke test that confirms `embedding length == 1024`.
  - Observable completion: a reader following the README's setup section in order ends up with `EMBEDDING_*` configured for local Ollama (no manual uncomment step) and with the `ollama pull` step queued before the first graph build.
  - _Requirements: 2.2, 6.2, 6.3, 6.4_
  - _Boundary: README.md_

- [x] 4.2 (P) Update CLAUDE.md to reflect Ollama as the default embedder
  - In `CLAUDE.md` "Required Environment Variables", state that the default `EMBEDDING_MODEL` is `mxbai-embed-large` via Ollama at `http://localhost:11434/v1`, demote OpenAI and Gemini to "Other supported configurations", and retain the 1024-dim invariant plus the explicit rejection of 768-dim `nomic-embed-text`.
  - Observable completion: the "Required Environment Variables" block names Ollama as the active default and CLAUDE.md no longer implies that `text-embedding-3-small` is the default.
  - _Requirements: 3.2, 6.1_
  - _Boundary: CLAUDE.md_

- [x] 4.3 (P) Tighten docker-compose.yml comment to point at the active `.env.example` block
  - In `docker-compose.yml`, update the comment at the `mirofish` service (around lines 31-33) so it documents `host.docker.internal:11434` as the way the container reaches the host Ollama daemon, and references the `.env.example` Ollama block as the active default rather than an optional override.
  - Do not change service definitions, networks, or env_file wiring.
  - Observable completion: `docker-compose.yml` reads as documentation that aligns with the new defaults; running `docker compose config` still produces a valid configuration (no syntax regression).
  - _Requirements: 6.3_
  - _Boundary: docker-compose.yml_

- [x] 4.4 Coordinate the `.env.example` diff (hook-protected file)
  - The Claude harness cannot write `.env.example` directly. Produce the exact diff (Ollama block uncommented as active, OpenAI/Gemini blocks present but commented) and record it in `.kiro/specs/graph-build-empty-fix/HANDOFF.md` so the developer can apply it manually before merge.
  - Confirm that the diff matches `Config`'s new defaults from Task 2.1 (model, base URL, key strings) so operator-visible defaults align with `Config` defaults.
  - Observable completion: `HANDOFF.md` contains the literal block to paste into `.env.example`, with a one-line "apply manually before merging" note; the diff is internally consistent with `Config`'s defaults from Task 2.1.
  - _Requirements: 2.2_
  - _Depends: 2.1_

- [x] 5. Validation: end-to-end and backwards compatibility
- [x] 5.1 End-to-end smoke: graph build → profile generation → report agent on the new defaults
  - With a running local Neo4j and a running local Ollama (with `mxbai-embed-large` pulled), run `npm run dev`, create a new project, upload a representative seed file, and exercise the pipeline through Step 4 (Report).
  - Confirm: the graph build `Task` terminates with `status=COMPLETED` and a non-zero `node_count`; the env-setup step produces a non-empty list of OASIS profiles; the report agent's `SearchResult` / `InsightForge` / `Panorama` / `Interview` tool calls return non-empty results.
  - If a representative seed file is not available locally, document this explicitly (no silent skip) and stop after the graph-build verification.
  - Observable completion: a short "Smoke Run" section is appended to `research.md` recording the project's `group_id`, the captured `node_count` / `edge_count`, and a one-line confirmation per downstream step; the PR description summarises this run.
  - _Requirements: 1.5, 2.3, 7.1, 7.2, 7.3, 7.4_
  - _Depends: 3.1, 4.4_

- [x] 5.2 Backwards-compatibility check for explicit OpenAI/Gemini overrides
  - With `.env` containing explicit OpenAI- or Gemini-compatible `EMBEDDING_*` values, restart the backend and confirm that `_build_llm_and_embedder` constructs the same embedder as the pre-change implementation (OpenAI branch when the operator sets OpenAI values; Gemini branch under `GRAPHITI_LLM_PROVIDER=gemini`).
  - Confirm the graph build completes against the override without engaging the new gate's failure path on the happy case.
  - Observable completion: the captured `Task.result.graph_info` shows a non-zero `node_count` under the override; no change in observed behaviour vs. the pre-change implementation for these providers; record outcome in the same `research.md` "Smoke Run" section under a "Backwards-compat" sub-heading.
  - _Requirements: 5.1, 5.2, 5.3_
  - _Depends: 3.1_

- [x] 5.3 Negative-path check: empty-graph gate fires and surfaces in the UI
  - Force the new gate to fire — either by pointing `EMBEDDING_*` at an unreachable Ollama, or by stubbing `_get_graph_info` to return `node_count=0` for one run — and confirm the resulting `Task` envelope.
  - Confirm: `Task.status == FAILED`, `Task.error` is the localised `progress.emptyGraphFailure` string in the active locale, the backend ERROR log entry from Task 3.1 is present, and the surrounding project's `status` moves out of `GRAPH_BUILDING` (not stuck).
  - Observable completion: the captured `Task` envelope and log excerpt are recorded in `research.md` (or the PR description) as the gate's negative-path evidence.
  - _Requirements: 2.4, 4.4, 4.5_
  - _Depends: 3.1_
