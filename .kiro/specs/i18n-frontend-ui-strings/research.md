# Research & Design Decisions — `i18n-frontend-ui-strings`

## Summary

- **Feature**: `i18n-frontend-ui-strings`
- **Discovery Scope**: Extension (existing Vue + vue-i18n adoption, brownfield codebase)
- **Key Findings**:
  - `Process.vue` has zero i18n adoption today; the other four files in scope are partially i18n'd. The volume of new keys lands almost entirely in `Process.vue` and falls under the existing `process.*` / `graph.*` / `step1.*` namespaces.
  - The 29 backend-coupled regexes in `Step4Report.vue` are matched against strings emitted by `backend/app/services/zep_tools.py` (and a few other services). Those backend strings are 100% Chinese today; the English translation of those prompts is owned by a *separate* spec (issue #25 / `i18n-report-agent-prompts` etc.) and has not landed.
  - The `Step5Interaction.vue` chat-history templating (`'提问者'`/`'你'`/`'以下是我们之前的对话：…'`) is *prompt content* sent to the LLM, not user-visible UI. It is safe to localize via `t()` because the backend report agent already accepts both Chinese and English (it's a multilingual LLM) and the wider initiative is moving the backend to English; the Chinese phrasing is preserved for the `zh` locale via `zh.json`.

## Research Log

### Backend marker emission audit

- **Context**: Requirement 5 demands that `Step4Report.vue` parsers tolerate post-translation backend output. We need to know what the backend emits today and whether the translated wording is already pinned.
- **Sources Consulted**:
  - `backend/app/services/zep_tools.py` (lines 47, 50, 78, 175–207, 258–276, 307–311, 379–395, 1365, 1424–1426, 1720)
  - `backend/app/services/oasis_profile_generator.py` (lines 424–475, 945)
  - GitHub issue #25 (open; backend prompt assembly translation not yet started)
  - `.kiro/specs/i18n-report-agent-prompts/` (open; tasks generated, not implemented)
- **Findings**:
  - All 29 markers/regexes used by the frontend originate from the listed backend files and are emitted as Chinese literals (e.g. `f"分析问题: {self.query}"`, `f"- 相关预测事实: {self.total_facts}条"`, `f"**采访人数:** {self.interviewed_count} / {self.total_agents} 位模拟Agent"`).
  - The English wording the backend will emit after translation is **not yet pinned** in the open spec. It will be decided when `i18n-report-agent-prompts` and #25 are implemented.
  - The no-reply markers (`（该平台未获得回复）`, `(该平台未获得回复)`, `[无回复]`) are also emitted by `zep_tools.py` as Chinese literals and used as user-visible "no answer" text in the report. These are the only markers whose translated wording we can reasonably anticipate (`(no response on this platform)` / `[no response]` etc.) and even those will be decided by the backend spec.
- **Implications**:
  - We cannot reliably encode English alternates for markers whose translated wording is undecided. Speculative English regexes risk silently failing once the backend translation chooses a different wording.
  - **Strategy**: centralize the markers in a single top-of-file constants block in `Step4Report.vue`, document them as "backend-coupled, deliberate Chinese — sync with `i18n-report-agent-prompts`", and surface them in the audit allowlist (Requirement 6). When the backend spec lands, a single-file edit updates every parser at once. This is the "deliberate" classification the ticket allows.
  - The log-severity classifier (`log.includes('错误')` / `log.includes('警告')`) is a special case: those substrings come from arbitrary log lines, not a fixed marker. Keep them with bilingual `OR` (`'ERROR'/'错误'/'WARNING'/'警告'` is already what the file does). No change required beyond noting it as deliberate.

### vue-i18n usage convention

- **Context**: Confirm the adoption pattern so the new substitutions match existing files.
- **Sources Consulted**: `frontend/src/i18n/index.js`; the four step components already using i18n; `locales/en.json` (1031 lines), `locales/zh.json` (1031 lines, aligned post-#20).
- **Findings**:
  - `<template>` uses `$t('namespace.key')` and `$t('namespace.key', { param })`; `<script setup>` uses `const { t } = useI18n()` then `t('namespace.key')`.
  - Existing namespaces: `common`, `meta`, `nav`, `home`, `main`, `step1` … `step5`, `graph`, `history`, `api`, `progress`, `log`, `report`, `console`. No `process` namespace yet; the `graph.*` namespace already covers ~5 of `Process.vue`'s graph-panel strings (refresh/maximize/loading) and should absorb those.
  - Default locale is `'zh'`; fallback locale is also `'zh'`. The frontend passes locale through `localStorage`. No SSR concerns.
- **Implications**:
  - Add a new `process.*` namespace for view-level strings. Reuse `graph.*` (already covers refresh/maximize/etc.) for graph-panel literals where a key already exists.
  - Add `step3.startFailed` (already exists — confirmed in en.json `step3.startFailed`), `step4.*` keys for the new Step4Report literals (`selectionReason`, `awaitingStart`, etc.), `step5.*` keys for the chat-history templating.

### Locale parity check

- **Context**: Issue #20 (`i18n-backfill-zh-json`) recently aligned `en.json` and `zh.json`. Don't regress that.
- **Sources Consulted**: `wc -l locales/{en,zh}.json` → both 1031.
- **Findings**: structurally aligned. Keys present in en.json are mirrored in zh.json. The discipline is fresh and respected.
- **Implications**: every new key added by this spec must land in *both* files in the same commit/PR. The existing audit script for parity is implicit — `diff <(jq -S 'keys_unsorted_recursive' en.json) <(jq -S 'keys_unsorted_recursive' zh.json)` is a one-liner that suffices. We will not add a CI gate (out of scope; tracked under issue #26).

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Pure extension (in-file `t()` substitution + add keys) | Match existing surrounding-file style; no new modules. | Smallest blast radius; reviewable file-by-file; aligns with steering "match the surrounding file's style." | Adds ~40 entries to each locale file; nothing centralized. | Picked for R1, R2, R3. |
| New `useStageMatcher` composable + `reportMarkers.js` util | Extract the two backend-coupled responsibilities (stage matching, parser markers) into shared modules. | Single source of truth; future backend translation is a one-line update. | More files; steering doc favours pipeline-stage logic *staying in* the matching Step component unless responsibilities truly diverge. They do diverge slightly (markers are coupled to backend, not to the Step's UI state). | Rejected for stage matcher (only 3 lines, not worth the extraction); chosen as in-file constants block for parser markers. |
| Hybrid (selected) | In-file `t()` substitution everywhere; in-file constants block for parser markers in `Step4Report.vue`; tiny in-file lookup for stage matcher in `Step2EnvSetup.vue`. | Balances clarity against the steering principle. Single edit when backend translation lands. | Constants block adds ~25 lines to `Step4Report.vue`. | **Selected**. |

## Design Decisions

### Decision: keep parser markers as in-file constants, not a separate utility

- **Context**: Requirement 5 wants the parsers to survive backend translation. The candidates for "where to put the marker definitions" are (a) inline in each parser, (b) top-of-file constants block, (c) separate `reportMarkers.js`.
- **Alternatives Considered**:
  1. **Inline** — what the file does today. Rejected: 29 markers scattered across 400+ lines makes a future single-file update impossible.
  2. **Separate utility module** — clean but pulls knowledge of report-agent output into a generic util that no other file uses. The steering doc's pipeline-aligned principle prefers staying in the Step component.
  3. **Top-of-file constants block** — selected.
- **Selected Approach**: A `const REPORT_MARKERS = { … }` block at the top of `Step4Report.vue`'s `<script setup>`, with each entry documenting the backend source line. Each parser uses `REPORT_MARKERS.foo.regex` instead of inlining the literal regex. When `i18n-report-agent-prompts` lands, the block is the only place that needs editing.
- **Rationale**: minimal architectural change; preserves the steering principle that pipeline-stage logic lives in the matching Step component; gives R5 a single defensible edit-site for the future backend update.
- **Trade-offs**: 25 extra lines in an already-large file (+0.06% of `Step4Report.vue`). Acceptable.
- **Follow-up**: when issue #25 / `i18n-report-agent-prompts` lands, edit `REPORT_MARKERS` to alternate Chinese/English forms.

### Decision: stage-matcher refactor, not stage-matcher extraction

- **Context**: `Step2EnvSetup.vue:680-689` has three string-equality checks (`'生成Agent人设'`, `'生成模拟配置'`, `'准备模拟脚本'`).
- **Alternatives Considered**:
  1. Leave alone — fails R4.
  2. Extract `useStageMatcher()` composable — over-engineered for 3 entries.
  3. Inline lookup map at top of file — selected.
- **Selected Approach**: a `const STAGE_PHASE_MAP = { 'generating_profiles': 1, '生成Agent人设': 1, 'generating_config': 2, '生成模拟配置': 2, 'copying_scripts': 2, '准备模拟脚本': 2 }`. Watcher becomes `phase.value = STAGE_PHASE_MAP[newStage] ?? phase.value`. New stages or new English forms are a one-line addition.
- **Rationale**: smallest possible refactor that satisfies R4.1, R4.2, R4.3, and R4.4.

### Decision: localize the `Step5Interaction.vue` chat-history templating

- **Context**: Lines 725 and 727 construct a prompt string that is sent **to the LLM**, not displayed to the user. There is a tension between (a) keeping it Chinese (matches the existing Chinese-tuned report agent) and (b) localizing it via `t()` (correct for English users, consistent with how the rest of the file handles strings).
- **Alternatives Considered**:
  1. Leave the literals — fails R2.3 of the spec; freezes the user's language back into Chinese once they enter the chat history flow.
  2. Always send English — breaks current Chinese behaviour.
  3. Localize via `t()` so the prompt language follows the active locale — selected.
- **Selected Approach**: introduce `step5.chatRolePrompter`, `step5.chatRoleYou`, `step5.chatHistoryPrefix`, `step5.chatNewQuestionPrefix`. Build the prompt with these keys.
- **Rationale**: report agents in this project run on multilingual LLMs (Qwen, GLM, MiniMax) that handle either input language. The Chinese phrasing is preserved exactly in `zh.json` so Chinese users see no behaviour change.
- **Trade-offs**: a Chinese-locale user chatting against an English-tuned model would have a slight mismatch — but this combination is not the production path, and would be a separate issue if/when it arises.
- **Follow-up**: if the report agent is later forced to a single language, revisit and pin to that language.

## Risks & Mitigations

- **R5 — encoding speculative English markers** that don't match what the backend ultimately emits → Mitigation: do not encode English alternates for markers whose translated wording is undecided; centralise into `REPORT_MARKERS` so the future backend spec can update them in one place. Add an explicit allowlist of deliberate Chinese tokens to the audit (Requirement 6).
- **R3 — locale-file drift** (en.json/zh.json key sets diverging) → Mitigation: add the `keys_unsorted_recursive` parity diff to the verification script in R6.
- **R1 — Process.vue review fatigue** (~40 substitutions in a 50KB file) → Mitigation: split the implementation tasks by logical block (header / building progress / errors / fallbacks / project-info modal) so the PR is reviewable section by section.
- **R2.3 — Step5 prompt language change** affects backend behaviour → Mitigation: preserve exact Chinese in `zh.json` so the production Chinese path is byte-identical to today; add an inline test or manual smoke-test note in the implementation tasks.

## References

- GitHub issue #23 — current ticket
- GitHub issue #11 — i18n epic (parent)
- GitHub issue #25 — backend LLM-prompt context label translation (downstream coordination point)
- GitHub issue #20 / spec `.kiro/specs/i18n-backfill-zh-json/` — locale parity precedent
- Open spec `.kiro/specs/i18n-report-agent-prompts/` — sibling backend translation spec; pinpointed as the future edit-trigger for `REPORT_MARKERS`
- `backend/app/services/zep_tools.py:47-1720` — canonical source of every backend marker the frontend parses
- vue-i18n 11 docs (already adopted; no new library decisions)
