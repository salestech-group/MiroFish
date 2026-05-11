# Requirements Document

## Project Description (Input)
Issue #10: i18n end-to-end verification of full pipeline. Run a verification pass to prove the entire 5-step pipeline (Graph Build, Env Setup, Simulation, Report, Interaction) works cleanly in English, with locale propagating across Flask routes, background tasks, OASIS subprocess, Graphiti/Neo4j, and the ReACT report agent. Produce a verification report (posted as a comment on issue #10) summarising pass/fail per checklist item and listing any leftover Chinese strings as `file:line` refs. Run the static audit `git grep -nE "[\\x{4e00}-\\x{9fff}]" -- backend/app frontend/src locales/en.json` and confirm only deliberately-kept Chinese remains. File any newly discovered gaps as follow-up issues (do NOT patch silently in this ticket). Acceptance: all checklist items pass for both EN and ZH; report posted; no surprise Chinese in EN paths. Out of scope: fixing newly discovered gaps inline; perf/load testing; new locales beyond EN/ZH.

## Introduction

This spec covers the final verification pass for the i18n epic (#11). After issues #2–#9, #12 land, the entire 5-step MiroFish pipeline must demonstrably run in English — UI, background work, LLM-generated artifacts (ontologies, agent profiles, sim configs, reports, chat replies), and backend logs — without any unintended Chinese leaking into English-locale paths. The pass also regression-checks that switching locale back to Chinese still produces fully Chinese output. Because the pipeline crosses a Flask app, background `Task` workers, an OASIS subprocess, Graphiti/Neo4j, and a ReACT report agent, the verification has both a static (grep + locale-file) component and a dynamic (live walkthrough of Step 1 → 5) component.

The deliverables are: (a) a static audit + categorization of any remaining Chinese strings under English paths, (b) a verification report posted as a comment on issue #10 summarising pass/fail per checklist item with `file:line` evidence, and (c) follow-up GitHub issues for every gap found — fixes are explicitly **out of scope** here.

## Boundary Context

- **In scope**:
  - Static audit (`git grep` for CJK Unified Ideographs) of `backend/app/`, `frontend/src/`, and `locales/en.json`.
  - Inspection of locale catalogues (`locales/en.json`, `locales/zh.json`) for parity, key coverage, and accidental Chinese in the EN catalogue.
  - Inspection of LLM-prompt assets that drive Step 1–5 outputs (ontology, profile, sim-config, report-agent prompts) to confirm they emit English under EN locale.
  - Inspection of locale propagation paths: HTTP request → Flask handler → `Task` background worker → OASIS subprocess → ReACT agent.
  - Verification report posted as a comment on issue #10.
  - Follow-up issues filed for every gap found.
- **Out of scope**:
  - Fixing any newly discovered gaps inline in this ticket — they are filed as separate issues.
  - Performance or load testing.
  - Adding new locales beyond EN/ZH.
  - The live UI walkthrough with screenshots, when no human or browser is available — the static audit results plus prompt/locale-catalogue evidence stand in. The verification report explicitly marks UI-only checklist items as "manual-pending" if not run live.
- **Adjacent expectations**:
  - Closes the i18n epic #11 once #12 also lands.
  - Depends on (and re-verifies) the work in #2, #3, #4, #5, #6, #8, #9, #12.

## Requirements

### Requirement 1: Static CJK audit of English code paths

**Objective:** As an i18n verifier, I want a deterministic grep-based audit of files that should be English-only, so that any Chinese leaking into the EN-locale code path is detected and recorded.

#### Acceptance Criteria

1. The Verification System shall execute `git grep -nE "[\x{4e00}-\x{9fff}]" -- backend/app frontend/src locales/en.json` and capture every match with `file:line` precision.
2. The Verification System shall classify each match as one of: (a) `deliberate` (e.g. test fixture demonstrating ZH input, doc example, comment explicitly retained per project convention), (b) `gap` (unintended Chinese in EN-facing code), or (c) `non-applicable` (false positive such as a regex character class).
3. When a match is classified as `gap`, the Verification System shall record `file:line`, the Chinese substring, and the affected pipeline step (Graph Build / Env Setup / Simulation / Report / Interaction / Logs / UI).
4. The Verification System shall not modify any matched file as part of this audit; remediation is filed as a follow-up issue per Requirement 7.
5. While the audit is running, the Verification System shall additionally inspect `locales/en.json` for entries whose value contains CJK characters and report those separately (an EN catalogue value containing Chinese is always a `gap`).

### Requirement 2: Locale catalogue parity check

**Objective:** As an i18n verifier, I want to confirm that the EN and ZH catalogues stay in lockstep, so that switching locale never falls back to a missing key or leaks the other locale.

#### Acceptance Criteria

1. The Verification System shall enumerate the key set of `locales/en.json` and `locales/zh.json` (recursively across nested objects) and compute the symmetric difference.
2. If a key is present in `en.json` but missing from `zh.json` (or vice versa), the Verification System shall record the missing key path and treat it as a `gap`.
3. If any value in `en.json` contains a CJK character, the Verification System shall record it as a `gap` (as in Requirement 1.5).
4. If any value in `zh.json` is identical to its `en.json` counterpart and the EN value is non-trivial English prose (more than two ASCII words), the Verification System shall flag it as a candidate untranslated entry — these are reported as `review-needed`, not auto-classified `gap`, since some technical terms (URLs, identifiers, single tokens) legitimately stay identical.
5. The Verification System shall not edit either catalogue file as part of this check.

### Requirement 3: LLM-prompt locale verification

**Objective:** As an i18n verifier, I want to confirm that every LLM prompt that drives a Step 1–5 output respects the requested locale, so that ontology entries, agent profiles, simulation configs, report prose, and chat replies render in the user's selected language.

#### Acceptance Criteria

1. The Verification System shall enumerate the prompt files that produce user-visible output for Steps 1–5 (e.g. ontology generator, OASIS profile generator, simulation-config generator, report agent prompts, interview chat).
2. For each prompt file, the Verification System shall confirm that it either (a) is fully English with an explicit "respond in ${locale}" directive, or (b) is rendered through a locale-aware template that injects the active locale.
3. If a prompt file hard-codes a Chinese-only directive (e.g. "请用中文回答") on the EN code path, the Verification System shall record it as a `gap`.
4. The Verification System shall confirm that the prompt files referenced by issues #3, #4, #5 are no longer Chinese-only post-merge; if any still are, they are recorded as `gap` blocking #10.

### Requirement 4: Locale propagation surface review

**Objective:** As an i18n verifier, I want to confirm that the active locale survives every process boundary, so that an EN request still produces EN output after it crosses into a `Task` worker, the OASIS subprocess, or the ReACT agent.

#### Acceptance Criteria

1. The Verification System shall identify each handoff boundary: HTTP → Flask handler, Flask handler → `Task` worker, `Task` worker → OASIS subprocess, ReACT agent → tool calls.
2. For each handoff, the Verification System shall confirm that the locale is either (a) carried explicitly in the call payload / kwargs, or (b) re-derived deterministically (e.g. from per-project config, `Accept-Language` header, or `set_locale` thread-local equivalent) on the receiving side.
3. If a boundary discards the locale and the receiving side defaults silently to Chinese (or any non-EN locale) under an EN request, the Verification System shall record the boundary as a `gap`.
4. The Verification System shall examine the backend logger to confirm that log messages on the EN code path resolve to English templates (depends on #6).

### Requirement 5: Verification report comment on issue #10

**Objective:** As the issue owner, I want a single canonical verification report posted as a comment on issue #10, so that reviewers can see pass/fail per checklist item and trace every `gap` to a `file:line` and a follow-up issue.

#### Acceptance Criteria

1. When the static audit, parity check, prompt verification, and propagation review are complete, the Verification System shall compose a markdown comment on issue #10 that lists every checklist item from the ticket body with one of the statuses `pass` / `gap` / `manual-pending`.
2. For each `gap` status, the comment shall include `file:line` references and a link to the follow-up issue filed per Requirement 7.
3. For each `manual-pending` status, the comment shall state explicitly that the item requires a live UI walkthrough (or full-stack run) which was not performed in this verification environment, and shall list the exact reproduction steps the next reviewer needs to run.
4. The comment shall include the raw output (or a path to the captured output) of the `git grep` audit so future verifiers can diff against the baseline.
5. The Verification System shall post the comment using `gh issue comment 10 --repo salestech-group/MiroFish` and shall record the resulting comment URL in the spec / commit message.

### Requirement 6: ZH regression check

**Objective:** As an i18n verifier, I want to confirm that the ZH locale still renders fully Chinese, so that the EN work has not regressed the original-language experience.

#### Acceptance Criteria

1. The Verification System shall confirm that `locales/zh.json` covers every key present in `locales/en.json` (Requirement 2) so that no UI string falls back to English under ZH.
2. The Verification System shall confirm that prompts rendered through locale-aware templates produce a Chinese variant when locale=zh (i.e. the templating mechanism is symmetric between EN and ZH).
3. If a UI string is English-only under ZH (i.e. `zh.json` value is identical to the EN value and the value is non-trivial English prose), the Verification System shall flag it per Requirement 2.4 as `review-needed`.
4. The Verification System shall record any ZH-specific regression as a separate `gap` and file a follow-up issue per Requirement 7.

### Requirement 7: Follow-up issues for every discovered gap

**Objective:** As the project owner, I want every gap discovered in this verification pass tracked as its own GitHub issue, so that fixes are sequenced separately and #10 stays scoped to verification only.

#### Acceptance Criteria

1. When a `gap` is recorded by Requirements 1–6, the Verification System shall file a GitHub issue against `salestech-group/MiroFish` containing: a one-sentence summary, the affected pipeline step, the `file:line` evidence, and a link back to issue #10 and to the verification report comment.
2. If grouping is sensible (e.g. five `gap`s in a single locale-catalogue file), the Verification System shall consolidate them into a single follow-up issue with a checklist body, instead of filing five micro-issues.
3. The Verification System shall not patch any gap inline in this ticket; the spec change-set must be limited to the verification artefacts (spec docs + report capture under `.kiro/specs/i18n-e2e-english-verification/`) and must not modify production source files under `backend/app/`, `frontend/src/`, or `locales/`.
4. The Verification System shall label every follow-up issue with the `i18n` label (and `bug` if the gap is regressing existing behaviour) so they aggregate under the i18n epic.
5. If the verification environment cannot file issues (e.g. no `gh` permissions), the Verification System shall list the would-be issues inline in the verification report as a fallback so a human can file them, and shall mark the corresponding checklist item `gap-pending-issue` instead of `gap`.

### Requirement 8: Reproducibility and idempotence

**Objective:** As a future verifier, I want this verification pass to be re-runnable, so that we can re-baseline after each subsequent merge to the i18n epic.

#### Acceptance Criteria

1. The Verification System shall capture the raw audit output to `.kiro/specs/i18n-e2e-english-verification/audit/` so the next verifier can diff against the previous run.
2. While a previous capture exists, the Verification System shall preserve it (timestamped or under a `previous/` subdirectory) rather than overwriting it silently.
3. The Verification System shall record the commit SHA at the time of the audit so the report comment can be tied to a specific tree state.
4. If the audit is re-run and the gap set is unchanged, the Verification System shall produce a no-op report comment that confirms parity rather than spamming a new gap list.
