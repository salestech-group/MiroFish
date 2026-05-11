# Implementation Tasks — `i18n-frontend-ui-strings`

> Approved requirements and design. Tasks ordered Foundation → Core → Integration → Validation per the project's tasks-generation rule.

- [x] 1. Foundation: locale-file additions and audit tooling

- [x] 1.1 Add the new `process.*`, `step3.*`, `step4.*`, `step5.*` keys to `locales/en.json` (English-only values)
  - Add a new top-level `process` namespace covering every literal flagged for `Process.vue` (header, status badges, progress hints, error messages, fallback names, project-info modal labels, environment-setup-coming-soon alert).
  - Add `step3.startFailed` if not already present (verify against current file).
  - Add `step4.selectionReason` and `step4.awaitingStart`.
  - Add `step5.chatRolePrompter`, `step5.chatRoleYou`, `step5.chatHistoryPrefix` (`{history}`, `{message}` ICU params).
  - Strings carry idiomatic English wording only — **no Chinese characters in `en.json`**; the design's bilingual sketch is only a reviewer aid.
  - Observable completion: `rg '[一-鿿]' locales/en.json` returns no hits in any newly added key (existing meta entries excluded).
  - _Requirements: 1.5, 3.1, 3.3, 3.4_

- [x] 1.2 (P) Mirror the new keys to `locales/zh.json` with the original Chinese wording
  - For each key added in 1.1, add an entry in `zh.json` carrying the **exact** Chinese string removed from the source files (no paraphrasing).
  - Preserve existing namespace order; add new entries at the end of each namespace block to minimise diff noise.
  - Observable completion: `jq -S 'paths(scalars) | join(".")' locales/en.json | sort -u` and the same for `zh.json` produce identical output.
  - _Requirements: 3.1, 3.2, 3.4, 3.5_
  - _Boundary: locales/zh.json_
  - _Depends: 1.1_

- [x] 1.3 (P) Author the audit verifier `frontend/scripts/audit-i18n-strings.sh`
  - Greps a CJK code-point range over the five files in scope only (no project-wide scan).
  - Filters out an explicit allowlist: the `REPORT_MARKERS` literal block in `Step4Report.vue`, the bilingual log-severity helper, and any line with a trailing `// i18n-allow:<reason>` comment.
  - Adds a key-parity check: `jq` over both locale files; reports keys missing from either side.
  - Exits 0 on success, 1 with a human-readable list otherwise.
  - Observable completion: running the script against the current branch (before the source-file changes) prints the expected hit list (sanity check); after the source-file changes it exits 0.
  - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - _Boundary: frontend/scripts/_

- [x] 2. Core: externalize `Process.vue`

- [x] 2.1 Wire `vue-i18n` into `Process.vue`
  - Add `import { useI18n } from 'vue-i18n'` and `const { t } = useI18n()` to the `<script setup>` block.
  - Run a smoke check (`npm run dev`, open the page) to confirm the import does not regress the existing render.
  - Observable completion: file compiles, dev server reloads, the page still renders identically (no Chinese strings replaced yet).
  - _Requirements: 1.1, 2.6_
  - _Boundary: Process.vue_

- [x] 2.2 Replace the graph-panel and header literals in `Process.vue`
  - Substitute lines 26, 30, 32, 36, 39, 53 (header title, node/edge counts, refresh-button title, fullscreen toggle title, real-time-updating hint).
  - Reuse `graph.*` keys where they already exist; introduce `process.graphPanelTitle`, `process.nodes`, `process.edges`, `process.refreshGraph`, `process.exitFullscreen`, `process.enterFullscreen`, `process.realtimeUpdating` only as needed.
  - Observable completion: switch to `en` locale, reload, confirm the graph panel header reads in English; switch to `zh`, confirm the original Chinese is unchanged.
  - _Requirements: 1.1, 1.2, 1.3_
  - _Boundary: Process.vue_

- [x] 2.3 Replace the build-flow section literals in `Process.vue`
  - Substitute the ontology section (lines 174, 192, 193, 203, 204, 228, 237, 247, 249, 255, 264, 277, 298) and the graph-build section (lines 308, 318, 320, 326, 346, 350, 354, 366, 367, 378).
  - Substitute the project-info modal labels (lines 388, 392, 396, 400, 404).
  - Substitute the environment-setup-coming-soon alert at line 482.
  - Observable completion: full walk of the build-flow on `en` locale shows English throughout; on `zh` matches today's wording.
  - _Requirements: 1.1, 1.2, 1.3_
  - _Boundary: Process.vue_

- [x] 2.4 Replace the script-side error/status literals and fallback names in `Process.vue`
  - Substitute the build-status computed (lines 452–458), the step-status computed (lines 536, 541, 543), the no-files error (line 563), and every error-assignment fallback through the watcher (lines 571, 598, 602, 634, 638, 657, 667, 673, 681, 686, 763, 778, 797).
  - Substitute the D3 fallback labels (lines 872, 884, 900, 901): `t('process.waitingGraphData')`, `t('process.fallbackNodeName')`, `t('common.unknown')`.
  - Observable completion: trigger an error path (e.g., upload no files) on `en` locale; the resulting error message renders in English.
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - _Boundary: Process.vue_

- [x] 3. Core: externalize step components

- [x] 3.1 (P) Replace the `'启动失败'` fallback in `Step3Simulation.vue`
  - Substitute `startError.value = res.error || '启动失败'` (line 423) with `t('step3.startFailed')`.
  - Confirm `step3.startFailed` is present in both locale files (added in 1.1/1.2 if missing).
  - Observable completion: trigger a backend simulation-start failure on `en` locale; the inline error message reads in English.
  - _Requirements: 2.1, 2.4, 2.6_
  - _Boundary: Step3Simulation.vue_
  - _Depends: 1.1, 1.2_

- [x] 3.2 (P) Replace user-visible Chinese literals and centralize regex markers in `Step4Report.vue`
  - Add a frozen `REPORT_MARKERS` constants block at the top of `<script setup>`, with one entry per backend-coupled marker (28 regex entries + a `noReply.is(value)` predicate + a `logSeverity.{isError,isWarning}(line)` helper). Each entry carries an inline comment naming the canonical backend source line in `zep_tools.py` (or other emitter).
  - Refactor every parser call site to reference the block: `text.match(REPORT_MARKERS.analysisQuery.regex)`, `if (REPORT_MARKERS.noReply.is(interview.redditAnswer)) …`, etc. Touch every flagged line: 555, 557, 561, 565, 566, 567, 573, 580, 590, 597, 598, 609, 644, 652, 663, 673, 702, 706, 714, 816, 844, 845, 871, 893, 915, 923, 930, 943, 850, 854, 1325, 2005, 2006.
  - Substitute the user-visible literals: line 1464 (`h('div', …, '选择理由')` → `t('step4.selectionReason')`), line 1774 (`'等待开始'` → `t('step4.awaitingStart')`).
  - Mark the `REPORT_MARKERS` block with a leading `// i18n-allow: backend-coupled markers; sync with i18n-report-agent-prompts spec` comment so the audit script accepts the literals inside.
  - Observable completion: open a finished project's report on `en` locale; key facts, core entities, relation chains, sub-queries, both interview platforms, and search results render with parity to `main`. The "selection reason" header and the "awaiting start" placeholder render in English.
  - _Requirements: 2.2, 2.4, 2.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11_
  - _Boundary: Step4Report.vue_
  - _Depends: 1.1, 1.2_

- [x] 3.3 (P) Localize the chat-history templating in `Step5Interaction.vue`
  - Substitute lines 721 and 723. The `historyContext` map becomes `t('step5.chatRolePrompter')` / `t('step5.chatRoleYou')`. The prompt template uses `t('step5.chatHistoryPrefix', { history: historyContext, message })`.
  - Confirm the `zh.json` entries are byte-identical to the original Chinese phrasing so the production Chinese path is unchanged.
  - Observable completion: on `en` locale, send a question and a follow-up; the second LLM response references the chat history coherently. On `zh` locale, the LLM behaviour is unchanged from `main` (smoke test).
  - _Requirements: 2.3, 2.4, 2.6_
  - _Boundary: Step5Interaction.vue_
  - _Depends: 1.1, 1.2_

- [x] 3.4 (P) Refactor the stage watcher in `Step2EnvSetup.vue` to use `STAGE_PHASE_MAP`
  - Add a `const STAGE_PHASE_MAP = Object.freeze({ '生成Agent人设': 1, 'generating_profiles': 1, '生成模拟配置': 2, 'generating_config': 2, '准备模拟脚本': 2, 'copying_scripts': 2 })` near other module-level constants.
  - Rewrite the `watch(currentStage, …)` body so `phase.value = STAGE_PHASE_MAP[newStage] ?? phase.value`. Preserve the existing side-effect: when transitioning *into* phase 2, call `addLog(t('log.startGeneratingConfig'))` and start config polling.
  - Mark the map with `// i18n-allow: backend stage tokens; multi-language tolerance` so the audit accepts the embedded Chinese.
  - Observable completion: simulating each backend stage emission (e.g. via dev-tools console setting `currentStage.value = '生成Agent人设'`) drives `phase.value` to the expected value; same for the snake_case variant. A new English emission (e.g. `'generating profiles'`) added as a one-line map row works without other edits.
  - _Requirements: 2.5, 2.6, 4.1, 4.2, 4.3, 4.4_
  - _Boundary: Step2EnvSetup.vue_

- [x] 4. Integration and validation

- [x] 4.1 Run the audit verifier and resolve any remaining hits
  - Execute `bash frontend/scripts/audit-i18n-strings.sh`.
  - For each hit, either (a) substitute the literal with a `t()` call (and add the new key to both locale files), or (b) annotate the line with `// i18n-allow:<reason>` if the literal is deliberate.
  - Re-run until the script exits 0.
  - Observable completion: the script exits 0 with no stdout. The `git diff` against `main` shows no further user-visible Chinese in the five files outside the allowlisted blocks.
  - _Requirements: 1.2, 2.4, 6.1, 6.2, 6.3, 6.4_
  - _Depends: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4_

- [ ] 4.2 Manual end-to-end smoke test on both locales (deferred — requires running backend + browser; flagged in PR description for human reviewer)
  - On `en` locale: start a fresh project (file upload → ontology → graph build → env setup → simulation → report → interaction). Verify no unexpected Chinese in the rendered DOM (excluding backend-emitted content currently in Chinese, which is out of scope per the spec boundary).
  - On `zh` locale: same flow. Verify visual parity with `main` for every screen.
  - On `en` locale: walk the chat flow in Step5 with one question and a follow-up; confirm the LLM response uses the prior turn coherently (validates the Step5 chat-history change).
  - On `en` locale: open a previously generated report; confirm key facts, core entities, relation chains, sub-queries, both Twitter and Reddit interview answers, and search-result panes render with parity to `main`.
  - Observable completion: a short note in the PR body listing the two locales tested, the routes walked, and any anomalies found (expected: none).
  - _Requirements: 1.2, 1.3, 2.4, 5.10_
  - _Depends: 4.1_

- [x] 4.3 Locale-parity sanity check
  - Run `wc -l locales/en.json locales/zh.json`; line counts equal.
  - Run the parity diff embedded in `audit-i18n-strings.sh`; no missing keys reported.
  - Observable completion: both checks pass; the PR description quotes the verifier output (zero hits + parity OK).
  - _Requirements: 3.1, 3.5, 6.1_
  - _Depends: 4.1_
