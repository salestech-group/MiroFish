# Requirements Document

## Introduction

This specification covers the English translation of the prompt strings in `backend/app/services/oasis_profile_generator.py`. The file converts Graphiti graph entities into OASIS agent persona dictionaries that drive Step 2 (Environment Setup) of the MiroFish pipeline. Today, the system prompt and the two `_build_*_persona_prompt` user-message templates are written in Chinese; the language is steered at runtime by appending `get_language_instruction()` to the system prompt and inside the user prompt body. While that postfix instructs the model *which* language to respond in, the base-prompt language biases the model's structural and lexical output, so persona prose (bio, persona, profession, interested_topics) skews Chinese under `Accept-Language: en`. Translating the base prompts to English removes that bias while preserving the existing locale-switching mechanism for non-English locales (`get_language_instruction()` returns `请使用中文回答。` when locale is `zh`, so a Chinese model response remains achievable from an English base prompt).

This work tracks GitHub issue [#3](https://github.com/salestech-group/MiroFish/issues/3) and is sibling to the already-merged ontology-generator (#2), simulation-config-generator (#4), and report-agent (#5) prompt translation specs.

## Boundary Context

- **In scope**:
    - Translating the system-prompt base string in `OasisProfileGenerator._get_system_prompt` (currently `"你是社交媒体用户画像生成专家。…"` at line ~664) from Chinese to English.
    - Translating the individual-persona user-message template in `OasisProfileGenerator._build_individual_persona_prompt` (currently lines ~680–714) from Chinese to English.
    - Translating the group/institution-persona user-message template in `OasisProfileGenerator._build_group_persona_prompt` (currently lines ~729–762) from Chinese to English.
    - Translating the small `attrs_str` and `context_str` fallback default literals (`"无"`, `"无额外上下文"`) to English equivalents.
    - Preserving all functional contracts: every `get_language_instruction()` call site, all variable interpolations, all JSON output keys, the `gender` enum constraint, the `age` integer constraint, and the institutional age=30 / gender="other" rule.
- **Out of scope**:
    - Logger calls (`logger.info`, `logger.warning`, `logger.error`) and the printed banner text inside `oasis_profile_generator.py` — covered by issue #6.
    - Module docstring, class docstrings, method docstrings, and inline comments — covered by issue #7.
    - The fallback Chinese string literals embedded in non-prompt code paths (e.g. `f"{entity_name}是一个{entity_type}。"` inside `_try_fix_json` and the rule-based fallback) — those are runtime data fallbacks, not LLM prompts, and are out of scope for this issue (they are part of the fallback flow covered when comments/docstrings #7 lands or in a future cleanup; they are not user-visible while the LLM path succeeds).
    - Refactoring the OASIS profile JSON schema, the `OasisAgentProfile` dataclass, the MBTI list, the `COMMON_COUNTRIES` list, the entity-type taxonomy splits (`PERSONAL_ENTITY_TYPES` vs `GROUP_ENTITY_TYPES`), or persona-generation flow control.
    - Changing OASIS profile-format compatibility — verified by `backend/scripts/test_profile_format.py`.
    - Editing the locale plumbing block (currently the `current_locale = get_locale()` capture and the `set_locale(current_locale)` call inside `generate_single_profile` around lines ~910–916).
- **Adjacent expectations**:
    - The Step 2 environment-setup pipeline must continue to consume the OASIS profile output unchanged. The Reddit (`to_reddit_format`) and Twitter (`to_twitter_format`) serializers are not coupled to prompt language; this is verified via the JSON schema contract preservation.
    - The locale resolution chain (`Accept-Language` header → `get_locale()` → `get_language_instruction()`) is owned by `backend/app/utils/locale.py` and is unchanged by this work.
    - Companion i18n issues (#6 logs, #7 comments/docstrings, #9 frontend comments, #10 e2e verification, #12 README) operate on different files or scopes and must not be touched here.

## Requirements

### Requirement 1: English Translation of the System Prompt

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the persona-generation system prompt to be authored in English, so that the LLM's persona prose is not biased toward Chinese structure or word choice.

#### Acceptance Criteria

1. The OASIS Profile Generator shall set the `base_prompt` constant inside `_get_system_prompt` to an English string containing zero Chinese characters.
2. The OASIS Profile Generator shall preserve the system-prompt assembly contract verbatim: the format `f"{base_prompt}\n\n{get_language_instruction()}"` and the call to `get_language_instruction()` at exactly that site.
3. The OASIS Profile Generator shall preserve the role and intent semantics of the original prompt: identifying the model as an expert in social-media user-persona generation, requesting detailed and realistic personas for opinion simulation that reflect existing real-world conditions, and mandating valid JSON output where string values must not contain unescaped newlines.
4. The OASIS Profile Generator shall preserve the function signature `_get_system_prompt(self, is_individual: bool) -> str`.

### Requirement 2: English Translation of the Individual-Persona User-Message Template

**Objective:** As a MiroFish operator generating personas for individual entities under `Accept-Language: en`, I want the user-message template constructed by `_build_individual_persona_prompt` to be authored in English, so that the rendered prompt does not interleave English `get_language_instruction()` directives with Chinese section headings.

#### Acceptance Criteria

1. The OASIS Profile Generator shall render the individual-persona user message with English section headings and prose in place of the current Chinese (entity name, entity type, entity summary, entity attributes, context section, JSON-fields enumeration, "important" trailing block).
2. The OASIS Profile Generator shall preserve all variable interpolations verbatim by name: `{entity_name}`, `{entity_type}`, `{entity_summary}`, `{attrs_str}`, `{context_str}`, and the inline `{get_language_instruction()}` call inside the trailing rules block.
3. The OASIS Profile Generator shall preserve the JSON output contract enumerated in the prompt: the keys `bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics` (verbatim, English).
4. The OASIS Profile Generator shall preserve the field-level constraints in the prompt:
    - `bio` ≈ 200 characters, social-media biography.
    - `persona` ≈ 2000 characters, single coherent text covering: basic information (age, profession, education, location), background (notable experience, event association, social ties), personality (MBTI, core traits, emotional expression), social-media behavior (posting frequency, content preferences, interaction style, language traits), stance (attitudes toward the topic, emotional triggers), unique features (catchphrases, special experiences, hobbies), and personal memory (the entity's relation to the event and prior actions/reactions in it).
    - `age` MUST be an integer.
    - `gender` MUST be one of `"male"` or `"female"` (English enum value, locale-independent).
    - `mbti` MUST be an MBTI four-letter type (e.g. INTJ, ENFP).
    - `country` MUST be a country name string.
    - `profession` MUST be a profession string.
    - `interested_topics` MUST be an array.
5. The OASIS Profile Generator shall preserve the trailing-block rules verbatim in spirit: every value is a string or number, no newlines inside string values, `persona` is a single coherent text, `gender` must be the English `male`/`female` enum even when locale is `zh`, content must stay consistent with the source entity, `age` must be a valid integer.
6. The OASIS Profile Generator shall preserve the function signature `_build_individual_persona_prompt(self, entity_name: str, entity_type: str, entity_summary: str, entity_attributes: Dict[str, Any], context: str) -> str`.
7. The OASIS Profile Generator shall preserve the `context[:3000]` truncation behaviour and the conditional fallback (`"无额外上下文"` translated to `"No additional context"`) when `context` is empty/falsy. Likewise, `attrs_str` shall fall back to an English placeholder (`"None"`) when `entity_attributes` is empty/falsy, replacing the current `"无"` literal.
8. The OASIS Profile Generator shall return zero Chinese characters across all string literals contributed to the assembled individual-persona prompt body.

### Requirement 3: English Translation of the Group/Institution-Persona User-Message Template

**Objective:** As a MiroFish operator generating personas for institutional/group entities under `Accept-Language: en`, I want the user-message template constructed by `_build_group_persona_prompt` to be authored in English, so that the rendered prompt does not interleave English `get_language_instruction()` directives with Chinese section headings.

#### Acceptance Criteria

1. The OASIS Profile Generator shall render the group-persona user message with English section headings and prose in place of the current Chinese.
2. The OASIS Profile Generator shall preserve all variable interpolations verbatim by name: `{entity_name}`, `{entity_type}`, `{entity_summary}`, `{attrs_str}`, `{context_str}`, and the inline `{get_language_instruction()}` call inside the trailing rules block.
3. The OASIS Profile Generator shall preserve the JSON output contract enumerated in the prompt: the keys `bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics` (verbatim, English).
4. The OASIS Profile Generator shall preserve the field-level constraints in the prompt:
    - `bio` ≈ 200 characters, an official-account biography that reads as professionally appropriate.
    - `persona` ≈ 2000 characters, single coherent text covering: institutional basics (formal name, type, founding background, primary functions), account positioning (account type, target audience, core function), voice (language traits, common phrasing, taboo topics), publishing pattern (content types, publishing frequency, active hours), stance (official position on the core topic, controversy-handling style), special notes (group portrait represented, operational habits), and institutional memory (the institution's relation to the event and prior actions/reactions in it).
    - `age` MUST be the integer `30` (the institutional virtual-age sentinel).
    - `gender` MUST be the literal `"other"` (English enum value, locale-independent), indicating non-individual.
    - `mbti` MUST be an MBTI four-letter type used to characterize account voice (e.g. ISTJ for strict/conservative).
    - `country` MUST be a country name string.
    - `profession` MUST describe institutional function.
    - `interested_topics` MUST be an array of focus areas.
5. The OASIS Profile Generator shall preserve the trailing-block rules verbatim in spirit: every value is a string or number, no `null` values, no newlines in string values, `persona` is a single coherent text, `gender` must be the English `"other"` enum even when locale is `zh`, the institutional account voice must match its identity positioning, and `age` must be the integer `30`.
6. The OASIS Profile Generator shall preserve the function signature `_build_group_persona_prompt(self, entity_name: str, entity_type: str, entity_summary: str, entity_attributes: Dict[str, Any], context: str) -> str`.
7. The OASIS Profile Generator shall preserve the `context[:3000]` truncation behaviour and the conditional English-equivalent fallback for empty `context` and empty `entity_attributes`, mirroring Requirement 2.
8. The OASIS Profile Generator shall return zero Chinese characters across all string literals contributed to the assembled group-persona prompt body.

### Requirement 4: Locale Switching Continues to Work via `get_language_instruction()`

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: zh` (or any other configured non-English locale), I want generated personas to remain in the requested locale at equivalent quality, so that translating the base prompt does not regress non-English support.

#### Acceptance Criteria

1. The OASIS Profile Generator shall preserve every existing `get_language_instruction()` call site exactly: the system-prompt site in `_get_system_prompt`, the inline call inside the trailing rules block of `_build_individual_persona_prompt`, and the inline call inside the trailing rules block of `_build_group_persona_prompt`.
2. The OASIS Profile Generator shall preserve the locale-capture/restore plumbing inside `generate_profiles_for_entities` (currently the `current_locale = get_locale()` capture and the `set_locale(current_locale)` call inside `generate_single_profile`) — this code is not modified by the change.
3. While the locale is `zh`, the OASIS Profile Generator shall produce profiles whose `bio`, `persona`, `profession`, and `interested_topics` content is in Chinese, equivalent in quality to the pre-change behaviour.
4. While the locale is `en`, the OASIS Profile Generator shall produce profiles whose `bio`, `persona`, `profession`, and `interested_topics` content is in English.
5. While the locale is `en` or `zh`, the OASIS Profile Generator shall produce profiles whose `gender` field is one of the literal English values `"male"`, `"female"` (individual entities) or `"other"` (group entities), regardless of locale.
6. The OASIS Profile Generator shall not alter `backend/app/utils/locale.py`, the `_languages`, the `_translations` registries, or the locales under `/locales/`.

### Requirement 5: Public API and Call-Site Stability

**Objective:** As a developer maintaining the rest of the MiroFish backend pipeline, I want the public surface of `OasisProfileGenerator` and `OasisAgentProfile` to remain unchanged, so that the Step 2 environment-setup flow and existing callers continue to work without modification.

#### Acceptance Criteria

1. The OASIS Profile Generator shall preserve the dataclass `OasisAgentProfile`, including its field set (`user_id`, `user_name`, `name`, `bio`, `persona`, `karma`, `friend_count`, `follower_count`, `statuses_count`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`, `source_entity_uuid`, `source_entity_type`, `created_at`), default values, and the `to_reddit_format`, `to_twitter_format`, `to_full_dict` serializers.
2. The OASIS Profile Generator shall preserve the signatures and call semantics of `OasisProfileGenerator.__init__`, `generate_profile_from_entity`, `generate_profiles_for_entities`, `_call_llm_with_retry`, `_generate_profile_rule_based`, `_get_system_prompt`, `_build_individual_persona_prompt`, `_build_group_persona_prompt`, `_print_generated_profile`, `_fix_truncated_json`, `_try_fix_json`, and `_generate_username`.
3. The OASIS Profile Generator shall preserve the LLM invocation parameters (`temperature`, `max_tokens`, model selection, retry behaviour) at the call sites that consume the prompts produced by the translated builders.
4. The OASIS Profile Generator shall preserve the `PERSONAL_ENTITY_TYPES` and `GROUP_ENTITY_TYPES` taxonomies, the `MBTI_TYPES` list, and the `COMMON_COUNTRIES` list verbatim.

### Requirement 6: Reasoning-Model Output Compatibility

**Objective:** As a MiroFish operator using a reasoning-model provider (e.g. MiniMax, GLM with `<think>` tags or markdown code fences), I want JSON parsing of the persona response to continue working, so that translating the base prompt does not regress provider compatibility.

#### Acceptance Criteria

1. The OASIS Profile Generator shall preserve the existing `_fix_truncated_json` and `_try_fix_json` resilience helpers exactly, including their regex-based extraction of `bio` and `persona` from partial output.
2. If a reasoning-model provider returns truncated, `<think>`-tagged, or markdown-fenced output, then the existing parsing/recovery flow shall continue to apply unchanged.
3. The OASIS Profile Generator shall not introduce any new pre-processing of the LLM response that depends on prompt language.
4. After translation, the OASIS Profile Generator shall continue to round-trip a representative entity through `generate_profile_from_entity` and produce a JSON object with at minimum a non-empty `bio` and a non-empty `persona`, matching the pre-change behaviour.

### Requirement 7: Step 2 Environment-Setup Parity (OASIS Format Compatibility)

**Objective:** As a MiroFish operator validating the change, I want the OASIS subprocess to accept the generated profiles unchanged, so that the translation does not silently break Step 2 → Step 3 hand-off.

#### Acceptance Criteria

1. While `uv run python -m pytest backend/scripts/test_profile_format.py` runs against the changed code, the test suite shall pass with zero regressions versus the pre-change baseline.
2. While a representative Reddit-format profile dictionary is produced under locale `en`, every field name shall match the existing OASIS-required schema: `user_id`, `username`, `name`, `bio`, `persona`, `karma`, `created_at`, plus optional `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`.
3. While a representative Twitter-format profile dictionary is produced under locale `en`, every field name shall match the existing OASIS-required schema: `user_id`, `username`, `name`, `bio`, `persona`, `friend_count`, `follower_count`, `statuses_count`, `created_at`, plus optional `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`.
4. The OASIS Profile Generator shall produce `gender` values that are exactly one of `"male"`, `"female"`, `"other"` regardless of locale, satisfying the OASIS subprocess's expected enum.

### Requirement 8: Out-of-Scope Surfaces Remain Untouched

**Objective:** As a reviewer of this PR, I want the change to remain narrowly scoped to prompt strings, so that translation responsibilities for adjacent surfaces (issues #6, #7, and the rule-based fallback) are not absorbed into this change.

#### Acceptance Criteria

1. The change shall not modify any `logger.warning(...)`, `logger.info(...)`, `logger.error(...)`, or `logger.debug(...)` call in `oasis_profile_generator.py` (covered by issue #6).
2. The change shall not modify the module docstring, class docstrings, method docstrings, or inline comments in `oasis_profile_generator.py` (covered by issue #7).
3. The change shall not modify the rule-based fallback Chinese fragments inside `_try_fix_json` (e.g. `f"{entity_name}是一个{entity_type}。"`) and the rule-based path inside `_generate_profile_rule_based` — those are runtime data fallbacks, not LLM prompts, and remain out of scope here.
4. The change shall not edit any file outside `backend/app/services/oasis_profile_generator.py` for production code.
5. The change shall not introduce a new dependency or modify `backend/pyproject.toml` / `backend/uv.lock`.
6. The change shall not modify `backend/scripts/test_profile_format.py` (the test is the contract; the implementation must match it).
