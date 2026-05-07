# Design Document — i18n-backfill-zh-json

## Overview

**Purpose**: Backfill ten English-only values in `locales/zh.json` with
natural Chinese translations so the Chinese UI renders fully Chinese
labels on Step 3, Step 4, Step 5, and the graph panel, plus the Step 2
log line that prints a task ID.

**Users**: Chinese-locale UI users; secondarily, frontend engineers and
i18n reviewers who depend on `en.json` and `zh.json` being structurally
aligned.

**Impact**: Pure data change — modifies values for ten keys in
`locales/zh.json`. No code, no schema, no contract changes. Tracks
GitHub issue #8.

### Goals

- Translate the nine user-facing English values into natural Chinese.
- Translate `log.prepareTaskId` to Chinese (gap analysis confirmed it is
  user-facing) while preserving the leading two-space indent, the `└─`
  glyph, and the `{taskId}` placeholder.
- Keep `home.heroDescBrand` literally as `MiroFish` (proper noun).
- Keep `locales/en.json` and `locales/zh.json` structurally aligned
  (same scalar key paths, same key order in unchanged objects).

### Non-Goals

- Translating `en.json` (covered by other epic tickets).
- Restructuring the locale files or the i18n loader.
- Adding new keys for currently-untranslated UI elements.
- Any frontend code change (`*.vue` / `*.js` / `*.ts`).

## Boundary Commitments

### This Spec Owns

- The values of exactly ten scalar keys in `locales/zh.json`:
  `home.heroDescBrand`, `step3.waitingForActions`,
  `step4.waitingForReportAgent`, `step5.interactiveTools`,
  `step5.agentsAvailable`, `step5.reportAgentChat`,
  `graph.panelTitle`, `graph.nodeDetails`, `graph.relationship`,
  `log.prepareTaskId`.
- The decision and rationale for `log.prepareTaskId` (translate, see
  research.md).

### Out of Boundary

- Any other value in `locales/zh.json` (must remain byte-identical).
- Any value in `locales/en.json` or `locales/languages.json`.
- The i18n loader, the Vue components that consume these keys, and any
  backend code.

### Allowed Dependencies

- The existing structural contract: `locales/en.json` and
  `locales/zh.json` MUST contain the same set of scalar key paths
  (verified by the `jq paths(scalars)` diff).
- The existing placeholder syntax used by `vue-i18n`
  (`{count}`, `{taskId}`, …).

### Revalidation Triggers

- A change to `vue-i18n` placeholder syntax (none expected).
- Any new English key added to `en.json` after this spec lands — that is
  a separate ticket (out of scope) and would invalidate the alignment
  diff if not mirrored to `zh.json`.

## Architecture

### Existing Architecture Analysis

- Locale files are flat JSON trees grouped by feature
  (`home`, `step3`, `step5`, `graph`, `log`, …) and consumed by
  `vue-i18n` via `frontend/src/i18n/`.
- `locales/en.json` and `locales/zh.json` are kept structurally aligned
  by convention; the alignment is verified by the `jq paths(scalars)`
  diff cited in the requirements doc and is currently empty.
- Translation convention in `zh.json`: surrounding `step*`, `graph.*`,
  and `log.*` values are direct natural-Chinese renderings of their
  English siblings, preserving placeholders and any leading/trailing
  glyphs.

### Architecture Pattern & Boundary Map

This change has no architectural surface area — it is a value-only edit
inside a configuration data file. No diagram needed.

- Selected pattern: **In-place data edit** of `locales/zh.json`.
- Domain boundary: locale data only.
- Existing patterns preserved: `vue-i18n` key/value contract; placeholder
  syntax; key order; key set.
- New components: none.
- Steering compliance: matches `tech.md`'s i18n setup
  (`vue-i18n` + JSON files in `/locales/`); no new dependency.

### Technology Stack

| Layer | Choice / Version | Role in Feature | Notes |
|-------|------------------|-----------------|-------|
| Frontend | `vue-i18n` | Consumes the translated keys at runtime | Unchanged |
| Data | `locales/zh.json` (UTF-8 JSON) | Storage of the translated values | Only file edited |
| Tooling | `jq`, `python -c "import json"` | Validation of JSON parseability and key alignment | No new tool |

## File Structure Plan

### Modified Files

- `locales/zh.json` — replace the value of ten specific keys (see the
  table in *Translation Contract* below). No keys are added, removed,
  reordered, or restructured.

No other file is touched.

## Requirements Traceability

| Requirement | Summary | Realized by |
|-------------|---------|-------------|
| 1.1 | Step 3 waiting label is Chinese | Edit value of `step3.waitingForActions` |
| 1.2 | Step 4 waiting label is Chinese | Edit value of `step4.waitingForReportAgent` |
| 1.3 | Step 5 labels are Chinese | Edit values of `step5.interactiveTools`, `step5.agentsAvailable`, `step5.reportAgentChat` |
| 1.4 | Graph panel labels are Chinese | Edit values of `graph.panelTitle`, `graph.nodeDetails`, `graph.relationship` |
| 1.5 | `step5.agentsAvailable` keeps `{count}` once, naturally placed | Translation contract row |
| 1.6 | `home.heroDescBrand` stays `MiroFish` | No edit (verified by spot check) |
| 2.1 | Decision recorded if scaffold kept English | N/A — decision is to translate (R2.2) |
| 2.2 | Translate scaffold preserving indent / `└─` / `{taskId}` | Edit value of `log.prepareTaskId` |
| 2.3 | PR description lists English-by-design keys | Done at /done time (PR description) |
| 3.1 | `en.json` ↔ `zh.json` key sets identical | Validated by alignment diff in *Validation Strategy* |
| 3.2 | Key order preserved in unchanged objects | Enforced by using `Edit` (string replace) only |
| 3.3 | Placeholders preserved byte-for-byte | Enforced by translation contract + parse check |
| 3.4 | Reject change if placeholder drifts | Enforced by review + grep check in *Validation Strategy* |
| 3.5 | `zh.json` remains valid JSON | Enforced by `jq empty` check |
| 4.1 | Only `locales/zh.json` changes | Enforced at /done time (`git status` review) |
| 4.2 | No add/rename/delete of keys | Enforced by using `Edit` only on values |
| 4.3 | If a value is already Chinese (upstream change), skip and note | Enforced by pre-edit re-read of current values |

## Components and Interfaces

There is no software component to design. The "interface" is the set of
exact value strings that `locales/zh.json` will contain after the
change.

## Translation Contract

The implementation MUST replace each listed value with exactly the
target string below, using `Edit` (string replace) on the JSON value
only. Leading/trailing whitespace inside the JSON value, all
placeholders, and the surrounding double quotes / commas are preserved
because the Edit operates only on the value bytes.

| Key | Current value (English) | Target value (Chinese) |
|-----|--------------------------|------------------------|
| `home.heroDescBrand` | `MiroFish` | `MiroFish` (unchanged — brand) |
| `step3.waitingForActions` | `Waiting for agent actions...` | `等待智能体执行动作...` |
| `step4.waitingForReportAgent` | `Waiting for Report Agent...` | `等待报告智能体...` |
| `step5.interactiveTools` | `Interactive Tools` | `交互工具` |
| `step5.agentsAvailable` | `{count} agents available` | `{count} 个智能体可用` |
| `step5.reportAgentChat` | `Report Agent - Chat` | `报告智能体 - 对话` |
| `graph.panelTitle` | `Graph Relationship Visualization` | `图谱关系可视化` |
| `graph.nodeDetails` | `Node Details` | `节点详情` |
| `graph.relationship` | `Relationship` | `关系` |
| `log.prepareTaskId` | `  └─ Task ID: {taskId}` | `  └─ 任务 ID: {taskId}` |

Translation rationale (matches existing `zh.json` conventions):

- "Agent" → "智能体" (e.g. existing `agent.title: "🤖 智能体详情"`).
- "Report Agent" → "报告智能体" (e.g. existing
  `step4.reportAgentReady: "报告智能体就绪"`).
- "Task ID" → "任务 ID" (Chinese tech UI keeps "ID" as a loanword;
  preserves the two-space indent and the `└─` continuation glyph used
  across the surrounding `log.*` lines).
- The trailing `...` is preserved on `waitingForActions` and
  `waitingForReportAgent` because it is a meaningful UI cue ("in
  progress") and the English source uses it.
- The ` - ` separator in `step5.reportAgentChat` is kept literally so the
  Chinese label keeps the same visual structure as the English one.

## Data Models

Not applicable. No schema or domain model is defined or changed.

## Error Handling

The only failure modes are (a) invalid JSON after edit and
(b) accidental key-set drift. Both are caught by the validation script
in the next section before the change is committed.

## Testing Strategy

### Static checks (mandatory before commit)

1. `jq empty locales/zh.json` — file remains valid JSON.
2. `diff <(jq -r 'paths(scalars) | join(".")' locales/en.json | sort)
   <(jq -r 'paths(scalars) | join(".")' locales/zh.json | sort)` —
   produces no output (key sets identical).
3. `jq -r '<key>' locales/zh.json` for each of the ten keys — output
   matches the *Target value* column of the Translation Contract.
4. `git diff --stat` shows exactly one file changed: `locales/zh.json`.
5. `git diff locales/zh.json` shows only value changes (no key adds,
   removes, or reorders) — visually confirm via `grep -nE
   '^[+-]' <(git diff locales/zh.json)` that every `+` line has a
   matching `-` line for the same key.

### Manual smoke test (recommended, optional)

- Run `npm run dev`, switch UI to Chinese (`zh`), and visit:
  - Step 2 (look for the translated `└─ 任务 ID: …` log line),
  - Step 3 (waiting state placeholder),
  - Step 4 (waiting state placeholder),
  - Step 5 (Interactive Tools heading, agent count, Report Agent chat
    panel title),
  - Graph panel (title, node details, relationship label).
- Confirm no English text remains for the targeted UI elements.

## Supporting References

- `.kiro/specs/i18n-backfill-zh-json/gap-analysis.md` — current-state
  inventory, `log.prepareTaskId` usage analysis, and the rationale for
  Option A (single targeted edit).
- `.ticket/8.md` — original GitHub issue snapshot.
