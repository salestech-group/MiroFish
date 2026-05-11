# Gap Analysis — i18n-locale-parity-guard

## Current State Investigation

### Domain assets

| Asset | Path | Role |
|------|------|------|
| Existing PR-time guard | `scripts/ci/i18n_cjk_guard.py` (393 lines) | Runs (a) zero-CJK-in-`en.json`, (b) per-path CJK ratchet on `backend/app` + `frontend/src`. CLI: `--update-baseline`, `--baseline`, `--repo-root`. Stdlib-only. |
| Workflow | `.github/workflows/i18n-cjk-guard.yml` | `pull_request` trigger; single step `python scripts/ci/i18n_cjk_guard.py`. 1-minute timeout. Python 3.11. |
| Existing tests | `scripts/ci/tests/test_i18n_cjk_guard.py` (358 lines) | `unittest`, stdlib-only. Per-function test classes (`ScanLocaleCjkTests`, `CountPathCjkTests`, `BaselineRoundTripTests`, `RunCheckEndToEndTests`, `UpdateBaselineTests`, `CliSmokeTests`). Synthetic git repos via `tempfile.TemporaryDirectory` + `git init`. |
| Reference parity logic | `.kiro/specs/i18n-e2e-english-verification/audit/scripts/check_parity.py` (128 lines) | Already implements `flatten()` (recursive dotted-key generator) and the EN/ZH symmetric-difference computation. Used only by the manual audit pipeline; not in CI. |
| Locale catalogues | `locales/en.json`, `locales/zh.json` | Two-space-indented JSON, `ensure_ascii=False`. 962 keys per side at HEAD; symmetric difference 0. Multi-level nesting (e.g. `common.confirm`, `step1.upload.title`, `log.api.graph.startBuild`). |
| Prior spec | `.kiro/specs/i18n-ci-guard/{design.md,baseline.txt}` | Documents the CJK-guard's design, format, and "scope ratchets only" rationale. The new check should compose, not replace. |

### Conventions extracted

- **Module layout**: One CLI script per check class; checks compose inside a `run_check(...)` orchestrator that returns 0/1.
- **Output discipline**: Stderr for failures, stdout for success summaries. Each failure line is self-contained (`<file>:<line>: <category>: <key/payload>`). Refresh hints (when applicable) printed once at the end.
- **No-short-circuit composition**: `run_check` evaluates every check before exiting (existing pattern at lines 230, 258, 271 in `i18n_cjk_guard.py`).
- **Stdlib-only, deterministic**: existing module imports only `argparse`, `json`, `os`, `re`, `subprocess`, `sys`, `pathlib`. All sorts use lexicographic order.
- **Test-fixture isolation**: Each test owns a `tempfile.TemporaryDirectory()` and writes its own JSON / source files. Negative-path tests never depend on the live `locales/`.
- **Atomic writes**: `write_baseline` uses tmp-file + `os.replace`; if any new persistence is added, mirror that pattern.
- **JSON line-resolution helper**: `_value_line_number(text_lines, value)` already implements the line-fallback semantics required by R2.2 (returns 1 when value not found). Reusable for parity reporting if we resolve by **key name** rather than by **value**.

### Integration surfaces

- The workflow file invokes the guard exactly once: `python scripts/ci/i18n_cjk_guard.py`. Anything done inside `run_check` is automatically picked up — **no workflow change needed** if we extend the existing script (R3.6).
- `--update-baseline` short-circuits inside `main()` *before* `run_check` is called; the new parity check naturally won't run in that mode (R3.4).
- The audit pipeline at `.kiro/specs/i18n-e2e-english-verification/audit/scripts/check_parity.py` is independent and stays untouched (R6's "spec for prior CI guard" boundary).
- Baseline file format is single-purpose (CJK counts) and does not need to grow to accommodate parity (parity has no baseline — divergence is binary).

## Requirement-to-Asset Map

| # | Requirement | Existing asset(s) | Gap tag | Notes |
|---|-------------|------------------|---------|-------|
| 1.1 | Flatten EN/ZH into dotted keys matching `check_parity.py` | `audit/scripts/check_parity.py:flatten` (reference); existing `_flatten` in guard also flattens but only collects (key, value) pairs into a list | **Constraint** | Two `_flatten` flavours exist. Need ONE canonical function inside the guard module that mirrors `check_parity.py.flatten` (recursive, descends into dicts only, emits leaf scalars). The existing private `_flatten(prefix, value, out)` in the guard is already key-value-emitting and will work; the parity check just consumes its keys. |
| 1.2 | Pass when key sets identical, emit success summary with key count | `success_summary` list in `run_check` | **Missing** | Add a parity success line in the same idiom: `"OK locale-parity: 962 keys per side"`. |
| 1.3 / 1.4 | Fail on en-only or zh-only keys | None — no parity check exists | **Missing** | Compute symmetric difference. |
| 1.5 | Treat dict leaves as non-leaves; treat scalar leaves the same as string leaves for parity | `_flatten` already descends only into dicts and emits any non-dict as a leaf; `scan_locale_cjk` then narrows to strings, but parity should NOT narrow | **Constraint** | Use `_flatten` directly (no narrowing). |
| 2.1 | Print `<file>:<line>: <key>: en-only|zh-only` | `_value_line_number` resolves a value's line; needs adaptation for keys | **Missing** | Search for the JSON key token (e.g. `"missingKey"`) in the source-text lines using a substring scan; reuse the line-1 fallback from `_value_line_number`. |
| 2.2 | Fall back to line 1 when location not found | `_value_line_number` already returns 1 in this case | **Reuse** | |
| 2.3 | Final summary `parity: en-only=<n>, zh-only=<m>` | None | **Missing** | One line, stderr. |
| 2.4 | All parity output to stderr | `print(..., file=sys.stderr)` pattern used everywhere | **Reuse** | |
| 2.5 | Lexicographic sort | Existing patterns use `sorted(...)` | **Reuse** | |
| 3.1 / 3.2 / 3.3 | Compose with existing checks; one exit code | `run_check` already composes (a) and (b) without short-circuit | **Constraint** | Insert (c) at the end of `run_check`, after the per-path block but before the final return. Each check toggles the same `failed` flag. |
| 3.4 | `--update-baseline` does not run parity | `main()` short-circuits to `update_baseline()` and never enters `run_check` | **Reuse** | Untouched. |
| 3.5 | `--baseline` and `--repo-root` semantics unchanged | `_build_parser` and `_detect_repo_root` | **Reuse** | Untouched. |
| 3.6 | Workflow file unchanged | `.github/workflows/i18n-cjk-guard.yml` | **Reuse** | No edit needed. |
| 4.1 | Stdlib-only | Existing module is stdlib-only | **Reuse** | `json` is the only library needed for ZH loading. |
| 4.2 | Sub-second runtime | ~1k keys; flatten + set diff is O(n) | **Constraint** | Trivially holds. |
| 4.3 | Deterministic output | All sorts lexicographic | **Reuse** | |
| 5.1–5.4 | Tests under `scripts/ci/tests/` for success / en-only / zh-only / both / scalar-leaves / no-short-circuit | `test_i18n_cjk_guard.py:RunCheckEndToEndTests` is the integration class | **Missing** | Add either a new `ParityCheckTests` class or extend `RunCheckEndToEndTests`. Reuse `_make_full_repo` style; need a `zh_json` argument or a new helper that writes both locale files. |
| 6.1 | Guard passes on live catalogues at merge target | EN/ZH parity verified manually (962/962, 0 diff) | **Reuse** | Manual run after implementation. |
| 6.2 | Document any blocking divergence in tasks.md | n/a | **Conditional** | Only relevant if 6.1 fails — currently does not. |

### Complexity signal

- **Algorithmic logic** only: load two JSON files, recursive flatten, set diff, sort, format, print. No external integrations, no I/O contention, no perf concerns at the catalogue size.

## Implementation Approach Options

### Option A — Extend `scripts/ci/i18n_cjk_guard.py` *(recommended)*

**What changes**:

- Add private helpers to the existing module:
  - `_flatten_keys(data) -> set[str]` — wrapper over the existing `_flatten` that returns just the dotted-key set.
  - `_locate_key_line(text_lines, dotted_key) -> int` — substring scan for the leaf segment (after the last `.`) wrapped in JSON quotes; returns 1 on miss (mirrors `_value_line_number`'s fallback).
  - `_format_parity_finding(file_rel_path, line_no, dotted_key, side) -> str` — single-line formatter.
- Add a function `run_parity_check(repo_root) -> tuple[bool, list[str], str]` returning `(passed, failure_lines, success_summary_line)`. Callable independently for tests.
- In `run_check`, after the per-path baseline block and before the final return:
  - Call `run_parity_check(repo_root)`.
  - If failed, set `failed = True`, print all failure lines + the `parity: ...` summary to stderr.
  - If passed, append the success line to `success_summary`.
- Add a `ZH_JSON_REL_PATH` constant alongside `EN_JSON_REL_PATH`.

**Compatibility assessment**:

- All existing CLI flags, exit codes, and stdout/stderr patterns preserved.
- No new top-level dependencies. `json` already imported.
- The module grows to ~470 lines, comparable to similar single-purpose CLI scripts in the repo (`oasis_profile_generator.py` is much larger). Single-responsibility is preserved: the responsibility is "PR-time i18n catalogue health," and parity is a sub-instance of that.
- Existing tests continue to pass unmodified (none of the changed functions break their contract).

**Trade-offs**:
- ✅ Zero workflow churn, single CI job, single CLI surface.
- ✅ Reuses `_flatten`, line-resolution fallback, sort/print idioms.
- ✅ All checks fail/pass together — easier to read in CI logs.
- ❌ Module name (`i18n_cjk_guard`) is now slightly misleading: it also enforces parity, not just CJK presence. Mitigated by docstring update.

### Option B — New parallel script `scripts/ci/i18n_locale_parity_guard.py` + new workflow step

**What changes**:

- New script that implements the parity check standalone.
- Either (i) add a second job to `.github/workflows/i18n-cjk-guard.yml`, or (ii) add a new workflow file `i18n-locale-parity-guard.yml`.
- New test file `scripts/ci/tests/test_i18n_locale_parity_guard.py`.

**Compatibility assessment**:

- Both scripts duplicate `_flatten`, line-resolution helper, JSON loader, repo-root detection, argparse boilerplate.
- Two CI runs (or two steps) to read and ack on every PR.

**Trade-offs**:
- ✅ Single-responsibility script per file (matches one literal reading of project conventions).
- ❌ Code duplication ~80 lines.
- ❌ Two CI surfaces; PR review fatigue.
- ❌ Violates the spirit of R3 ("compose with the existing checks") — composing across two scripts requires either `&&` or two-job aggregation.

### Option C — Hybrid: new helper module + extended guard

**What changes**:

- New module `scripts/ci/locale_parity.py` exposing `compute_parity_findings(en_path, zh_path) -> ParityResult`.
- The existing `i18n_cjk_guard.py` imports from it and integrates the call into `run_check`, identical to Option A's runtime behaviour.
- Tests split: `test_locale_parity.py` covers the helper in isolation; `test_i18n_cjk_guard.py` gains one composition test.

**Compatibility assessment**:

- Adds package-style imports inside `scripts/ci/` (currently flat — `scripts/ci/i18n_cjk_guard.py` adds `_GUARD_DIR` to `sys.path` via the test bootstrap, which works for sibling modules without further config).
- No workflow change.

**Trade-offs**:
- ✅ Clean separation, more reusable helper.
- ✅ Possible to import the helper from the audit pipeline later (collapsing the duplicate `check_parity.py`).
- ❌ More files for what is ~80 lines of new logic; over-engineering for current scope.
- ❌ Risks scope creep into "deduplicate `check_parity.py`," which is explicitly out of scope.

## Effort & Risk

- **Effort**: **S** (1–2 days). Existing module patterns are mature; the algorithmic logic is small and proven (`check_parity.py`); test scaffolding is already in place.
- **Risk**: **Low**. Stdlib-only; no external integrations; no shared mutable state; deterministic algorithm; existing CI workflow unchanged; live catalogues already pass.

## Recommendations for Design Phase

### Preferred approach: Option A (extend `scripts/ci/i18n_cjk_guard.py`)

Rationale:

1. The existing module's docstring already says "PR-time guard: fail when locales/en.json contains CJK or when backend/app + frontend/src CJK match counts exceed the committed baseline." Extending it to also fail on locale-key parity is the smallest possible delta that also reads naturally in the codebase.
2. R3 ("composes with the existing CJK and per-path checks; one CLI; no workflow edit") is satisfied trivially.
3. Reuses `_flatten`, line-fallback, sort/print idioms verbatim.
4. The module name remains accurate — "CJK Guard" is the canonical name of the i18n PR-time gate; we'll add a docstring note that parity is the third covered check.

### Key design decisions to settle in `design.md`

- **Function boundary**: should `run_parity_check` live in the same module or in a small helper module? *Suggest: same module, as a private function alongside `count_path_cjk` / `scan_locale_cjk` for symmetry.*
- **Failure line format**: exact string layout (file:line:key:side, ordering of the four pieces, separator characters). *Suggest mirroring `_format_locale_finding` exactly: `f"{file}:{line}: {category}: {key}"` where `category` is `parity-en-only` or `parity-zh-only`.*
- **Test fixture for `RunCheckEndToEndTests`**: extend `_make_full_repo` to accept an optional `zh_json` parameter, or add a sibling helper. *Suggest extending — keeps the integration test in one place and lets the existing tests opt out by passing `zh_json=None` (the helper writes a parity-clean default).*
- **Whether to expose a `--check=parity` selector**: *Out of scope per R3.1 (no short-circuit, all-or-nothing).*

### Research items to carry forward

None. All required information is in the existing repo and the cited reference scripts. No external dependencies, no new tech, no perf research, no security implications.
