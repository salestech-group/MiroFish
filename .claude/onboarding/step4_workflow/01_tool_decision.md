# Step 4 — Planning Tool Decision

## Date: 2026-05-06

## Decisions

| Question | Choice |
|----------|--------|
| Q1 — Planning tool | **CC-SDD** (Claude Code Spec Driven Development, Kiro flow). Recommended in the Salestech onboarding doc and matches the project's expected `spec-init → spec-design → spec-tasks → spec-impl → spec-validate` workflow. |
| Q2 — Plan persistence | **In-tool** — `.kiro/specs/<feature>/`. CC-SDD owns this directory; no parallel `.claude/plans/` needed. |
| Q3 — Checkpoint cadence | **After every task** — strictest setting; matches the project rule "no code without an approved plan". |

## What CC-SDD installed

The user ran `npx cc-sdd@latest --claude --lang en` in the terminal.
The installer added:

- **`.kiro/settings/`** — rules and templates that drive the Kiro flow:
  - `rules/` — design-discovery, EARS format, requirements/design review gates, gap analysis, steering principles, tasks generation, parallel-analysis.
  - `templates/specs/` — `requirements.md`, `design.md`, `tasks.md`, `research.md`, `init.json`, `requirements-init.md`.
  - `templates/steering/` — `product.md`, `tech.md`, `structure.md`.
  - `templates/steering-custom/` — optional steering docs (api-standards, auth, db, deployment, error-handling, security, testing).
- **`.claude/commands/kiro/`** — slash commands invoked by the Kiro flow:
  - `/kiro:steering`, `/kiro:steering-custom`
  - `/kiro:spec-init`, `/kiro:spec-requirements`, `/kiro:spec-design`, `/kiro:spec-tasks`, `/kiro:spec-impl`, `/kiro:spec-status`
  - `/kiro:validate-gap`, `/kiro:validate-design`, `/kiro:validate-impl`

Notes:
- The installer **did not append to `CLAUDE.md`** in this run, so no
  refactor was needed afterwards. (Some CC-SDD versions append; this
  one didn't.)
- `.kiro/` is **not** gitignored — specs and steering docs are project
  artefacts that need to be shared with the team.

## Slash command added: `/plan`

Created `.claude/commands/plan.md`. Behaviour:
1. **Source description**: uses `$ARGUMENTS`, or falls back to a single
   `.ticket/<n>.md` snapshot, or asks the user.
2. **Plan mode**: read-only research; no production-code edits.
3. **Kiro flow**:
   `/kiro:steering` (only if `.kiro/steering/` is empty) →
   `/kiro:spec-init` → `/kiro:spec-requirements` →
   `/kiro:validate-gap` → `/kiro:spec-design` →
   `/kiro:validate-design` → `/kiro:spec-tasks`.
   **Stops for human approval after each artefact.**
4. **Persistence**: in `.kiro/specs/<feature>/`. Ticket linkage noted
   in `spec.json` / `requirements.md`.
5. **Implementation handoff**: separate, explicit step using
   `/kiro:spec-impl`, with `/kiro:validate-impl` at the end and
   `/kiro:spec-status` for progress checks.

The command rejects "just code it" requests — approval-first is
enforced.

## SessionStart hook extended

`.claude/hooks/session_start.sh` now also prints:

- **Active tickets** — issue numbers cached under `.ticket/` (excludes
  `repo.md`/`.gitkeep`).
- **Open specs** — directory names under `.kiro/specs/`, with phase /
  status pulled from each `spec.json` if available.

The branch + working-tree-state line is preserved.

## Open follow-ups

- **Run `/kiro:steering`** in a new Claude session to seed `.kiro/steering/` with product/tech/structure context (recommended in brownfield setups). Out of scope for this onboarding pass — flagged for the developer.
- The Stop hook (quality gate around plans / tests / lint) is built in **Step 6**.

## Next
- Step 5: Agents & Skills (subagents, skills, rules from tech-stack).
