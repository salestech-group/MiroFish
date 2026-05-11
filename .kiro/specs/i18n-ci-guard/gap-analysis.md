# Gap Analysis — i18n-ci-guard

Comparison of the approved requirements against the current MiroFish
codebase, focused on what already exists, what is missing, and what
options the design phase should choose between.

## 1. Current State Investigation

### Domain assets already in the repo

- **`scripts/check_i18n_logs.py`** — Python-stdlib-only, exit-code-based
  i18n verification script. Uses the same canonical CJK regex
  `[一-鿿]` (`U+4E00..U+9FFF`) the new guard needs, prints findings as
  `<file>:<line>: <reason>: <snippet>`, and was written for ticket #6.
  Strong precedent for the new guard's CLI surface and output format.
- **`scripts/_apply_translations.py`, `scripts/_codemod_i18n.py`,
  `scripts/_merge_locale_keys.py`** — i18n tooling sibling scripts.
  Convention is to keep auxiliary i18n scripts under `scripts/` at the
  repo root.
- **`.github/workflows/docker-image.yml`** — only existing GH Actions
  workflow; triggers on tag pushes and `workflow_dispatch`. No PR-time
  workflow exists yet, so the new guard introduces the project's first
  PR-blocking CI check.
- **PR #27 / branch `chore/i18n-10-e2e-english-verification`** — defines
  the audit methodology referenced by the ticket. Its `audit_cjk.sh`
  uses `git grep -nIP '[\x{4e00}-\x{9fff}]' -- backend/app frontend/src
  locales/en.json` — the canonical scoped scan command. PR #27 is open;
  the new guard must work with or without it merged.
- **`.kiro/specs/<feature>/`** — established home for spec artefacts.
  `i18n-externalize-backend-logs/` is the closest precedent for an
  i18n-flavoured spec.
- **`locales/en.json`, `locales/zh.json`, `locales/languages.json`** —
  shared i18n source consumed by both runtimes.

### Conventions extracted

- Auxiliary scripts: `scripts/<purpose>.py`, Python ≥3.11 stdlib only,
  shebang `#!/usr/bin/env python3`, double-quoted strings, snake_case,
  Google-style docstrings on the module and public functions.
- Output format: `<file>:<line>: <reason>: <snippet>`, summary line
  `OK` or `N issues`, exit `0`/`1`.
- Reuse the canonical regex `[一-鿿]` rather than re-deriving range
  literals.
- 4-space indent, ≤120 cols, no trailing whitespace, single trailing
  newline (`.claude/rules/dev-guidelines.md`).

### Integration surfaces

- **CI**: GitHub Actions, `.github/workflows/`. `ubuntu-latest` runner,
  Python 3.11+ via `actions/setup-python@v5` (use the same version
  pin already present in the docker-image workflow ecosystem if any).
- **Repo layout boundaries** scoped by the audit: `backend/app/`,
  `frontend/src/`, `locales/en.json` — all live at repo root or two
  levels deep.
- **Git working tree**: the guard relies on `git grep -I` for tracked,
  text-only matches; this binds the guard to a runner that has `git`
  available (true on `ubuntu-latest` and on developer machines).

## 2. Requirement-to-Asset Map

| Req | Need                              | Existing asset                                                                                  | Gap         |
| --- | --------------------------------- | ----------------------------------------------------------------------------------------------- | ----------- |
| 1   | CJK scan of `locales/en.json`     | `scripts/check_i18n_logs.py` already loads `locales/*.json` and runs the canonical regex.       | Missing — new guard must scan en.json specifically and emit `key:line` per offender. |
| 2   | CJK count under `backend/app/` and `frontend/src/` against baseline | Audit `audit_cjk.sh` (PR #27) demonstrates `git grep -nIP` is the canonical scan; no baseline file exists yet on main. | Missing — no per-path counter, no baseline file. |
| 3   | Actionable failure messaging      | `check_i18n_logs.py` output format reusable.                                                    | Missing — need refresh-baseline command in failure text. |
| 4   | Baseline file lifecycle           | None.                                                                                            | Missing — file format and refresh subcommand to design. |
| 5   | GH Actions PR integration         | `.github/workflows/` directory exists; one tag-only workflow.                                   | Missing — new `pull_request` workflow. |
| 6   | Local reproducibility             | Existing scripts run locally with stdlib; same pattern reusable.                                | None — covered by following the existing pattern. |

## 3. Implementation Approach Options

### Option A — Extend `scripts/check_i18n_logs.py`

Add a new `--cjk-guard` mode (catalogue scan + per-path baseline diff)
to the existing script, then call it from the new workflow.

- ✅ One file to maintain; reuses the regex constant and CLI.
- ❌ The existing script is tightly scoped to the in-scope backend
  modules and the parity check. Mixing a PR-gating regression check into
  it dilutes its intent and grows it past the SRP line that the
  surrounding scripts respect.
- ❌ The existing script targets a fixed list of backend modules; the
  new guard scans whole subtrees. The two scopes don't fit one CLI.

### Option B — New, focused script `scripts/ci/i18n_cjk_guard.py` + new workflow (recommended)

A new directory `scripts/ci/` holds CI-only scripts; the guard is a
single file that performs both checks and supports a `--refresh-baseline`
flag. New workflow `.github/workflows/i18n-cjk-guard.yml` runs it on
every PR to `main`.

- ✅ Clean separation: production-i18n script (`check_i18n_logs.py`)
  and CI-gating script (`i18n_cjk_guard.py`) live side by side without
  overlapping responsibilities.
- ✅ Mirrors the established convention of one script per
  responsibility under `scripts/`.
- ✅ The baseline file lives under the spec dir
  (`.kiro/specs/i18n-ci-guard/baseline.txt`), matching the ticket's
  "baseline must be committed and reviewable" requirement.
- ❌ One more file in the repo, but the file is small (~150 LoC).

### Option C — Hybrid: shared `cjk_scan.py` helper + thin guard script

Factor the regex + git-grep logic into a tiny shared helper consumed by
both `check_i18n_logs.py` and the new guard.

- ✅ DRY for the regex constant.
- ❌ Premature abstraction: today the only shared element is one
  one-line regex. The two scripts have different scopes, output
  formats, and consumers. Pulling a helper out now satisfies
  consistency without paying for itself; defer until a third caller
  appears.

### Recommendation

**Option B**. It matches the project's established "one focused script
per responsibility" convention, isolates the new CI surface from
existing i18n scripts, and keeps the baseline file collocated with
spec metadata where reviewers expect to find it.

## 4. Research Items for Design Phase

- **Baseline file format**: prefer a stable, line-oriented text format
  over JSON to minimize diff churn (e.g., `path<TAB>count` per line,
  trailing newline). Confirm in design.
- **`git grep` invocation portability**: `git grep -nIP` works on all
  modern git builds (≥2.4 ships PCRE2). `ubuntu-latest` ships ≥2.40.
  No portability concern; record the assumption explicitly.
- **`fetch-depth`** for the `actions/checkout@v4` step: `git grep`
  scans the working tree, not history, so a shallow clone (`fetch-depth:
  1`) is sufficient.
- **Workflow timeout budget**: capture the empirical runtime of the
  full scan locally (already measured: a single `git grep` over the
  scoped paths runs in <2 seconds with ~3.6k matches). The 60-second
  ceiling in Req 5 is comfortable.
- **Failure-message refresh command** wording: the design should pin
  the exact command shown to contributors so it stays one stable
  string developers can copy.
- **Initial baseline values**: with `git grep -nIP '[\x{4e00}-\x{9fff}]'`
  on the current branch — `backend/app` = 2707, `frontend/src` = 902,
  `locales/en.json` = 0. The committed baseline must be regenerated
  against `main` at implementation time so it reflects the merge target.

## 5. Effort & Risk

- **Effort**: **S** (1–3 days). Small, self-contained additions
  (one Python script, one workflow file, one baseline file, plus the
  spec). All patterns already exist in the repo.
- **Risk**: **Low**. No production-source changes, no new dependencies,
  no architectural shifts. The only failure mode is a noisy guard
  blocking unrelated PRs — mitigated by the per-path baseline ratchet.

## 6. Recommendations for Design Phase

- Adopt **Option B** (new focused script + new workflow + baseline file
  under spec dir).
- Lock in the canonical regex `[一-鿿]` and the canonical scan command
  `git grep -nIP '[\x{4e00}-\x{9fff}]' -- <path>` to keep this guard
  bytewise-aligned with the audit pipeline.
- Use a line-oriented baseline format keyed by scoped path; explicit
  `--refresh-baseline` (or equivalent) subcommand updates it; no
  implicit overwrite.
- Output: machine-friendly findings on stderr, summary on stdout,
  exit `0`/`1`.
- The workflow should run only on `pull_request` to `main` (Req 5.1)
  with `fetch-depth: 1` and `actions/setup-python@v5`. No third-party
  packages.
- Baseline counts must be recomputed against `main` before the PR
  ships; do not commit baselines from a feature branch's working tree.
