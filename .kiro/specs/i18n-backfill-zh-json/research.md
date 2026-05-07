# Research & Design Decisions — i18n-backfill-zh-json

## Summary

- **Feature**: `i18n-backfill-zh-json`
- **Discovery Scope**: Simple Addition (data-only edits to one JSON file).
- **Key Findings**:
  - All ten flagged keys in `locales/zh.json` currently hold the exact
    English value listed in issue #8 (verified via `jq`).
  - `en.json` and `zh.json` key sets are currently identical
    (`paths(scalars)` diff is empty), so we must preserve that
    invariant.
  - `log.prepareTaskId` is consumed by `Step2EnvSetup.vue:801` via
    `addLog(t('log.prepareTaskId', { taskId: ... }))` — it IS
    user-facing, and surrounding `log.*` keys are translated; therefore
    we translate it.

## Research Log

### Current values of the targeted keys
- **Context**: Confirm the issue's claim that ten specific values are
  English-only.
- **Sources Consulted**: `locales/zh.json`, `locales/en.json` (via `jq`).
- **Findings**:
  - Each of the ten target keys in `zh.json` matches the English value
    in `en.json` byte-for-byte today.
  - `home.heroDescBrand` is the brand name `MiroFish` and should stay
    English.
- **Implications**: Direct value replacement is safe; no upstream
  changes have already translated any of them.

### `log.prepareTaskId` usage classification
- **Context**: Issue requires a documented decision on whether this
  value is locale-neutral scaffold or a user-facing string.
- **Sources Consulted**: `Grep` for `prepareTaskId` across the repo;
  inspection of `frontend/src/components/Step2EnvSetup.vue:801`;
  inspection of sibling `log.*` values in `zh.json`.
- **Findings**:
  - The key is rendered into the in-UI log panel via `addLog(t(...))`.
  - All sibling `log.*` values in `zh.json` are translated to natural
    Chinese while preserving placeholders and continuation glyphs.
- **Implications**: Translate the value; preserve the leading two-space
  indent, the `└─` glyph, and the `{taskId}` placeholder.

### Translation conventions in `zh.json`
- **Context**: Choose Chinese wordings consistent with the existing
  vocabulary so reviewers don't need to debate terminology.
- **Sources Consulted**: `jq` dumps of `home.*`, `step3.*`, `step4.*`,
  `step5.*`, `graph.*`, `agent.*`, `log.*` in `zh.json`.
- **Findings**:
  - "Agent" → "智能体" (e.g. `agent.title: "🤖 智能体详情"`).
  - "Report Agent" → "报告智能体"
    (e.g. `step4.reportAgentReady: "报告智能体就绪"`).
  - "Graph" → "图谱" (e.g. existing `graphLoadFailed: "图谱加载失败"`).
  - "Task ID" → "任务 ID" — keeps "ID" as a loanword, which is the
    standard rendering in Chinese tech UIs and matches surrounding
    log-line tone.
- **Implications**: Wording table in `design.md` follows these
  conventions; a native reviewer can still suggest polish but no
  reviewer should be surprised by the chosen vocabulary.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| In-place value `Edit` (selected) | Use the `Edit` tool for each of the ten lines in `zh.json` | No risk of key reorder; minimal blast radius; reviewable diff | Requires care that `old_string` is unique per edit | Matches surrounding convention |
| `jq` script rewrite | One-off `jq --arg ... '.x = $v'` script | Mechanizable | Older `jq` versions may reorder object keys, breaking structural alignment | Rejected |
| Manual full-file rewrite via `Write` | Rewrite the file with new values | Fewer edits | Highest risk of accidental whitespace/key-order drift | Rejected |

## Design Decisions

### Decision: Translate `log.prepareTaskId` rather than leave it English
- **Context**: Issue allows either choice, conditional on a documented
  rationale.
- **Alternatives Considered**:
  1. Leave English on the grounds that it is a "log scaffold".
  2. Translate, matching the surrounding `log.*` translations.
- **Selected Approach**: Translate to `  └─ 任务 ID: {taskId}`.
- **Rationale**: The key is consumed by a user-visible log panel
  (`Step2EnvSetup.vue:801`), and every other `log.*` key in `zh.json`
  is already translated. Leaving this one in English would be the
  inconsistent choice.
- **Trade-offs**: None material; the indent and `└─` glyph carry the
  scaffold semantics and are preserved.
- **Follow-up**: Document the decision in the PR description so a
  reviewer can override if they prefer to keep "Task ID" as a literal
  technical identifier.

### Decision: Use `Edit` (string replace) rather than a `jq` rewrite
- **Context**: Need to change ten values without disturbing key order
  or the file's whitespace.
- **Selected Approach**: One `Edit` per key, matching the value with
  enough surrounding context to be unique.
- **Rationale**: `Edit` operates on raw bytes — it cannot reorder keys
  or drop comments/whitespace. `jq` rewrites are not safe across all
  versions for object key order.
- **Trade-offs**: Slightly more tool calls; offset by safety.
- **Follow-up**: After the edits, run the alignment diff and the
  `jq empty` check before committing.

## Risks & Mitigations
- **Translation polish disagreements** — Reviewer may prefer different
  wording. *Mitigation*: PR description lists the chosen renderings and
  invites suggestions; copy changes are cheap.
- **Accidental placeholder drift** — `{count}` or `{taskId}` lost during
  edit. *Mitigation*: post-edit `grep` check that each placeholder
  still appears exactly once in its key's value.
- **Accidental key reorder** — JSON tooling sometimes reorders keys.
  *Mitigation*: use `Edit` only; do not run `jq` write-back.

## References
- `.kiro/specs/i18n-backfill-zh-json/gap-analysis.md`
- `.ticket/8.md`
- `frontend/src/components/Step2EnvSetup.vue:801` — usage of
  `log.prepareTaskId`.
