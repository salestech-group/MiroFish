# Requirements Document

## Introduction
This specification covers the developer-facing internationalization of `backend/` Python source: translating Chinese docstrings and inline comments to English so that English-speaking maintainers can read and review the code without translation overhead. The change is mechanical — no behavior, no public strings, no symbol names are modified. It is one of several i18n tickets (#2, #3, #4, #5, #6, #7); this spec covers ticket #7 only.

## Boundary Context
- **In scope**: Translation of Chinese-language characters that appear in Python docstrings (module/class/function) and inline `#` comments under `backend/`. Removal of comments that merely restate the code. Preservation of `TODO:` / `FIXME:` markers and embedded ticket references.
- **Out of scope**: Chinese characters inside string literals (prompt templates, `logger.{info,warning,error}` arguments, API response bodies, error messages returned to clients) — these are tracked separately by issues #2/#3/#4/#5/#6. No refactoring, reformatting, renaming, or behavior changes.
- **Adjacent expectations**: Spec `i18n-externalize-backend-logs` (issue #6) and the prompt-translation specs handle string-literal Chinese; this spec must leave those untouched so the other tickets remain mergeable.

## Requirements

### Requirement 1: Translation Coverage of In-Scope Files
**Objective:** As a maintainer, I want every Chinese docstring and inline comment in the in-scope backend files translated to English, so that I can read and review the code without translation tools.

#### Acceptance Criteria
1. The Backend Codebase shall contain no Chinese characters (Unicode range U+4E00–U+9FFF) inside Python docstrings under `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/models/`, `backend/app/services/`, `backend/app/api/`, `backend/app/utils/`, `backend/run.py`, and `backend/scripts/`.
2. The Backend Codebase shall contain no Chinese characters inside Python `#` inline comments under the same paths.
3. When `grep -rln '[一-鿿]' backend/ --include='*.py'` is run after this change, the Backend Codebase shall return only files whose remaining Chinese is contained within string literals owned by issues #2/#3/#4/#5/#6.
4. When a docstring is translated, the Translator shall preserve Google-style docstring shape (`Args:`, `Returns:`, `Raises:`, `Yields:` sections) per `dev-guidelines.md`.

### Requirement 2: Preservation of Code Behavior
**Objective:** As a maintainer, I want the translation to be comments-and-docstrings-only, so that runtime behavior is provably unchanged.

#### Acceptance Criteria
1. The Translator shall not modify any executable Python statement (assignments, function calls, control flow, decorators, imports).
2. The Translator shall not modify any Python string literal (single-, double-, triple-quoted, f-string, raw, byte) regardless of whether it contains Chinese characters.
3. The Translator shall not rename any symbol (variable, function, class, module, parameter).
4. When `uv run python -m pytest backend/scripts/test_profile_format.py` is run after the change, the Backend Codebase shall exit with status 0.
5. If a diff line touches any non-comment, non-docstring code, the Translator shall reject that diff hunk and revise.

### Requirement 3: Comment Quality Hygiene
**Objective:** As a maintainer, I want translated comments to add value, so that the codebase remains easy to read after the migration.

#### Acceptance Criteria
1. When a Chinese comment merely restates the immediately following code (e.g. `# 初始化客户端` above `client = Client()`), the Translator shall delete the comment rather than translate it.
2. When a Chinese comment captures non-obvious *why* (constraints, workarounds, invariants), the Translator shall translate it to a faithful English equivalent.
3. The Translator shall preserve any `TODO:` / `FIXME:` marker and any embedded ticket reference (e.g. `#1234`, `PROJ-456`) verbatim within the translated comment.
4. The Translator shall not introduce new comments that did not exist (or had no Chinese equivalent) in the original source.

### Requirement 4: Style and Format Compliance
**Objective:** As a maintainer, I want the translated output to comply with project style rules, so that no follow-up cleanup PR is needed.

#### Acceptance Criteria
1. The Translator shall keep all translated docstrings and comments at or below 120 characters per line.
2. The Translator shall not introduce trailing whitespace on any line.
3. The Translator shall preserve the original indentation (tabs/spaces) of every comment and docstring.
4. The Translator shall use double quotes for any docstring it rewrites, matching the existing Python convention in the file.
5. Where a file already uses 4-space indentation, the Translator shall preserve that indentation.

### Requirement 5: Discovery and Verification Workflow
**Objective:** As a reviewer, I want a reproducible discovery and verification workflow, so that I can confirm coverage and absence of regressions in CI or locally.

#### Acceptance Criteria
1. The Translator shall enumerate candidate files using `grep -rln '[一-鿿]' backend/ --include='*.py'` before beginning work.
2. The Translator shall re-run the same `grep` after each batch and confirm the residual hits are limited to string-literal Chinese owned by adjacent tickets (#2/#3/#4/#5/#6).
3. When the residual `grep` hits include any non-string-literal Chinese, the Translator shall classify those hits as in-scope and continue translation until they are gone.
4. The Translator shall verify that `git diff --stat` only reports changes inside the in-scope file paths listed in Requirement 1.

### Requirement 6: Tracking and Branching
**Objective:** As a release manager, I want the work tracked against ticket #7 on a dedicated branch, so that the PR remains scoped and traceable.

#### Acceptance Criteria
1. The Translator shall produce changes on a branch named `docs/i18n-7-translate-backend-comments`.
2. The Translator shall reference issue `salestech-group/MiroFish#7` in commit messages or PR description.
3. When committing, the Translator shall use Conventional Commits with type `docs` and scope `i18n` (e.g. `docs(i18n): translate chinese docstrings/comments in backend/<area>`).
4. The Translator shall not include unrelated changes (e.g. dependency bumps, config changes, refactors) in the resulting PR.
