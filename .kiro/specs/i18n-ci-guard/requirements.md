# Requirements Document

## Project Description (Input)
Add a permanent CI guard that runs an i18n CJK audit on every pull request.

Linked GitHub issue: #26 (.ticket/26.md).

The guard must fail a PR build when:
1. locales/en.json contains any CJK character (range U+4E00..U+9FFF), or
2. The total count of CJK matches across backend/app/ and frontend/src/ regresses (i.e. exceeds) a committed baseline value.

## Introduction

The i18n initiative has driven the project toward English-by-default UI, logs,
prompts, and documentation. Manual audits (see PR #27, the
`i18n-e2e-english-verification` spec) have repeatedly surfaced regressions
where Chinese strings re-enter the codebase. This spec installs a permanent,
self-contained CI guard that runs on every pull request and fails the build
when (a) `locales/en.json` is no longer CJK-clean, or (b) the total CJK match
count under `backend/app/` and `frontend/src/` regresses against a committed
baseline.

The guard is intentionally minimal: it captures the two highest-signal checks
from the larger audit pipeline so it can run on every PR with a sub-minute
budget and without depending on the (currently unmerged) verification spec.
The committed baseline lets the project ratchet down gaps over time without
blocking unrelated PRs on pre-existing CJK content.

## Boundary Context

- **In scope**:
  - A locally runnable Python script that performs both guard checks on the
    current working tree.
  - A baseline file committed under the spec directory recording the
    accepted CJK match counts per scoped path.
  - A GitHub Actions workflow that runs the script on every pull request
    targeting `main` and fails the build when either check fails.
  - A clear, actionable failure message (which path regressed, baseline
    value, current value, command to update the baseline).
- **Out of scope**:
  - The full classification pipeline (`classify.py`, `render_report.py`,
    `post_comment.sh`) from the unmerged `i18n-e2e-english-verification`
    spec — those scripts perform deeper audit work and are not required
    for the PR-time guard.
  - Auto-updating the baseline on `main` (the baseline is a normal
    reviewable file).
  - Translation work itself; this spec only enforces a regression gate.
  - Any change to production source under `backend/app/`, `frontend/src/`,
    or `locales/` apart from translations needed to satisfy the guard
    against its own initial baseline.
- **Adjacent expectations**:
  - PR #27 (`chore/i18n-10-e2e-english-verification`) provides the
    methodology referenced here. This spec must remain functional whether
    PR #27 has been merged or not.
  - The guard reuses the canonical CJK regex range
    `[一-鿿]` already established by that audit.

## Requirements

### Requirement 1: Locale-catalogue CJK cleanliness check

**Objective:** As a maintainer of the English locale catalogue, I want every
PR to fail when `locales/en.json` reintroduces any CJK character, so that the
English catalogue stays CJK-free.

#### Acceptance Criteria

1. When the guard script is run from the repository root, the i18n CI Guard
   shall scan the contents of `locales/en.json` for any character in the
   range `U+4E00..U+9FFF`.
2. If `locales/en.json` contains at least one such character, the i18n CI
   Guard shall exit with a non-zero status and report each offending
   `key:line` pair on standard output.
3. While `locales/en.json` contains zero such characters, the i18n CI Guard
   shall report the catalogue as CJK-clean.
4. If `locales/en.json` is missing or unreadable, the i18n CI Guard shall
   exit with a non-zero status and emit an explicit error message naming
   the missing file.

### Requirement 2: Backend/frontend CJK regression check against committed baseline

**Objective:** As a maintainer of English support across the codebase, I
want every PR to fail when the total CJK match count under `backend/app/`
or `frontend/src/` exceeds a committed baseline, so that the codebase
ratchets monotonically toward English-only without blocking PRs on
pre-existing CJK content.

#### Acceptance Criteria

1. When the guard script is run, the i18n CI Guard shall count the total
   number of CJK matches (range `U+4E00..U+9FFF`, line-level, text files
   only) under each of the scoped paths `backend/app/` and `frontend/src/`.
2. The i18n CI Guard shall read the baseline counts from a single
   committed baseline file under the spec directory.
3. If the current count for any scoped path exceeds the baseline count for
   that path, the i18n CI Guard shall exit with a non-zero status.
4. While the current count for every scoped path is less than or equal to
   the baseline, the i18n CI Guard shall exit with status zero for this
   check.
5. The i18n CI Guard shall ignore matches inside binary files
   (image, font, archive, lockfile, or other non-text formats) by relying
   on `git grep -I` semantics.
6. The i18n CI Guard shall scope its scan to tracked files only (matches
   in untracked or ignored files shall not contribute to the count).

### Requirement 3: Actionable failure messaging

**Objective:** As a contributor whose PR was rejected by the guard, I want
the failure message to tell me exactly what regressed and how to fix it,
so that I can either translate the offending content or — when intentional —
update the baseline through normal review.

#### Acceptance Criteria

1. If the locale-catalogue check fails, the i18n CI Guard shall print, for
   each offending entry: the dotted catalogue key, the line number in
   `locales/en.json`, and a truncated snippet of the value.
2. If the regression check fails, the i18n CI Guard shall print, for each
   regressed scoped path: the path name, the baseline count, the current
   count, and the delta.
3. If the regression check fails, the i18n CI Guard shall print the exact
   shell command a contributor must run locally to refresh the baseline
   file so the PR can be re-reviewed against the new value.
4. The i18n CI Guard shall print, on success, a one-line summary per check
   confirming the catalogue is CJK-clean and the per-path counts are at or
   below baseline.

### Requirement 4: Baseline file lifecycle

**Objective:** As a reviewer enforcing English support, I want the baseline
to live in the repository as a small, human-readable file that only changes
through code review, so that downward ratcheting is intentional and
auditable.

#### Acceptance Criteria

1. The i18n CI Guard shall store the baseline as a single committed file
   under `.kiro/specs/i18n-ci-guard/`.
2. The baseline file shall record one count per scoped path, in a stable,
   diff-friendly text format (no JSON line shuffling, no trailing
   whitespace).
3. When the guard script is invoked with an explicit "refresh baseline"
   subcommand or flag, the i18n CI Guard shall overwrite the baseline file
   with the current per-path counts and exit with status zero.
4. While no refresh flag is supplied, the i18n CI Guard shall never modify
   the baseline file.
5. If the baseline file is missing at check time, the i18n CI Guard shall
   exit with a non-zero status and instruct the contributor to refresh it.

### Requirement 5: GitHub Actions PR integration

**Objective:** As a project maintainer, I want every pull request targeting
`main` to be gated by the guard, so that no merge silently regresses the
English-only state of the catalogue or codebase.

#### Acceptance Criteria

1. The i18n CI Guard workflow shall trigger on every `pull_request` event
   whose base ref is `main`.
2. While the workflow runs, the i18n CI Guard shall check out the PR head
   commit with full history sufficient for `git grep` to scan tracked
   files.
3. When the guard script exits with non-zero status, the workflow shall
   fail and surface the script's standard output and standard error in the
   GitHub Actions log.
4. When the guard script exits with status zero, the workflow shall pass.
5. The workflow shall use only Python from the standard
   `actions/setup-python` distribution and tools already available on the
   GitHub-hosted `ubuntu-latest` runner (`bash`, `git`); it shall not
   install third-party Python packages.
6. The workflow shall complete within sixty seconds of wall-clock time on
   a clean `ubuntu-latest` runner.

### Requirement 6: Local reproducibility

**Objective:** As a developer preparing a PR, I want to run the same guard
locally before pushing, so that I can catch regressions before CI does.

#### Acceptance Criteria

1. When the guard script is invoked from a developer machine that has
   Python 3.11 or newer and `git` available, the i18n CI Guard shall
   produce the same pass/fail result and the same per-path counts that
   it would produce in CI for the same working tree.
2. The i18n CI Guard shall expose a single, stable invocation entry point
   (a script under `scripts/ci/`) documented in the spec's design and
   README touchpoints.
3. The i18n CI Guard shall require zero environment variables or secrets
   to run locally.
