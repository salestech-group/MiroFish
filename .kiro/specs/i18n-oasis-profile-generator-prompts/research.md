# Research & Design Decisions — i18n-oasis-profile-generator-prompts

## Summary

- **Feature**: `i18n-oasis-profile-generator-prompts`
- **Discovery Scope**: Extension (string-literal localization within an existing service, parallel to the just-merged sibling spec `i18n-ontology-generator-prompts`).
- **Key Findings**:
    - Unlike `ontology_generator.py`, this module owns its own JSON-repair logic (`_fix_truncated_json`, `_try_fix_json`, lines 573–660). The repair flow is byte-/character-level (regex-based) and language-agnostic, so R7 (reasoning-model output compatibility) is satisfied implicitly so long as those helpers are not edited.
    - The locale postfix is appended at three sites: `_get_system_prompt` (line 665), `_build_individual_persona_prompt` (line 711), `_build_group_persona_prompt` (line 760). The postfix at lines 711 and 760 is interpolated *inside* the user message, immediately followed by a Chinese gloss (`(gender字段必须用英文male/female)` and `(gender字段必须用英文"other")`) which must be translated to English while preserving the inline `{get_language_instruction()}` interpolation.
    - The thread-local locale is propagated into worker threads at line 914 via `set_locale(current_locale)`. This is required because OASIS profile generation runs through a `ThreadPoolExecutor` and `get_locale()` reads from `_thread_local` outside a request context.
    - The country instruction in both prompt builders currently hard-codes Chinese country names (`国家（使用中文，如"中国"）`) regardless of locale. To deliver the acceptance criterion "personas in English under en", this must become locale-neutral so `get_language_instruction()` drives the language.
    - Three Chinese fallback persona strings (`f"{entity_name}是一个{entity_type}。"`) at lines 547, 644, 659 are output values from the JSON-repair fallback path, not prompt strings. Per the requirements, these are out of scope for #3 — they belong to the broader persona-generation-flow translation work.
    - The OASIS subprocess validates a known set of profile fields (`user_id`, `username`, `name`, `bio`, `persona`, `karma`, `created_at`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`). The schema is preserved by R6 (no API surface change).

## Research Log

### Locale resolution semantics for background threads

- **Context**: Under request context, `get_locale()` reads `Accept-Language`. Under a worker thread inside `ThreadPoolExecutor`, `has_request_context()` returns `False` and `get_locale()` falls back to `getattr(_thread_local, 'locale', 'zh')`. The default is `zh` if no thread-local is set.
- **Sources Consulted**: `backend/app/utils/locale.py`, `oasis_profile_generator.py:909–914`.
- **Findings**:
    - Line 910 captures `current_locale = get_locale()` *before* the thread pool spawns workers (so it reads from the request context).
    - Line 914 calls `set_locale(current_locale)` inside `generate_single_profile`, which runs inside each worker thread. This restores the locale captured from the request context into the worker's thread-local.
    - `get_language_instruction()` is therefore called inside each worker thread with the correct locale.
- **Implications**: The locale-propagation mechanism is correct and unchanged. No code changes needed here. This corroborates R5 acceptance criteria 5 (preserve `set_locale(current_locale)` at line 914).

### JSON-repair flow ownership

- **Context**: R7 requires preservation of the `<think>`/markdown-fence stripping path. Unlike `ontology_generator.py` (which delegates to `LLMClient.chat_json`), this module uses the OpenAI SDK directly.
- **Sources Consulted**: `oasis_profile_generator.py:520–571` (the LLM call) and 573–660 (repair helpers).
- **Findings**:
    - The OpenAI SDK call uses `response_format={"type": "json_object"}` (line 526). This forces JSON object output but does not strip `<think>` tags.
    - `_fix_truncated_json` (lines 573–594) is a brace-/bracket-balance heuristic. Language-agnostic.
    - `_try_fix_json` (lines 596–660) extracts `{...}` via regex, normalizes whitespace, and falls back to extracting `bio` and `persona` via key-prefix regex. Language-agnostic.
    - Crucially, `<think>`-tag stripping is **not** present in this file. If a reasoning-model provider emits `<think>` content, the LLM call here will receive it as JSON-incompatible content and fall through to `_try_fix_json`, which extracts via regex (still works with thinking content as long as a `{...}` block is present).
- **Implications**: Translating the prompts cannot break the repair logic. The single risk is providers that emit non-JSON before the JSON object — already handled by the regex extraction in `_try_fix_json`. R7 is satisfied implicitly.

### OASIS profile schema and downstream consumers

- **Context**: R8 requires the OASIS subprocess (CAMEL-OASIS) to continue accepting the produced profiles.
- **Sources Consulted**: `oasis_profile_generator.py:1060–1183` (`_save_twitter_csv`, `_save_reddit_json`), `backend/scripts/test_profile_format.py`.
- **Findings**:
    - Reddit JSON: emits `user_id, username, name, bio, persona, karma, created_at, age, gender, mbti, country, profession, interested_topics`. Required by OASIS: `user_id`, `username`, `gender ∈ {male, female, other}`, `age` integer.
    - Twitter CSV: emits header `user_id, name, username, user_char, description`. Required by OASIS Twitter loader.
    - `_normalize_gender` (lines 1111–1134) maps Chinese gender words to the OASIS enum. This is needed so that `zh` locale outputs are still accepted by OASIS. Must remain.
    - `test_profile_format.py` instantiates a fully-formed `OasisAgentProfile` and exercises `_save_twitter_csv` and `_save_reddit_json` only. It does not exercise prompt generation. So it is unaffected by this PR's changes.
- **Implications**: All schema-bearing fields are output keys, not prompt content. R6 preserves these. R8 is satisfied as long as the JSON output keys remain `bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`.

### Country-instruction language coupling

- **Context**: The prompt currently instructs the model with `国家（使用中文，如"中国"）` ("country (use Chinese, e.g. 'China'-zh)"). This is the strongest English-bias-leakage point under `en` locale: the prompt explicitly demands Chinese country names. Under `en` locale, that produces a contradiction with `get_language_instruction()` ("Please respond in English.").
- **Sources Consulted**: `oasis_profile_generator.py:704, 753`. The COUNTRIES list (line 164) uses English names (`China`, `US`, `UK`, ...).
- **Findings**:
    - The hard-coded `country: "中国"` defaults in `_save_reddit_json` (line 1169) and `_generate_profile_rule_based` (lines 808, 819) are output-side defaults, not prompt content. They remain in scope of broader i18n issues (#6 likely).
    - The prompt's country instruction is fixable here: replace `国家（使用中文，如"中国"）` with `country` (no language qualifier) and let `get_language_instruction()` drive the response language.
- **Implications**: This is a small but important translation: it removes the strongest cross-locale bias in the prompt. Documented in the design as an explicit decision.

### Sibling test pattern: AST-based no-CJK guard

- **Context**: The just-merged sibling spec `i18n-ontology-generator-prompts` introduced `backend/scripts/test_ontology_prompts_no_cjk.py`, an AST-based static check that asserts zero CJK characters in the targeted prompt-bearing literals.
- **Sources Consulted**: `backend/scripts/test_ontology_prompts_no_cjk.py`, `backend/scripts/test_profile_format.py`.
- **Findings**:
    - The sibling pattern is AST-only — it does not import the production module's Flask/LLM dependency chain, so it runs without `LLM_API_KEY` or Neo4j configured. Suitable for CI.
    - The pattern walks specific functions (`_string_literals_in_function`) and a specific module-level constant (`_module_constant_value`). For oasis profile, we walk five functions instead of one constant + one function.
- **Implications**: A near-direct port produces an analogous guard for #3. ~80 lines, no new dependencies, no Flask import chain, runnable as `uv run python backend/scripts/test_oasis_profile_prompts_no_cjk.py`. Adopted in the design.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| In-place lexical translation | Translate the four affected functions' Chinese literals directly | Minimal diff, no new abstractions, parallels sibling spec | English base prompt biases `zh` outputs; mitigated by per-locale `llmInstruction` postfix and post-LLM `_normalize_gender` | Preferred — matches the just-merged sibling pattern. |
| Externalize prompts to `/locales/*.json` | Move prompt text to locale files, resolve via `t()` | Eliminates cross-locale bias entirely | Out of scope per ticket; conflicts with sibling pattern; expands surface beyond #3 | Rejected. |
| In-place + AST static guard test | Option 1 plus a sibling-pattern no-CJK regression test | Adds CI-runnable regression guard at low cost | One additional script to maintain | Selected — adds confidence on the "no CJK" acceptance criterion. |

## Design Decisions

### Decision: In-place translation of four functions plus a no-CJK static guard

- **Context**: R1–R4 require translating the system prompt, the two user-message templates, and the context-building strings inlined into them, while preserving every functional contract.
- **Alternatives Considered**:
    1. In-place translation only (no test).
    2. Externalize prompts to `/locales/*.json`.
    3. In-place translation plus a sibling-pattern AST-based no-CJK guard test.
- **Selected Approach**: Option 3. Translate the four affected functions in place (preserving every interpolation, every code structure, every adjacent helper), and add `backend/scripts/test_oasis_profile_prompts_no_cjk.py` mirroring `test_ontology_prompts_no_cjk.py`.
- **Rationale**: Matches the precedent set by the just-merged `i18n-ontology-generator-prompts` PR (commit `0806832`). AST-based static guard is cheap (~80 lines, no new deps), runs without Flask/LLM/Neo4j, and protects the "no CJK in prompt strings" acceptance criterion against regressions during future edits.
- **Trade-offs**: Adds one new file under `backend/scripts/`. Does not eliminate cross-locale bias under `zh` (mitigated by `get_language_instruction()` postfix at three sites and `_normalize_gender` for the gender enum).
- **Follow-up**: Run a manual round-trip under `en` and `zh` locales after implementation to confirm persona content language. Verify `uv run python backend/scripts/test_profile_format.py` still passes.

### Decision: Locale-neutralize the country instruction

- **Context**: The prompt currently says `国家（使用中文，如"中国"）`, which contradicts `get_language_instruction()` under `en` locale.
- **Alternatives Considered**:
    1. Translate verbatim: `country (use Chinese, e.g. "China-zh")` — would lock the country to Chinese under `en`, defeating the purpose.
    2. Translate verbatim: `country (use English, e.g. "China")` — would lock the country to English under `zh`, regressing Chinese-locale output.
    3. Locale-neutralize: `country` (no language qualifier).
- **Selected Approach**: Option 3. The country becomes a plain field; the model's response language is governed by the `get_language_instruction()` postfix, which is the same mechanism every other free-text field uses.
- **Rationale**: Eliminates the contradiction. Under `en` locale, country names appear in English (e.g., `China`, `Germany`). Under `zh` locale, country names appear in Chinese (e.g., `中国`, `德国`). The COUNTRIES list (line 164) uses English names but is only used by the rule-based fallback (`_generate_profile_rule_based`) — not the LLM path, so no inconsistency.
- **Trade-offs**: A model under `zh` locale that previously always output `"中国"` may now produce a more diverse range of country names. This is an improvement (the previous behaviour was a heavy bias).
- **Follow-up**: Confirm during the runtime check that under `en` locale, country fields are English country names, and under `zh` locale, country fields are Chinese country names.

### Decision: Translate context-building section headings inlined into prompts

- **Context**: `_build_entity_context` and `_search_zep_for_entity` emit Chinese section headings (`### 实体属性`, `### 相关事实和关系`, etc.) into the `context_str` that is interpolated into both user-message templates. Under `en` locale, these inject Chinese into an otherwise English prompt.
- **Alternatives Considered**:
    1. Leave the headings Chinese — but this creates a mixed-language prompt under `en`, which biases the model.
    2. Translate the headings to English unconditionally.
    3. Make the headings locale-aware via `t(...)` calls — would require new translation keys.
- **Selected Approach**: Option 2. Translate the headings to English unconditionally. The `get_language_instruction()` postfix governs the *response* language, not the prompt language.
- **Rationale**: Consistent with the in-place translation approach; matches the sibling pattern. The headings are prompt-side instructions to the LLM about how the context is structured — they are not user-visible. English headings under `zh` locale do not affect `bio`/`persona`/`profession`/`interested_topics` content language, because those fields' language is governed by `get_language_instruction()`.
- **Trade-offs**: A small additional set of literals is in scope. Mitigated by including all of them in R4 and the static guard test.
- **Follow-up**: The static guard test must walk `_build_entity_context` and the relevant literals of `_search_zep_for_entity`. Logger calls inside the same functions remain out of scope (filtered by AST-walk function-scope and by excluding logger-call argument literals).

## Risks & Mitigations

- **Risk: English base prompt biases `zh`-locale persona prose** — Mitigated by `get_language_instruction()` at three sites (system + each user prompt) plus the explicit gender-enum gloss after each postfix; `_normalize_gender` is the code-level safety net for the gender enum.
- **Risk: Static guard test misses a literal** — Mitigated by an explicit list of in-scope functions (`_get_system_prompt`, `_build_individual_persona_prompt`, `_build_group_persona_prompt`, `_build_entity_context`, and the in-scope literals of `_search_zep_for_entity`). The test fails on any CJK in those scopes; out-of-scope scopes (loggers, prints, fallback persona strings) are not checked.
- **Risk: Country instruction change increases output diversity under `zh` locale** — Acceptable: this is an improvement over the current heavy `"中国"` bias. Operator-acceptable per the existing acceptance-criterion phrasing in R5.
- **Risk: `test_profile_format.py` schema mismatch** — Pre-existing project oddity (`realname` vs `name` field-name mismatch in the test). Not introduced or worsened by this PR. Out of scope.

## References

- `backend/app/services/oasis_profile_generator.py` — current Chinese prompt content (the source of translation).
- `backend/app/utils/locale.py` — locale resolver.
- `/locales/languages.json` — per-locale `llmInstruction` postfixes.
- `backend/scripts/test_ontology_prompts_no_cjk.py` — sibling AST-based no-CJK guard (template for the new script).
- `backend/scripts/test_profile_format.py` — existing OASIS profile-format check (must continue to pass).
- `.kiro/specs/i18n-ontology-generator-prompts/` — sibling spec for issue #2 (recently merged); used as design template and pattern reference.
- `.ticket/3.md` — ticket snapshot.
