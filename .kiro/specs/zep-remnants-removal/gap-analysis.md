# Gap Analysis — zep-remnants-removal

## Summary

- **Functional risk: Low.** No live Zep SDK imports exist; `zep-cloud` is an unused dependency pin. All four `zep_*` modules already operate against `GraphitiAdapter`.
- **Mechanical scope: Larger than ticket #47 stated.** The locale-key footprint is ~135 keys (not ~50), several key paths are different from the ticket's table (`api.zepApiKeyMissing` vs. `text.*`; `progress.creatingZepGraph` vs. `log.*`), and there are additional namespaces (`log.zep_entity_reader.*`, `log.zep_graph_memory_updater.*`, `console.zep*`, and a top-level `zep_graph_memory_updater.*` action/platform namespace).
- **Hidden surface: Steering docs reference `zep_*` filenames.** `.kiro/steering/{structure,tech,database,api-standards}.md` reference the legacy filenames and need updating in lock-step.
- **Symbol rename beyond classes:** `oasis_profile_generator.py` has `_search_zep_for_entity()` method and `zep_results` local variable — internal, but worth aligning with the new naming.
- **Recommendation: Single-PR, three-commit refactor.** Phase 1 (cleanup) → Phase 2 (rename) → Phase 3 (docs+steering). Use `replace_all` edits aggressively because almost all changes are mechanical. Verify via `rg`, `python -c "import …"`, and `python scripts/check_i18n_logs.py`.

## Requirement-to-Asset Map

### Requirement 1 — Dependency, Config, Dead-Code (Phase 1)

| Sub-item | Asset | Status |
|---|---|---|
| Remove `zep-cloud` pin | `backend/requirements.txt:17` | **Present**, safe |
| Remove `ZEP_API_KEY` | `backend/app/config.py:74` (note: ticket said `:79` — actual is `:74`) | **Present**, safe |
| Remove `.env.example` line | `.env.example` (hook-protected; trust ticket) | Cannot verify directly — pre-tool guard blocks `.env*` reads. **Assumption**: line still exists per ticket. |
| Delete `generate_python_code()` | `backend/app/services/ontology_generator.py:398` | Method exists, **0 callers** confirmed |
| Update `graphiti_adapter.py` docstring | `backend/app/services/graphiti_adapter.py:1–9` | "Drop-in replacement for the Zep Cloud client" + references to `zep_tools`, `zep_entity_reader` |
| Remove `api.zepApiKeyMissing` locale key | `locales/{en,zh}.json` line 407 | Ticket said `text.zepApiKeyMissing` — actual path is `api.zepApiKeyMissing`. **0 callers** in frontend grep. Safe to delete. |

### Requirement 2 — File and Class Renames (Phase 2)

| From | To | Importers Found |
|---|---|---|
| `backend/app/services/zep_tools.py` | `graph_retrieval_tools.py` | 3 (report_agent, api/report ×2) + class-name uses |
| `backend/app/services/zep_entity_reader.py` | `graph_entity_reader.py` | 5 (simulation_manager, simulation_config_generator, oasis_profile_generator, api/simulation, services/__init__) |
| `backend/app/services/zep_graph_memory_updater.py` | `graph_memory_updater.py` | 2 (simulation_runner, services/__init__) |
| `backend/app/utils/zep_paging.py` | `graph_paging.py` | 3 (zep_tools, zep_entity_reader, graph_builder) |

**Class rename map**:
- `ZepToolsService` → `GraphToolsService`
- `ZepEntityReader` → `GraphEntityReader`
- `ZepGraphMemoryUpdater` → `GraphMemoryUpdater`
- `ZepGraphMemoryManager` → `GraphMemoryManager`

**Plus `services/__init__.py` `__all__` list** — 5 entries to update.

### Requirement 3 — Locale Key Migration (Phase 2) — REVISED FROM TICKET

Ticket #47's locale-key table understates the actual footprint. Verified inventory:

| Old key (path verified) | New key (proposed) | Callers |
|---|---|---|
| `api.zepApiKeyMissing` (ticket said `text.*`) | DELETE (no callers) | 0 |
| `progress.creatingZepGraph` (ticket said `log.*`) | `progress.creatingGraph` | TBD via grep |
| `progress.waitingZepProcess` (ticket said `log.*`) | `progress.waitingGraphProcess` | TBD |
| `progress.zepProcessing` (ticket said `log.*`) | `progress.graphProcessing` | `graph_builder.py:372` |
| `progress.connectingZepGraph` (ticket said `log.*`) | `progress.connectingGraph` | TBD |
| `progress.zepSearchQuery` (ticket said `text.*`) | `progress.graphSearchQuery` | `oasis_profile_generator.py:303` |
| `log.zepEntitiesFound` | `log.graphEntitiesFound` | `Step2EnvSetup.vue:817` |
| `log.zep_tools.*` (52 keys, m001–m051) | `log.graph_retrieval_tools.*` | 51 sites in `zep_tools.py` |
| `log.zep_entity_reader.*` (11 keys) **— not in ticket** | `log.graph_entity_reader.*` | inside `zep_entity_reader.py` |
| `log.zep_graph_memory_updater.*` (16 keys) **— not in ticket** | `log.graph_memory_updater.*` | inside `zep_graph_memory_updater.py` |
| `console.zepToolsInitialized` **— not in ticket** | `console.graphToolsInitialized` (or DELETE if no caller) | TBD |
| `console.zepRetryAttempt` **— not in ticket** | `console.graphRetryAttempt` | TBD |
| `console.zepAllRetriesFailed` **— not in ticket** | `console.graphAllRetriesFailed` | TBD |
| `console.zepSearchApiFallback` **— not in ticket** | `console.graphSearchApiFallback` | TBD |
| Top-level `zep_graph_memory_updater.*` (50 action/platform keys) **— not in ticket** | Top-level `graph_memory_updater.*` | inside `zep_graph_memory_updater.py` action-formatting code |

Also need value-text fixes (no key change, just string content):
- `step.graphBuildDescription` (line 107) — value mentions "Zep API"
- `step.graphRagDesc` (line 157) — value mentions "Zep"
- Every message value inside `log.zep_*.mXXX` that contains the literal word "Zep" or "ZepToolsService" or "ZepGraphMemoryUpdater" — these are user/operator-facing log strings and should read "Graphiti" / "Graph" instead.

**Parity guard**: `zh.json` carries 38 occurrences of `Zep`/`zep` substring — same key structure must be renamed in parallel.

### Requirement 4 — Tooling & Inline References (Phase 2)

- `scripts/check_i18n_logs.py:41, 45, 48` — three hard-coded `zep_*.py` paths.
- `frontend/src/components/Step4Report.vue:545, 551, 553, 555, 557, 559, 561, 563, 565, 567, 569, 571, 578, 580, 582, 584, 586, 588, 590, 592, 600, 604, 607, 610` — 24 comment references to `zep_tools.py:LINE`. The LINE numbers are stale anyway (file mutated since); safest fix is to rename the file mention to `graph_retrieval_tools.py` and drop precise line numbers, leaving section headers.
- Self-references inside `zep_tools.py` docstring/comments — update after rename.

### Requirement 5 — Documentation Cleanup (Phase 3)

- `CLAUDE.md:55, 104, 117, 119` — Zep deprecation paragraph, `ZEP_API_KEY` env var line, "legacy Zep tools" bullet, "Zep pagination" bullet.
- `README.md:232` — migration notice paragraph mentioning "Zep Cloud".
- `README-EN.md:178` — same migration notice paragraph.
- `README-ZH.md` — **excluded by spec** (Chinese localisation, out of scope).
- `.kiro/steering/structure.md:36, 38, 52, 161, 163` — "legacy filename" notes.
- `.kiro/steering/tech.md:124–127` — Zep-Cloud-replaces note + `ZEP_API_KEY` mention.
- `.kiro/steering/database.md:17, 19, 100` — adapter shape note + `zep_paging.py` reference.
- `.kiro/steering/api-standards.md:130` — `zep_paging.py` reference.
- `.claude/onboarding/step1_codebase/02_conventions.md` and `03_readme_decisions.md` — Zep mentions found (but onboarding docs are low-priority; trim or update).

### Requirement 6 — Functional Regression Safety

- `_recover_stuck_projects` (in `app/__init__.py`) — verify it doesn't import any `zep_*` directly. If it does, update.
- `report_agent.py`, `simulation_runner.py`, `simulation_manager.py`, `api/simulation.py`, `api/report.py`, `oasis_profile_generator.py`, `simulation_config_generator.py`, `graph_builder.py` — all importers; smoke-test by import after rename.
- Variable rename **internal-only** but worth doing for consistency: `oasis_profile_generator.py` `_search_zep_for_entity` → `_search_graph_for_entity`, `zep_results` → `graph_results`.

### Requirement 7 — Acceptance Verification

- `rg -ni 'zep' .` with documented exclusions.
- `rg 'import zep|from zep' --type py` should already pass.
- `python scripts/check_i18n_logs.py` should exit 0 after the SOURCE_FILES list is updated.

## Implementation Approach Options

### Option A — Single-PR Mechanical Refactor (Recommended)

One feature branch, three commits, no transitional shims.

- **Commit 1 (Phase 1):** drop `zep-cloud` pin; remove `ZEP_API_KEY` from `config.py` and `.env.example`; delete dead `generate_python_code()`; rewrite `graphiti_adapter.py` module docstring; delete `api.zepApiKeyMissing` from both locale files (assumed zero callers; verified before deletion).
- **Commit 2 (Phase 2):** `git mv` four files; rename classes via `Edit replace_all`; update all import sites; rename locale keys in both `en.json` / `zh.json` with parity preserved; update every caller (`t(...)` invocations) using `replace_all`; rewrite log/value strings containing "Zep" → "Graphiti"/"Graph" inside message values where they appear; rename `_search_zep_for_entity` and `zep_results`; update `scripts/check_i18n_logs.py` SOURCE_FILES list; update `Step4Report.vue` comment refs.
- **Commit 3 (Phase 3):** update `CLAUDE.md`, `README.md`, `README-EN.md`, `.kiro/steering/*`, `.claude/onboarding/*`.

**Trade-offs**:
- ✅ Atomic — easy to revert if something breaks.
- ✅ Matches established project conventions (mechanical refactors land as one PR).
- ✅ No dual-name period reduces import confusion.
- ❌ Big diff — ~50 file touches expected.

### Option B — Backwards-Compat Shim (Not recommended)

Keep `zep_tools.py` as a re-export module: `from .graph_retrieval_tools import *`. Same for the other three.

**Trade-offs**:
- ✅ Zero risk of broken imports during transition.
- ❌ Defeats the cleanup's purpose: ticket #47's acceptance criterion 2 (`rg -ni 'zep' .` → zero hits) cannot pass with shim files in place.
- ❌ Adds dead code we will later need to remove.

Reject Option B.

### Option C — Phased Across Multiple PRs

Land Phase 1, then Phase 2, then Phase 3 in three PRs.

**Trade-offs**:
- ✅ Smaller individual reviews.
- ❌ Phase 2 is the bulk; Phase 1 and Phase 3 are each <30 min. Splitting buys little.
- ❌ Coordination cost with issue #46 (which expects post-rename naming). Ticket #47 explicitly notes #47 must land "before #46 Gap 1".

Reject Option C — single-PR (Option A) is better aligned with the dev-guidelines workflow ("squash-merge feature branches").

## Effort and Risk

- **Effort: M (3–7 days estimate; realistically 4–6 hours of focused work)**.
  - Phase 1: ~30 min.
  - Phase 2: ~3 h (the locale-key migration dominates; ~135 keys × 2 locale files + 50+ callers).
  - Phase 3: ~30 min.
  - Smoke testing + verification: ~1 h.
- **Risk: Low**.
  - No runtime Zep dependency; pure rename.
  - Risk concentrated in `i18n-locale-parity-guard` and `check_i18n_logs.py` failing if a key is missed in one locale — mitigated by running both scripts before commit.
  - Risk that `.env.example` differs from ticket — mitigated by asking the developer to verify (file is hook-protected).

## Research Needed (carry forward to design)

1. **Existing console-key callers** — `console.zepToolsInitialized` and siblings (lines 1061–1067). Grep frontend for `t('console.zep*` to confirm if any caller exists. If none → delete; if some → rename.
2. **Top-level `zep_graph_memory_updater.*` callers** — lines 1136–1184 contain action/platform message-fragment keys. Grep the backend for `'zep_graph_memory_updater.action.*'` and `'zep_graph_memory_updater.platform.*'` to confirm they're consumed by `zep_graph_memory_updater.py` only. (Expected: yes, that module formats human-readable agent activities.)
3. **`progress.creatingZepGraph`, `progress.waitingZepProcess`, `progress.connectingZepGraph` callers** — verify which Python/Vue files reference these so they get renamed in the same commit.
4. **`.env.example` line confirmation** — ask developer to confirm `ZEP_API_KEY=` line exists; if missing, drop that sub-step.

These are all small, mechanical lookups that the design phase will resolve in line.

## Recommendations for Design Phase

1. Adopt **Option A** (single PR, three commits).
2. **Update Requirement 3** in `requirements.md` to reflect the actual locale-key topology before design (the design will fan out from these key names, so getting the map right matters). Specifically:
   - Replace `text.zepApiKeyMissing` → `api.zepApiKeyMissing` (delete).
   - Replace `log.creatingZepGraph` etc. → `progress.*` paths.
   - Replace `log.zepProcessing` → `progress.zepProcessing`.
   - Add the three additional namespaces (`log.zep_entity_reader.*`, `log.zep_graph_memory_updater.*`, top-level `zep_graph_memory_updater.*`) and the `console.zep*` keys.
3. **Pick concrete new names**:
   - File: `zep_tools.py` → `graph_retrieval_tools.py` (matches its role).
   - Locale namespace: `log.zep_tools.*` → `log.graph_retrieval_tools.*` (lock-step with file).
   - Class: `ZepToolsService` → `GraphRetrievalToolsService` is more accurate but verbose; ticket suggested `GraphToolsService` which is fine. Pick one and stick with it. **Recommendation: `GraphToolsService`** per ticket — shorter, the role is already implied by the file path.
4. **Update internal log-message *values*** that include "Zep" / "ZepToolsService" / "ZepGraphMemoryUpdater" literals, since these are user-visible log output (not just keys). Pattern: replace with "Graphiti" / "GraphToolsService" / "GraphMemoryUpdater".
5. **Add steering-doc updates** (`structure.md`, `tech.md`, `database.md`, `api-standards.md`) explicitly to Requirement 5; currently it only mentions CLAUDE.md and READMEs.
6. **Add `_search_zep_for_entity` / `zep_results` symbol rename** to Requirement 2 acceptance criteria (currently only class-name renames are listed; internal helpers should be in scope).
