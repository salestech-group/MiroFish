# Research & Design Decisions — zep-remnants-removal

## Summary

- **Feature**: `zep-remnants-removal`
- **Discovery Scope**: Extension (refactor of existing codebase; zero functional change)
- **Key Findings**:
  - Zero live Zep SDK imports remain in Python source. The legacy `zep-cloud==3.13.0` pin in `backend/requirements.txt` is unused and safe to drop.
  - Locale-key footprint is ~135 keys across `en.json` and `zh.json`, larger and structurally different from ticket #47's table. Several key paths in the ticket are wrong (`text.*` vs. `api.*`; `log.*` vs. `progress.*`). Three namespaces and one top-level namespace were missing from the ticket: `log.zep_entity_reader.*`, `log.zep_graph_memory_updater.*`, top-level `zep_graph_memory_updater.*`, and `console.zep*` keys.
  - Steering documentation under `.kiro/steering/` references `zep_*` filenames in four places (`structure.md`, `tech.md`, `database.md`, `api-standards.md`) and must be updated in lock-step with the file rename.

## Research Log

### Live Zep SDK usage
- **Context**: Confirm whether Zep removal is mechanical or whether real code paths depend on the SDK.
- **Sources Consulted**: `rg 'import zep|from zep' --type py`, `rg 'zep_cloud'` across the repo.
- **Findings**:
  - Zero runtime imports of any `zep` Python module.
  - The only `zep_cloud` reference in Python source is at `backend/app/services/ontology_generator.py:414`, inside `generate_python_code()` — a method with zero callers (confirmed via `rg 'generate_python_code\('`). The string is unreachable at runtime.
  - `backend/app/services/graphiti_adapter.py` module docstring presents itself as a "drop-in replacement" for `from zep_cloud.client import Zep`.
- **Implications**: Removal is a pure rename + dead-code-pruning task. No migration shim or compatibility layer is required.

### Locale-key inventory
- **Context**: Ticket #47 listed ~50 zep-tagged locale keys; design needs the actual list to plan the rename.
- **Sources Consulted**: `rg '[Zz]ep' locales/en.json`, `rg '[Zz]ep' locales/zh.json`, structural grep of top-level keys.
- **Findings** (en.json, verified line numbers):
  - `step.graphBuildDescription` (107), `step.graphRagDesc` (157) — values mention "Zep API"/"Zep" but keys are clean.
  - `api.zepApiKeyMissing` (407) — *not* `text.zepApiKeyMissing` as ticket claimed.
  - `progress.creatingZepGraph` (553), `progress.waitingZepProcess` (556), `progress.zepProcessing` (571), `progress.connectingZepGraph` (576), `progress.zepSearchQuery` (602) — under `progress.*`, not `log.*` as ticket claimed.
  - `log.zepEntitiesFound` (653) — correct under `log.*` per ticket.
  - `log.zep_tools.*` (728) — namespace with ~52 mXXX keys.
  - `log.zep_graph_memory_updater.*` (866) — namespace with ~16 mXXX keys (missing from ticket).
  - `log.zep_entity_reader.*` (882) — namespace with ~11 mXXX keys (missing from ticket).
  - `console.zepToolsInitialized` (1061), `console.zepRetryAttempt` (1062), `console.zepAllRetriesFailed` (1063), `console.zepSearchApiFallback` (1067) — missing from ticket.
  - Top-level `zep_graph_memory_updater.*` (1136–1184) — action/platform message-fragment keys (~50). Missing from ticket.
- **Implications**: Requirement 3 in `requirements.md` was rewritten to reflect the corrected topology before design.

### Locale-key callers
- **Context**: Determine which Python/Vue files reference each zep-tagged locale key so the rename touches every caller.
- **Sources Consulted**: `rg "t\('log\.zep" --type py --type vue`, `rg "progress.zep"`, etc.
- **Findings**:
  - `backend/app/services/zep_tools.py` — 51 `t("log.zep_tools.mXXX", …)` calls (lines 423–1727).
  - `backend/app/services/zep_entity_reader.py` — 10 `t("log.zep_entity_reader.mXXX", …)` calls.
  - `backend/app/services/zep_graph_memory_updater.py` — 14 `t("log.zep_graph_memory_updater.mXXX", …)` calls plus references to the top-level `zep_graph_memory_updater.action.*` and `zep_graph_memory_updater.platform.*` keys.
  - `backend/app/services/graph_builder.py:372` — `t('progress.zepProcessing', …)`.
  - `backend/app/services/oasis_profile_generator.py:303` — `t('progress.zepSearchQuery', …)`.
  - `frontend/src/components/Step2EnvSetup.vue:817` — `t('log.zepEntitiesFound', …)`.
  - `console.zep*` keys: no caller surfaced in initial grep — likely dead, candidates for deletion (verify before delete).
- **Implications**: All callers are well-localised. A single Phase-2 commit can rename keys and callers atomically.

### Symbol-level zep references inside non-zep modules
- **Context**: Find symbol names (method/local-variable) that should be renamed for naming consistency even though they aren't in the file-rename table.
- **Sources Consulted**: `rg '_search_zep|zep_results' backend/`.
- **Findings**:
  - `backend/app/services/oasis_profile_generator.py:272` — `def _search_zep_for_entity(self, entity: …)` — internal helper.
  - Same file lines 458, 460, 462, 466, 467 — local variable `zep_results`.
- **Implications**: Add to Requirement 2 (acceptance criterion 8). Internal-only refactor, no external API impact.

### Steering and documentation
- **Context**: Audit `.md` files for Zep references that document the current stack.
- **Sources Consulted**: `rg '[Zz]ep' --type md` filtered to non-spec/non-ticket files.
- **Findings**:
  - `CLAUDE.md` lines 55, 104, 117, 119.
  - `README.md:232`, `README-EN.md:178` (migration notice paragraph).
  - `README-ZH.md` — excluded by ticket scope.
  - `.kiro/steering/structure.md` lines 36, 38, 52, 161, 163.
  - `.kiro/steering/tech.md` lines 124–127.
  - `.kiro/steering/database.md` lines 17, 19, 100.
  - `.kiro/steering/api-standards.md:130`.
  - `.claude/onboarding/step1_codebase/02_conventions.md` and `03_readme_decisions.md` — found via grep.
- **Implications**: Phase 3 must cover steering and onboarding docs, not just CLAUDE.md and README.

### Tooling references
- **Context**: Find scripts that hard-code `zep_*.py` filenames.
- **Sources Consulted**: `rg 'zep_(tools|entity_reader|graph_memory_updater|paging)\.py' --type py`.
- **Findings**:
  - `scripts/check_i18n_logs.py` lines 41, 45, 48 — SOURCE_FILES list.
  - `frontend/src/components/Step4Report.vue` lines 545–610 — 24 comment-only references to `zep_tools.py:LINE`. Line numbers are stale; the safest fix is to swap filename to `graph_retrieval_tools.py` and drop precise line numbers.
- **Implications**: One Python script + one Vue component require minor non-import edits.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A: Single-PR mechanical refactor (3 commits: Phase 1 → 2 → 3) | One feature branch; atomic per-phase commits; no shims. | Atomic revert; matches project's "squash-merge feature branches" workflow; satisfies acceptance criterion 2 (zero `zep` hits). | Diff is large (~50 files) and harder to review piecemeal. | Aligns with steering's prohibition on "transitional shims" for cleanup work. **Selected.** |
| B: Backwards-compat shim period | Keep old module names as re-export modules pointing at the new ones. | Zero broken-import risk during transition. | Defeats acceptance criterion 2 (`rg -ni 'zep' .` → zero hits cannot pass with shim files). Adds future cleanup debt. | Rejected. |
| C: Multi-PR phased rollout (Phase 1, 2, 3 each separate PR) | Land each phase in its own PR. | Smaller reviews per PR. | Phases 1 and 3 are tiny (~30 min each); the cost of three separate PRs is not justified. Conflicts with #46 sequencing constraint (#47 must land before #46 Gap 1). | Rejected. |

## Design Decisions

### Decision: New file/class names
- **Context**: The four `zep_*` files need names that describe their post-Graphiti role.
- **Alternatives Considered**:
  1. `graph_*` short prefix — concise.
  2. `graphiti_*` prefix — exact-technology marker but couples filename to the library name (anti-pattern: if Graphiti is ever replaced, files must rename again).
  3. Domain-named (no prefix, e.g. `entity_reader.py`) — cleanest but loses the grouping cue that says "all graph-backed operations".
- **Selected Approach**: `graph_*` prefix per ticket's proposal.
  - `zep_tools.py` → `graph_retrieval_tools.py` (the file does retrieval/search; the simpler `graph_tools.py` was ambiguous because `graph_builder.py` already exists).
  - `zep_entity_reader.py` → `graph_entity_reader.py`.
  - `zep_graph_memory_updater.py` → `graph_memory_updater.py` (drop the redundant duplicated word).
  - `zep_paging.py` → `graph_paging.py`.
  - Locale namespaces follow: `log.zep_tools.*` → `log.graph_retrieval_tools.*`; others mirror their file names.
- **Rationale**: Matches existing `graph_builder.py` / `GraphitiAdapter` naming convention; describes role, not implementation library.
- **Trade-offs**: `GraphToolsService` (a class name shorter than `GraphRetrievalToolsService`) creates a slight asymmetry with its module name `graph_retrieval_tools.py`. Accepted because the ticket already specifies the shorter class name and consumers (`report_agent.py`, `api/report.py`) reference the class far more often than the module.
- **Follow-up**: Confirm `_recover_stuck_projects` in `app/__init__.py` does not import any `zep_*` directly; if it does, update.

### Decision: Locale-key naming asymmetry
- **Context**: Locale namespace `log.zep_tools.*` could become `log.graph_tools.*` (per ticket) or `log.graph_retrieval_tools.*` (matching the new file name).
- **Alternatives Considered**:
  1. `log.graph_tools.*` — matches the class name `GraphToolsService`.
  2. `log.graph_retrieval_tools.*` — matches the file name `graph_retrieval_tools.py`.
- **Selected Approach**: `log.graph_retrieval_tools.*`.
- **Rationale**: The `scripts/check_i18n_logs.py` log-coverage check pairs locale namespaces with the **filename** of the module that emits them. Aligning the namespace to the file name keeps that pairing intuitive.
- **Trade-offs**: Slight verbosity in log-key lookups; offset by clearer module-to-key mapping.
- **Follow-up**: Update Requirement 3 acceptance criterion 2 (already aligned to `log.graph_retrieval_tools.*`).

### Decision: `console.zep*` and `api.zepApiKeyMissing` — delete vs. rename
- **Context**: These keys appear in the locale files but no callers were surfaced by grep.
- **Alternatives Considered**:
  1. Delete unconditionally.
  2. Rename to `console.graph*` / `api.graphApiKeyMissing` to preserve future-proofing.
- **Selected Approach**: Delete after a final verification grep at implementation time. If any caller is found, rename instead.
- **Rationale**: Removing unused keys avoids dead translations and keeps `i18n-locale-parity-guard` clean.
- **Trade-offs**: Slight risk that a caller is added later and references a no-longer-existing key. Mitigated because the project's CI guard catches missing-key lookups.
- **Follow-up**: Implementer runs `rg "console\.zep" "api\.zepApiKey"` over `.vue`, `.ts`, `.js`, `.py` immediately before deletion.

### Decision: Phase 3 scope — include steering docs
- **Context**: Ticket #47's Phase 3 lists `CLAUDE.md`, `README.md`, `README-EN.md`. Steering docs were missed.
- **Alternatives Considered**:
  1. Defer steering doc updates to a follow-up spec.
  2. Bundle steering doc updates into Phase 3 of this spec.
- **Selected Approach**: Bundle (option 2). Acceptance criterion 7.1 (`rg -ni 'zep' .` → zero hits) cannot pass while steering docs reference `zep_*` filenames.
- **Rationale**: Coupling the steering update to the rename PR keeps the doc and code consistent; deferring would leave steering describing files that no longer exist.
- **Trade-offs**: Slightly larger PR.

## Risks & Mitigations

- **Risk — Locale parity drift**: a renamed key in `en.json` that's missed in `zh.json` (or vice versa) will fail `i18n-locale-parity-guard`. *Mitigation*: rename both files in the same edit pass; run the parity guard before commit.
- **Risk — Missed caller**: a `t('log.zep_tools.mXXX', …)` callsite outside the renamed module fails after the namespace rename. *Mitigation*: post-rename grep `rg "log\.zep|log\.zep_tools\." --type py --type vue` must return zero hits.
- **Risk — `_recover_stuck_projects` failure**: if it imports a `zep_*` module directly the backend won't boot after rename. *Mitigation*: grep `app/__init__.py` for any `zep_*` import as the first implementation step; if found, include in the rename pass.
- **Risk — `.env.example` line cannot be verified directly** (pre-tool guard blocks `.env*` reads). *Mitigation*: implementer asks the developer to confirm the line exists before deletion, or uses a `git diff` review on the final patch.
- **Risk — Coordination with issue #46**: #46's Gap 1 expects the new `log.graph_retrieval_tools.*` namespace. *Mitigation*: ship #47 first (this spec), then #46 picks up.

## References

- Ticket #47: https://github.com/salestech-group/MiroFish/issues/47
- `CLAUDE.md` (project root) — describes Zep as deprecated, lines 55/104/117/119.
- `.kiro/steering/tech.md` — explains the Neo4j+Graphiti replacement and `ZEP_API_KEY` empty-string convention.
- `scripts/check_i18n_logs.py` — i18n log-coverage check that hard-codes `zep_*.py` filenames.
