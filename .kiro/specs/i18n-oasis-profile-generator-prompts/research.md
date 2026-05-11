# Research & Design Decisions — i18n-oasis-profile-generator-prompts

## Summary

- **Feature**: `i18n-oasis-profile-generator-prompts`
- **Discovery Scope**: **Extension** (single-file translation in an existing
  brownfield service; sibling pattern already merged in #2, #4, #5)
- **Key Findings**:
  - The existing `get_language_instruction()` postfix mechanism (defined in
    `backend/app/utils/locale.py`) is the project-canonical way to steer LLM
    output language. Translating the base prompt does not interfere with it
    and is the same approach taken in already-merged sibling specs.
  - The only Chinese surfaces inside the prompt-rendering path are
    `_get_system_prompt`, `_build_individual_persona_prompt`,
    `_build_group_persona_prompt`, and the four `attrs_str`/`context_str`
    fallback literals (`"无"`, `"无额外上下文"`). All other Chinese in the
    file is logger keys (already done by #6), docstrings/comments
    (out-of-scope, #7), or rule-based fallback data (out-of-scope).
  - `backend/scripts/test_profile_format.py` does not exercise prompts; it
    only constructs `OasisAgentProfile` and round-trips through
    `_save_twitter_csv` / `_save_reddit_json`. A pure-translation diff
    cannot break it.

## Research Log

### Locale steering mechanism

- **Context**: Confirm that translating the base prompt does not regress
  Chinese output under `Accept-Language: zh`.
- **Sources Consulted**:
  - `backend/app/utils/locale.py` (lines 50–96).
  - `locales/languages.json` (entries for `en` and `zh` with
    `llmInstruction` field).
  - Sibling spec `i18n-ontology-generator-prompts/design.md` and the
    merged commits referenced by it.
- **Findings**:
  - `get_language_instruction()` returns `Please respond in English.`
    for locale `en`, `请使用中文回答。` for locale `zh`.
  - The function is called as an inline f-string interpolation in the
    individual-persona and group-persona prompt bodies, and explicitly
    appended in `_get_system_prompt`. All three sites must be preserved
    byte-for-byte.
  - The thread-local locale is captured in
    `generate_profiles_for_entities` (line ~910) and restored inside the
    worker via `set_locale(current_locale)` (line ~914). This plumbing is
    untouched by the change.
- **Implications**:
  - Design lock-in: the inline `{get_language_instruction()}` call must
    remain in each of the three builders. Removing or renaming it would
    silently regress non-English locales.
  - The Chinese hint `country: 国家（使用中文，如"中国"）` in the original
    prompt overrides the locale postfix and forces Chinese output for one
    field. The English translation drops that hint so the locale postfix
    decides the country language. The rule-based fallback (out of scope)
    has its own (Chinese) defaults and is not affected.

### Test contract

- **Context**: Verify that `backend/scripts/test_profile_format.py`
  remains green after a prompt-only translation.
- **Sources Consulted**: `backend/scripts/test_profile_format.py`,
  `oasis_profile_generator.py:_save_twitter_csv`,
  `oasis_profile_generator.py:_save_reddit_json`,
  `oasis_profile_generator.py:to_reddit_format`,
  `oasis_profile_generator.py:to_twitter_format`.
- **Findings**:
  - The pytest function `test_profile_formats` constructs
    `OasisAgentProfile` instances directly without invoking the LLM.
  - It calls `_save_twitter_csv` and `_save_reddit_json` to verify CSV
    and JSON shape. Required CSV header: `user_id, user_name, name, bio,
    friend_count, follower_count, statuses_count, created_at`. Required
    JSON keys: `realname, username, bio, persona`.
- **Implications**:
  - Translating prompts cannot regress this test. The validation
    requirement (Requirement 7) is satisfied automatically as long as
    serializer code is not edited.
  - No new tests are required for this change.

### Sibling specs already shipped

- **Context**: Confirm there is an established project pattern this work
  must mirror.
- **Sources Consulted**:
  - `.kiro/specs/i18n-ontology-generator-prompts/{design,tasks,requirements}.md`
  - `.kiro/specs/i18n-report-agent-prompts/`
  - `.kiro/specs/i18n-simulation-config-generator-prompts/`
  - Recent merged commits referencing #2, #4, #5.
- **Findings**:
  - All three siblings used a single-file in-place translation diff.
  - All three preserved every `get_language_instruction()` call site.
  - All three left logger calls and docstrings to companion issues
    (#6 / #7).
  - None externalized prompts to `/locales/*.json`.
- **Implications**:
  - The same approach is correct here. Reviewer expectations are set by
    the sibling diffs.

### OASIS profile schema

- **Context**: Verify that translated prompts continue to satisfy the
  OASIS subprocess's expected schema (especially `gender` enum and
  `age` integer).
- **Sources Consulted**: `OasisAgentProfile` dataclass,
  `to_reddit_format`, `to_twitter_format`, sibling `_generate_profile_rule_based`.
- **Findings**:
  - OASIS-required fields are produced by serializers, not by the
    prompt: `user_id`, `username`, `name`, `bio`, `karma`/`friend_count`/`follower_count`/`statuses_count`, `created_at`.
  - The prompt-defined fields land in optional positions: `age`,
    `gender`, `mbti`, `country`, `profession`, `interested_topics`.
  - The `gender` enum constraint (`"male"`/`"female"` for individuals,
    `"other"` for groups) is locale-independent and must remain in
    English text inside the translated prompt.
- **Implications**:
  - The English prompt must explicitly call out `gender ∈ {male, female}`
    (individual) and `gender == "other"` (group), independent of the
    `get_language_instruction()` postfix.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| **A — In-place builder edit** | Translate three method bodies + four fallback literals directly | Smallest diff; matches sibling pattern; zero API change | None of note | **Selected** |
| B — Module-level constants | Hoist prompts to `INDIVIDUAL_PERSONA_PROMPT_TEMPLATE` etc. | Easier `git grep` | Larger diff; the inline `{get_language_instruction()}` call would need to become a `.format()` kwarg, which is a behavioural change beyond translation | Diverges from #4 / #5 |
| C — Externalize to `locales/*.json` | Move every prompt sentence into `t(...)` keys | Most i18n-pure | Three-file diff; diverges from project rationale (prompts use postfix mechanism, not key files) | Rejected |

## Design Decisions

### Decision: In-place edit of the three prompt builders (Option A)

- **Context**: Three methods build prompt strings; one of them is a
  one-line system prompt, the other two are large f-string templates
  with embedded `{variable}` interpolations and an inline
  `{get_language_instruction()}` call.
- **Alternatives Considered**:
  1. Option B — module-level constants.
  2. Option C — externalize to `/locales/*.json` keys.
- **Selected Approach**: Translate each method body in place. Replace
  the four `"无"` / `"无额外上下文"` fallbacks with English equivalents
  (`"None"` and `"No additional context"`). Preserve all `{...}`
  interpolations and the inline `{get_language_instruction()}` call.
- **Rationale**: Matches merged sibling specs verbatim. Smallest review
  surface. Zero API change. Out-of-scope surfaces (logger, docstrings,
  rule-based fallback) cleanly avoided.
- **Trade-offs**: Leaves the file mixed-language in non-prompt parts
  (docstrings, rule fallback) until #7 lands. Acceptable per scope
  split.
- **Follow-up**: During implementation, run a regex audit for any
  Chinese codepoints inside the three method bodies after the edit and
  confirm the diff stays within
  `backend/app/services/oasis_profile_generator.py`.

### Decision: Drop the "use Chinese country names" hint

- **Context**: The current prompt at line 704 reads
  `country: 国家（使用中文，如"中国"）` and at line 753
  `country: 国家（使用中文，如"中国"）`. This forces Chinese for the
  `country` field even under `Accept-Language: en`.
- **Alternatives Considered**:
  1. Translate to English literally:
     `country: country (use English, e.g. "China")`.
  2. Drop the language hint entirely:
     `country: country name string`.
- **Selected Approach**: Drop the language hint. Let
  `get_language_instruction()` steer the country language alongside
  every other free-text field.
- **Rationale**: Hard-coding a language in the prompt defeats the
  locale-steering mechanism. The rule-based fallback (out of scope)
  carries its own Chinese defaults; under the LLM path, locale should
  decide.
- **Trade-offs**: Under `Accept-Language: zh`, the LLM may produce a
  Chinese country name (e.g. `中国`) — this is the desired behaviour.
  Under `Accept-Language: en`, the LLM produces English (`China`),
  matching `COUNTRIES = ["China", "US", ...]` already in the file.
- **Follow-up**: Verify in the validation phase that a sample run under
  locale `en` produces an English country name.

### Decision: Keep `gender` enum constraint in English inside the prompt

- **Context**: `gender` must be one of `"male"`/`"female"`/`"other"`
  regardless of locale, because OASIS consumers and the
  `_generate_profile_rule_based` fallback assume English values.
- **Alternatives Considered**: None — the constraint is a contract.
- **Selected Approach**: The translated prompt explicitly states the
  enum in English, even when the locale postfix asks for Chinese
  output: `gender MUST be one of "male" or "female" (English literal)`.
- **Rationale**: Same as the existing Chinese prompt (which already
  states `必须是英文: "male" 或 "female"`). The translation preserves
  the same lock-in.
- **Trade-offs**: None.
- **Follow-up**: Validation phase will check that under both locales
  the produced `gender` is one of the three English literals.

## Risks & Mitigations

- **Risk**: Mistranslation drops a locale-independent constraint
  (e.g. `gender` enum, `age` integer rule, `persona` no-newline rule).
  - **Mitigation**: The implementation task list will enumerate every
    constraint inline so reviewers can check by diff.
- **Risk**: Variable-name typo inside an f-string causes a `KeyError`
  at runtime.
  - **Mitigation**: Implementation task verifies that the set of
    `{variable}` interpolations in each translated block matches the
    pre-change set 1:1; a `python -c "import ..."` smoke import and a
    `pytest backend/scripts/test_profile_format.py` run are mandatory.
- **Risk**: Accidentally leaving a CJK codepoint inside the three
  builders.
  - **Mitigation**: Final implementation step runs the project's
    repo-level CJK guard regex (added by #26) constrained to the three
    builders' line ranges.

## References

- `backend/app/services/oasis_profile_generator.py` — target file.
- `backend/app/utils/locale.py` — locale infrastructure.
- `locales/languages.json`, `locales/en.json`, `locales/zh.json` —
  locale registries.
- `.kiro/specs/i18n-ontology-generator-prompts/` — sibling spec #2.
- `.kiro/specs/i18n-simulation-config-generator-prompts/` — sibling
  spec #4.
- `.kiro/specs/i18n-report-agent-prompts/` — sibling spec #5.
- GitHub issue
  [#3](https://github.com/salestech-group/MiroFish/issues/3).
