# Requirements Document

## Introduction

The MiroFish codebase carries legacy "Zep Cloud" naming artefacts from a prior memory backend, even though all runtime functionality now relies on Neo4j + Graphiti. Per audit in ticket #47, there are zero live Zep SDK imports — the remnants are a dependency pin, four `zep_*`-prefixed source files, ~15 import call sites, ~50 locale keys (including the `log.zep_tools.*` namespace), a deprecated `ZEP_API_KEY` config, dead code, and documentation references. This spec defines the cleanup so the codebase no longer mentions "Zep" (outside `README-ZH.md` and historical commit/changelog references) and all five pipeline steps continue to work unchanged.

## Boundary Context

- **In scope**:
  - Renaming the four `zep_*` Python files and their public classes to `graph_*` / `Graph*` equivalents.
  - Updating all backend and tooling import sites for the renamed modules and classes.
  - Renaming locale keys (`text.zepApiKeyMissing`, `text.zepSearchQuery`, `log.creatingZepGraph`, `log.waitingZepProcess`, `log.zepProcessing`, `log.connectingZepGraph`, `log.zepEntitiesFound`, and the entire `log.zep_tools.*` namespace) in `locales/en.json` and `locales/zh.json` and every caller.
  - Removing the `zep-cloud==3.13.0` dependency pin, the `ZEP_API_KEY` config slot, and `.env.example` line.
  - Deleting the dead `generate_python_code()` method in `ontology_generator.py`.
  - Rewriting "Zep"-mentioning values in `step.graphBuildDescription` and `step.graphRagDesc` locale entries.
  - Updating `CLAUDE.md`, `README.md`, `README-EN.md`, `scripts/check_i18n_logs.py` paths, and `Step4Report.vue` comment line references.
- **Out of scope**:
  - Functional changes to graph retrieval, memory updates, or simulation behaviour.
  - Touching `README-ZH.md`'s historical Chinese content.
  - Reworking the `log.graph_tools.*` namespace semantics (only the key prefix changes).
  - Coordinating downstream changes for issue #46 (#47 must land first so #46 can adopt the new namespace directly).
- **Adjacent expectations**:
  - `i18n-locale-parity-guard` and `i18n-ci-guard` checks must continue passing after locale key renames (no orphaned/missing keys across `en` vs `zh`).
  - `scripts/check_i18n_logs.py` must still validate that the renamed files have full log externalisation coverage.
  - `_recover_stuck_projects` startup recovery path imports the renamed memory updater module — must boot cleanly.

## Requirements

### Requirement 1: Dependency, Config, and Dead-Code Cleanup (Phase 1)
**Objective:** As a developer maintaining MiroFish, I want all Zep-related dependency pins, config slots, and unreachable dead code removed, so that the project no longer carries unused third-party surface area.

#### Acceptance Criteria

1. When the cleanup is complete, the codebase shall not contain `zep-cloud` in `backend/requirements.txt`.
2. When the cleanup is complete, the codebase shall not declare `ZEP_API_KEY` in `backend/app/config.py` or `.env.example`.
3. When the cleanup is complete, the codebase shall not contain the unreachable `generate_python_code()` method in `backend/app/services/ontology_generator.py`.
4. The `backend/app/services/graphiti_adapter.py` module docstring shall no longer describe itself as a Zep drop-in replacement.
5. If the `api.zepApiKeyMissing` locale key has no remaining caller after Phase 1, then the cleanup shall remove that key from both `locales/en.json` and `locales/zh.json`.
6. When Phase 1 changes are applied, running `npm run dev` (or `npm run backend`) shall start without import errors.

### Requirement 2: File, Class, and Internal-Symbol Renames (Phase 2)
**Objective:** As a developer reading the codebase, I want the four `zep_*` files, their classes, and internal helpers renamed to `graph_*` / `Graph*` names that reflect their actual Graphiti-backed role, so that file, class, and symbol names match runtime behaviour.

#### Acceptance Criteria

1. When the rename phase is complete, the codebase shall contain `backend/app/services/graph_retrieval_tools.py` and shall not contain `backend/app/services/zep_tools.py`.
2. When the rename phase is complete, the codebase shall contain `backend/app/services/graph_entity_reader.py` and shall not contain `backend/app/services/zep_entity_reader.py`.
3. When the rename phase is complete, the codebase shall contain `backend/app/services/graph_memory_updater.py` and shall not contain `backend/app/services/zep_graph_memory_updater.py`.
4. When the rename phase is complete, the codebase shall contain `backend/app/utils/graph_paging.py` and shall not contain `backend/app/utils/zep_paging.py`.
5. The renamed modules shall export the classes `GraphToolsService`, `GraphEntityReader`, `GraphMemoryUpdater`, and `GraphMemoryManager` in place of their `Zep`-prefixed predecessors, and `backend/app/services/__init__.py` `__all__` shall list the new class names.
6. When the rename phase is complete, every importer of the legacy modules (including but not limited to `backend/app/api/{simulation,report,graph}.py`, `backend/app/services/{simulation_manager,simulation_config_generator,oasis_profile_generator,report_agent,simulation_runner,graph_builder,__init__}.py`, and `scripts/check_i18n_logs.py`) shall reference the new module paths and class names.
7. If a renamed module references a sibling renamed module, then the importing module shall use the new path (no transitional shims).
8. When the rename phase is complete, internal helpers and local variables that previously named "zep" shall be renamed to the "graph" equivalent — specifically `_search_zep_for_entity` → `_search_graph_for_entity` and `zep_results` → `graph_results` in `backend/app/services/oasis_profile_generator.py`.

### Requirement 3: Locale Key Migration (Phase 2)
**Objective:** As a user reading log output or UI text, I want locale keys and visible strings to reflect "Graph" / "Graphiti" rather than "Zep", so that the surface text matches the actual backend.

#### Acceptance Criteria

1. When the rename phase is complete, `locales/en.json` and `locales/zh.json` shall not contain any top-level key whose dotted path contains the substring `zep` (case-insensitive).
2. The locale keys shall be renamed as follows, preserving message identifiers within each namespace:
   - `progress.creatingZepGraph` → `progress.creatingGraph`
   - `progress.waitingZepProcess` → `progress.waitingGraphProcess`
   - `progress.zepProcessing` → `progress.graphProcessing`
   - `progress.connectingZepGraph` → `progress.connectingGraph`
   - `progress.zepSearchQuery` → `progress.graphSearchQuery`
   - `log.zepEntitiesFound` → `log.graphEntitiesFound`
   - `log.zep_tools.*` → `log.graph_retrieval_tools.*`
   - `log.zep_entity_reader.*` → `log.graph_entity_reader.*`
   - `log.zep_graph_memory_updater.*` → `log.graph_memory_updater.*`
   - `console.zepToolsInitialized` → `console.graphToolsInitialized` (or DELETE if no caller exists)
   - `console.zepRetryAttempt` → `console.graphRetryAttempt` (or DELETE if no caller exists)
   - `console.zepAllRetriesFailed` → `console.graphAllRetriesFailed` (or DELETE if no caller exists)
   - `console.zepSearchApiFallback` → `console.graphSearchApiFallback` (or DELETE if no caller exists)
   - Top-level `zep_graph_memory_updater.*` namespace (action and platform subkeys, ~50 keys) → top-level `graph_memory_updater.*`
3. When a renamed locale key is referenced by frontend or backend code (including `frontend/src/components/Step2EnvSetup.vue` calling `t('log.zepEntitiesFound', …)`, `backend/app/services/graph_builder.py` calling `t('progress.zepProcessing', …)`, and `backend/app/services/oasis_profile_generator.py` calling `t('progress.zepSearchQuery', …)`), the caller shall be updated to use the new key.
4. When the rename phase is complete, `locales/en.json` and `locales/zh.json` shall not contain any value string mentioning "Zep" — including but not limited to the keys `step.graphBuildDescription`, `step.graphRagDesc`, and every message value inside the renamed `log.graph_retrieval_tools.*`, `log.graph_entity_reader.*`, and `log.graph_memory_updater.*` namespaces.
5. If a locale key is renamed in `en.json`, then the corresponding key in `zh.json` shall be renamed in the same commit so the parity guard (`i18n-locale-parity-guard`) passes with zero orphaned or missing keys.

### Requirement 4: Tooling and Inline Reference Updates (Phase 2)
**Objective:** As a developer running CI checks and reading inline comments, I want tooling and comment references to point at the renamed files, so that automation and code navigation continue to work.

#### Acceptance Criteria

1. When the rename phase is complete, `scripts/check_i18n_logs.py` shall reference the renamed module paths (replacing the three hard-coded `zep_*.py` paths) and shall exit with status 0 on the renamed files.
2. When the rename phase is complete, `frontend/src/components/Step4Report.vue` shall not contain comment references to `zep_tools.py` filenames or its prior line numbers.
3. If any inline comment, docstring, or string literal in the four renamed Python modules previously named the legacy module (e.g., self-reference as "zep_tools"), then the rename phase shall update it to the new module name.

### Requirement 5: Documentation and Steering Cleanup (Phase 3)
**Objective:** As a contributor onboarding to the project, I want the public-facing documentation and persistent steering knowledge to no longer present Zep as a deprecated-but-supported path, so that the recommended stack reads cleanly.

#### Acceptance Criteria

1. When Phase 3 is complete, `CLAUDE.md` shall not contain the Zep deprecation paragraph, the `zep_*` filename-prefix bullet, the `ZEP_API_KEY` env-var line, the "legacy Zep tools" services bullet, or the "Zep pagination" utility bullet.
2. When Phase 3 is complete, `README.md` and `README-EN.md` shall not contain user-facing references to "Zep" outside of historical changelog or commit-message context.
3. The `README-ZH.md` file shall remain unchanged by this spec (Chinese localisation content is out of scope).
4. When Phase 3 is complete, `.kiro/steering/structure.md`, `.kiro/steering/tech.md`, `.kiro/steering/database.md`, and `.kiro/steering/api-standards.md` shall not contain `zep_*` filename references or "Zep Cloud" notes that describe the project's current stack.
5. When Phase 3 is complete, the `.claude/onboarding/step1_codebase/` files shall not contain references that describe Zep as part of the current stack (historical commentary is permitted only with explicit historical framing).

### Requirement 6: Functional Regression Safety
**Objective:** As an operator running MiroFish, I want the 5-step pipeline to behave exactly as before, so that this rename introduces no regression.

#### Acceptance Criteria

1. When the renamed code is loaded, the Flask backend shall start without raising `ImportError`, `ModuleNotFoundError`, or `AttributeError` from the renamed modules or classes.
2. When the rename is complete, the `_recover_stuck_projects` startup recovery path shall load the renamed memory-updater module successfully.
3. While a simulation is running, the renamed `GraphMemoryUpdater` shall stream agent activity into Neo4j with the same behaviour as before the rename.
4. When a report request is dispatched, the renamed `GraphToolsService` shall expose the `SearchResult`, `InsightForge`, `Panorama`, and `Interview` tools to the `ReportAgent` with their previous semantics.
5. If a project's `group_id` filter previously isolated graph access in a `Zep*` module, then the renamed module shall preserve the same `group_id` scoping.

### Requirement 7: Acceptance Verification
**Objective:** As a reviewer of the cleanup PR, I want a deterministic check that the codebase contains no residual `zep` mentions, so that the acceptance criteria of ticket #47 are objectively verifiable.

#### Acceptance Criteria

1. When the verification command `rg -ni 'zep' .` is run from the repository root with the documented exclusion globs (`!README-ZH.md`, `!.git/`, `!node_modules/`, `!.venv/`, project changelog), the result shall contain zero hits outside historical changelog or commit-message references.
2. When `rg 'import zep|from zep' --type py` is run from the repository root, the result shall return zero hits.
3. When `scripts/check_i18n_logs.py` is executed, it shall exit with status 0 for the four renamed files.
4. If the verification command surfaces any hit, then the cleanup is not complete and shall require remediation before the spec is closed.
