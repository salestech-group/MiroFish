---
description: Plan a feature or fix using Spec-Driven Development (CC-SDD / Kiro). Mandatory before code.
argument-hint: [task-description] (optional — falls back to the active ticket)
---

# /plan — Plan before you code (MANDATORY)

You are running the `/plan` slash command. The user typed:

```
/plan $ARGUMENTS
```

**Rule:** No feature without a plan. No code without an approved plan. This command sets up a spec via CC-SDD (Kiro) and walks the user through Requirements → Design → Tasks before any implementation.

## Step 0 — Determine the source description

1. If `$ARGUMENTS` is non-empty → use it verbatim as the task description.
2. Otherwise, look for ticket snapshots in `.ticket/`:
   - List files matching `.ticket/*.md` excluding `repo.md` and `.gitkeep`.
   - If exactly one snapshot exists → use the body of that ticket as the description (and report which ticket).
   - If multiple exist → ask the user which one (`#42`, `#17`, …).
   - If none exist → ask the user "What should I plan?" and stop until they answer.

Treat the resulting text as **the task brief** for the rest of this command.

## Step 1 — Activate Plan Mode

Stay in research/read-only mode for the rest of this command. **Do not edit production code, do not run migrations, do not write code files outside `.kiro/specs/`.** Reading code, running `gh`, and creating files under `.kiro/specs/` are permitted.

## Step 2 — Run the Kiro spec flow

Invoke the Kiro slash commands installed by `cc-sdd` (in `.claude/commands/kiro/`). The expected sequence is:

1. **`/kiro:steering`** — only if `.kiro/steering/` is empty. Establishes product/tech/structure steering docs from the codebase. Skip if steering already exists.
2. **`/kiro:spec-init <task brief>`** — creates `.kiro/specs/<feature>/` with `spec.json` and `requirements.md` skeleton.
3. **`/kiro:spec-requirements`** — fills in requirements (EARS format).
4. **`/kiro:validate-gap`** — gap-analysis review of requirements before design (recommended in the project workflow).
5. **`/kiro:spec-design`** — produce the design document.
6. **`/kiro:validate-design`** — design-review gate.
7. **`/kiro:spec-tasks`** — break the design into tasks with parallel-work analysis.

After each Kiro command, **show the resulting artefact and stop for human approval** before moving to the next phase. The plan is not approved until the user explicitly says so.

## Step 3 — Persistence

CC-SDD stores everything under `.kiro/specs/<feature>/`. Do not duplicate plans elsewhere — that directory is the source of truth.

If a `.ticket/<n>.md` snapshot is associated with this work, link it from `spec.json` (or note the ticket number in `requirements.md`) so the trace from issue → spec is preserved.

## Step 4 — Implementation handoff

Implementation is **a separate, explicit step**:

- Use **`/kiro:spec-impl`** to execute tasks against the approved plan.
- Check progress against the plan **after every task** (the project's chosen checkpoint cadence).
- Use **`/kiro:validate-impl`** at the end to verify the implementation matches the spec.
- Use **`/kiro:spec-status`** at any time to see where the spec stands.

If the user asks to "just code it" without going through the spec, push back and remind them of the rule. Approval first, then code.

## Output expectation

Be terse. State which step you ran, what artefact it produced, and what the user needs to review. One short paragraph per phase, not a wall of text.
