# Gap Analysis — i18n-mandarin-gap-coverage

## 1. Current State Investigation

### Existing i18n infrastructure (reusable)

- `backend/app/utils/locale.py` exposes `t(key, **kwargs)` and `set_locale(locale)`. All translations live in `locales/{en,zh}.json`; missing-key fallback already returns the key string and dedups warnings. Per-thread locale is supported via `_thread_local`.
- `locales/en.json` and `locales/zh.json` already host `log.zep_tools.*` (51 keys), `log.simulation_runner.*` (40 keys), `log.profile_generator.*`, etc. New keys can be added under sibling namespaces.
- Frontend uses `vue-i18n` with the same JSON catalogues via the `@locales` Vite alias (so frontend and backend share keys).
- Several backend modules already follow the convert-to-`t()` pattern (e.g. `zep_entity_reader.py`, `simulation_ipc.py`, `llm_client.py`, `config.py`, `run.py`).

### In-scope source state (verified 2026-05-12)

| File | Han-line count |
|---|---:|
| `backend/app/services/zep_tools.py` | 146 |
| `backend/app/services/zep_graph_memory_updater.py` | 41 |
| `backend/scripts/run_twitter_simulation.py` | 55 |
| `backend/scripts/run_reddit_simulation.py` | (subset of twitter; very similar) |
| `backend/scripts/run_parallel_simulation.py` | 79 |
| `backend/scripts/test_profile_format.py` | 20 |
| `frontend/src/components/Step4Report.vue` | 105 |

Note: the umbrella issue estimated ~138 for `zep_tools.py`; the actual count is 146 because lines 1095–1101, 1574–1597, 1638–1656, 1692–1713 contain three LLM **prompt** blocks (sub-query generation, agent-selection planner, interview-question generator, interview-summary writer). These are part of `zep_tools.py` and must be translated for R1's acceptance criteria to hold.

### Cross-layer coupling

`Step4Report.vue:550-639` declares a `REPORT_MARKERS` object whose regex patterns reference Han phrases that exactly mirror the literals in `zep_tools.py`. Examples:

| Backend literal | Frontend marker | Frontend line |
|---|---|---:|
| `分析问题: {self.query}` | `analysisQuery: /分析问题:\s*(.+?)/` | 552 |
| `### 【关系链】` | `relationChainHdr: /### 【关系链】\n(...)/` | 572 |
| `【Twitter平台回答】\n...` | `twitterAnswer: /【Twitter平台回答】.../` | 605 |
| `行 ... '错误'` | `isError: line.includes('错误')` | 639 |

`isError` already checks `'ERROR'` (English) alongside `'错误'` (Chinese), giving us a precedent for dual-token matching.

### CJK CI guard

- `scripts/ci/tests/test_i18n_cjk_guard.py` — fixture tests for the guard logic.
- `scripts/check_i18n_logs.py` (if present) — scans the codebase and fails on Han literals.
- `.kiro/specs/i18n-ci-guard/` — owns the guard's scan-set; the in-scope files must be on it (verify before declaring R7 done).

### Other prompt-generator specs (R6 refinement target)

- `i18n-oasis-profile-generator-prompts/` — covers prompt blocks. Two Han hits remain in `oasis_profile_generator.py` (lines 193 — `"LLM_API_KEY 未配置"` ValueError, and 796–810 — `country = "中国"` plus comment fragments).
- `i18n-ontology-generator-prompts/` — covers prompt blocks. Han remnants exist in `ontology_generator.py` (lines 409–473 — generated-code header strings written into the ontology Python file).
- `i18n-simulation-config-generator-prompts/` — covers prompt blocks. Two Han hits remain in `simulation_config_generator.py` (lines 240 and 484 — `ValueError("LLM_API_KEY 未配置")` and `Exception("LLM调用失败")`).

These are error-message strings, **not** prompts — so they fall outside the three prompt-generator specs' explicit scope. R6's audit must clearly classify each as "covered" or "uncovered" and append follow-up tasks to the appropriate spec rather than silently dropping them.

## 2. Requirements Feasibility Analysis

| Requirement | Needs | Gap classification |
|---|---|---|
| R1 zep_tools.py externalization | ~40 new locale keys under `zep_tools.output.*`; route `to_text()` and inline prompts through `t()` | Missing (no spec, but pattern is established) |
| R2 zep_graph_memory_updater.py | ~20 new keys under `zep_graph_memory_updater.action.*`; preserve interpolation | Missing |
| R3 backend script console output | ~140 new keys under `scripts.<file>.*`; `set_locale()` boot in each script | Missing |
| R4 Step4Report.vue marker source | locale-aware `REPORT_MARKERS` (parameterised or per-locale set); dual-token `isError` | Missing (existing dual-check pattern at L639 is precedent) |
| R5 cross-layer e2e test | fixture-driven verification that English `to_text()` output matches all `REPORT_MARKERS` | Missing; extend existing audit harness under `.kiro/specs/i18n-e2e-english-verification/` |
| R6 prompt-coverage audit | read-only artefact `prompt-coverage-audit.md` + append-tasks to three existing specs' `tasks.md` | Constraint: do not modify the generator sources |
| R7 CJK guard passes | confirm guard scan set includes the six files | Constraint: must not regress |

**Non-functional concerns**:

- The Report Agent reads `zep_tools.py` `to_text()` output and renders it back to the LLM. If a key resolves to the key string itself (missing), the Report Agent receives a debug-style identifier and the report degrades visibly. Acceptable per R1.AC4 (no exception), but the locale-parity guard (`i18n-locale-parity-guard`) should already block missing-key drift.
- `Step4Report.vue` runs in the browser; the active locale comes from `vue-i18n`'s `useI18n()`. The Report Agent server-side response carries no explicit locale marker — but the request that produced it does. The simplest correct approach: pick the report locale from `useI18n().locale.value` in the component (same locale the request used).

## 3. Implementation Approach Options

### Option A — Single big-bang PR covering R1–R7 (recommended)

Treat the umbrella spec as one atomic deliverable: every in-scope file is rewritten, all new keys land in both locale JSONs at once, the frontend parser is updated in the same commit-set, and the e2e test gate is added before any of the changes flip production behavior.

- ✅ Closes the umbrella issue in one PR; no half-state where the backend emits English but the frontend still expects Chinese (Gap 4 risk avoided by construction).
- ✅ The new cross-layer test (R5) protects against future regression.
- ❌ XL diff. Review burden is high. Reviewers will want the diff split into logical commits.
- **Mitigation**: stage commits so each is reversible — (1) add locale keys, (2) `zep_tools.py` route through `t()`, (3) `zep_graph_memory_updater.py`, (4) `Step4Report.vue` locale-aware markers + dual-token `isError`, (5) backend scripts, (6) R6 audit artefact, (7) R5 cross-layer test.

### Option B — Phased: ship Gap 2 + Gap 3 first, then a second PR for Gap 1 + Gap 4 + R5

- ✅ Smaller individual PRs; reviewers see a clean separation.
- ❌ Two PRs for one umbrella ticket. The autonomous workflow expects ONE PR per ticket; Option B requires splitting the ticket into sub-issues, which is out of scope for this run.
- ❌ Doesn't close umbrella issue #46 in one motion.

### Option C — Hybrid: Option A's scope, but defer R6's audit to a "spec-only" companion PR

- ✅ Code PR has zero `.kiro/specs/i18n-*-prompts/tasks.md` edits.
- ❌ R6 acceptance moves into a second commit/PR. Same autonomy problem as Option B.

**Recommendation**: Option A, staged-commit form. The Gap 4 lock-step risk is the dominant factor — atomic landing eliminates it. The R6 audit can be a single new artefact + targeted task-list appends without touching generator source.

## 4. Out-of-Scope (Research Needed flagged for design)

- **Locale propagation from Report Agent response → Step4Report.vue rendering**: confirm whether the frontend should re-fetch markers per render or freeze them once per component mount. Both work; default to per-render (cheap; supports locale switching mid-session).
- **Are the inline prompts in `zep_tools.py` (sub-query generator, agent-selection planner, interview question/summary writers) actually translation candidates, or do they require `get_language_instruction()` post-injection like other prompt specs?** Most likely the latter — keep their bodies in English, suffix `get_language_instruction()` to instruct the LLM to respond in the user's locale. Verify in design.
- **Backend script `set_locale()` source**: env var (`MIROFISH_LOCALE`) vs. CLI flag vs. `LANG`/`LC_ALL`. Pick one in design; pragmatically `os.environ.get("MIROFISH_LOCALE", "zh")` matches the rest of the backend's default.

## 5. Implementation Complexity & Risk

- **Effort**: **L** (1–2 weeks if conservatively reviewed) → realistic minimum **5–7 working days** to:
  - 40 + 20 + 140 = ~200 new locale keys × 2 languages = ~400 catalogue entries.
  - 7 source-file rewrites.
  - 1 new test artefact.
  - 1 new audit artefact + minor task-list edits in three existing specs.
- **Risk**: **Medium**.
  - Lock-step risk between zep_tools.py and Step4Report.vue is the headline concern; Option A absorbs it but a reviewer who only reads one half of the diff could miss a regression. **Mitigate** by listing every removed Chinese literal and its frontend dependent in the PR description.
  - The inline-prompt blocks in `zep_tools.py` (lines 1095–1101, 1574–1597, etc.) are LLM-facing — translation drift can change model behavior. Treat them with the same care as the existing prompt-generator specs: keep system-prompt bodies in English and inject `get_language_instruction()` for the user-visible response.

## 6. Recommendation for Design Phase

- **Preferred approach**: Option A, with the seven-commit staging described above.
- **Key decisions to lock in design**:
  1. Locale key namespace shape: `zep_tools.output.<symbol>` vs. flat `zep_tools.<symbol>`. Recommend nested to match `log.zep_tools.*`.
  2. Frontend marker source: parameterised regex (a `markersForLocale(locale)` factory) is preferable to per-locale duplicated objects — single source of truth, easier review.
  3. `set_locale()` source for backend scripts: env var, default `zh`.
  4. Inline-prompt translation: rewrite system prompts in English; append `get_language_instruction()` for response-language control. Mirror the convention from `i18n-report-agent-prompts`.
- **Research items** (carried forward to design): the three "Out-of-Scope" items above.

## 7. Risks not blocking design

- Some Chinese characters embedded in regex char-classes inside `zep_tools.py` (e.g. `re.split(r'[。！？]', clean_text)`, `r'[，,；;：:、]'`) are **Unicode punctuation**, not natural-language strings, and should remain as-is. Design must list these explicitly so the implementation does not over-zealously translate punctuation that drives sentence segmentation.
- `Step4Report.vue` regex must also keep the Chinese-quotation-mark splitters intact: those are punctuation, not user-facing copy.
