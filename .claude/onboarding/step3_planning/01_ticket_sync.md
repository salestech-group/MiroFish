# Step 3 — Ticket Sync (GitHub Issues + gh CLI)

## Date: 2026-05-06

## Tooling Decision (vs. the original Notion prompt)
The Notion prompt is Jira/MCP-oriented. For this project we use:

- **Issue tracker:** GitHub Issues at https://github.com/salestech-group/MiroFish
- **Transport:** the `gh` CLI (already installed and authenticated as
  `dseemann`).
- **No Atlassian MCP usage in these commands** — `gh` is faster, scoped
  by token, and matches the rest of the team's Git workflow.

Equivalences vs. the prompt:
- *"board.md"* → `.ticket/repo.md` (stores `owner/name`).
- *"IN ARBEIT" transition* → GitHub doesn't have a built-in
  in-progress state; we approximate it with self-assignment + an
  `in-progress` label (graceful fallback if the label doesn't exist).

## What Was Created

### `.ticket/`
- Directory created. Most contents are gitignored — only `repo.md` and
  `.gitkeep` are tracked, so the local cache of in-progress tickets
  stays out of the repo.
- `.ticket/repo.md` — declares `salestech-group/MiroFish` as the
  target repo.
- `.gitignore` — added `.ticket/*` with negations for `repo.md` and
  `.gitkeep`.

### `.claude/commands/ticket.md`
Slash command: `/ticket <issue-number>`
- Reads the repo from `.ticket/repo.md`.
- `gh issue view --json …` to fetch the issue.
- Self-assigns (`gh issue edit --add-assignee @me`).
- Tries to add the `in-progress` label; silently skips if the label
  doesn't exist on the repo.
- Snapshots the issue (frontmatter + full body) to `.ticket/<n>.md` so
  later planning / implementation steps have the description without
  re-fetching.

### `.claude/commands/ticket-list.md`
Slash command: `/ticket-list` (interactive)
- Reads the repo from `.ticket/repo.md`.
- Asks the user for filters before running anything:
  - include closed
  - status (todo / in-progress / all open)
  - assigned to me only
  - milestone
  - labels
- Builds a single `gh issue list` invocation from the answers.
- For "no assignee" filtering, post-processes the JSON locally because
  `gh` has no `--no-assignee` flag.
- Renders a compact markdown table; ends with a hint to use
  `/ticket <n>` to start work.

### `.claude/settings.json`
- Allow-listed `gh issue view/list/edit/comment`, `gh repo view`,
  `gh pr view/list`, `gh auth status` so the slash commands run
  without permission prompts.

## Verification
- `gh issue list --repo salestech-group/MiroFish --state open` returned
  the open issue list (issue #1 currently open).
- `settings.json` parses as valid JSON.
- `gh auth status` confirmed (token: `ghp_…`, scopes incl. `repo`).

## Limitations / Notes
- "In progress" semantics on GitHub Issues is convention-driven. If
  the team adopts a GitHub Project (v2) with a Status field, update
  the `/ticket` command to call `gh project item-edit …` instead of
  the label/assignee approximation.
- Atlassian MCP setup from Step 0 is unused here. Leave it configured
  for any cross-project Jira lookups.

## Next
- Step 4: Planning (MANDATORY) — `/plan` command, persistence, hooks.
