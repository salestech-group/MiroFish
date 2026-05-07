# Implementation Plan

- [x] 1. Backfill English-only values in `locales/zh.json` with the natural Chinese translations from the design's Translation Contract
  - Edit `step3.waitingForActions` → `等待智能体执行动作...`
  - Edit `step4.waitingForReportAgent` → `等待报告智能体...`
  - Edit `step5.interactiveTools` → `交互工具`
  - Edit `step5.agentsAvailable` → `{count} 个智能体可用` (placeholder `{count}` preserved exactly once)
  - Edit `step5.reportAgentChat` → `报告智能体 - 对话`
  - Edit `graph.panelTitle` → `图谱关系可视化`
  - Edit `graph.nodeDetails` → `节点详情`
  - Edit `graph.relationship` → `关系`
  - Edit `log.prepareTaskId` → `  └─ 任务 ID: {taskId}` (preserves the two-space indent, the `└─` glyph, and the `{taskId}` placeholder verbatim)
  - Leave `home.heroDescBrand` as the literal string `MiroFish` (brand)
  - Use the `Edit` tool only (do not run any `jq` write-back); do not add, remove, or reorder any keys
  - Observable completion: `git diff --stat` shows exactly one file changed (`locales/zh.json`); `git diff locales/zh.json` shows only value changes for the listed keys (no key adds/removes/reorders)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.2, 3.2, 3.3, 4.1, 4.2, 4.3_

- [x] 2. Validate JSON parseability, key alignment, and placeholder preservation after the backfill
  - Run `jq empty locales/zh.json` and confirm exit code 0 (file is valid JSON)
  - Run `diff <(jq -r 'paths(scalars) | join(".")' locales/en.json | sort) <(jq -r 'paths(scalars) | join(".")' locales/zh.json | sort)` and confirm output is empty (key sets identical)
  - Run `jq -r '<key>'` for each of the ten keys and confirm the value matches the design's Translation Contract row (or `MiroFish` for `home.heroDescBrand`)
  - Confirm `{count}` appears exactly once inside the new value of `step5.agentsAvailable`, and `{taskId}` appears exactly once inside the new value of `log.prepareTaskId`
  - Observable completion: all five checks above pass; if any fails, return to task 1 and revise the offending edit before re-running validation
  - _Requirements: 3.1, 3.3, 3.4, 3.5_

- [x] 3. Capture the `log.prepareTaskId` decision and any English-by-design exceptions for the PR description
  - Record in a short note (in `.kiro/specs/i18n-backfill-zh-json/HANDOFF.md` if needed, or directly in the PR body at /done time) that: (a) `home.heroDescBrand` is intentionally kept as `MiroFish` because it is a brand; (b) `log.prepareTaskId` was translated to `  └─ 任务 ID: {taskId}` because it is rendered into the user-visible log panel by `Step2EnvSetup.vue:801` and surrounding `log.*` keys are translated.
  - Observable completion: the rationale text is ready for inclusion in the PR description so reviewers can see the decisions at a glance
  - _Requirements: 2.1, 2.3_
