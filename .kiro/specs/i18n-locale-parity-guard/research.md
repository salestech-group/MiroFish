# Research & Design Decisions — i18n-locale-parity-guard

## Summary

- **Feature**: `i18n-locale-parity-guard`
- **Discovery Scope**: Extension (extends an existing single-script CI guard)
- **Key Findings**:
  - The existing PR-time guard `scripts/ci/i18n_cjk_guard.py` already implements the no-short-circuit composition pattern, the JSON-flatten primitive, and the line-fallback line-resolution helper that the new parity check needs to reuse.
  - The audit pipeline's `check_parity.py` (in `.kiro/specs/i18n-e2e-english-verification/audit/scripts/`) already proves the algorithm: flatten both catalogues into dotted-key sets and compute their symmetric difference. It runs only in the manual audit path; promoting it to CI is a pure plumbing exercise.
  - The live catalogues at `HEAD` of `main` are parity-clean (962 keys per side, symmetric difference 0), so the new guard's first run will not produce a false alarm and Requirement 6.1 holds out of the gate.

## Research Log

### Composition with the existing guard

- **Context**: Requirement 3 mandates that all checks (CJK-clean, per-path ratchet, parity) run in a single invocation without short-circuit and surface a unified exit code.
- **Sources Consulted**: `scripts/ci/i18n_cjk_guard.py:run_check` (lines 220–299).
- **Findings**: `run_check` uses a `failed: bool` accumulator and a `success_summary: list[str]` collector, evaluating every block before deciding the exit code. The parity check fits trivially as a third block at the end of `run_check`, before the final `if not failed: print(success_summary)` block.
- **Implications**: No structural refactor is needed. The extension is additive.

### Flatten and key resolution semantics

- **Context**: Requirement 1.1 anchors the flatten contract to `check_parity.py.flatten`. Requirement 1.5 specifies that scalar leaves and string leaves are treated identically for parity (only dict leaves are skipped).
- **Sources Consulted**: `.kiro/specs/i18n-e2e-english-verification/audit/scripts/check_parity.py:flatten`; `scripts/ci/i18n_cjk_guard.py:_flatten`.
- **Findings**: The two implementations are byte-equivalent in behaviour: both descend only into `dict`, both yield `(dotted-path, value)` for any non-dict leaf, both build dotted paths with `.` separators. The guard's existing `_flatten` is suitable; the parity check just consumes its keys (set comprehension over the flattened pairs).
- **Implications**: No new flatten function is needed. Requirement 1.1's "exactly match" clause is satisfied by reusing `_flatten`. Add a thin `_flatten_keys(data) -> set[str]` wrapper to keep call sites readable.

### Line resolution for missing keys

- **Context**: Requirement 2.1 demands `<file>:<line>: <key>: <side>` output. Requirement 2.2 demands a line-1 fallback when location is unknown.
- **Sources Consulted**: `scripts/ci/i18n_cjk_guard.py:_value_line_number` (lines 70–87).
- **Findings**: `_value_line_number` resolves a value's line by substring scan with two candidates (raw + JSON-escaped), falling back to line 1. For parity we must resolve a key, not a value. The minimal adaptation is a `_locate_key_line(text_lines, dotted_key)` that searches for the leaf segment of the dotted key wrapped in JSON quotes (e.g. `"missingKey"`). Falling back to line 1 mirrors `_value_line_number`'s contract.
- **Implications**: A small new helper is needed; it follows the same code idiom as `_value_line_number`. Edge cases: leaf segments that appear elsewhere in the file (other keys, value text) — accepting a coarse first-match is acceptable because the *primary* signal (the dotted key + side) is unambiguous; the line number is a navigation aid.

### Stdlib-only enforcement

- **Context**: Requirement 4.1 prohibits new dependencies.
- **Sources Consulted**: `pyproject.toml`, `requirements*.txt` (none at repo root); existing guard imports.
- **Findings**: The existing guard imports `argparse`, `json`, `os`, `re`, `subprocess`, `sys`, `pathlib`. Parity needs none beyond `json` and `pathlib` — both already in use.
- **Implications**: No `pyproject.toml` change. CI runtime image needs no addition.

### Live catalogue parity at HEAD

- **Context**: Requirement 6.1 asserts the guard must pass on the merge target's current state.
- **Sources Consulted**: `locales/en.json`, `locales/zh.json` flattened via stdlib `json.loads` + recursive descent.
- **Findings**: 962 keys per side, symmetric difference 0. Pre-existing `log.*` namespace fully mirrored (373 keys per side).
- **Implications**: No remediation translation work is needed. Requirement 6.2's conditional ("if divergence is found, fix it before completing") does not trigger.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Extend existing guard (Option A — selected) | Add parity helpers + a third block in `run_check` inside `scripts/ci/i18n_cjk_guard.py`; no workflow edit. | Single CI surface; reuses `_flatten`, line-fallback, sort/print idioms; trivially satisfies Requirement 3.6. | Module grows ~80 lines; module name no longer narrowly "CJK" — mitigated by docstring update. | Recommended in `gap-analysis.md`. |
| Parallel script + step (Option B) | New `scripts/ci/i18n_locale_parity_guard.py`; either second job in existing workflow or new workflow file. | Tightest single-responsibility per file. | Code duplication (~80 lines); two CI surfaces; violates the spirit of Requirement 3 ("compose with existing checks"). | Rejected. |
| Helper module + thin import (Option C) | New `scripts/ci/locale_parity.py`; the existing guard imports it and integrates the call. | Cleaner unit-test isolation; possible future de-duplication of audit `check_parity.py`. | Adds package-style imports for ~80 lines of logic; risks scope creep into "deduplicate audit script" (out of scope). | Rejected. |

## Design Decisions

### Decision: Extend `scripts/ci/i18n_cjk_guard.py` rather than create a new script

- **Context**: Requirement 3 mandates a single CLI invocation that runs all i18n CI checks together with no short-circuit and one exit code.
- **Alternatives Considered**:
  1. New parallel script + workflow step — duplicates ~80 lines of plumbing.
  2. New helper module imported by the guard — introduces package structure for trivial logic.
- **Selected Approach**: Add `_flatten_keys`, `_locate_key_line`, `_format_parity_finding`, and `run_parity_check` to the existing module; insert a third block into `run_check` after the per-path baseline block.
- **Rationale**: Smallest delta that fully satisfies Requirement 3; reuses the existing no-short-circuit accumulator pattern verbatim; no workflow edit (Requirement 3.6 holds for free); existing test scaffolding (`unittest`, synthetic git repos) extends naturally.
- **Trade-offs**: The module name (`i18n_cjk_guard`) becomes slightly broader than literal — mitigated by an updated module docstring listing all three checks. Module length grows from ~393 to ~470 lines, still well below the project's de facto threshold for splitting (`oasis_profile_generator.py` exceeds 1000).
- **Follow-up**: Update the module docstring; verify `--help` text and existing CLI smoke test still pass after the change.

### Decision: Treat scalar leaves identically to string leaves for parity

- **Context**: Requirement 1.5 — `_flatten` does not narrow by type; scalars (numbers, booleans, null) at a leaf must register as keys.
- **Alternatives Considered**:
  1. Narrow to string leaves only (mirror `scan_locale_cjk`'s behaviour). Rejected because a numeric or null value on one side is still a string-on-the-other-side parity question, and the `log.*` namespace today is all strings — there's no payoff in narrowing.
  2. Skip dict leaves; emit everything else. Selected.
- **Selected Approach**: `_flatten_keys(data) -> set[str]` returns every dotted path emitted by the existing `_flatten`, regardless of value type.
- **Rationale**: Aligns with the audit script's `flatten` contract (which also does not type-narrow). Catches accidental type drift across catalogues as a side benefit (any divergence at a key surfaces as a missing key).
- **Trade-offs**: None significant — the catalogues today are entirely string-typed at leaves; the choice is mostly future-proofing.
- **Follow-up**: Add a unit test (Requirement 5.1.e) that plants a scalar-typed leaf on both sides at the same path and asserts the parity check passes.

### Decision: Failure category strings — `parity-en-only` / `parity-zh-only`

- **Context**: Requirement 2.1 specifies the format `<file>:<line>: <key>: en-only` (or `... zh-only`). The existing CJK-clean check formats failures as `<file>:<line>: cjk-in-en: <key> = <snippet>`.
- **Alternatives Considered**:
  1. Use bare `en-only` / `zh-only` as the category. Inconsistent with the CJK check's namespaced category (`cjk-in-en`).
  2. Use namespaced categories `parity-en-only` / `parity-zh-only`. Selected.
- **Selected Approach**: Format failure lines as `<en.json|zh.json>:<line>: parity-en-only: <key>` and `... parity-zh-only: <key>` (file is whichever catalogue the missing key would belong to).
- **Rationale**: Mirrors the CJK check's `cjk-in-en` category naming, so a dev grepping CI logs for `parity-` finds all parity failures. The bare-side requirement of 2.1 is satisfied because the side appears verbatim after `parity-` (`parity-en-only` contains `en-only`).
- **Trade-offs**: Minor verbosity vs. consistency — favour consistency.
- **Follow-up**: Tests assert exact substring `parity-en-only` / `parity-zh-only` in failure lines.

## Risks & Mitigations

- **Risk**: A future maintainer renames the existing `_flatten` and the parity check silently breaks. **Mitigation**: A test in the new `ParityCheckTests` class asserts that flattening a known nested fixture produces the expected dotted-key set (locking in the contract).
- **Risk**: The `_locate_key_line` helper produces a misleading line number when the leaf segment also appears in another (unrelated) key or in a value. **Mitigation**: First-match on the JSON-quoted leaf is "good enough" for navigation; the dotted key in the message is the source of truth. Document this in the helper's docstring.
- **Risk**: Future test writers forget the no-short-circuit invariant when extending `run_check`. **Mitigation**: Requirement 5.1.f's composition test guards this — both the parity check and the existing CJK check fail in the same run, and the test asserts both failure lines appear together.

## References

- `scripts/ci/i18n_cjk_guard.py` — existing guard (extension target).
- `.kiro/specs/i18n-e2e-english-verification/audit/scripts/check_parity.py` — reference parity algorithm.
- `.kiro/specs/i18n-ci-guard/design.md` — prior CI guard design (style and boundary precedents).
- `scripts/ci/tests/test_i18n_cjk_guard.py` — existing test patterns (extension target).
- `.github/workflows/i18n-cjk-guard.yml` — workflow that runs the guard (no edit required).
