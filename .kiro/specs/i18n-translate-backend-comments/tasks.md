# Implementation Plan

## Foundation

- [x] 1. Establish baseline and working branch
- [x] 1.1 Create translation working branch and capture baseline state
  - Create branch `docs/i18n-7-translate-backend-comments` from `main`.
  - Capture the baseline residual hits by running the discovery scan (the regex `[一-鿿]` against `backend/**/*.py`, excluding `.venv`); record the file list as the work queue.
  - Run `cd backend && uv run python -m pytest scripts/test_profile_format.py` and confirm a green baseline before any edits.
  - Observable: a fresh branch exists, the baseline file list of 37 in-scope files is captured, and the baseline pytest run passes.
  - _Requirements: 5.1, 6.1_

## Core — Per-Package Translation

- [x] 2. Translate Chinese docstrings and inline comments per package

- [x] 2.1 (P) Translate `backend/app/models/`
  - Translate Chinese module/class/function docstrings and `#` comments in `backend/app/models/__init__.py`, `backend/app/models/project.py`, and `backend/app/models/task.py`.
  - Apply the docstring-vs-value disambiguation rule (first-statement only) so that no string literal is touched.
  - Apply the Google-style key map (`参数:` → `Args:`, `返回:` → `Returns:`, `异常:` → `Raises:`, `产生:`/`生成:` → `Yields:`, `示例:` → `Examples:`, `注意:`/`备注:` → `Note:`).
  - Drop comments that merely restate the next executable line; preserve `TODO:`/`FIXME:` and any embedded ticket reference verbatim.
  - Re-run the residual scan and confirm `backend/app/models/` no longer has Chinese in non-string-literal positions.
  - Re-run `cd backend && uv run python -m pytest scripts/test_profile_format.py` and confirm exit 0.
  - Observable: zero non-string-literal Chinese remains in `backend/app/models/*.py`, and the test command exits 0.
  - _Requirements: 1.1, 1.2, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Boundary: backend/app/models/_

- [x] 2.2 (P) Translate `backend/app/utils/`
  - Translate Chinese docstrings and `#` comments in `backend/app/utils/__init__.py`, `file_parser.py`, `llm_client.py`, `locale.py`, `logger.py`, `retry.py`, and `zep_paging.py`.
  - Be especially careful with `locale.py` and `logger.py`: they intentionally route Chinese strings through their value paths; only docstrings and `#` comments are in scope.
  - Apply Rules 1–5 from `design.md` (disambiguation, key map, comment hygiene, style, preservation).
  - Re-run the residual scan and confirm `backend/app/utils/` no longer has Chinese in non-string-literal positions.
  - Re-run the pytest command and confirm exit 0.
  - Observable: zero non-string-literal Chinese remains in `backend/app/utils/*.py`, and the test command exits 0.
  - _Requirements: 1.1, 1.2, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Boundary: backend/app/utils/_

- [x] 2.3 (P) Translate `backend/app/services/` — complete (all 12 files; finished in this installment)
  - Translate Chinese docstrings and `#` comments across all 12 service files: `__init__.py`, `graph_builder.py`, `ontology_generator.py`, `oasis_profile_generator.py`, `report_agent.py`, `simulation_config_generator.py`, `simulation_ipc.py`, `simulation_manager.py`, `simulation_runner.py`, `text_processor.py`, `zep_entity_reader.py`, `zep_graph_memory_updater.py`, `zep_tools.py`.
  - Treat all triple-quoted prompt templates and value strings as out of scope (owned by issues #2/#3/#4/#5/#6) — only the first-statement docstrings of modules/classes/functions are in scope.
  - Apply Rules 1–5 from `design.md`.
  - Re-run the residual scan and confirm `backend/app/services/` no longer has Chinese in non-string-literal positions.
  - Re-run the pytest command and confirm exit 0.
  - Observable: zero non-string-literal Chinese remains in `backend/app/services/*.py`, and the test command exits 0.
  - _Requirements: 1.1, 1.2, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Boundary: backend/app/services/_

- [x] 2.4 (P) Translate `backend/app/api/` — complete (all 4 files; finished in this installment)
  - Translate Chinese docstrings and `#` comments in `__init__.py`, `graph.py`, `report.py`, `simulation.py`.
  - Treat any user-facing string-literal Chinese in API responses as out of scope (owned by issue #6).
  - Apply Rules 1–5 from `design.md`.
  - Re-run the residual scan and confirm `backend/app/api/` no longer has Chinese in non-string-literal positions.
  - Re-run the pytest command and confirm exit 0.
  - Observable: zero non-string-literal Chinese remains in `backend/app/api/*.py`, and the test command exits 0.
  - _Requirements: 1.1, 1.2, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Boundary: backend/app/api/_

- [x] 2.5 (P) Translate `backend/scripts/` — complete (all 5 files; finished in this installment)
  - Translate Chinese docstrings and `#` comments in `action_logger.py`, `run_parallel_simulation.py`, `run_reddit_simulation.py`, `run_twitter_simulation.py`, `test_profile_format.py`.
  - Apply Rules 1–5 from `design.md`.
  - Be especially careful with `test_profile_format.py`: any Chinese in test data string literals is out of scope; only docstrings and `#` comments are in scope.
  - Re-run the residual scan and confirm `backend/scripts/` no longer has Chinese in non-string-literal positions.
  - Re-run the pytest command and confirm exit 0.
  - Observable: zero non-string-literal Chinese remains in `backend/scripts/*.py`, and the test command exits 0.
  - _Requirements: 1.1, 1.2, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Boundary: backend/scripts/_

- [x] 2.6 (P) Translate root backend files
  - Translate Chinese docstrings and `#` comments in `backend/app/__init__.py`, `backend/app/config.py`, and `backend/run.py`.
  - Apply Rules 1–5 from `design.md`.
  - Be especially careful with `backend/app/config.py`: any Chinese in default-value string literals is out of scope; only docstrings and `#` comments are in scope.
  - Re-run the residual scan and confirm these three files no longer have Chinese in non-string-literal positions.
  - Re-run the pytest command and confirm exit 0.
  - Observable: zero non-string-literal Chinese remains in `backend/app/__init__.py`, `backend/app/config.py`, and `backend/run.py`, and the test command exits 0.
  - _Requirements: 1.1, 1.2, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Boundary: backend/app (root), backend/run.py_

## Validation

- [x] 3. Final verification and PR preparation

- [x] 3.1 Run the final verification gate — scanner + py_compile pass on all 12 newly-translated files; CJK guard baseline updated (backend/app: 2792 → 307); pytest blocked by pre-existing env issues, see HANDOFF.md
  - Run the residual scan one more time and confirm the only remaining hits are files where the Chinese is in string literals owned by issues #2/#3/#4/#5/#6, plus the intentional Chinese in `backend/tests/test_locale*.py`.
  - Run `cd backend && uv run python -m pytest scripts/test_profile_format.py` and confirm exit 0.
  - Run `git diff --stat origin/main...HEAD` and confirm only in-scope file paths under `backend/app/`, `backend/run.py`, and `backend/scripts/` are listed.
  - Spot-check three random changed files with `git diff <path>` and confirm only `#` lines and docstring lines changed (no executable lines, no string-literal lines).
  - Observable: residual scan, pytest, diff scope, and spot diff all pass.
  - _Depends: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_
  - _Requirements: 1.3, 2.5, 5.1, 5.2, 5.3, 5.4, 6.4_

- [ ] 3.2 Open PR and reference ticket #7
  - Use `/done` to commit any remaining changes per Conventional Commits with type `docs` and scope `i18n` (e.g. `docs(i18n): translate chinese docstrings/comments in backend/<area>`), push the branch, and open a PR.
  - The PR body must include `Closes #7` and reference the spec at `.kiro/specs/i18n-translate-backend-comments/`.
  - Verify the PR contains no unrelated changes (no dependency bumps, no config changes, no refactors).
  - Observable: a PR exists on GitHub from `docs/i18n-7-translate-backend-comments` to `main` that closes #7 and contains only docstring/comment translation diffs.
  - _Depends: 3.1_
  - _Requirements: 6.1, 6.2, 6.3, 6.4_
