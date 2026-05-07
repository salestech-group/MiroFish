# Requirements Document

## Project Description (Input)
Replace hard-coded Chinese UI strings in frontend Vue components and views with vue-i18n keys, and update Step4Report.vue regex parsers that depend on Chinese tokens emitted by the backend so they keep working once those backend prompts are translated to English. Scope: frontend/src/components/Step2EnvSetup.vue, Step3Simulation.vue, Step4Report.vue, Step5Interaction.vue and frontend/src/views/Process.vue. The audit list lives at .kiro/specs/i18n-e2e-english-verification/audit/classified.csv. Acceptance: every flagged file:line is fixed (translated via i18n keys, or kept as deliberate) and the audit script .kiro/specs/i18n-e2e-english-verification/audit/scripts/run_audit.sh reports zero gaps in this category. Reference: GitHub issue #23.

## Introduction

Five frontend Vue files (`Process.vue`, `Step2EnvSetup.vue`, `Step3Simulation.vue`, `Step4Report.vue`, `Step5Interaction.vue`) still emit Chinese strings directly to the user instead of routing them through `vue-i18n`. The `Step4Report.vue` parsers also pattern-match against Chinese tokens emitted by backend prompts; once those backend prompts are translated as part of the wider i18n initiative, those parsers will silently fail. This spec scopes both fixes: externalise user-visible strings to `/locales/{en,zh}.json`, and make the report parsers tolerate the post-translation backend output.

This is a remediation slice of the broader i18n initiative tracked by epic #11.

## Boundary Context

- **In scope**:
  - User-visible Chinese strings in templates, alert/message bodies, error fallbacks, and runtime messages inside the five files listed above.
  - Comparison/branching logic that relies on Chinese stage tokens for stable behaviour (e.g., `currentStage === '生成Agent人设'`).
  - Regex parsers and string-equality checks in `Step4Report.vue` and `Step5Interaction.vue` that depend on Chinese tokens emitted by the backend (`相关预测事实: X条`, `位模拟Agent`, `选择…（index …）`, `（该平台未获得回复）`, `[无回复]`, `问题X：`, `分析问题:`, `最终答案:`, `提问者`/`你`, `以下是我们之前的对话`, etc.).
  - Adding any newly required keys to both `locales/en.json` and `locales/zh.json` so the existing parity is preserved.
- **Out of scope**:
  - Translating backend log messages, ontology/report agent prompts, or other backend code (covered by issues #24, #25, and the existing per-prompt specs).
  - Translating Chinese comments in source files (covered by issues #7 and #9).
  - Re-running the audit script — the artefacts at `.kiro/specs/i18n-e2e-english-verification/audit/scripts/` no longer exist. Acceptance is verified by direct grep over the five files.
  - Changes to other Vue components/views beyond the five named in scope, unless a shared key the five files use needs extending.
- **Adjacent expectations**:
  - i18n key naming follows the conventions already in `/locales/en.json` (camelCase, namespaced by view/component, e.g. `step2.*`, `step4.*`, `process.*`).
  - The frontend uses `vue-i18n` 11; the global `$t` is available in templates and `useI18n()`'s `t` is used in `<script setup>` blocks already in each file.
  - Both Chinese (`zh.json`) and English (`en.json`) entries must be supplied for every new key — no English-only keys (this matches the resolution applied in #20 / spec `i18n-backfill-zh-json`).
  - Backend prompts will be translated under separate specs; this spec must keep the parsers working both **before** and **after** that backend change, because the two changes will not land atomically.

## Requirements

### Requirement 1: Externalize hard-coded UI strings in `Process.vue`

**Objective:** As an English-locale user, I want the workflow orchestrator page to render every label, status, button title, and error message in the language selected via the language switcher, so that I am not unexpectedly shown Chinese text in the middle of an otherwise English UI.

#### Acceptance Criteria

1. The `Process.vue` file shall render every user-visible string flagged in the ticket evidence (lines 26, 30, 32, 36, 39, 53, 452–456, 482, 536, 541, 543, 563, 571, 598, 602, 634, 638, 657, 667, 673, 681, 686, 763, 778, 797, 872, 884, 900, 901, plus their immediate Chinese-only siblings within those template/script blocks) through `vue-i18n` keys instead of inlined Chinese literals.
2. When the active locale is `en`, the `Process.vue` file shall render no Chinese characters in the rendered DOM for any path exercised on a clean project build (initial load, ontology generation, graph build start, graph build progress, graph build success, graph build error, refresh button, fullscreen toggle, fallback node/edge labels).
3. When the active locale is `zh`, the `Process.vue` file shall render the same Chinese wording the user sees today for every flagged string (no regression for Chinese users).
4. If a flagged string is a fallback for an entity name from the graph (`节点名 = n.name || '未命名'`), then the `Process.vue` file shall use a translated fallback (e.g., `t('process.fallbackNodeName')`) instead of the Chinese literal.
5. The `Process.vue` file shall not introduce any new English-only string literal in `<template>` or in user-visible script paths; every newly added literal shall be added to both `en.json` and `zh.json`.

### Requirement 2: Externalize hard-coded UI strings in step components

**Objective:** As an English-locale user, I want the Step2/Step3/Step4/Step5 components to surface every status badge, error toast, log line, modal copy, and inline label through i18n keys, so that no step of the pipeline silently shows Chinese to an English user.

#### Acceptance Criteria

1. The `Step3Simulation.vue` file shall route the simulation start-failure fallback (`'启动失败'`) through an i18n key (e.g. `t('step3.startFailed')`) so the message renders in the active locale.
2. The `Step4Report.vue` file shall route every user-visible Chinese literal flagged in the ticket evidence (lines 850, 854, 1325, 1464, 1774, 2005–2006, plus any equivalent literals discovered while editing those blocks) through i18n keys, including inline render-function strings (`h('div', …, '选择理由')`), placeholder titles (`'等待开始'`), the no-reply markers used in display branches, and log-classification labels.
3. The `Step5Interaction.vue` file shall route the chat-history templating (`'提问者'`, `'你'`, `'以下是我们之前的对话：…现在我的新问题是：…'`) through i18n keys so that the prompt sent to the backend reflects the active UI language, with the prior Chinese behaviour preserved when locale is `zh`.
4. When the active locale is `en`, the four step components in scope shall render no Chinese characters on any UI path that does not display backend-supplied content verbatim.
5. The `Step2EnvSetup.vue` file shall continue to track the simulation stage transitions for backend stage names whose Chinese form is currently observed (`'生成Agent人设'`, `'生成模拟配置'`, `'准备模拟脚本'`); see Requirement 4 for how this is preserved.
6. The four step components shall use the existing `useI18n()` `t` import already present in each file rather than introducing a different translation utility.

### Requirement 3: Maintain `en.json` and `zh.json` parity for newly externalized strings

**Objective:** As a maintainer, I want every new i18n key added by this work to exist in both the English and Chinese locale files with appropriate translations, so that neither locale ends up with English fallbacks shown to users (the regression that was just fixed in #20).

#### Acceptance Criteria

1. The locale files shall contain an entry for every new key added under this spec, in both `locales/en.json` and `locales/zh.json`.
2. The `locales/zh.json` entries shall preserve the exact Chinese wording removed from the source files (no paraphrasing) so that the user-visible text in the Chinese UI is unchanged.
3. The `locales/en.json` entries shall contain idiomatic English translations consistent with the existing tone of the file (sentence case, no trailing punctuation unless the surrounding entries use it).
4. New keys shall be grouped under existing namespaces where one fits (e.g., `process.*`, `step2.*`, `step4.*`, `step5.*`); a new namespace shall only be introduced if no existing one covers the surface.
5. The two files shall remain structurally aligned (same set of keys, same nesting). Keys present in one locale but missing in the other shall be considered a defect.

### Requirement 4: Replace Chinese stage-name comparisons with stable language-independent identifiers

**Objective:** As a developer, I want the frontend's branching logic to rely on stable backend-emitted identifiers rather than Chinese display strings, so that translating those backend strings to English does not silently break stage transitions.

#### Acceptance Criteria

1. The `Step2EnvSetup.vue` watcher shall continue to enter the correct phase when the backend emits any of the stage forms currently observed in production: the legacy Chinese display strings (`'生成Agent人设'`, `'生成模拟配置'`, `'准备模拟脚本'`), the existing snake_case identifiers (`'generating_profiles'`, `'generating_config'`, `'copying_scripts'`), and any English display strings the backend may emit after its prompts are translated.
2. While the backend has not yet been translated, the `Step2EnvSetup.vue` file shall not regress its current behaviour for users on Chinese builds (the Chinese stage names must continue to map to the correct phase).
3. If the backend later removes the Chinese stage strings entirely, the `Step2EnvSetup.vue` file shall still drive `phase.value` correctly using the snake_case stage identifiers without any further frontend change.
4. The `Step2EnvSetup.vue` file shall encode the stage matching once (e.g., a small lookup) rather than scattering string equality checks, so that future stage additions only need to be made in one place.

### Requirement 5: Make `Step4Report.vue` parsers tolerate translated backend output

**Objective:** As a user running with translated backend prompts, I want the report renderer to extract counters, interview answers, persona titles, query strings, and final answers correctly even after the backend stops emitting Chinese, so that the report does not silently degrade once the i18n backend work lands.

#### Acceptance Criteria

1. When the backend emits the legacy Chinese counter format (`相关预测事实: X条`), the `Step4Report.vue` file shall extract the counter value as it does today.
2. When the backend emits the equivalent English counter format produced by the translated prompts (e.g., `Related prediction facts: X` or whatever the translated prompt actually emits), the `Step4Report.vue` file shall extract the same counter value.
3. When the backend emits the legacy interview-count format (`5 / 9 位模拟Agent`), the `Step4Report.vue` file shall extract the numerator and denominator.
4. When the backend emits the equivalent English interview-count format (e.g., `5 / 9 simulated agents`), the `Step4Report.vue` file shall extract the same numerator and denominator.
5. When the backend emits a "no reply" marker — `（该平台未获得回复）`, `(该平台未获得回复)`, `[无回复]`, or the corresponding English markers produced by the translated prompts — the `Step4Report.vue` file shall recognise it as a no-reply value and suppress the empty bubble.
6. When the backend emits a numbered question label in the Chinese-style format (`问题X：` / `问题X:`) or its translated equivalent (e.g. `Question X:`), the `Step4Report.vue` file shall recognise both and split the prompt accordingly.
7. When the backend emits a "selection reason" line in the Chinese-style format (`- 选择<name>（index <i>）：<reason>`) or its translated equivalent, the `Step4Report.vue` file shall recognise both and extract the same fields.
8. When the backend emits a `分析问题:` marker or the equivalent translated marker (e.g. `Analyse question:` / whatever the prompt produces), the `Step4Report.vue` file shall extract the query.
9. When the backend emits a `最终答案:` marker or its translated equivalent, the `Step4Report.vue` file shall extract the final answer body.
10. The `Step4Report.vue` file shall keep working when the backend has been only partially translated (some markers still Chinese, some English) — i.e., parsers shall accept either form, not require both.
11. The `Step4Report.vue` file shall keep its log-classification (`ERROR`/`错误`, `WARNING`/`警告`) functioning for both forms.

### Requirement 6: Verifiability

**Objective:** As a reviewer, I want a deterministic way to confirm that the five files no longer hard-code user-visible Chinese, so that I can sign off on the PR without manually walking every line.

#### Acceptance Criteria

1. The repository shall provide a check that, given the five files in scope, reports zero hard-coded user-visible Chinese strings (i.e., string literals containing CJK characters that flow into the rendered DOM, an `alert()`, or a backend prompt).
2. While the audit script referenced in the original ticket no longer exists in the repo, the spec shall document the equivalent check used to verify acceptance (e.g. a `grep` invocation scoped to the five files, with a small allowlist for translation-equivalence checks performed in Requirement 5).
3. If a Chinese literal is intentionally retained (e.g., to match a backend marker for backwards compatibility under Requirement 5), the `requirements.md` and the inline code shall identify it as deliberate, and the verification check shall not flag it.
4. The verification shall be runnable locally in under one minute and shall not require a running backend.
