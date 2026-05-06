---
description: Pull a GitHub issue into the local ticket workspace and mark it as in-progress
argument-hint: <issue-number>
---

# /ticket — Start work on a GitHub issue

You are running the `/ticket` slash command. The user has typed:

```
/ticket $ARGUMENTS
```

Goal: pick up the GitHub issue identified by `$ARGUMENTS`, transition it to "in progress", and snapshot it as a markdown file under `.ticket/` so later steps (planning, implementation) can read its description without making more API calls.

## Repository

Read the target repo from `.ticket/repo.md` (look for the `Repo (owner/name)` line). If the file does not exist, ask the user for the `owner/name` slug, write it to `.ticket/repo.md`, then continue.

Set `REPO` to that value (e.g., `salestech-group/MiroFish`) and use it explicitly in every `gh` command via `--repo "$REPO"`.

## Steps

1. **Validate input.** `$ARGUMENTS` must be a non-empty issue number (or a string GitHub will accept). If empty, ask the user for the issue number and stop.

2. **Fetch the issue.**
   ```bash
   gh issue view "$ARGUMENTS" --repo "$REPO" \
       --json number,title,state,url,labels,assignees,milestone,author,createdAt,updatedAt,body
   ```
   If this fails, surface the error and stop. Common causes: wrong number, no access, network.

3. **Mark as in-progress.** GitHub Issues has no built-in "in progress" state. Approximate it:
   - Self-assign: `gh issue edit "$ARGUMENTS" --repo "$REPO" --add-assignee @me`
   - Try to add the `in-progress` label. If the label does not exist, do not create it — just continue without it. (`gh issue edit ... --add-label in-progress 2>/dev/null || true`)
   - If the user indicates the project uses a different label or a GitHub Project with a status field, follow that instead.

4. **Snapshot to `.ticket/<number>.md`.** Write a markdown file with this structure (replace fields from the JSON above):

   ```markdown
   ---
   number: <number>
   title: <title>
   state: <state>
   url: <url>
   author: <author.login>
   assignees: <comma-separated logins, "—" if none>
   labels: <comma-separated names, "—" if none>
   milestone: <milestone.title or "—">
   createdAt: <createdAt>
   updatedAt: <updatedAt>
   workingSince: <today YYYY-MM-DD>
   ---

   # #<number> — <title>

   <body verbatim from the issue>
   ```

   This description is consumed by later planning steps — keep it intact.

5. **Confirm to the user.** One short summary: ticket number, title, current state, what was changed (assignee, label), and the path to the snapshot. Don't dump the whole body back to the terminal.

## Constraints

- Use `gh` exclusively for GitHub. Do not call the REST API directly.
- Do not commit `.ticket/<number>.md` — the directory is gitignored except for `repo.md` / `.gitkeep`.
- Be quiet on success. Be loud on failure (state what failed and the next action).
