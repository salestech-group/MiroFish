# Requirements Document

## Introduction

This specification covers the English translation of the prompt strings in `backend/app/services/oasis_profile_generator.py`. The file converts entities from the Graphiti/Neo4j knowledge graph into OASIS Agent Profiles (Step 2 of the MiroFish pipeline). Today, the system prompt and the two user-message templates (individual persona, group/institution persona) are written in Chinese; the language is steered at runtime by appending `get_language_instruction()` to the system prompt and inside the two user-message templates. While that postfix instructs the model *which* language to respond in, the base-prompt language biases structural and lexical output. As a result, generated `bio`, `persona`, `profession`, and `interested_topics` skew Chinese under `Accept-Language: en`. Translating the base prompts to English removes that bias while preserving the existing locale-switching mechanism for non-English locales (verified: `get_language_instruction()` returns the Chinese postfix `请使用中文回答。` when locale is `zh`, so a Chinese model response remains achievable from an English base prompt).

This work tracks GitHub issue [#3](https://github.com/salestech-group/MiroFish/issues/3).

## Boundary Context

- **In scope**:
    - Translating the system prompt constructed in `OasisProfileGenerator._get_system_prompt` (the `base_prompt` literal that is concatenated with `get_language_instruction()`) from Chinese to English.
    - Translating the user-message template in `OasisProfileGenerator._build_individual_persona_prompt` (instruction headings, schema description, the embedded "重要" rules block) from Chinese to English.
    - Translating the user-message template in `OasisProfileGenerator._build_group_persona_prompt` (instruction headings, schema description, the embedded "重要" rules block) from Chinese to English.
    - Translating the section headings used by `OasisProfileGenerator._build_entity_context` that are inlined into the user-message context (`### 实体属性`, `### 相关事实和关系`, `### 关联实体信息`, `### Zep检索到的事实信息`, `### Zep检索到的相关节点`) and the inline placeholder text used inside that context (`相关实体`, `事实信息`, `相关实体`).
    - Translating the directional placeholder strings emitted into context when an edge has only `edge_name` (`(相关实体)` on either side of the `--[edge_name]-->` arrow).
    - Translating the empty-context fallback string (`"无额外上下文"`) and the empty-attributes fallback string (`"无"`) used inside the user-message templates.
    - Translating the embedded English-bound `country` instruction so that the model is no longer told to answer with Chinese country names regardless of locale (currently `国家（使用中文，如"中国"）`); instead, the country instruction shall be neutral and let `get_language_instruction()` drive the language.
    - Preserving all functional contracts: JSON schema, key names, gender enum (`male` / `female` / `other`), the `interested_topics` array contract, all `{variable}` interpolations, and the `get_language_instruction()` call sites at lines 665 (system prompt), 711 (individual prompt), and 760 (group prompt).
- **Out of scope**:
    - Logger messages (`logger.warning`, `logger.info`, `logger.error`, `logger.debug`) — covered by issue #6.
    - The `print(...)` lines used for console progress reporting (`开始生成Agent人设`, `人设生成完成`) and the section labels in `_print_generated_profile` (`【简介】`, `【详细人设】`, `【基本属性】`, `用户名`, `年龄`, `性别`, `MBTI`, `职业`, `国家`, `兴趣话题`, `无`) — these are diagnostic console outputs, not LLM prompts; covered alongside other UX strings under #6 if they need translation.
    - Module docstring, class docstrings, method docstrings, and inline comments — covered by issue #7.
    - The Chinese fallback `persona` strings produced when the LLM call fails or JSON parsing fails (`f"{entity_name}是一个{entity_type}。"` at the call sites in `_generate_profile_with_llm` and `_try_fix_json`) — these are fallback output values, not prompt strings; their localization belongs to the broader persona-generation-flow translation work (out of scope for issue #3 per "Refactoring … persona-generation flow").
    - The `_normalize_gender` Chinese-to-English mapping table (`男`, `女`, `机构`, `其他`) — this maps non-English LLM outputs to the OASIS gender enum and is required for `zh` locale support; it is not a prompt and must remain.
    - The hard-coded `country: "中国"` defaults in `_normalize_gender`-adjacent fallbacks (`_save_reddit_json`, `_generate_profile_rule_based`) — these are output defaults, not prompt strings; touching them would change runtime profile defaults and is out of scope.
    - Refactoring the OASIS profile JSON schema, the `MBTI_TYPES` list, the `COUNTRIES` list, the `INDIVIDUAL_ENTITY_TYPES` list, the `GROUP_ENTITY_TYPES` list, the persona-generation flow, the parallel-execution flow, the file-saving flow, the realtime save flow, or the truncated-JSON repair flow.
    - Changing OASIS profile-format compatibility (verified by `backend/scripts/test_profile_format.py`).
- **Adjacent expectations**:
    - The OASIS subprocess (CAMEL-OASIS) and Step 3 simulation pipeline must continue to consume the generated profiles unchanged. The profile schema (`user_id`, `username`, `name`, `bio`, `persona`, `karma`, `friend_count`, `follower_count`, `statuses_count`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`, `source_entity_uuid`, `source_entity_type`, `created_at`) is preserved.
    - The locale resolution chain (`Accept-Language` header → `get_locale()` → `get_language_instruction()`, with `set_locale(current_locale)` propagated into worker threads at line 914) is owned by `backend/app/utils/locale.py` and is unchanged by this work.
    - The Graphiti adapter (`graphiti_adapter`) and the entity-context retrieval (`_search_zep_for_entity`) continue to provide entity context to the prompt; only the language of the section headings used to format that context changes.
    - Companion i18n issues (#2, #4, #5, #6, #7, #8, #9, #10) operate on different files or scopes and are not touched here. In particular: `t('progress.zepSearchQuery', name=entity_name)` and `t('progress.profileGenerated', name=..., type=...)` are sourced from `/locales/*.json` and are owned by issue #6 — this spec does not modify them.

## Requirements

### Requirement 1: English Translation of the System Prompt

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the OASIS profile-generation system prompt to be authored in English, so that the LLM's persona output is not biased toward Chinese sentence structure or word choice.

#### Acceptance Criteria

1. The OASIS Profile Generator shall define the `base_prompt` string in `_get_system_prompt` containing zero Chinese characters in any string-literal content.
2. The OASIS Profile Generator shall preserve the directive that the response must be a valid JSON object whose string values do not contain unescaped newline characters (the contract: "valid JSON, no unescaped newlines in string values").
3. The OASIS Profile Generator shall preserve the call to `get_language_instruction()` at the existing site in `_get_system_prompt` (the line returning `f"{base_prompt}\n\n{get_language_instruction()}"`), so that the locale postfix continues to be appended at runtime.
4. The OASIS Profile Generator shall preserve the `is_individual` argument and the function signature of `_get_system_prompt(self, is_individual: bool) -> str`.

### Requirement 2: English Translation of the Individual-Persona User-Message Template

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the user-message template constructed by `_build_individual_persona_prompt` to be authored in English, so that personas for individual entities (students, professors, public figures, journalists, etc.) are produced in English with English-language phrasing patterns.

#### Acceptance Criteria

1. The OASIS Profile Generator shall render the individual user-message template with English instruction headings in place of the existing Chinese labels (`实体名称`, `实体类型`, `实体摘要`, `实体属性`, `上下文信息`, `请生成JSON，包含以下字段`, `重要`).
2. The OASIS Profile Generator shall render the field-by-field schema description in English, preserving each field's identifier verbatim (`bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`) and preserving the documented constraints for each field's value (200-character bio, ~2000-character persona, integer age, gender enum `male` / `female`, MBTI types like `INTJ` / `ENFP`, `country` as a string, profession string, `interested_topics` as an array).
3. The OASIS Profile Generator shall render the `persona` sub-field guidance in English, preserving the seven sub-categories the persona must cover: basic information (age, occupation, education, location), background (significant experiences, event involvement, social ties), personality (MBTI, traits, emotional expression), social-media behavior (post frequency, content preferences, interaction style, language style), stance (views on the topic, what could anger or move them), distinctive traits (catchphrases, unique experiences, hobbies), and personal memory (event-specific actions and reactions).
4. The OASIS Profile Generator shall render the trailing "重要" rules block in English, preserving the rules: all field values must be strings or numbers, no unescaped newline characters, `persona` must be a single coherent paragraph, `gender` must be `male` or `female`, content must remain consistent with the entity information, and `age` must be a valid integer.
5. The OASIS Profile Generator shall preserve the inline `{get_language_instruction()}` interpolation inside the rules block (currently the line `- {get_language_instruction()} (gender字段必须用英文male/female)`), so that the locale postfix continues to appear in the user message.
6. The OASIS Profile Generator shall preserve every Python f-string interpolation verbatim by name: `{entity_name}`, `{entity_type}`, `{entity_summary}`, `{attrs_str}`, `{context_str}`, and `{get_language_instruction()}`.
7. The OASIS Profile Generator shall replace the country instruction `国家（使用中文，如"中国"）` with a locale-neutral instruction so that the country value is generated in the language indicated by `get_language_instruction()` (under `en` locale, English country names; under `zh` locale, Chinese country names).
8. The OASIS Profile Generator shall return zero Chinese characters across all string literals contributed to the assembled individual-persona user message.

### Requirement 3: English Translation of the Group/Institution-Persona User-Message Template

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the user-message template constructed by `_build_group_persona_prompt` to be authored in English, so that personas for group/institutional entities (universities, NGOs, government agencies, media outlets, etc.) are produced in English with English-language phrasing patterns.

#### Acceptance Criteria

1. The OASIS Profile Generator shall render the group/institution user-message template with English instruction headings in place of the existing Chinese labels (`实体名称`, `实体类型`, `实体摘要`, `实体属性`, `上下文信息`, `请生成JSON，包含以下字段`, `重要`).
2. The OASIS Profile Generator shall render the field-by-field schema description in English, preserving each field's identifier verbatim (`bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`) and preserving the documented constraints for each field's value (200-character bio, ~2000-character persona, fixed `age = 30` for institutional virtual age, fixed `gender = "other"` for non-individual accounts, MBTI types describing account style with `ISTJ` representing rigorous/conservative, `country` as a string, profession describing the institution's function, `interested_topics` as an array).
3. The OASIS Profile Generator shall render the `persona` sub-field guidance in English, preserving the seven sub-categories the persona must cover: institution basics (formal name, nature, founding context, primary function), account positioning (account type, target audience, core function), voice/style (language characteristics, common expressions, taboo topics), content patterns (content types, posting frequency, active periods), stance (official stance on core topics, handling of controversy), special notes (the represented group profile, operational habits), and institutional memory (event-specific actions and reactions).
4. The OASIS Profile Generator shall render the trailing "重要" rules block in English, preserving the rules: all field values must be strings or numbers (no `null`), `persona` must be a single coherent paragraph without unescaped newlines, `gender` must be the string `"other"`, `age` must be the integer `30`, and the institutional account's voice must align with its identity.
5. The OASIS Profile Generator shall preserve the inline `{get_language_instruction()}` interpolation inside the rules block (currently the line `- {get_language_instruction()} (gender字段必须用英文"other")`), so that the locale postfix continues to appear in the user message.
6. The OASIS Profile Generator shall preserve every Python f-string interpolation verbatim by name: `{entity_name}`, `{entity_type}`, `{entity_summary}`, `{attrs_str}`, `{context_str}`, and `{get_language_instruction()}`.
7. The OASIS Profile Generator shall replace the country instruction `国家（使用中文，如"中国"）` with a locale-neutral instruction so that the country value is generated in the language indicated by `get_language_instruction()`.
8. The OASIS Profile Generator shall return zero Chinese characters across all string literals contributed to the assembled group/institution-persona user message.

### Requirement 4: English Translation of Context-Building Strings Inlined into Prompts

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the entity context that is interpolated into the user-message templates to use English headings and English placeholder text, so that the assembled prompt does not contain a mix of English instructions and Chinese context labels.

#### Acceptance Criteria

1. The OASIS Profile Generator shall render the section heading currently emitted as `### 实体属性` in `_build_entity_context` as its English equivalent ("Entity Attributes" or equivalent English wording).
2. The OASIS Profile Generator shall render the section heading currently emitted as `### 相关事实和关系` in `_build_entity_context` as its English equivalent.
3. The OASIS Profile Generator shall render the section heading currently emitted as `### 关联实体信息` in `_build_entity_context` as its English equivalent.
4. The OASIS Profile Generator shall render the section heading currently emitted as `### Zep检索到的事实信息` in `_build_entity_context` as its English equivalent.
5. The OASIS Profile Generator shall render the section heading currently emitted as `### Zep检索到的相关节点` in `_build_entity_context` as its English equivalent.
6. The OASIS Profile Generator shall replace the Chinese inline labels emitted in `_search_zep_for_entity` (`事实信息`, `相关实体`) with English equivalents when those labels feed into `results["context"]` and are subsequently interpolated into the user message.
7. The OASIS Profile Generator shall replace the Chinese inline label `相关实体: {node_name}` emitted in `_search_zep_for_entity` (when iterating over node summaries) with an English equivalent.
8. The OASIS Profile Generator shall replace the Chinese placeholder `(相关实体)` emitted in `_build_entity_context` on either side of the `--[edge_name]-->` arrow (when an edge has no `fact` field) with an English equivalent.
9. The OASIS Profile Generator shall replace the Chinese fallback strings `"无额外上下文"` and `"无"` used inside `_build_individual_persona_prompt` and `_build_group_persona_prompt` (as `context[:3000] if context else "无额外上下文"` and `json.dumps(...) if entity_attributes else "无"`) with English equivalents.
10. The OASIS Profile Generator shall preserve the conditional inclusion of each context section (a section is appended only when its source data is non-empty), preserving the existing truthiness checks.
11. The OASIS Profile Generator shall preserve the cap on edge facts (`new_facts[:15]`) and the cap on node summaries (`zep_results["node_summaries"][:10]`) in `_build_entity_context`, and the cap on facts (`results["facts"][:20]`) and on node summaries (`results["node_summaries"][:10]`) in `_search_zep_for_entity`.

### Requirement 5: Locale Switching Continues to Work via `get_language_instruction()`

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: zh` (or any other configured non-English locale), I want the generated personas to remain in the requested locale of equivalent quality, so that translating the base prompts does not regress non-English support.

#### Acceptance Criteria

1. The OASIS Profile Generator shall preserve the call to `get_language_instruction()` exactly at the existing site in `_get_system_prompt` (`return f"{base_prompt}\n\n{get_language_instruction()}"`).
2. The OASIS Profile Generator shall preserve the call to `get_language_instruction()` exactly at the existing site in `_build_individual_persona_prompt` (the line containing `- {get_language_instruction()} (gender字段必须用英文male/female)`), with the bracketed gender clarification translated to English while keeping the call.
3. The OASIS Profile Generator shall preserve the call to `get_language_instruction()` exactly at the existing site in `_build_group_persona_prompt` (the line containing `- {get_language_instruction()} (gender字段必须用英文"other")`), with the bracketed gender clarification translated to English while keeping the call.
4. The OASIS Profile Generator shall preserve the import of `get_language_instruction`, `get_locale`, `set_locale`, and `t` from `..utils.locale` (the existing import statement is unchanged in identifiers and source).
5. The OASIS Profile Generator shall preserve the `set_locale(current_locale)` call inside `generate_single_profile` (line 914) so that the locale captured before thread-pool dispatch is restored inside each worker thread.
6. The OASIS Profile Generator shall preserve the call to `t('progress.zepSearchQuery', name=entity_name)` in `_search_zep_for_entity` so that the Zep search query string continues to be sourced from the locale files.
7. The OASIS Profile Generator shall preserve the call to `t('progress.profileGenerated', name=entity_name, type=entity_type)` in `_print_generated_profile` so that the per-profile console heading continues to be sourced from the locale files.
8. When the locale is `zh`, the OASIS Profile Generator shall produce profiles whose `bio`, `persona`, `profession`, and `interested_topics` content is in Chinese, equivalent in quality to the pre-change behaviour (a small variance in word choice is acceptable; English text in these fields under `zh` locale is not).
9. When the locale is `en`, the OASIS Profile Generator shall produce profiles whose `bio`, `persona`, `profession`, and `interested_topics` content is in English (no Chinese characters in any of these fields).

### Requirement 6: Public API and Call-Site Stability

**Objective:** As a developer maintaining the rest of the MiroFish backend pipeline (Step 2 environment setup, the `simulation_runner`, the `simulation_config_generator`, the API blueprints), I want the public surface of `OasisProfileGenerator` and `OasisAgentProfile` to remain unchanged, so that existing callers continue to work without modification.

#### Acceptance Criteria

1. The OASIS Profile Generator shall preserve the signature of `OasisProfileGenerator.__init__(self, api_key, base_url, model_name, zep_api_key, graph_id)` with all parameters optional.
2. The OASIS Profile Generator shall preserve the signature of `generate_profile_from_entity(self, entity, user_id, use_llm=True) -> OasisAgentProfile`.
3. The OASIS Profile Generator shall preserve the signature of `generate_profiles_from_entities(self, entities, use_llm, progress_callback, graph_id, parallel_count, realtime_output_path, output_platform)`.
4. The OASIS Profile Generator shall preserve the signatures of `save_profiles`, `save_profiles_to_json`, `_save_twitter_csv`, `_save_reddit_json`, and `set_graph_id`.
5. The OASIS Profile Generator shall preserve the signatures of the private helpers used inside the prompt-building flow: `_get_system_prompt(self, is_individual: bool) -> str`, `_build_individual_persona_prompt(self, entity_name, entity_type, entity_summary, entity_attributes, context) -> str`, `_build_group_persona_prompt(self, entity_name, entity_type, entity_summary, entity_attributes, context) -> str`, `_build_entity_context(self, entity) -> str`, `_search_zep_for_entity(self, entity) -> Dict[str, Any]`, `_is_individual_entity(self, entity_type) -> bool`, `_is_group_entity(self, entity_type) -> bool`, and `_normalize_gender(self, gender) -> str`.
6. The OASIS Profile Generator shall preserve the dataclass `OasisAgentProfile` fields (all field names and types) and the methods `to_reddit_format`, `to_twitter_format`, and `to_dict`.
7. The OASIS Profile Generator shall preserve the LLM invocation parameters in `_generate_profile_with_llm`: the system + user message structure, `response_format={"type": "json_object"}`, the temperature schedule (`0.7 - (attempt * 0.1)`), the absence of `max_tokens`, the retry count (`max_attempts = 3`), and the exponential-backoff sleep (`time.sleep(1 * (attempt + 1))`).
8. The OASIS Profile Generator shall preserve the OASIS-required gender enum (`male`, `female`, `other`) — both as a contract instructed in the prompts and as the output of `_normalize_gender`.
9. The OASIS Profile Generator shall preserve all JSON output keys produced by the LLM and surfaced through `OasisAgentProfile`: `bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`. (Keys are matched verbatim by `result.get("bio", ...)` and similar accessor calls in `_generate_profile_with_llm`.)

### Requirement 7: Reasoning-Model Output Compatibility

**Objective:** As a MiroFish operator using a reasoning-model provider (e.g. MiniMax, GLM with `<think>` tags or markdown code fences) for OASIS profile generation, I want JSON parsing of the persona response to continue working, so that translating the base prompts does not regress provider compatibility.

#### Acceptance Criteria

1. The OASIS Profile Generator shall delegate JSON parsing to `json.loads(content)` exactly as today, with the existing pre-pass `_fix_truncated_json` and post-failure `_try_fix_json` flow.
2. If a reasoning-model provider returns a truncated or otherwise malformed response, then the existing repair logic in `_fix_truncated_json` and `_try_fix_json` shall continue to apply unchanged.
3. The OASIS Profile Generator shall not introduce any new pre-processing of the LLM response that depends on prompt language.
4. After translation, the OASIS Profile Generator shall continue to round-trip a representative entity through `generate_profile_from_entity` and produce a non-empty `OasisAgentProfile` with `bio` and `persona` set (either from the LLM, from the JSON-repair path, or from the rule-based fallback).

### Requirement 8: Step 2 Environment-Setup Parity

**Objective:** As a MiroFish operator validating the change, I want the Step 2 environment-setup pipeline (entity → profile → OASIS-format CSV/JSON) to produce profiles that the OASIS subprocess accepts, so that the translation does not silently break Step 3.

#### Acceptance Criteria

1. When a representative set of entities is processed end-to-end with locale `en`, the OASIS Profile Generator shall produce a list of `OasisAgentProfile` instances whose `gender` field is one of `male`, `female`, or `other` for every profile.
2. When a representative set of entities is processed end-to-end with locale `en`, the resulting Reddit JSON file (via `_save_reddit_json`) shall contain `user_id`, `username`, `name`, `bio`, `persona`, `karma`, `created_at`, `age`, `gender`, `mbti`, and `country` fields for every entry, conforming to the schema verified by `backend/scripts/test_profile_format.py`.
3. When a representative set of entities is processed end-to-end with locale `en`, the resulting Twitter CSV file (via `_save_twitter_csv`) shall contain the OASIS-required header `user_id, name, username, user_char, description` with one row per profile, conforming to the schema verified by `backend/scripts/test_profile_format.py`.
4. The change shall not modify the function signatures or call sequence used by the Step 2 pipeline (verified by Requirement 6).
5. The change shall not change the OASIS subprocess's ability to load the produced profiles (the `_normalize_gender` call in `_save_reddit_json`, the field set written to JSON/CSV, and the `username` key spelling are all preserved per Requirement 6).

### Requirement 9: Out-of-Scope Surfaces Remain Untouched

**Objective:** As a reviewer of this PR, I want the change to remain narrowly scoped to prompt strings and the prompt-context strings inlined into them, so that translation responsibilities for adjacent surfaces (issues #6 and #7) are not absorbed into this change.

#### Acceptance Criteria

1. The change shall not modify any `logger.warning(...)`, `logger.info(...)`, `logger.error(...)`, or `logger.debug(...)` call in `oasis_profile_generator.py` (covered by issue #6).
2. The change shall not modify the `print(...)` console-progress strings in `generate_profiles_from_entities` (e.g., `开始生成Agent人设 - 共 {total} 个实体，并行数: {parallel_count}` and `人设生成完成！共生成 ... 个Agent`) and `_print_generated_profile` (e.g., `用户名:`, `【简介】`, `【详细人设】`, `【基本属性】`, `年龄:`, `性别:`, `MBTI:`, `职业:`, `国家:`, `兴趣话题:`, `无`) — these console outputs are owned by issue #6.
3. The change shall not modify the module docstring, the `OasisAgentProfile` dataclass docstring, the `OasisProfileGenerator` class docstring, the docstrings on any method, or any inline comment in `oasis_profile_generator.py` (covered by issue #7).
4. The change shall not modify the `MBTI_TYPES`, `COUNTRIES`, `INDIVIDUAL_ENTITY_TYPES`, or `GROUP_ENTITY_TYPES` lists.
5. The change shall not modify the Chinese keys in the `_normalize_gender` mapping (`男`, `女`, `机构`, `其他`); these enable normalization of `zh`-locale outputs to the OASIS gender enum and must remain.
6. The change shall not modify the rule-based fallback strings in `_generate_profile_rule_based` (e.g., `"Student"`, `"Expert"`, `"Media"`, `"中国"` defaults), which produce profile values when the LLM path is bypassed.
7. The change shall not modify the Chinese-language fallback persona strings (`f"{entity_name}是一个{entity_type}。"`) at the JSON-repair sites (`_generate_profile_with_llm` line ~547, `_try_fix_json` lines ~644 and ~659); these are the JSON-repair fallback path and belong to issue #6/#7's broader translation work.
8. The change shall not edit any file outside `backend/app/services/oasis_profile_generator.py` for production code.
9. The change shall not introduce a new dependency or modify `backend/pyproject.toml` / `backend/uv.lock`.
