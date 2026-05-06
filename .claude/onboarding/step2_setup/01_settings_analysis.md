# Step 2 — Settings & Hooks Analysis

Decisions made while configuring `.claude/settings.json` and the hooks
(Step 2).

## Date: 2026-05-06

## Project Context (PHASE 1 findings)
- **Backend:** Python (Flask, `uv`). No Ruff / Black / pre-commit config.
- **Frontend:** Vue 3 + Vite. No Prettier / ESLint config.
- **Sensitive paths:** `.env`, `.env.example`. No `secrets/` folder
  exists today; rule blocks the path proactively. User uploads land in
  `backend/uploads/`. CodeGraph index lives in `.codegraph/`.
- **Project decision (Step 1):** No enforced formatter — match the
  surrounding file's style.

## Decisions

| Question | Decision |
|----------|----------|
| Q1 — Allow more bash? | **Yes.** Added `npm run:*`, `npm test:*`, `npm install:*`, `git status`, `git diff:*`, `git log:*`, `git show:*`, `git add:*`, `git branch:*`, `git checkout:*`, `git commit:*`, `git restore:*`, `uv run:*`, `uv sync:*`, `docker compose:*`, `docker-compose:*`. |
| Q2 — Deny additions? | **Yes.** Added Read/Write/Edit denials for `*/uploads/*` and `*/.codegraph/*`. |
| Q3 — PostToolUse formatter? | **Skipped.** No formatter configured in this project. Matches the established convention (Step 1 — "no enforced formatter at present"). Add later if/when the team adopts one. |
| Q4 — PreToolUse `.env` guard hook? | **Added** as a friendly, logged refusal layered on top of the `permissions.deny` rules. |
| Q5 — SessionStart hook? | **Both** — branch + status. Single line: `📍 Branch: <branch> (ahead N, behind M vs upstream) — clean / N uncommitted change(s)`. |
| Q6 — `.gitignore` for `settings.local.json`? | **Already done in Step 0** — `.claude/settings.local.json` and `.claude/.credentials.json` are ignored. |

## What Was Created / Updated

### `.claude/settings.json`
- **Permissions:**
  - `allow` — safe nav (`cd`, `ls`, `find`, `cat`, `mkdir`), `npm` /
    `uv` task running, common read-only and staging git commands,
    docker-compose for the recommended deployment path.
  - `deny` — `.env*`, `secrets/`, `uploads/`, `.codegraph/` (Read /
    Write / Edit), destructive bash (`rm -f*`, `rm -rf*`,
    `git push -f*`, `git push --force*`).
- **Hooks:**
  - `SessionStart` → `.claude/hooks/session_start.sh`
  - `PreToolUse` (matcher: `Read|Write|Edit|Bash|NotebookEdit`) →
    `.claude/hooks/pre_tool_env_guard.sh`

### `.claude/hooks/session_start.sh`
- Prints branch + ahead/behind vs. upstream + working-tree state
  (clean / N uncommitted changes) on session start.
- Silent exit when not inside a git repo.

### `.claude/hooks/pre_tool_env_guard.sh` + `_env_guard.py`
- Defence-in-depth on top of `permissions.deny`.
- Inspects `tool_input.file_path` and `tool_input.command` for
  `.env*` / `secrets/` references.
- Blocks (`exit 2`) with a clear, friendly stderr message:
  - what was blocked (path or command excerpt)
  - why (project policy)
  - how to grant a one-off exception (developer copy-pastes the
    relevant value)
- Tested against positive and negative inputs (Read on `/foo/.env`,
  bash `cat /foo/.env`, plain `ls`, plain file Read).

### Stop hook
- **Not configured here** — Step 6 (Quality & Review) covers the
  full quality-gate Stop hook. Out of scope for Step 2.

## Test Results (PHASE 6 verification)
- `session_start.sh` prints the expected single-line summary.
- `pre_tool_env_guard.sh`:
  - Read `/foo/.env` → blocked, exit 2 ✓
  - Read `/foo/safe.txt` → allowed, exit 0 ✓
  - Bash `cat /foo/.env` → blocked, exit 2 ✓
  - Bash `ls` → allowed, exit 0 ✓
- `settings.json` parses as valid JSON ✓

## Next
- Step 3: Planning Tool Integration (MCP server, sprint context).
