# Step 0 — Code Conventions & Rules

Documentation of the rules and code conventions configured during the
Claude Code workspace setup (Step 0).

## Context
- **Project:** MiroFish — Multi-Agent Swarm Intelligence Prediction Engine
- **Stack:** Python (Flask, uv) backend + Vue 3 / Vite frontend
- **Date applied:** 2026-05-06

## What Was Configured

### 1. `.claude/settings.json` — Permissions
**Always allow (bash):**
- `cd:*`
- `ls:*`
- `find:*`
- `cat:*`
- `mkdir:*`

**Always deny (Read / Write / Edit):**
- `*/.env*`
- `*/secrets/*`

**Always deny (bash):**
- `rm -f*`
- `rm -rf*`
- `git push -f*`
- `git push --force*`

This protects secrets and forbids destructive Git / filesystem
operations while allowing safe navigation and inspection commands.

### 2. `.claude/rules/` — Rule Files

| File | Purpose |
|------|---------|
| `markdown.md` | Adhere to standard Markdown syntax (markdownguide.org). |
| `file-paths.md` | Always wrap file paths in quotes; use a generic placeholder path in docs/examples. |
| `commits.md` | Conventional Commits standard; never add `Co-Authored-By:` watermarks. |
| `error-handling.md` | When an error occurs, offer to save it as a rule. |
| `dev-guidelines.md` | Salestech Products Development Guidelines (live source on Notion). |

### 3. Salestech Development Guidelines
- **Notion source (authoritative):** https://candylabs.notion.site/development-guidelines
- A summary snapshot is stored in `.claude/rules/dev-guidelines.md`.
- Always consult the live document via the Notion MCP server for the
  latest version.
- Snapshot covers: formatting & style, naming, comments,
  Git workflow, React & TypeScript, Tailwind 4, folder structure,
  accessibility, environments / secrets / dependencies, security,
  infrastructure, enforcement.

### 4. Commit Watermarks
- `Co-Authored-By:` blocks must **never** be added to commits
  (matches §4.2 of the dev guidelines: *"Avoid 'watermarks' like
  'co-authored by Claude'"*).

## Manual Setup Items (Not Automated)
The following items in Step 0 are user / environment setup and are
**not** performed by this onboarding pass — they must be completed by
the developer:

1. **Claude Code clients**
   - Claude Desktop, Claude Code CLI, VSCode extension
2. **MCP servers** (run from terminal, not from inside Claude)
   - Notion: `claude mcp add --transport http notion https://mcp.notion.com/mcp`
   - Atlassian: `claude mcp add --transport http atlassian https://mcp.atlassian.com/v1/mcp`
   - Figma: `claude mcp add --transport http figma-remote-mcp https://mcp.figma.com/mcp`
   - Authenticate each via `/mcp` in Claude after restart.
3. **Basics**
   - Node.js (https://nodejs.org/en) — required for CC-SDD.
   - Git + GitHub CLI (`gh auth login`) — required for PRs.

## Next
- Step 1: Prepare the codebase (CLAUDE.md, README.md, structure)
