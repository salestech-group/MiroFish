# Research & Design Decisions — `i18n-translate-backend-comments`

## Summary
- **Feature**: `i18n-translate-backend-comments`
- **Discovery Scope**: Simple Addition (mechanical translation, no architectural change)
- **Key Findings**:
  - 37 in-scope `backend/` Python files contain Chinese characters in docstrings or `#` comments. The full list is in `gap-analysis.md`.
  - Existing docstrings mix English-shape Google-style keys (`Args:`/`Returns:`) with Chinese descriptions, and a smaller subset uses Chinese keys (`参数:`/`返回:`/`异常:`). Both patterns must converge to canonical English Google-style.
  - Several `tests/test_locale*.py` files contain Chinese only inside string literals (intentional test data) and are out of scope by the ticket's enumerated paths.

## Research Log

### Discovery scan: where is Chinese in `backend/`?
- **Context**: Need a deterministic enumeration of files to translate.
- **Sources Consulted**: `grep`/Python-driven scan against `backend/**/*.py`.
- **Findings**:
  - 37 in-app files (under `backend/app/`, `backend/run.py`, `backend/scripts/`).
  - 2 additional test files in `backend/tests/` whose Chinese is only in string literals; not in ticket scope.
  - `.venv/` matches are noise and excluded.
- **Implications**: The ticket-listed paths are exhaustive; no unexpected location. Order of traversal can be alphabetical within package groups.

### Disambiguation: docstring vs string literal
- **Context**: A triple-quoted string is a docstring iff it is the first statement of a module, class, or function body. Otherwise it is a value (e.g. a prompt template) owned by adjacent tickets.
- **Sources Consulted**: Python language reference; spot inspection of `services/ontology_generator.py`, `services/report_agent.py`.
- **Findings**:
  - In-scope files contain both kinds of triple-quoted strings.
  - Translating only the *first-statement* triple-quoted string per scope keeps the change comments-and-docstrings-only.
- **Implications**: Translation pass must visually verify each triple-quoted string is the first statement before rewriting; otherwise leave it alone.

### Google-style docstring conversions
- **Context**: `dev-guidelines.md` requires Google-style docstrings; existing Chinese docstrings sometimes use Chinese keys.
- **Findings**: The following key map applies:
  - `参数:` → `Args:`
  - `返回:` → `Returns:`
  - `异常:` → `Raises:`
  - `产生:` / `生成:` → `Yields:`
  - `示例:` → `Example:` (or `Examples:`)
  - `注意:` / `备注:` → `Note:` (or `Notes:`)
- **Implications**: Document this mapping in design.md so the implementation pass is mechanical.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Manual file-by-file pass | Walk in alphabetical order, package-grouped commits | Predictable, easy to review per package | Human time required | Selected approach |
| Multi-PR per package | One PR per backend package | Smaller diffs to review | Higher overhead, more PR churn | Allowed by ticket but not required |
| Tooling-assisted bulk script | LLM-driven find-and-replace tool | Reusable | Risk of touching string literals; tool itself becomes a deliverable | Out of proportion |

## Design Decisions

### Decision: Single-pass, package-grouped commits, single PR
- **Context**: 37 files, mechanical change, ticket allows either single or split PRs.
- **Alternatives Considered**:
  1. Multi-PR per package — more granular review but higher overhead.
  2. Tooling-assisted bulk script — overkill for one ticket.
- **Selected Approach**: Single PR with one or more commits, grouped by package (`models/`, `utils/`, `services/`, `api/`, `scripts/`, root) so reviewers can read the diff one package at a time.
- **Rationale**: Mechanical change with low risk; ticket explicitly allows it; reduces PR overhead; `/done` produces one PR per branch by default.
- **Trade-offs**: One large PR, but partitioned by commit. Reviewer can use commit history to navigate.
- **Follow-up**: After each package commit, re-run residual `grep` and `pytest` to maintain the invariant.

### Decision: First-statement disambiguation rule
- **Context**: Distinguish docstrings (in scope) from value strings (out of scope).
- **Selected Approach**: A triple-quoted string is treated as a docstring (in scope) only if it is the first statement of a module / class / function body. All other triple-quoted strings are values (out of scope).
- **Rationale**: Matches Python's own definition; keeps boundary with adjacent tickets unambiguous.

### Decision: Drop comments that restate code
- **Context**: R3 requires deletion of comments whose translated form would merely paraphrase the next line.
- **Selected Approach**: Apply a one-line heuristic: if the translated comment would be a verb phrase that mirrors the immediately following executable line, delete the comment instead of writing it.
- **Rationale**: Aligns with project rule "comment the why, not the what".

## Risks & Mitigations
- **Risk**: Accidental edit to a string literal (would belong to ticket #2/#3/#4/#5/#6) — **Mitigation**: After each package commit, run `git diff --stat` and a per-file diff sanity check; verify only `#` lines and docstring lines change.
- **Risk**: Tests failing because a string-shape changed — **Mitigation**: Run `uv run python -m pytest backend/scripts/test_profile_format.py` after each commit.
- **Risk**: Line length violations after English expansion — **Mitigation**: Reflow long English at <= 120 chars within the docstring/comment only; never reflow code.

## References
- `dev-guidelines.md` — repo-level coding standards, Google-style docstring requirement.
- `.claude/rules/commits.md` — Conventional Commits standard for the commit message.
- Issue #7 — salestech-group/MiroFish: source ticket.
- Issues #2/#3/#4/#5/#6 — adjacent i18n tickets that own the string-literal Chinese.
