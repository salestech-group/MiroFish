---
description: List GitHub issues for this project with selectable filters
argument-hint: (no args — interactive)
---

# /ticket-list — Show GitHub issues for this project

You are running the `/ticket-list` slash command. The user wants an overview of issues for the current project's GitHub repo so they can decide what to pick up next.

## Repository

Read the target repo from `.ticket/repo.md` (look for the `Repo (owner/name)` line). If the file does not exist, ask the user for the `owner/name` slug, write it to `.ticket/repo.md`, then continue.

Set `REPO` to that value (e.g., `salestech-group/MiroFish`).

## Filters — ask the user first

Before running anything, ask which subset of issues to list. Offer these toggles (the user can answer in plain language; default any unanswered to "no"):

1. **Include closed?** (default: no — open only)
2. **Status filter:**
   - "todo" / "no assignee" — only issues that nobody is working on yet
   - "in-progress" — only issues with the `in-progress` label or a self-assignee
   - "all open" — no status filter
3. **Assigned to me only?** (default: no)
4. **Milestone / sprint:** the user can name a milestone, or skip
5. **Label filter:** optional comma-separated labels to require

Wait for the user's answers before running `gh`.

## Run the query

Build a single `gh issue list` invocation from the answers. Useful flags:

```bash
gh issue list --repo "$REPO" \
    --state open                                  # or "all" / "closed"
    --assignee "@me"                              # if "assigned to me only"
    --label "in-progress"                         # if status=in-progress
    --label "<label1>,<label2>"                   # if user gave label filter
    --milestone "<milestone>"                     # if user named one
    --limit 50 \
    --json number,title,state,labels,assignees,milestone,updatedAt,url
```

For "todo / no assignee" issues, GitHub doesn't expose a `--no-assignee` flag — list open issues without `--assignee` and **filter the JSON locally** to keep only items where `.assignees == []`.

## Output

Render a compact table (markdown) ordered by `updatedAt` desc:

| # | Title | Labels | Assignees | Milestone | Updated |

Truncate titles to ~70 chars; show `—` for empty fields. End with a one-line hint: *"Pick one: `/ticket <number>` to start work."*

If there are no results, say so plainly and suggest relaxing a filter.

## Constraints

- Use `gh` exclusively. Do not call the REST API directly.
- Be conservative with output size — cap at 50 rows by default.
- Don't refetch on every minor question; ask once, then run once.
