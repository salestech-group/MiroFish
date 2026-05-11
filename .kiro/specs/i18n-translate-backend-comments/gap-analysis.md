# Gap Analysis — `i18n-translate-backend-comments`

## Scope Recap
- **Ticket**: salestech-group/MiroFish#7
- **Goal**: Translate Chinese docstrings and `#` comments in `backend/` to English without behavior changes.
- **Blast radius**: Comments and docstrings only; runtime semantics preserved.

## Current State Investigation

### Discovered files
A scan with the regex `[一-鿿]` across `backend/**/*.py` (excluding `.venv`) returns **37 in-app files** plus 2 test files:

| Area | Count | Files |
| --- | --- | --- |
| `backend/app/__init__.py` | 1 | `__init__.py` |
| `backend/app/config.py` | 1 | `config.py` |
| `backend/app/api/` | 4 | `__init__.py`, `graph.py`, `report.py`, `simulation.py` |
| `backend/app/models/` | 3 | `__init__.py`, `project.py`, `task.py` |
| `backend/app/services/` | 12 | `__init__.py`, `graph_builder.py`, `oasis_profile_generator.py`, `ontology_generator.py`, `report_agent.py`, `simulation_config_generator.py`, `simulation_ipc.py`, `simulation_manager.py`, `simulation_runner.py`, `text_processor.py`, `zep_entity_reader.py`, `zep_graph_memory_updater.py`, `zep_tools.py` |
| `backend/app/utils/` | 7 | `__init__.py`, `file_parser.py`, `llm_client.py`, `locale.py`, `logger.py`, `retry.py`, `zep_paging.py` |
| `backend/run.py` | 1 | `run.py` |
| `backend/scripts/` | 5 | `action_logger.py`, `run_parallel_simulation.py`, `run_reddit_simulation.py`, `run_twitter_simulation.py`, `test_profile_format.py` |
| `backend/tests/` (extra, not in ticket file list) | 2 | `test_locale.py`, `test_locale_request_resolution.py` |

Spot checks (`models/task.py`, `models/project.py`, `services/text_processor.py`, `utils/locale.py`):
- Module-level docstrings in Chinese (e.g. `"""任务状态管理"""`).
- Class/method docstrings in Chinese, often Google-shaped (`Args:` translated as `参数:`).
- Inline `#` comments tagging fields, sections, or restating obvious code (e.g. `# 标准化换行` above an `\n` normalization call).
- Status-enum trailing comments (e.g. `PENDING = "pending"  # 等待中`).

### Conventions to preserve
- Project guideline: 4-space indent, max 120 char/line, double-quoted strings (Python).
- Docstring style: Google-style per `dev-guidelines.md`. Existing files mix English-shape `Args:`/`Returns:` keys with Chinese descriptions, or use Chinese keys (`参数:`, `返回:`). Translate both to canonical Google-style English.
- File-level convention: `snake_case` filenames, Python `__init__.py` modules typically have a one-line module docstring.

### Integration surfaces
None. This work touches only commentary; no API contracts, schemas, or imports change.

## Requirements Feasibility

| Requirement | Status | Notes |
| --- | --- | --- |
| R1 (coverage) | Feasible — straightforward | Files identified by `grep` rule. |
| R2 (behavior preservation) | Feasible | Achieved by limiting diffs to comment/docstring lines. Need to be careful with multi-line triple-quoted docstrings vs string literals (they are syntactically identical to strings — disambiguation: docstring is the *first* statement of a module/class/function body). |
| R3 (comment hygiene) | Feasible | Some judgment required; will adopt heuristic: drop comments whose translated form would be a single verb-phrase paraphrase of the next executable line. |
| R4 (style compliance) | Feasible | Watch line-length when translating dense Chinese to English (English is typically longer); rewrap as needed without changing executable code. |
| R5 (verification) | Feasible | The `grep -rln '[一-鿿]'` rule is reliable. Residual hits should land only in: prompt template strings (#2/#3/#4/#5), logger/API string literals (#6), and the `tests/test_locale*` files (intentional Chinese test data). |
| R6 (tracking/branching) | Feasible | Branch + commit conventions are standard for this repo; `/done` skill enforces them. |

### Gaps and constraints
- **Constraint**: Triple-quoted strings used as values (not as docstrings) must NOT be edited if their content is in scope of issues #2–#6 (prompts/log messages/error messages). Disambiguation matters.
- **Constraint**: Chinese characters appearing inside f-string literal segments must remain. They are out of scope.
- **Unknown / Research Needed**: None — task is mechanical and well-bounded.

### Adjacent specs / overlap with other tickets
- `i18n-externalize-backend-logs` (#6) owns translating `logger.{info,warning,error}` Chinese arguments and API response strings.
- `i18n-report-agent-prompts` (#5), and tickets #2/#3/#4 own prompt template strings.
- We must NOT touch any string literal that those tickets own. After this PR, residual `grep` hits should reduce by exactly the count of comments and docstrings translated and nothing else.
- The two `backend/tests/test_locale*.py` files are **not in the ticket's listed file scope**, and inspection shows their Chinese is exclusively in string literals (test data and a Unicode range check). They are out of scope by R1's enumerated paths and remain untouched.

## Implementation Approach Options

### Option A — Single-pass file-by-file translation (recommended)
- Walk the 37 in-scope files in a deterministic order (alphabetical), translating docstrings/comments per file, running the residual grep after each batch.
- Group commit by area (models, utils, services, api, scripts, root) to keep PR diff readable.
- ✅ Simple, low risk, easy to revert per-area.
- ✅ Maps directly to the requirements; easy to verify.
- ❌ Larger PR than option B, but ticket explicitly allows a single PR.

### Option B — Multi-PR per package
- Split into one PR per package (`models/`, `utils/`, …). The ticket allows this.
- ✅ Smaller diffs to review.
- ❌ More overhead (multiple branches/PRs); not necessary for a mechanical change of this size.

### Option C — Tooling-assisted bulk script
- Build a one-shot translation script (LLM-driven) that rewrites docstrings/comments.
- ✅ Could scale to other repos.
- ❌ Out of proportion for a single-ticket task; risk of errant edits to string literals; tooling itself becomes a deliverable to test and maintain.

## Effort and Risk
- **Effort**: **M (3–7 days of focused work)** — 37 files, hundreds of comments. In an interactive AI-assisted run, this collapses to a few hours.
- **Risk**: **Low** — comments-only diff; covered by mechanical verification (grep + pytest); easy to rollback per file/area.

## Recommendations for Design Phase

- **Preferred approach**: Option A (single-pass file-by-file, package-grouped commits, single PR).
- **Key decisions to capture in design**:
  - Order of traversal (proposed: `models/` → `utils/` → `services/` → `api/` → `scripts/` → root files `__init__.py`, `config.py`, `run.py`).
  - Heuristic for "drops the obvious comment" (one-line rule).
  - How to handle Google-style docstring keys: always translate `参数:` → `Args:`, `返回:` → `Returns:`, `异常:` → `Raises:`.
  - Verification cadence: re-run the grep after each package batch.
- **Research items to carry forward**: None.
