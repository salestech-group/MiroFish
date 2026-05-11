# Requirements Document

## Introduction

Epic #11 ("complete english support across ui, agents, logs, and docs") states as acceptance criterion #4: *"For every externalized log message, matching `log.*` keys exist in both `locales/en.json` and `locales/zh.json`."* The wider intent is symmetric: any externalized string introduced into either locale catalogue must have a counterpart in the other, otherwise English users hit fallback keys at runtime (and the inverse for Chinese users).

Parity holds today (962 keys per side, symmetric difference 0), but no automated check enforces it. The existing CI guard at `scripts/ci/i18n_cjk_guard.py` (workflow `.github/workflows/i18n-cjk-guard.yml`, landed via #26) only enforces (1) zero CJK in `locales/en.json` and (2) a per-path CJK count ratchet for `backend/app` + `frontend/src`. The audit script at `.kiro/specs/i18n-e2e-english-verification/audit/scripts/check_parity.py` does compute the symmetric difference, but only as part of a manual audit — it never runs in CI.

This spec extends the existing PR-time CI guard to enforce locale-key parity permanently. Once shipped, any pull request that introduces a key on only one side will fail CI with a precise list of the offending keys, freezing AC #4 in place for the rest of the epic and beyond.

## Boundary Context

- **In scope**:
  - Symmetric-difference check between flattened dotted-key sets of `locales/en.json` and `locales/zh.json`.
  - Integration of the new check into the existing `scripts/ci/i18n_cjk_guard.py` so the existing workflow `.github/workflows/i18n-cjk-guard.yml` exercises it without any workflow edit beyond what's strictly necessary.
  - Test coverage under `scripts/ci/tests/` matching the style of the existing CJK-guard tests.
  - Failure output formatted so a developer can locate the offending key without further tooling.
- **Out of scope**:
  - Translating any remaining hard-coded strings in `backend/app` or `frontend/src` (tracked under open assigned issues #7, #23, #25).
  - Value-equality, identical-value, or "review-needed" heuristics from the audit script's `[identical-values]` block — only key presence is asserted here.
  - Any change to the `locales/` directory layout, schemas, or to `vue-i18n` / `backend/app/utils/locale.py` consumers.
  - Cross-locale value-shape checks (e.g. matching ICU placeholders).
  - README, `.env.example`, or documentation updates beyond what's needed inside the spec / guard module itself.
- **Adjacent expectations**:
  - The existing CJK-clean and per-path-ratchet checks in `scripts/ci/i18n_cjk_guard.py` continue to run unchanged and report independently of the new parity check.
  - The audit pipeline at `.kiro/specs/i18n-e2e-english-verification/audit/scripts/` keeps its own copy of `check_parity.py` for manual deep-dive use; the new CI check does not depend on the audit pipeline being invoked.
  - All four checks (CJK in en.json, per-path ratchet, en-only keys, zh-only keys) run in a single CI job and surface together; no short-circuit between them.

## Requirements

### Requirement 1: Locale-key parity check

**Objective:** As a maintainer of the i18n catalogues, I want a CI check that detects any key present on only one of `locales/en.json` / `locales/zh.json`, so that AC #4 of epic #11 stays satisfied as new strings are added.

#### Acceptance Criteria

1. The i18n CJK Guard shall load `locales/en.json` and `locales/zh.json` and flatten each into a set of dotted keys whose paths exactly match those produced by `flatten()` in `.kiro/specs/i18n-e2e-english-verification/audit/scripts/check_parity.py`.
2. When the flattened EN and ZH key sets are identical, the i18n CJK Guard shall pass the parity check and emit a single success summary line that includes the shared key count.
3. When the flattened EN key set contains any key that is absent from ZH, the i18n CJK Guard shall fail the parity check.
4. When the flattened ZH key set contains any key that is absent from EN, the i18n CJK Guard shall fail the parity check.
5. The i18n CJK Guard shall treat a leaf whose value is a nested object as a non-leaf (no key emitted) and shall treat a leaf whose value is a non-string scalar (number, boolean, null) the same way it treats a string leaf for parity purposes.

### Requirement 2: Actionable failure reporting

**Objective:** As a developer whose PR is failing on parity, I want the failure message to name every offending key and the side it is missing on, so that I can fix the divergence without re-running the audit pipeline.

#### Acceptance Criteria

1. If the parity check fails, then the i18n CJK Guard shall print one line per missing key in the form `<locales/en.json|locales/zh.json>:<line>: <dotted-key>: en-only` or `... zh-only`, with `<line>` being the 1-based line number of that key in the source JSON file.
2. If a missing key cannot be located in its source file (e.g. owing to JSON formatting), then the i18n CJK Guard shall fall back to line 1 and still print the offending key and side.
3. If the parity check fails, then the i18n CJK Guard shall print a final summary line of the form `parity: en-only=<n>, zh-only=<m>` where `<n>` and `<m>` are the counts of en-only and zh-only keys.
4. The i18n CJK Guard shall print all parity-related output to stderr.
5. The i18n CJK Guard shall sort each side's missing-key list lexicographically so that the failure output is deterministic across environments.

### Requirement 3: Integration with the existing guard

**Objective:** As a maintainer extending the CI guard, I want the new parity check to compose with the existing CJK-clean and per-path-ratchet checks rather than replace them, so that all four checks are visible in a single CI run.

#### Acceptance Criteria

1. The i18n CJK Guard shall execute all of (a) the CJK-clean check on `locales/en.json`, (b) the per-path baseline ratchet on `backend/app` and `frontend/src`, and (c) the new parity check on every invocation of `python scripts/ci/i18n_cjk_guard.py` without short-circuiting between checks.
2. When any of (a), (b), or (c) fail, the i18n CJK Guard shall exit with status code 1.
3. When all of (a), (b), and (c) pass, the i18n CJK Guard shall exit with status code 0.
4. The i18n CJK Guard shall continue to support the `--update-baseline` flag with its existing semantics (refresh per-path counts and exit 0); the parity check shall not run in `--update-baseline` mode.
5. The i18n CJK Guard shall continue to support the `--baseline` and `--repo-root` flags with their existing semantics.
6. The existing GitHub Actions workflow `.github/workflows/i18n-cjk-guard.yml` shall continue to invoke the guard via the same single command (`python scripts/ci/i18n_cjk_guard.py`), with no new workflow steps required.

### Requirement 4: Stdlib-only, deterministic, fast

**Objective:** As a CI operator, I want the parity check to run quickly and without new dependencies, so that the existing 1-minute job timeout still holds.

#### Acceptance Criteria

1. The i18n CJK Guard shall implement the parity check using only the Python standard library; no new package shall be added to `pyproject.toml`, `requirements*.txt`, or any other dependency manifest.
2. The i18n CJK Guard shall complete the parity check in well under one second on the current catalogue size (~1000 keys per side) under normal CI conditions.
3. The i18n CJK Guard shall produce identical output for identical inputs across runs (no timestamps, no run IDs, no nondeterministic ordering).

### Requirement 5: Test coverage

**Objective:** As a future contributor modifying the guard, I want automated tests for every parity behaviour, so that regressions in either check or in their composition are caught locally.

#### Acceptance Criteria

1. The repository shall contain unit tests under `scripts/ci/tests/` that cover at minimum: (a) the success path where EN and ZH have identical key sets, (b) an en-only-key failure, (c) a zh-only-key failure, (d) a both-sides-divergent failure, (e) a leaf-value-type-mismatch case (string vs scalar/null) that does NOT count as a parity failure, and (f) the integration case where the parity check runs alongside the existing CJK-clean and per-path-ratchet checks without short-circuiting.
2. The new tests shall use the same testing style and framework already used by the existing tests in `scripts/ci/tests/`.
3. When a new test fixture is required for a JSON file, the fixture shall live under `scripts/ci/tests/` in a self-contained form (no reliance on `locales/` content for negative-path tests).
4. When the test suite is run from the repository root, the i18n CJK Guard test module shall pass without warnings on a clean checkout where `locales/en.json` and `locales/zh.json` have full key parity.

### Requirement 6: Self-test against the live catalogues

**Objective:** As an epic-#11 closer, I want to know the moment this guard ships that it observes the live catalogues as parity-clean, so that the guard's first PR doesn't produce a false alarm.

#### Acceptance Criteria

1. While the live catalogues `locales/en.json` and `locales/zh.json` have a symmetric difference of zero on the merge target branch, the i18n CJK Guard shall pass the parity check on a manual run from the repository root.
2. If the merge target branch is found to have a non-zero symmetric difference at the time this spec is implemented, then the implementer shall (a) document the divergence in the spec's `tasks.md` as a blocking finding and (b) fix the divergence before completing the implementation tasks, rather than weakening the parity check.
