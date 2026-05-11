# Implementation Tasks — i18n-ci-guard

> Approved spec: see `requirements.md`, `design.md`, `research.md`,
> `gap-analysis.md` in this directory.

## Tasks

- [x] 1. Foundation: scaffold the CI guard script with stable CLI surface and stdlib-only dependencies
- [x] 1.1 Create the empty guard script and CLI skeleton
  - Place the new script at the path designated by the design (`scripts/ci/`).
  - Establish the module docstring, the canonical CJK regex constant, the
    scoped-paths constant tuple, and the `argparse` parser exposing default
    check mode plus an explicit `--update-baseline` flag and a
    `--baseline` path override.
  - Confirm the script exits 0 on a smoke `--help` invocation and rejects
    unknown flags with non-zero exit.
  - Observable: running `python scripts/ci/i18n_cjk_guard.py --help` from
    the repo root prints usage text containing every documented flag and
    exits 0; running with an unknown flag exits non-zero.
  - _Requirements: 5.5, 6.2, 6.3_
  - _Boundary: i18n_cjk_guard.py_

- [x] 2. Core: implement the two CJK checks
- [x] 2.1 Implement the locale-catalogue scan
  - Recursively walk the parsed `locales/en.json` dict, applying the
    canonical regex to every string leaf to gather offending entries.
  - Compute the source line number by re-reading the file as text and
    matching the value's first textual occurrence; truncate snippets to
    the documented snippet length.
  - On a missing or unreadable catalogue file, emit a clear stderr
    message and exit non-zero.
  - Observable: against a synthetic clean catalogue, the function returns
    an empty list; against a synthetic catalogue with one CJK value, it
    returns exactly one finding tuple with the correct dotted key and
    line number.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.1_
  - _Boundary: i18n_cjk_guard.py_

- [x] 2.2 (P) Implement the per-path CJK count via `git grep`
  - Invoke `git grep -nIP '[\x{4e00}-\x{9fff}]' -- <scoped_path>` for each
    scoped path; treat exit codes 0 (matches found) and 1 (no matches) as
    success, any other exit code as a hard error reported on stderr.
  - Count lines of stdout; the result for a zero-match path must be the
    integer `0`, never an exception.
  - Reject working-tree states where `git` is not available or PCRE is
    not enabled, with a clear stderr message.
  - Observable: against a tmp git repository with N planted CJK lines
    under a scoped path, the function returns N; with zero CJK content,
    it returns 0; binary files and untracked files do not contribute.
  - _Requirements: 2.1, 2.4, 2.5, 2.6_
  - _Boundary: i18n_cjk_guard.py_

- [x] 2.3 Implement baseline file read/write with strict format
  - Parse the baseline file as `<path>\t<count>` lines, ignoring `#`
    comments and blank lines, raising a typed error on malformed input
    or missing file.
  - Write atomically (`tmp + os.replace`) with sorted entries, a single
    header comment block, and a single trailing newline.
  - Observable: a round-trip write/read of a deterministic counts dict
    yields the same dict; a baseline file containing a non-tab line is
    rejected with a clear error; the baseline file ends with exactly one
    `\n`.
  - _Requirements: 4.2, 4.3_
  - _Boundary: i18n_cjk_guard.py_

- [x] 3. Integration: wire the two checks into the default and refresh modes
- [x] 3.1 Compose the default check mode
  - Run both checks under all conditions (do not short-circuit), so a
    single CI log shows every failure in one pass.
  - Print a one-line success summary per check on stdout when both pass.
  - On locale failure, print `<file>:<line>: <reason>: <snippet>` lines
    on stderr and a trailing `N issues` summary; on regression failure,
    print `<path>: cjk-regression: baseline=<b> current=<c> delta=+<d>`
    lines plus the exact verbatim refresh command.
  - Surface a non-zero exit when either check fails and exit 0 only when
    both pass.
  - Observable: against a working tree with the committed baseline at or
    above the current count and a CJK-clean en.json, exit code is 0 and
    stdout contains the success summary; planting one CJK char in
    en.json or planting enough new CJK lines to break the baseline
    yields exit 1 and the documented stderr text.
  - _Requirements: 1.2, 1.3, 1.4, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 4.4, 4.5_
  - _Boundary: i18n_cjk_guard.py_

- [x] 3.2 Compose the `--update-baseline` mode
  - When the flag is provided, recompute current per-path counts and
    overwrite the baseline file via the atomic writer; print the new
    counts on stdout; exit 0.
  - When the flag is absent, never write the baseline file under any
    code path.
  - Observable: invoking with `--update-baseline` rewrites the baseline
    file's contents to match current counts and exits 0; running the
    default mode immediately afterward exits 0.
  - _Requirements: 4.3, 4.4_
  - _Boundary: i18n_cjk_guard.py_

- [x] 4. Establish the committed baseline anchored to `main`
- [x] 4.1 Capture initial baseline counts against `main`
  - Operate from a tree that reflects `origin/main`'s state for the
    scoped paths (e.g., a fresh checkout, a worktree at `origin/main`,
    or `git checkout origin/main -- backend/app frontend/src` followed
    by a clean revert) so the committed baseline does not over- or
    under-count relative to the merge target.
  - Run `--update-baseline` to materialize the counts; confirm the
    resulting file is exactly two non-comment data lines (one per
    scoped path) sorted lexicographically.
  - Observable: the baseline file is committed to
    `.kiro/specs/i18n-ci-guard/baseline.txt` and `python scripts/ci/i18n_cjk_guard.py`
    against the same `main`-aligned tree exits 0.
  - _Requirements: 4.1, 4.2_
  - _Boundary: baseline.txt_

- [x] 5. Wire the guard into GitHub Actions on every PR to `main`
- [x] 5.1 Add the PR-time workflow
  - Create the workflow file at the path designated by the design,
    triggered on `pull_request` whose base ref is `main`.
  - Set explicit minimal permissions (`contents: read`), a one-minute
    job timeout, `actions/checkout@v4` with `fetch-depth: 1`, and
    `actions/setup-python@v5` pinned to Python 3.11.
  - The single executable step invokes the guard script with no
    arguments; the workflow surfaces the script's stdout and stderr in
    the GitHub Actions log without filtering.
  - Observable: the workflow YAML parses cleanly; on a PR with no CJK
    regression, the job passes; on a PR that introduces a CJK regression
    or CJK in en.json, the job fails and the log shows the documented
    failure messages.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  - _Boundary: i18n-cjk-guard.yml_

- [x] 6. Validation: tests and end-to-end checks
- [x] 6.1 Add unit and integration tests for the guard script
  - Cover the locale scan against a synthetic clean catalogue and a
    synthetic CJK-tainted catalogue, asserting findings tuples match.
  - Cover the per-path counter against a tmp git repo with both N>0
    and N=0 planted CJK lines, asserting the zero-match path exits
    cleanly with a count of 0.
  - Cover the baseline read/write round-trip and the malformed-input
    rejection path.
  - Cover the default mode end-to-end (pass and fail paths) with the
    expected exit codes and stderr fragments, including the verbatim
    refresh command on regression failure.
  - Observable: `python -m pytest scripts/ci/tests/test_i18n_cjk_guard.py`
    from the repo root passes locally with stdlib-only Python.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.4, 2.5, 2.6, 3.3, 4.3, 4.5, 6.1, 6.3_
  - _Boundary: scripts/ci/tests/_

- [x] 6.2 Run the guard locally to confirm reproducibility against the committed baseline
  - From a clean working tree at `main` (or a worktree at `origin/main`
    + this branch's new files merged on top), invoke the guard with no
    arguments and confirm exit code 0 and the success summary.
  - Confirm the same command is the documented developer entry point
    referenced from the failure-message refresh hint.
  - Observable: terminal session shows exit code 0 and the documented
    one-line per-check success summary; the same script path (`scripts/ci/i18n_cjk_guard.py`)
    appears verbatim in the regression-failure refresh hint.
  - _Requirements: 6.1, 6.2, 6.3_
  - _Boundary: i18n_cjk_guard.py, baseline.txt_
