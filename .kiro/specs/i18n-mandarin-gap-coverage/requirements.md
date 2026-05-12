# Requirements Document

## Introduction

GitHub issue [#46](../../../.ticket/46.md) is the i18n umbrella tracker that
records the remaining hardcoded Mandarin strings in the MiroFish codebase
once the prior `i18n-*` specs have landed. The audit identified **three
concrete gaps**, **one cross-layer integration risk**, and **one
spec-coverage refinement** that are not yet owned by any other spec.

This specification closes those gaps so that:

- The four backend files in scope no longer carry hardcoded Mandarin
  literals (`zep_tools.py`, `zep_graph_memory_updater.py`, and the four
  backend simulation/test scripts).
- The frontend Step 4 report parser (`Step4Report.vue`) continues to
  extract structured content when the backend emits the English variant
  of the report-facing strings, removing the cross-layer breakage that
  would otherwise occur the moment Gap 1 ships.
- The three prompt-generator specs are confirmed to cover inline
  prompt-builder strings (not only top-level constants), with any
  uncovered strings either added to the appropriate spec's `tasks.md`
  or externalized inline.
- The existing `i18n-e2e-english-verification` spec is extended with a
  cross-layer test gate that fails if the backend's English report
  surface drifts away from `Step4Report.vue`'s extraction patterns.
- The CJK CI guard (`scripts/check_i18n_logs.py` /
  `scripts/ci/tests/test_i18n_cjk_guard.py`) passes for every file
  listed in Gaps 1–3.

This is the closing umbrella spec — once it lands, all backend i18n
externalization work tracked under `.kiro/specs/i18n-*` is complete.

## Boundary Context

- **In scope**:
  - `backend/app/services/zep_tools.py` — all `to_text()` /
    return-string output (Gap 1).
  - `backend/app/services/zep_graph_memory_updater.py` — the 16
    action-description methods (Gap 2).
  - `backend/scripts/run_twitter_simulation.py`,
    `backend/scripts/run_reddit_simulation.py`,
    `backend/scripts/run_parallel_simulation.py`,
    `backend/scripts/test_profile_format.py` — operator-facing
    `print()` and `argparse` strings (Gap 3).
  - `frontend/src/components/Step4Report.vue` — the `REPORT_MARKERS`
    regex map plus the `isError` helper (Gap 4 lock-step partner of
    Gap 1).
  - `.kiro/specs/i18n-oasis-profile-generator-prompts/tasks.md`,
    `.kiro/specs/i18n-ontology-generator-prompts/tasks.md`,
    `.kiro/specs/i18n-simulation-config-generator-prompts/tasks.md` —
    coverage audit only (refinement).
  - `.kiro/specs/i18n-e2e-english-verification/` — extend with the
    cross-layer report-parser test (Gap 5).
  - `locales/en.json` and `locales/zh.json` — new keys for the
    externalized strings.
- **Out of scope**:
  - `/locales/*.json` source files beyond the new keys this spec
    introduces.
  - `README-ZH.md`, CI test fixtures (e.g.,
    `scripts/ci/tests/test_i18n_cjk_guard.py`), per the established
    audit excludes.
  - `backend/app/services/report_agent.py` — covered by
    `i18n-report-agent-prompts`.
  - Files already converted to use the `t()` helper
    (`zep_entity_reader.py`, `simulation_ipc.py`, `llm_client.py`,
    `file_parser.py`, `config.py`, `run.py`).
  - Log-level strings inside `zep_tools.py` already externalized
    under the `log.zep_tools.*` namespace.
- **Adjacent expectations**:
  - The backend `t()` helper in `backend/app/utils/locale.py` is the
    only translation entry point; new code must not bypass it.
  - `Step4Report.vue` reads report text through `REPORT_MARKERS`.
    Backend Gap 1 changes the literal phrases those regex patterns
    expect — so the two sides must ship together (or with an
    integration-test gate that fails closed).
  - The CJK CI guard in `scripts/check_i18n_logs.py` enforces a
    deny-list of Han characters in files it scans; the listed files
    must be added to (or kept in) its scan set.

## Requirements

### Requirement 1: Externalize zep_tools.py report-facing output

**Objective:** As a non-Chinese-speaking operator, I want the
LLM-facing and report-facing strings emitted by `zep_tools.py` to be
rendered in the active locale, so that English-locale Report Agent
sessions produce coherent reports.

#### Acceptance Criteria
1. When the `to_text()` method of `SearchResult`, `InsightForgeResult`,
   `PanoramaResult`, or `InterviewResult` is invoked under the English
   locale, the `zep_tools` module shall return the corresponding
   English locale value via the `t()` helper.
2. When the same `to_text()` method is invoked under the Chinese
   locale, the `zep_tools` module shall return the existing Chinese
   wording unchanged in semantics.
3. The `zep_tools` module shall route every previously hardcoded
   Mandarin literal in `to_text()` / return strings through the `t()`
   helper using keys under a single new namespace
   (`zep_tools.output.*`).
4. If a `t()` lookup misses (key not present in either locale), the
   `t()` helper shall return the key itself unchanged, and the
   `zep_tools` module shall behave as if a non-empty string was
   returned (no exception bubbling up).
5. The `zep_tools` module shall contain zero Han characters in
   non-test code paths as verified by
   `rg -nP '[\p{Han}]' backend/app/services/zep_tools.py`.

### Requirement 2: Externalize zep_graph_memory_updater.py action descriptions

**Objective:** As a non-Chinese-speaking operator, I want simulation
action descriptions written to the knowledge graph to render in the
active locale, so that downstream report text is internally consistent.

#### Acceptance Criteria
1. When the `zep_graph_memory_updater` module renders an action
   description under the English locale, the module shall emit the
   English text resolved via `t()`.
2. While processing one of the 16 documented action types
   (post / like / repost / follow / search / etc.), the
   `zep_graph_memory_updater` module shall use a deterministic key
   under the namespace `zep_graph_memory_updater.action.*` to look
   up the description template.
3. The `zep_graph_memory_updater` module shall preserve every
   interpolated variable (content, target user, query, etc.) in the
   localized template via the `t(..., key=value)` parameter
   substitution mechanism.
4. The `zep_graph_memory_updater` module shall contain zero Han
   characters in non-test code paths as verified by
   `rg -nP '[\p{Han}]' backend/app/services/zep_graph_memory_updater.py`.

### Requirement 3: Externalize backend simulation/test script console output

**Objective:** As a contributor running simulation scripts directly,
I want operator-facing CLI output and argparse descriptions in the
active locale, so that the developer experience is consistent with
the rest of the codebase.

#### Acceptance Criteria
1. When any of `run_twitter_simulation.py`, `run_reddit_simulation.py`,
   `run_parallel_simulation.py`, or `test_profile_format.py` is
   executed, the script shall render every previously hardcoded
   Mandarin `print()` / `argparse` / output string through the `t()`
   helper.
2. While each script initializes, it shall call `set_locale(...)` with
   a locale resolved from the environment (default to `zh` to
   preserve current behavior) before emitting any localized output.
3. The four backend scripts shall use keys under a single new
   namespace (`scripts.<script_name>.*`) so the CJK CI guard and
   future locale-parity checks can scope them.
4. The four backend scripts shall contain zero Han characters in
   their executable code paths as verified by
   `rg -nP '[\p{Han}]'` against each path.
5. If `set_locale()` is unavailable (e.g., the script is run before
   `backend/app/utils/locale.py` is on the import path), the script
   shall fall back to `print()`-ing the key string instead of
   raising.

### Requirement 4: Lock-step coordination of Step4Report.vue report parser

**Objective:** As a frontend user viewing the Step 4 report, I want
the structured-report extraction to keep working after the backend
emits the English variant of the report surface, so that the report
view does not silently break.

#### Acceptance Criteria
1. When the backend emits a report under the English locale, the
   `Step4Report.vue` component shall extract every section that it
   currently extracts under the Chinese locale (analysis query,
   relation chain header, Twitter answer, Reddit answer, prediction
   scenario, related facts, etc.).
2. The `Step4Report.vue` component shall derive its `REPORT_MARKERS`
   regex patterns from a single locale-aware source — either by
   parameterizing the literal portion of each pattern with the
   active locale's translation, or by introducing per-locale pattern
   sets keyed by locale code.
3. When the `Step4Report.vue` component encounters an error line,
   the `isError(line)` helper shall return `true` for both the
   English (`"ERROR"`) and Chinese (`"错误"`) error markers.
4. If a marker is missing from a locale, the `Step4Report.vue`
   component shall fall back to a regex that matches no input
   (rather than `undefined` matching every input) and log a
   developer-facing warning once per missing key.
5. The `Step4Report.vue` component shall contain no hardcoded
   Mandarin pattern outside the locale-aware marker source after
   this spec lands.

### Requirement 5: Cross-layer English-verification test

**Objective:** As a maintainer, I want CI to catch any drift between
the backend's English report surface and the frontend report parser,
so that future i18n work cannot silently break the Step 4 view.

#### Acceptance Criteria
1. The `i18n-e2e-english-verification` spec shall include a test
   (or task that adds a test) that exercises the
   English-locale report surface end-to-end and asserts that every
   `REPORT_MARKERS` pattern matches at least one section of the
   produced report.
2. If a `REPORT_MARKERS` pattern fails to match its corresponding
   backend section under English, the verification test shall fail
   with a message that names the missing marker key.
3. The verification test shall be invokable from the repository
   root as a standalone command (e.g., a `pytest -k` selector or a
   script under `scripts/ci/`) so that it can be wired into CI in a
   later spec without requiring a redesign.
4. The verification test shall not require Neo4j, Graphiti, or
   live LLM access — it shall run against a fixture or mocked
   `to_text()` output captured from the new English locale.

### Requirement 6: Confirm prompt-generator spec coverage of inline strings

**Objective:** As a reviewer, I want the three prompt-generator specs
to either cover their respective inline prompt-builder strings or
explicitly call out any uncovered string for follow-up, so that no
inline prompt fragment is silently left in Chinese.

#### Acceptance Criteria
1. While the `tasks.md` of each of
   `i18n-oasis-profile-generator-prompts`,
   `i18n-ontology-generator-prompts`, and
   `i18n-simulation-config-generator-prompts` is reviewed, the
   reviewer shall record the list of inline prompt-builder strings
   actually covered.
2. If an inline string is found that is not covered by the
   corresponding spec, the reviewer shall append a new task to that
   spec's `tasks.md` referencing the file:line of the uncovered
   string.
3. The audit shall produce a single artefact at
   `.kiro/specs/i18n-mandarin-gap-coverage/prompt-coverage-audit.md`
   listing, per spec, the inline strings found and whether they are
   covered.
4. The audit shall not modify the prompt-generator source files
   themselves — only the spec `tasks.md` files and the audit
   artefact.

### Requirement 7: CJK CI guard passes on all in-scope backend files

**Objective:** As a maintainer, I want the existing CJK CI guard to
mechanically prove that the in-scope backend files are clean of
Han-character literals after the spec lands.

#### Acceptance Criteria
1. While `scripts/check_i18n_logs.py` (or the equivalent CJK CI
   guard) is run against the repository, the guard shall include
   `backend/app/services/zep_tools.py`,
   `backend/app/services/zep_graph_memory_updater.py`,
   `backend/scripts/run_twitter_simulation.py`,
   `backend/scripts/run_reddit_simulation.py`,
   `backend/scripts/run_parallel_simulation.py`, and
   `backend/scripts/test_profile_format.py` in its scan set.
2. When the CJK CI guard is invoked after the spec is implemented,
   the guard shall exit with status `0` and shall not report any
   Han-character literal in those files.
3. If a Han-character literal is reintroduced in any of those files
   in a later change, the CJK CI guard shall fail with a message
   that names the file and line number.
