# Tasks — i18n-e2e-english-verification

## 1. Foundation — audit workspace and entrypoint

- [x] 1.1 Create the audit script directory and the read-only orchestrator skeleton
  - Establish `.kiro/specs/i18n-e2e-english-verification/audit/scripts/` with a `run_audit.sh` skeleton that uses `set -euo pipefail`.
  - The orchestrator captures HEAD sha (`git rev-parse HEAD`) and creates `.kiro/specs/i18n-e2e-english-verification/audit/<sha>/` as the artefact root.
  - Observable completion: running `bash .kiro/specs/i18n-e2e-english-verification/audit/scripts/run_audit.sh` from repo root creates an empty `audit/<sha>/` directory and exits `0`.
  - _Requirements: 1.4, 7.3, 8.1, 8.2, 8.3, 8.4_
  - _Boundary: run_audit.sh_

## 2. Core — read-only audit producers

- [x] 2.1 (P) Implement the canonical CJK grep with PCRE
  - `audit_cjk.sh` runs `git grep -nP '[\x{4e00}-\x{9fff}]' -- backend/app frontend/src locales/en.json` and writes the raw output to `<sha>/cjk-grep.txt`.
  - Produces a partitioned `<sha>/cjk-grep-bucketed.txt` with one section per top-level path (`backend/app`, `frontend/src`, `locales/en.json`).
  - Excludes binary file matches (e.g. `.jpeg`) by skipping paths whose `git check-attr` reports `binary` (or by file-extension allowlist if check-attr is unset).
  - Observable completion: `<sha>/cjk-grep.txt` contains exactly the same lines as a manual `git grep -nP …` run, and `<sha>/cjk-grep-bucketed.txt` has the three labelled sections with line counts.
  - _Requirements: 1.1, 1.5_
  - _Boundary: audit_cjk.sh_

- [x] 2.2 (P) Implement the locale-catalogue parity diff
  - `check_parity.py` loads `locales/en.json` and `locales/zh.json`, recursively flattens nested-dict keys with dotted paths, and writes `<sha>/parity.txt` with three labelled blocks: `[missing-keys]`, `[cjk-in-en]`, `[identical-values]`.
  - The `[identical-values]` block flags entries only when EN value equals ZH value AND the value is non-empty AND has more than two ASCII words.
  - Observable completion: `<sha>/parity.txt` exists; on the current tree `[missing-keys]` is empty and `[cjk-in-en]` is empty (matching the gap-analysis baseline).
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 6.1, 6.3_
  - _Boundary: check_parity.py_

- [x] 2.3 Implement the four-class classifier
  - `classify.py` consumes `<sha>/cjk-grep.txt` and `<sha>/parity.txt` and writes `<sha>/classified.csv` with columns `file,line,match,class,category,pipeline_step`.
  - Implements the closed-set rules from design.md "classify.py": `locales/en.json` CJK → `gap`/`catalogue-parity`; `frontend/src/{views,components}/*.vue` string literal → `gap`/`frontend-ui-string`; `text.match(/.../)` regex pattern with CJK → `gap`/`frontend-regex-parser`; `.py` line starting with `#` or inside a triple-quoted block → `deliberate`/`backend-{comment,docstring}`; `.py` `logger.|log.|print(` line with CJK in a string literal → `gap`/`backend-log` with appropriate step tag; `.py` LLM-prompt label in `services/{ontology,oasis_profile,simulation_config,report_agent}_generator.py` → `gap`/`backend-prompt-label`; binary file → `non-applicable`/`binary-false-positive`; everything else → `review-needed`.
  - Asserts row-count equality with the input grep (no silent drops).
  - Observable completion: `<sha>/classified.csv` row count == `cjk-grep.txt` line count, and at least one row of each non-empty class is present (verified by counting per-class rows in stdout summary).
  - _Requirements: 1.2, 1.3, 1.5, 3.1, 3.2, 3.3, 3.4, 4.3, 4.4, 6.4_
  - _Boundary: classify.py_
  - _Depends: 2.1, 2.2_

## 3. Core — report assembly

- [x] 3.1 Render the gap report and the issue-#10 comment body
  - `render_report.py` reads `<sha>/classified.csv` and `.ticket/10.md`; writes `<sha>/gap-report.md` (with the seven sections from design.md) and `<sha>/comment-body.md` (mirroring the issue's checklist with `pass`/`gap`/`manual-pending` per line + a "How to re-run" footer + a `Run on commit <sha>` header).
  - Section 4 of `gap-report.md` enumerates the four propagation boundaries and reports each as `pass`/`gap`/`unknown`, with file:line evidence drawn from `classified.csv`.
  - Section 5 maps every checklist item from `.ticket/10.md` to a `pass` / `gap` / `manual-pending` status. UI-checklist items default to `manual-pending` (live walkthrough not feasible in sandbox) and include a concrete reproduction script.
  - Always writes the four follow-up issue body templates to `<sha>/PENDING-followups/`: `01-frontend-ui-strings.md`, `02-backend-log-strings.md`, `03-backend-prompt-labels.md`, `04-permanent-ci-guard.md` — empty placeholder if the corresponding category had zero `gap` rows.
  - Observable completion: `<sha>/gap-report.md`, `<sha>/comment-body.md`, and `<sha>/PENDING-followups/01..04-*.md` all exist; opening `<sha>/comment-body.md` shows every checkbox from `.ticket/10.md` mapped to a status.
  - _Requirements: 4.1, 4.2, 5.1, 5.2, 5.3, 5.4, 6.2_
  - _Boundary: render_report.py_

## 4. Integration — orchestrator and GitHub side effects

- [x] 4.1 Wire run_audit.sh to the four producer steps and add the GitHub posting hooks
  - `run_audit.sh` invokes (in order) `audit_cjk.sh`, `check_parity.py`, `classify.py`, `render_report.py`, then `post_comment.sh` and `file_followups.sh`.
  - On any error in steps 1-4 the orchestrator aborts (`set -euo pipefail`) before any subsequent step runs.
  - On `gh` failure in steps 5 or 6, the orchestrator continues to the next step but exits `2` at the end (audit succeeded, side effects didn't fully apply).
  - Observable completion: a clean run on the current tree creates a complete `<sha>/` directory; if `gh` is forced absent (e.g. `PATH=$(pwd)/empty bash run_audit.sh`), the orchestrator still produces all four producer artefacts and the `PENDING-followups/` and exits with `2`.
  - _Requirements: 1.4, 7.3, 8.1, 8.2, 8.3, 8.4_
  - _Boundary: run_audit.sh_
  - _Depends: 2.3, 3.1_

- [x] 4.2 Implement post_comment.sh and file_followups.sh with PENDING fallback
  - `post_comment.sh` calls `gh issue comment 10 --repo salestech-group/MiroFish --body-file <sha>/comment-body.md`; on failure it copies the body to `<sha>/PENDING-issue-10-comment.md` and exits non-zero. On success it writes the resulting URL to `<sha>/comment-url.txt`.
  - `file_followups.sh` iterates `<sha>/PENDING-followups/*.md`; for each non-empty body it calls `gh issue create --repo salestech-group/MiroFish --title <title-from-body-first-line> --body-file <body> --label i18n` (and `--label bug` when the body's frontmatter declares regression). On per-category failure it leaves that body in place; on success it removes the body and appends the issue URL to `<sha>/followup-urls.txt`.
  - Observable completion: with `gh` available, the comment URL appears in `<sha>/comment-url.txt` and any non-empty follow-up body produces an issue URL in `<sha>/followup-urls.txt`; with `gh` absent, both bodies stay under `<sha>/PENDING-*` and exit codes are non-zero.
  - _Requirements: 5.5, 7.1, 7.2, 7.4, 7.5_
  - _Boundary: post_comment.sh, file_followups.sh_
  - _Depends: 3.1_

## 5. Validation — execute the verification pass

- [x] 5.1 Execute the audit on the current tree and capture a baseline run
  - Run `bash .kiro/specs/i18n-e2e-english-verification/audit/scripts/run_audit.sh` from repo root.
  - Confirm `<sha>/cjk-grep.txt`, `cjk-grep-bucketed.txt`, `parity.txt`, `classified.csv`, `gap-report.md`, `comment-body.md`, and `PENDING-followups/01..04-*.md` all exist and are non-empty (the placeholders for empty categories may be empty by design).
  - Confirm `parity.txt` `[missing-keys]` and `[cjk-in-en]` blocks are empty (matches the gap-analysis baseline).
  - Confirm `classified.csv` row count matches `cjk-grep.txt` line count exactly.
  - Observable completion: the baseline `<sha>/` directory is committed under `.kiro/specs/i18n-e2e-english-verification/audit/`.
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 8.1, 8.3_
  - _Boundary: run_audit.sh and producer scripts_
  - _Depends: 4.1_

- [x] 5.2 Post the comment on issue #10 and file the follow-up issues
  - Run `post_comment.sh <sha-dir>` and `file_followups.sh <sha-dir>` (or rely on `run_audit.sh` to invoke them) so the verification report comment is posted and follow-up issues are filed for non-empty categories.
  - Capture `comment-url.txt` and `followup-urls.txt` under `<sha>/` so the PR description can link to them.
  - If `gh` lacks permissions for any of the calls, the corresponding `PENDING-*` file is left in place per R7.5; the run summary surfaces the partial state.
  - Observable completion: a comment appears on https://github.com/salestech-group/MiroFish/issues/10 mirroring `comment-body.md`; follow-up issues for non-empty categories exist and carry the `i18n` label.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.4, 7.1, 7.2, 7.4, 7.5_
  - _Boundary: post_comment.sh, file_followups.sh_
  - _Depends: 4.2, 5.1_
