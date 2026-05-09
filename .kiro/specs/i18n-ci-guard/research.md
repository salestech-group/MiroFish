# Research & Design Decisions — i18n-ci-guard

## Summary
- **Feature**: `i18n-ci-guard`
- **Discovery Scope**: Simple Addition (one Python script + one GH Actions
  workflow + one baseline file). Extension-flavoured because it builds on
  established `scripts/` conventions and the canonical CJK regex used by
  the larger audit pipeline.
- **Key Findings**:
  - The canonical CJK match command `git grep -nIP '[\x{4e00}-\x{9fff}]'
    -- <path>` is already used by the unmerged audit pipeline (PR #27)
    and is portable on every git ≥2.4 (`ubuntu-latest` ships ≥2.40).
  - `scripts/check_i18n_logs.py` is a strong CLI/style precedent:
    Python-stdlib-only, exit `0`/`1`, output as `<file>:<line>:
    <reason>: <snippet>`, canonical regex `[一-鿿]`.
  - The repository has no existing `pull_request`-triggered GH Actions
    workflow; this guard introduces the first one. The only existing
    workflow (`.github/workflows/docker-image.yml`) runs on tag pushes
    only.
  - Current per-path counts on this branch:
    `backend/app=2707, frontend/src=902, locales/en.json=0`. These are
    sample counts; the committed baseline must be regenerated against
    `main` at implementation time.

## Research Log

### Canonical scan command
- **Context**: Requirement 2 needs a stable per-path CJK count and
  Requirement 5.5 forbids third-party packages.
- **Sources Consulted**:
  - `audit_cjk.sh` from PR #27 commit `3481408`.
  - `git grep` man page.
- **Findings**:
  - `git grep -nIP '[\x{4e00}-\x{9fff}]' -- <path>` returns one match
    per matching line in tracked, text-only files. `-I` excludes binary
    files; `-P` enables PCRE2 so the `\x{...}` Unicode range works.
  - This matches the input format consumed by the existing audit
    classifier, so the guard's match counts are directly comparable
    across pipelines.
- **Implications**:
  - The guard re-uses this exact command; no new dependencies.
  - Because `-I` skips binary files and tracked-only is the default,
    Requirements 2.5 and 2.6 are satisfied by the command itself
    rather than by additional script logic.

### Baseline file format
- **Context**: Requirement 4 needs a diff-friendly committed baseline.
- **Sources Consulted**:
  - Diff churn behaviour of JSON vs. line-oriented text in this repo's
    history (e.g. `locales/*.json` PR diffs frequently re-key, while
    plain-text `parity.txt` from PR #27 reads cleanly).
- **Findings**:
  - Line-oriented `<path>\t<count>` files produce minimal diffs and
    require no JSON parser.
  - A two-line file (one per scoped path) is large enough to be
    self-explanatory and small enough to never line-shuffle.
- **Implications**:
  - Use plain text, sorted by path, single trailing newline. Reject
    the file as malformed if the script cannot parse it (Req 4.5).

### Locale-catalogue scan path
- **Context**: Requirement 1 wants `key:line` per CJK offender in
  `locales/en.json`.
- **Sources Consulted**:
  - `scripts/check_i18n_logs.py` (`flatten_keys` reuse pattern).
  - `check_parity.py` from PR #27 (`flatten`, `[cjk-in-en]` block).
- **Findings**:
  - Both precedents flatten the locale dict and run the canonical
    regex against each leaf string value. Line numbers are derivable
    by re-reading the file as text and matching the value's first
    occurrence (good enough for an actionable error message).
  - Empty-string values and non-string leaf values (booleans, null)
    are skipped.
- **Implications**:
  - Implement a tiny flatten-then-scan helper inside the guard
    script; do not add a new shared utility module.

### GH Actions trigger and budget
- **Context**: Requirements 5.1, 5.5, 5.6.
- **Sources Consulted**:
  - GitHub-hosted runners reference (`ubuntu-latest`).
  - `actions/setup-python@v5` README.
- **Findings**:
  - `ubuntu-latest` has Python 3.10+ pre-installed; `actions/setup-python@v5`
    pins to 3.11 in <5 s.
  - A single `git grep` over the scoped paths runs in <2 s on this
    repo (~3.6k matches). End-to-end the workflow comfortably fits
    inside the 60 s ceiling.
- **Implications**:
  - Use `actions/checkout@v4` with `fetch-depth: 1`,
    `actions/setup-python@v5` with `python-version: '3.11'`, and run
    the script directly. No caching layer needed.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A. Extend `check_i18n_logs.py` | Add `--cjk-guard` mode to existing script | Reuses one file | Conflates two scopes; existing script is module-scoped, guard is subtree-scoped | Rejected |
| B. New `scripts/ci/i18n_cjk_guard.py` + new workflow | Single-purpose script + workflow + baseline file | Clean SRP; matches "one script per responsibility" precedent | One additional file | **Selected** |
| C. Shared `cjk_scan.py` helper + thin guard | Factor regex/git-grep into helper | DRY for regex constant | Premature abstraction; only one shared symbol today | Rejected |

## Design Decisions

### Decision: Single-purpose CI script + GH Actions workflow (Option B)
- **Context**: Requirements 1–6 demand a small, self-contained guard.
- **Alternatives Considered**: A (extend), C (shared helper).
- **Selected Approach**: New script `scripts/ci/i18n_cjk_guard.py`,
  new workflow `.github/workflows/i18n-cjk-guard.yml`, baseline file
  `.kiro/specs/i18n-ci-guard/baseline.txt`.
- **Rationale**: Matches the project's "one focused script per
  responsibility" convention; isolates a CI-blocking surface from the
  existing i18n developer scripts; keeps the baseline collocated with
  the spec for review traceability.
- **Trade-offs**: One more file in `scripts/` vs. tighter cohesion.
- **Follow-up**: When a third caller wants the canonical regex, factor
  it out then.

### Decision: Plain-text baseline format
- **Context**: Requirement 4.2 demands stable, diff-friendly format.
- **Alternatives Considered**: JSON, YAML.
- **Selected Approach**: One line per scoped path: `<path>\t<count>`,
  sorted lexicographically by path, single trailing newline.
- **Rationale**: Zero parser dependency; predictable diffs; trivial
  to refresh atomically.
- **Trade-offs**: Less expressive than JSON (no nested structure), but
  the data model is two integers — nesting is unnecessary.

### Decision: Refresh via `--update-baseline` subcommand-style flag
- **Context**: Requirement 4.3 needs an explicit refresh path.
- **Alternatives Considered**: Separate `update_baseline.py` script;
  Makefile target.
- **Selected Approach**: Single script with two modes: default (check
  + exit 0/1) and `--update-baseline` (overwrite baseline + exit 0).
- **Rationale**: One CLI surface to remember; the failure message
  prints the exact command to run.
- **Trade-offs**: Slightly more conditional logic in one script;
  acceptable given the small total LoC.

### Decision: Workflow runs only on `pull_request` to `main`
- **Context**: Requirement 5.1.
- **Alternatives Considered**: Run on `push` to all branches as well;
  run on `pull_request` to any base branch.
- **Selected Approach**: `on.pull_request.branches: [main]` only.
- **Rationale**: Aligns with how the existing project uses `main` as
  the protected branch (see `gh pr list` history; every feature PR
  targets `main`). Avoids redundant runs on intra-branch chains.
- **Trade-offs**: A direct push to `main` would not be guarded — but
  branch protection already discourages that path (per
  `dev-guidelines.md`).

## Risks & Mitigations

- **Risk**: Baseline drifts upward unintentionally during
  `--update-baseline` runs, hiding real regressions.
  - *Mitigation*: Failure message instructs contributors to refresh
    *only when intentional*; the baseline file is reviewed in the same
    PR diff. Acceptance Criteria 3.3 makes this explicit.
- **Risk**: `git grep -P` not built with PCRE on a developer's local
  git build (rare on Linux/macOS, possible on minimal Windows builds).
  - *Mitigation*: The guard prints a clear error if `git grep` exits
    non-zero with PCRE mode; documents Python ≥3.11 + git ≥2.20 as
    prerequisites.
- **Risk**: Baseline counts captured on a feature branch include
  changes not yet on `main`, mis-anchoring the ratchet.
  - *Mitigation*: The implementation task explicitly recomputes
    baseline against `origin/main` before committing; documented in
    `tasks.md`.

## References
- PR #27 audit pipeline (`audit_cjk.sh`, `check_parity.py`,
  `classify.py`) — methodology source of truth.
- `scripts/check_i18n_logs.py` — CLI/style precedent.
- `git grep` man page — `-n`, `-I`, `-P` flag semantics.
- GitHub Actions `actions/setup-python@v5` and `actions/checkout@v4`
  README pages.
