# Gap Analysis — `i18n-frontend-ui-strings`

## 1. Scope and current state

The five files in scope are at very different stages of i18n adoption. The audit drilled into each one and uncovered substantially more flagged sites than the ticket body enumerated; the spec is broader in practice than its evidence list suggests.

| File                          | i18n adoption today                                                                                   | Touch surface                                                |
| ----------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `views/Process.vue`           | **None**. No `useI18n()` import, no `$t` calls. ~40 user-visible Chinese literals across template + JS. | All template headers, status badges, modal/info labels, error strings, fallback names. |
| `components/Step2EnvSetup.vue` | High (~70%). Templates already use `$t`. Remaining: 3 backend-stage equality checks (lines 680/682/689) and a few `console.warn` strings (not user-visible). | Stage-watcher logic only.                                   |
| `components/Step3Simulation.vue` | Sparse (1 `$t` call). The template is mostly English already, but the JS has `startError.value = res.error \|\| '启动失败'` (line 423/427). | A single fallback string.                                   |
| `components/Step4Report.vue`  | Sparse (2 `$t` calls). The bulk of the file is **29 regex patterns** matching Chinese section markers emitted by `report_agent.py`, plus three string-equality checks for the no-reply marker, plus a log-severity classifier. | Parser/regex layer + a small set of UI literals (e.g. line 1464 `'选择理由'`, line 1774 `'等待开始'`). |
| `components/Step5Interaction.vue` | Extensive (~35 `$t` calls). Two literals remain: lines 725 and 727 — both **prompt strings sent to the backend LLM**, not user-visible UI. | Prompt construction in the chat-history feature.            |

`createI18n` lives at `frontend/src/i18n/index.js`. Default locale is `'zh'` (read from `localStorage`), fallback `'zh'`. Locales come from repo-root `/locales/*.json` via `import.meta.glob`. Both `en.json` and `zh.json` are aligned at 1031 lines after issue #20's backfill.

The audit script the original ticket refers to (`.kiro/specs/i18n-e2e-english-verification/audit/scripts/run_audit.sh`) **does not exist** — only the empty directory shell remains. Verification has to be done by direct grep over the five files (Requirement 6).

## 2. Requirement-to-asset map

| Req | Need                                                                                  | Existing asset (file)                                                | Gap label                                              |
| --- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------ |
| R1  | Wire `useI18n()` into `Process.vue`; route ~40 strings through new `process.*` keys    | No i18n import; no `process.*` namespace yet                         | **Missing** — both wiring and namespace                |
| R2  | Externalize remaining UI literals in Step3/Step4/Step5                                 | `useI18n()` already imported in all three; namespaces `step3/4/5.*` exist | **Constraint** — match existing namespace structure   |
| R3  | en.json/zh.json parity for new keys                                                    | Issue #20 / spec `i18n-backfill-zh-json` already aligned them         | **Constraint** — must not regress; checker exists informally |
| R4  | Stage-name comparator that survives backend translation                                | `Step2EnvSetup.vue:679-692` watcher; backend emits both Chinese display strings and snake_case ids | **Missing** — small lookup map needed                  |
| R5  | Bilingual (Chinese + English) tolerance for 29 regex parsers + 3 marker checks + log classifier | `Step4Report.vue:557-943` regex block; `:1334`, `:2014-2015` checks | **Missing** — backend-coupled; depends on what translated prompts emit |
| R6  | Local verification check                                                               | Audit script gone; vanilla `grep` available                          | **Missing** — small script or documented one-liner    |

### Research-needed flags

- **Backend-emitted English strings** (R5) — issues #25 (LLM prompt assembly translation) and the open `i18n-report-agent-prompts` spec dictate what English markers `report_agent.py` will eventually emit (e.g., will it become `Analysis question:`, `Analyze question:`, or stay as a stable `分析问题:`?). The frontend can't pin its English regexes to specific wording until that backend spec is settled. **Mitigation strategy**: keep the existing Chinese regexes intact (for backwards compat with current backend) and add deliberately permissive English alternates that match a documented set of likely renderings, plus keep an explicit allowlist of "deliberate Chinese tokens for backend compatibility" so the audit doesn't re-flag them.
- **Step5Interaction.vue prompt strings** (lines 725, 727) — these are not UI; they are *prompt content sent to the LLM*. If the user is on `zh` locale and chats with a Chinese-trained agent, the Chinese phrasing is intentional. Two viable strategies: (a) localize to active locale via `t()` (correct linguistically; assumes the agent handles both), or (b) keep Chinese literally because the agent is currently Chinese-tuned. The wider initiative is moving the backend to English, so option (a) aligns better — but coordinating with the report agent's actual prompt translation (separate spec) would be ideal. For this spec, route through i18n keys and let the active locale dictate; document the assumption.

## 3. Implementation approach options

### Option A — Pure extension (recommended)

Treat this as a localized cleanup of five existing files plus locale-file additions. All work is "match the surrounding file's style," no new abstractions.

- **Files extended**: 5 Vue files + 2 locale files. No new files (or 1 new file: a small grep-based verifier).
- **Compatibility**: The new i18n keys layer onto an existing pattern (`step2.*`, `step4.*`, etc.). No public surface changes.
- **Complexity**: Low to medium. The big number is the count of strings, not their individual difficulty. The two genuinely tricky pieces are (i) the bilingual regex strategy in `Step4Report.vue`, (ii) the stage-comparator refactor in `Step2EnvSetup.vue`.

**Trade-offs**:

- ✅ Least architectural change; matches the steering principle "match the surrounding file's style."
- ✅ Each file's edits are independent; reviewable in isolation.
- ❌ Adds size to `Process.vue` (already ~50KB) — but the additions are mostly `t()` substitutions, not new logic.

### Option B — Extract a `useStageMatcher()` composable + a `parseReportSection()` utility

Make new files for the two backend-coupled responsibilities (R4 and R5):

- `frontend/src/composables/useStageMatcher.js` — owns the legacy-Chinese ↔ snake_case ↔ future-English equivalence map.
- `frontend/src/utils/reportParsers.js` — owns the bilingual regex set and exposes typed extractors.

**Trade-offs**:

- ✅ Cleaner separation; future backend-output changes localize into one parser file.
- ❌ Moves regexes out of `Step4Report.vue` where today they sit alongside the consumer; the steering doc favors keeping pipeline-stage logic in the matching Step component unless responsibilities truly diverge. Arguably they don't yet.
- ❌ Larger PR, more files for reviewers to navigate.

### Option C — Hybrid

Apply Option A everywhere, but extract `useStageMatcher()` (Option B's smaller half) because the stage equality check is duplicated three times in one watcher and obviously benefits from a single source of truth. Leave the `Step4Report.vue` parsers in place and add the bilingual alternates inline; this avoids designing an extraction boundary against a backend that's still being translated.

## 4. Recommendation

**Hybrid (Option C)**.

- **R1, R2, R3**: pure extension — substitute `t('…')` and add keys to both locale files.
- **R4**: introduce a tiny in-file lookup (or, if it earns its keep, a small composable) so that future stage strings only need adding in one place.
- **R5**: extend the existing regexes inline. Each parser becomes `chineseRegex.test(...) ? extract(chineseRegex) : englishRegex.exec(...)` (or an explicitly bilingual single regex like `/(?:分析问题|Analysis question):/`). Document the deliberate Chinese tokens at the top of the parser block so the verifier in R6 can allowlist them.
- **R6**: a `frontend/scripts/audit-i18n-strings.{sh,js}` (the existing repo has no equivalent yet) that greps the five files for unicode CJK literals minus an allowlist; runnable locally in seconds, no backend required. Keep it tiny — this is verification, not a new test framework.

**Effort**: **M** (3–7 days of focused work). The volume in `Process.vue` is significant (~40 keys), but each substitution is mechanical. R5 is the only piece with real design content.

**Risk**: **Medium**. Risk concentration:

- **R5 (parsers)** — Medium. If the backend prompt translations land between this PR's merge and a release, and the actual English wording doesn't match the alternates we encoded, reports degrade silently. Mitigation: write the alternates against the actual prompts in `backend/app/services/report_agent.py` rather than guessing, and keep all Chinese regexes alive as fallbacks for as long as the backend is partially-translated.
- **R3 (locale parity)** — Low. Tooling-aided; #20 just established the discipline.
- **R1 (Process.vue)** — Low individually, but the volume means review fatigue is a real risk. Recommend the PR call out logical chunks (header / progress / errors / fallback labels) so the reviewer can sign off section by section.

## 5. Research items to carry into design

1. Read `backend/app/services/report_agent.py` (and any prompt template referenced by it) to enumerate the *actual* English strings it emits *today*, not what we assume it will emit. The R5 regex alternates must be grounded in real backend output. Cross-reference the open spec `i18n-report-agent-prompts` for the planned English wording.
2. Confirm whether `Step2EnvSetup.vue:680-689` ever sees backend-emitted English display strings now, or only the snake_case identifiers. If only snake_case, the comparator can prefer those and treat the Chinese as backwards-compat-only.
3. Confirm that `Step5Interaction.vue:725-727` (chat history templating) is acceptable to localize via `t()` — i.e., that the report agent handles both `Question: …` and `提问者：…` framings of chat history. If not, leave Chinese in for now and open a separate ticket to migrate alongside the backend agent prompt translation.
4. Decide naming for the new `process.*` namespace: align with adjacent step namespaces (`step1.*` etc.) or use a fresher grouping. The existing `graph.*` namespace already covers some of the graph-panel headers and may absorb several of `Process.vue`'s strings rather than duplicating them.

---

## Output checklist

- ✅ Requirement-to-asset map with gaps tagged
- ✅ Options A/B/C with trade-offs
- ✅ Effort **M**, Risk **Medium** with justification
- ✅ Recommendation: Option C (hybrid)
- ✅ Research items carried forward
