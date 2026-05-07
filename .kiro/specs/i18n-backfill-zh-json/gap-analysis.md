# Gap Analysis — i18n-backfill-zh-json

## Scope

Translate ten English-only values in `locales/zh.json` to natural Chinese,
preserving structural alignment with `locales/en.json`. Data-only change.

## Current State Investigation

- **Locale files** live at the repo root: `locales/en.json`, `locales/zh.json`,
  `locales/languages.json`. The frontend loader is `frontend/src/i18n/`
  (vue-i18n).
- **Key alignment**: `diff <(jq -r 'paths(scalars) | join(".")'
  locales/en.json | sort) <(jq -r 'paths(scalars) | join(".")'
  locales/zh.json | sort)` is currently empty — same key set, no drift.
- **Confirmed English-only values in `zh.json`** (verified via `jq`):
  - `home.heroDescBrand` → `"MiroFish"` (brand, keep as-is)
  - `step3.waitingForActions` → `"Waiting for agent actions..."`
  - `step4.waitingForReportAgent` → `"Waiting for Report Agent..."`
  - `step5.interactiveTools` → `"Interactive Tools"`
  - `step5.agentsAvailable` → `"{count} agents available"`
  - `step5.reportAgentChat` → `"Report Agent - Chat"`
  - `graph.panelTitle` → `"Graph Relationship Visualization"`
  - `graph.nodeDetails` → `"Node Details"`
  - `graph.relationship` → `"Relationship"`
  - `log.prepareTaskId` → `"  └─ Task ID: {taskId}"`
- `en.json` contains the same English values for these keys (as expected).

### `log.prepareTaskId` usage

Confirmed via `Grep`: this key is consumed by
`frontend/src/components/Step2EnvSetup.vue:801` —
`addLog(t('log.prepareTaskId', { taskId: res.data.task_id }))` — i.e. it is
rendered into the in-UI log panel that the user reads. The surrounding
`log.*` keys in `zh.json` are all translated to natural Chinese (e.g.
`prepareTaskStarted: "准备任务已启动"`, `simEnvClosed: "✓ 模拟环境已关闭"`).
**Conclusion**: this is a user-facing log line, not a locale-neutral
scaffold; it should be translated, with the leading two-space indent, the
`└─` continuation glyph, and the `{taskId}` placeholder preserved.

## Implementation Approach

### Option A — Single targeted edit to `locales/zh.json` (recommended)

Open `locales/zh.json`, locate each of the ten keys, and replace the value
with its Chinese translation. Re-run the `jq` alignment diff and parse-check
afterward.

- ✅ Minimal blast radius, single file changed.
- ✅ Matches the surrounding convention (other `log.*`, `step3.*`, `step5.*`
  Chinese values are already direct translations of their English siblings).
- ✅ No risk of key reorder or shape change if edits are value-only.
- ❌ None — this is the only sensible approach for a 10-value backfill.

### Option B — Script-driven rewrite

Write a one-off `jq` or Node script to set the ten values. Overkill for ten
values and increases the chance of accidental key reorder (`jq` does not
guarantee key-order preservation in older versions).

**Decision**: Option A.

## Translation Plan (proposed values)

| Key | Proposed Chinese value |
| --- | --- |
| `home.heroDescBrand` | `MiroFish` (unchanged — brand) |
| `step3.waitingForActions` | `等待智能体执行动作...` |
| `step4.waitingForReportAgent` | `等待报告智能体...` |
| `step5.interactiveTools` | `交互工具` |
| `step5.agentsAvailable` | `{count} 个智能体可用` |
| `step5.reportAgentChat` | `报告智能体 - 对话` |
| `graph.panelTitle` | `图谱关系可视化` |
| `graph.nodeDetails` | `节点详情` |
| `graph.relationship` | `关系` |
| `log.prepareTaskId` | `  └─ 任务 ID: {taskId}` |

Notes:
- "Agent" is rendered as "智能体" — consistent with existing `zh.json` usage
  (e.g. `step3.recentActions: "最近行为"`, `agent.title: "🤖 智能体详情"`).
- "Report Agent" → "报告智能体" — matches existing translations such as
  `step4.reportAgentReady: "报告智能体就绪"`.
- `step5.reportAgentChat` keeps the ` - ` separator literally to match the
  English style in the same key family.
- `log.prepareTaskId` keeps the two leading spaces and `└─` glyph because
  surrounding log lines (e.g. `simEnvClosed: "✓ 模拟环境已关闭"`) preserve
  their leading glyph; the indent is meaningful in the log panel.

These are proposals to be finalized at design time; minor wording polish
(e.g. "对话" vs "聊天") can be revisited during /kiro:spec-design.

## Validation Strategy

1. `jq empty locales/zh.json` — file remains valid JSON.
2. `diff <(jq -r 'paths(scalars) | join(".")' locales/en.json | sort)
   <(jq -r 'paths(scalars) | join(".")' locales/zh.json | sort)` — empty.
3. Spot-check via `jq -r '<key>'` that the ten target values now match the
   translation table (or the brand/scaffold exception, where applicable).
4. Manual: launch the dev server, switch UI to Chinese, walk through Step 2
   logs (look for translated `log.prepareTaskId` line), Step 3 / Step 4
   waiting states, Step 5 interactive tools, and the graph panel.

## Risks / Unknowns

- **Wording quality**: My proposed translations follow the conventions used
  elsewhere in `zh.json`; a native reviewer may prefer alternatives. The PR
  description should call this out so reviewers can suggest edits.
- **Key order preservation**: `Edit` (string-replace) is safe; `jq`-based
  rewrites would not be. We will use `Edit` exclusively.
- **No additional research needed** — this is a well-bounded data change.

## Recommendation

Proceed to `/kiro:spec-design` with Option A and the translation table
above. Design phase will only need to specify the exact `Edit` operations
and the validation script — no architecture work.
