# Research & Design Decisions — i18n-mandarin-gap-coverage

## Summary

- **Feature**: `i18n-mandarin-gap-coverage`
- **Discovery Scope**: Extension (closing gaps in an established i18n initiative)
- **Key Findings**:
  - The backend `t()` helper in `backend/app/utils/locale.py` already supports per-thread locale, `{key}` interpolation, and a missing-key fallback that returns the key itself — no new infrastructure needed.
  - `Step4Report.vue:541-548` already documents the intended migration strategy: "a translated marker is added by appending an alternation branch to the relevant regex." This is the cheapest correct approach for R4 and removes the need for a per-locale marker factory.
  - The `i18n-allow-block` annotation around `REPORT_MARKERS` indicates the CJK CI guard already recognizes a deliberate-exception block delimiter; we will retain the block (Chinese alternates remain), and add the English alternates inside it.

## Research Log

### Locale helper capabilities

- **Context**: Decide whether the existing `t()` helper covers all needed cases for backend-script use.
- **Sources Consulted**: `backend/app/utils/locale.py`.
- **Findings**:
  - `t(key, **kwargs)` performs `value.replace(f'{{{k}}}', str(v))` — pure-string substitution, no `.format()` semantics. Templates must use `{name}` placeholders, never `{0}` positional or `{name:>10}` format specs.
  - `set_locale(locale)` writes to thread-local storage; safe to call from any thread before emitting localized output. Backend scripts run as the main thread, so calling `set_locale(...)` once at entry is enough.
  - Missing-key fallback already returns the key string and warns once per `(locale, key)` pair — exactly what R1.AC4, R2.AC*, and R3.AC5 require.
- **Implications**: No new helper APIs needed. Backend scripts can `from app.utils.locale import t, set_locale`; new locale-key namespaces (`zep_tools.output.*`, `zep_graph_memory_updater.action.*`, `scripts.<name>.*`) plug straight in.

### Frontend marker-source strategy

- **Context**: Choose between (a) parameterised regex factories per locale, (b) per-locale marker objects, or (c) alternation-branch regexes that accept both languages.
- **Sources Consulted**: `frontend/src/components/Step4Report.vue:541-643`.
- **Findings**:
  - The file already documents alternation-branch as the planned migration mechanism (comment at line 547).
  - `isError(line)` already returns true for either `'ERROR'` or `'错误'`, demonstrating the dual-token pattern.
  - Marker patterns are simple — they don't need to differ structurally between locales, only in the literal labels they look for (e.g. `分析问题:` vs `Analysis question:`).
- **Implications**: Apply alternation branches consistently. Each regex such as `/分析问题:\s*(.+?)(?:\n|$)/` becomes `/(?:分析问题|Analysis question):\s*(.+?)(?:\n|$)/`. No new abstractions; every match path the frontend uses today continues to work; the English path is additive. The `i18n-allow-block` boundary stays intact.

### Inline LLM prompts in `zep_tools.py`

- **Context**: `zep_tools.py:1095-1101`, `:1574-1597`, `:1638-1656`, `:1692-1713` contain four LLM system/user prompt blocks emitted in Chinese.
- **Sources Consulted**: existing `.kiro/specs/i18n-report-agent-prompts/` design patterns, `backend/app/utils/locale.py:get_language_instruction`.
- **Findings**:
  - The convention in sibling prompt specs is: rewrite the system prompt body in **English** as the canonical source; append `get_language_instruction()` at the end of the system message so the model responds in the user's locale.
  - `get_language_instruction()` reads from `_languages` (sourced from `locales/languages.json`) and returns the LLM-facing instruction string for the current locale.
- **Implications**: Treat the four inline prompts the same way as the report-agent-prompts spec did. They are **not** routed through `t()` because their content is a single English baseline, not a translatable string set — only the appended language directive varies.

### Punctuation regex characters

- **Context**: `zep_tools.py` and `Step4Report.vue` both contain Han characters embedded in regex character classes that drive sentence segmentation, not display copy.
- **Sources Consulted**: `zep_tools.py:312`, `:1425-1443`; `Step4Report.vue` (no Han in regex char-classes after first scan, but quote-mark normalization at L307-310 of `zep_tools.py` uses CJK quote codepoints).
- **Findings**: Listed exhaustively below. These are punctuation, not strings.
  - `re.split(r'[。！？]', ...)` — sentence-end punctuation.
  - `re.sub(r'问题\d+[：:]\s*', '', ...)` — question-numbering label.
  - `re.sub(r'【[^】]+】', '', ...)` — bracketed-section stripping.
  - `re.findall(r'「([^「」]{15,100})」', ...)` — paired CJK corner brackets.
  - The leading-punctuation strip set `'，,；;：:、。！？\n\r\t '`.
- **Implications**: These remain in the source. The CJK CI guard must either skip these expressions (via the existing `# i18n-allow-line` mechanism if one exists) or they must be moved into a named constant whose value is then either unaffected by the guard or annotated.

### CJK CI guard scope

- **Context**: R7 requires the guard to scan all six in-scope backend files and exit 0.
- **Sources Consulted**: `.kiro/specs/i18n-ci-guard/`, `scripts/ci/tests/test_i18n_cjk_guard.py`.
- **Findings**: The CJK guard exists and is owned by the `i18n-ci-guard` spec. Its scan set is configured in the guard implementation (`scripts/check_i18n_logs.py` if present, or the closely-named alternative).
- **Implications**: Verify the guard scans `backend/app/services/*.py` and `backend/scripts/*.py` by default. If it does, R7 is satisfied automatically once the source files are clean. If it doesn't, add the paths to the guard's allow-list of scanned files.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A | Single big-bang PR; alternation-branch regex for frontend; `t()` for all backend literals | Closes umbrella issue in one motion; eliminates Gap 4 lock-step risk by construction; reuses existing helpers | Large diff; reviewer load | Selected |
| B | Phased: Gap 2 + Gap 3 first PR, Gap 1 + Gap 4 + R5 second PR | Smaller individual diffs | Two PRs; doesn't fit the one-ticket-one-PR autonomous workflow | Rejected |
| C | Per-locale marker factory in `Step4Report.vue` | Cleaner separation of locale data | New abstraction the file doesn't currently need; conflicts with the existing `i18n-allow-block` documentation that already plans alternation | Rejected |

## Design Decisions

### Decision: Alternation-branch regex in `Step4Report.vue`

- **Context**: The Step 4 report parser must accept both Chinese (legacy) and English (post-translation) backend output.
- **Alternatives Considered**:
  1. Per-locale `REPORT_MARKERS` selected by the active `vue-i18n` locale.
  2. Marker factory that builds patterns from a key → `{en, zh}` literal map.
  3. **Alternation-branch regexes** that match either language.
- **Selected Approach**: Option 3. Each regex literal embeds `(?:CN|EN)` for the language-variable portion, leaving the rest of the pattern unchanged.
- **Rationale**: Matches the file's own documented migration plan (line 547); requires zero new abstractions; backward-compatible (existing Chinese output still parses); the `i18n-allow-block` annotation stays in place. Frontend never needs to know the active locale at parse time.
- **Trade-offs**: Patterns become slightly longer; minor regex-cost increase. Marker names stay stable.
- **Follow-up**: Once `i18n-report-agent-prompts` and this spec are both live, a future spec can simplify by removing the Chinese branches — but that's out of scope here.

### Decision: Locale key namespacing

- **Context**: Choose a stable namespace for new keys.
- **Alternatives Considered**: flat (`zep_tools_search_query`) vs. nested (`zep_tools.output.search_query`).
- **Selected Approach**: Nested, mirroring the existing `log.zep_tools.*` convention.
  - `zep_tools.output.<symbol>` for `to_text()` output and inline-prompt fallbacks.
  - `zep_graph_memory_updater.action.<verb>` for the 16 action descriptions.
  - `scripts.<script_stem>.<symbol>` for backend-script output.
- **Rationale**: Consistent with existing namespaces; the locale-parity guard (`i18n-locale-parity-guard`) already handles nested dictionaries.
- **Trade-offs**: Slightly more keystrokes in `t()` calls; outweighed by readability.
- **Follow-up**: Add a single-paragraph note to the spec's PR description listing the new namespaces so reviewers can grep them.

### Decision: Inline LLM prompts handled as plain English, not `t()`-routed

- **Context**: The four prompt blocks inside `zep_tools.py` are LLM-facing, not user-facing.
- **Alternatives Considered**:
  1. Route every prompt block through `t()` with per-locale variants.
  2. Rewrite prompt bodies in English; append `get_language_instruction()` so the model replies in the user's locale.
- **Selected Approach**: Option 2.
- **Rationale**: Matches the sibling `i18n-report-agent-prompts` and three prompt-generator specs' convention; avoids drift between locale catalogues for prompts (the prompt is a model interface, not a user copy).
- **Trade-offs**: A bilingual operator who scans the source sees only English prompts; that is consistent with the rest of the i18n initiative.
- **Follow-up**: None — same convention as four other specs in this repo.

### Decision: Backend-script locale source

- **Context**: R3 requires backend scripts to honor a locale.
- **Alternatives Considered**: `LANG`/`LC_ALL`, `--locale` CLI flag, dedicated `MIROFISH_LOCALE` env var.
- **Selected Approach**: `MIROFISH_LOCALE` env var with default `zh` (current behavior).
- **Rationale**: Simplest; consistent with the no-flag, no-extra-CLI ethos of `config.py`; doesn't collide with system locale settings that might be `en_US.UTF-8` on a Chinese-locale operator's box.
- **Trade-offs**: Less discoverable than a CLI flag; mitigated by referencing it in `.env.example`.
- **Follow-up**: Add `MIROFISH_LOCALE` to `.env.example` documentation as an optional override.

## Risks & Mitigations

- **R-1 Lock-step regression** — externalizing `zep_tools.py` without coordinating `Step4Report.vue` breaks the Step 4 view. **Mitigation**: alternation-branch regex + R5 cross-layer test gate.
- **R-2 Inline-prompt model-behavior drift** — translating an LLM-facing prompt may change generation behavior. **Mitigation**: keep prompt bodies in English (the convention used throughout the i18n initiative); rely on `get_language_instruction()` to swing the response language.
- **R-3 Punctuation regex false positives in CJK guard** — character-class regexes containing Han punctuation could trip the guard. **Mitigation**: lift such patterns into named module-level constants where annotation comments can suppress per-line, or rely on the existing per-block `i18n-allow-block` marker pattern.

## References

- `.kiro/specs/i18n-report-agent-prompts/` — sibling spec; convention for English-prompt + language-instruction injection.
- `backend/app/utils/locale.py` — `t()`, `set_locale()`, `get_language_instruction()` reference.
- `frontend/src/components/Step4Report.vue:540-643` — `REPORT_MARKERS` block and the existing `i18n-allow-block` annotation.
- `.kiro/specs/i18n-ci-guard/` — owner of the CJK guard scan-set.
- `.kiro/specs/i18n-e2e-english-verification/` — owner of the audit harness this spec extends.
