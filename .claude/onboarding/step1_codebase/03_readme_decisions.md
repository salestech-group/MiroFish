# Step 1 — README Decisions

Decisions made while reviewing / repairing the READMEs (Step 1, PROMPT 3).

## Date: 2026-05-06

## Critical Finding
`README.md` contained **unresolved git merge conflict markers**
(`<<<<<<< HEAD` / `=======` / `>>>>>>>`) at two locations: the
prerequisites table and the env-vars block. These were left over from
the recent `feat/graphiti-neo4j-migration` merge (commit `6264828`) and
needed to be resolved as part of Step 1.

`README-EN.md` and `README-ZH.md` did **not** have markers but the ZH
file still referenced the previous knowledge-graph backend (out of date).

## Decisions

| Question | Decision |
|----------|----------|
| Q1 — Resolve conflicts? | **Take Neo4j-branch content** (Neo4j prerequisite + Neo4j env vars). Stale references removed. |
| Q2 — Prerequisites refinement? | **Out of scope for now.** Kept Neo4j install instructions as-is, will be revisited separately. |
| Q3 — Add `LLM_BOOST_*` to README env vars? | **Yes.** Added as an optional block with a note to omit entirely if not used (matches `.env.example`). |
| Q4 — Installation flow? | **Always assume Docker.** Reordered: Docker is now Option 1 (Recommended); Source is Option 2. |
| Q5 — Sync three READMEs? | **Yes.** All three updated to reflect Neo4j and Docker-first install. |

## What Changed

### `README.md` (English default)
- Resolved both merge conflict regions (prerequisites + env vars).
- Reordered: **Docker first** (Option 1, recommended), Source second
  (Option 2).
- Added `LLM_BOOST_*` optional env-var block with omit-if-unused note.
- Removed the redundant note at end of source-deploy block.

### `README-EN.md` (explicit English)
- Fixed language switcher: was `[English](./README-EN.md) | [中文文档](./README.md)` — now points to the correct files (`README.md` is English, `README-ZH.md` is Chinese).
- Reordered Docker-first / Source-second to match `README.md`.
- Added `LLM_BOOST_*` optional block.

### `README-ZH.md` (Chinese)
- Removed the stale knowledge-graph env-var section.
- Added Neo4j prerequisite row + install instructions (translated).
- Added `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` /
  `EMBEDDING_MODEL` env-var block (translated).
- Reordered Docker-first / Source-second to match `README.md`.
- Added `LLM_BOOST_*` optional block (translated).
- Added the Graphiti + Neo4j note in Chinese.

## Verification
- `grep` for `<<<<<<<` / `>>>>>>>` / `=======` across all three READMEs
  and `CLAUDE.md` returned no matches.
- All three files are valid Markdown.
- Language-switcher links between the three files are now consistent.

## Step 1 — Complete
Outputs:
- `.claude/onboarding/step1_codebase/01_repo_analysis.md`
- `.claude/onboarding/step1_codebase/02_conventions.md`
- `.claude/onboarding/step1_codebase/03_readme_decisions.md`

Updated files:
- `CLAUDE.md` (Neo4j+Graphiti primary, full env vars,
  must-respect rules, project-internal coding conventions).
- `README.md` / `README-EN.md` / `README-ZH.md` (Docker-first flow,
  Neo4j env vars, optional LLM_BOOST, language-switcher fixed).

## Next
- Step 2: Claude Setup (settings.json, hooks, permissions)
