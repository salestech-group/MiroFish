---
description: Finish a ticket — branch, commit, push, and open a PR closing the issue
argument-hint: [--draft] (optional — open the PR as a draft)
---

# /done — Ship the work

You are running the `/done` slash command. The user typed:

```
/done $ARGUMENTS
```

Goal: take the work that has just been completed for the active ticket and turn
it into a pull request — branch, commit, push, open PR, link the issue. This is
the final step of the ticket → plan → implement → ship workflow.

## Repository

Read the target repo from `.ticket/repo.md` (the `Repo (owner/name)` line). Set
`REPO` to that value (e.g. `salestech-group/MiroFish`) and use it explicitly in
every `gh` command via `--repo "$REPO"`.

## Step 0 — Determine the active ticket and spec

1. **Ticket.** List `.ticket/*.md` excluding `repo.md` and `.gitkeep`.
   - Exactly one snapshot → use it.
   - Multiple → pick the one with the newest `workingSince` in its frontmatter
     (fall back to the file with the most recent mtime).
   - Zero → ask the user for the issue number, or abort if no human is present.

   Extract `<number>` and `<title>` from the frontmatter.

2. **Spec.** Look under `.kiro/specs/`. Pick the spec directory whose
   `spec.json` references this ticket number, or — if none reference it
   explicitly — the most recently modified spec. Note the directory as
   `<spec-dir>` for the PR body.

## Step 1 — Sanity checks (abort early if any fail)

- `git status` is clean of unrelated noise. If there are changes outside
  `.kiro/specs/<spec-dir>/` and the directories your implementation touched,
  warn and ask before continuing.
- No `.env`, credentials, or files matching `.gitignore` patterns are staged.
- The current branch is **not** `main` or `dev`. If it is, you will create a
  new branch in the next step.
- Working tree has at least one change to commit. If not, abort with a clear
  message — there is nothing to ship.

## Step 2 — Determine commit type and branch name

1. **Type.** Inspect the diff and the ticket title to choose one of:
   `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`, `perf`.
   Default to `feat` for new functionality and `fix` for bug-fix tickets.

2. **Scope.** Optional. Use a short kebab-case area name if one is obvious from
   the changed paths (e.g. `auth`, `graph`, `simulation`). Omit the parens
   entirely if no clear scope.

3. **Branch name.** Format:

   ```
   <type>/<issue-number>-<short-kebab-summary>
   ```

   Example: `feat/142-add-two-factor-auth`. Keep the summary ≤ 50 chars.

4. **Branch handling.**
   - If the current branch already matches `<type>/<issue-number>-*`, reuse it.
   - Otherwise create and switch:
     `git checkout -b "$BRANCH"`.
   - Never reset, force-checkout, or delete an existing branch.

## Step 3 — Stage and commit

1. **Stage explicitly.** Add only the files this work intentionally changed
   plus the spec directory. Do NOT use `git add -A` or `git add .`. Examples:

   ```bash
   git add backend/app/services/foo.py
   git add frontend/src/components/Bar.vue
   git add .kiro/specs/<spec-dir>/
   ```

   `.ticket/<n>.md` is gitignored — do not stage it.

2. **Commit message.** Conventional Commits, per
   `.claude/rules/commits.md`:

   ```
   <type>(<scope>): <imperative summary, lowercase, ≤72 chars, no period>

   <body — what changed and WHY, not how>

   Closes #<issue-number>
   ```

   **Hard rules:**
   - Lowercase summary. No trailing period. Imperative mood ("add", not
     "added"/"adds").
   - **No `Co-Authored-By:` trailer.** The project rule explicitly forbids AI
     watermarks.
   - **No `--no-verify`**, `--no-gpg-sign`, or other hook bypasses. If a
     pre-commit hook fails, fix the underlying issue and create a new commit
     (do not amend).
   - Always pass the message via a HEREDOC for clean formatting:

     ```bash
     git commit -m "$(cat <<'EOF'
     <type>(<scope>): <summary>

     <body>

     Closes #<issue-number>
     EOF
     )"
     ```

3. If the work spans multiple unrelated concerns, split into multiple commits
   on the same branch — one per concern — rather than mixing them.

## Step 4 — Push

```bash
git push -u origin "$BRANCH"
```

If the push is rejected (remote has commits the local branch doesn't), stop
and surface the error. Do **not** force-push.

## Step 5 — Open the pull request

```bash
gh pr create --repo "$REPO" \
    --base main --head "$BRANCH" \
    --title "<same as the commit summary>" \
    --body "$(cat <<'EOF'
## Summary

- <1-3 bullets describing what changed and why>

## Spec

See `.kiro/specs/<spec-dir>/` for requirements, design, and tasks.

## Test plan

- [ ] <what to verify locally>
- [ ] <edge case to check>

Closes #<issue-number>
EOF
)"
```

If `$ARGUMENTS` contains `--draft`, append `--draft` to the `gh pr create`
invocation. Use draft mode whenever the implementation is incomplete or
`/kiro:validate-impl` flagged outstanding issues that were not resolved.

## Step 6 — Confirm

Print one line: the PR URL. Nothing else.

## Constraints

- Never push to `main` or `dev` directly.
- Never force-push (`--force` / `--force-with-lease`).
- Never bypass hooks or signing.
- Never stage `.env` files, credentials, or secrets.
- Never add `Co-Authored-By:` trailers.
- Use `gh` exclusively for GitHub interactions.
- Be quiet on success (one-line PR URL). Be loud on failure (state what
  failed and the next action).
