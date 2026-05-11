# Requirements Document

## Introduction

This specification covers the English translation of the LLM-prompt assembly strings in `backend/app/services/oasis_profile_generator.py`. The file generates OASIS Agent profiles (bio, persona, demographics) from Graphiti/Zep entities during pipeline Step 2. Today, the system prompt and the two user-message builders (`_build_individual_persona_prompt`, `_build_group_persona_prompt`) are written in Chinese, and the runtime context-builders (`_search_zep_for_entity`, `_build_entity_context`) embed Chinese section labels (`事实信息:`, `相关实体:`, `### 实体属性`, `### 关联实体信息`, etc.) into the prompt context that is later interpolated into the user message. Locale is steered at runtime by appending `get_language_instruction()` to the system message and the user-message rules block, but the base-prompt language and the embedded context labels bias the LLM toward Chinese output even when `Accept-Language: en`. Translating the prompt body and the context labels removes that bias while preserving the existing locale-switching mechanism for non-English locales.

This work tracks GitHub issue [#25](https://github.com/salestech-group/MiroFish/issues/25).

## Boundary Context

- **In scope**:
    - Translating the system-prompt base string in `_get_system_prompt` (`base_prompt = "你是社交媒体用户画像生成专家..."`).
    - Translating the user-message body in `_build_individual_persona_prompt` (header line, field labels, JSON-field descriptions, "重要" rules block).
    - Translating the user-message body in `_build_group_persona_prompt` (header line, field labels, JSON-field descriptions, "重要" rules block).
    - Translating the placeholder values used inside those builders: `"无"` and `"无额外上下文"` (substituted when an entity has no attributes or no context).
    - Translating the section-heading labels prepended to context fragments by `_search_zep_for_entity` (`"相关实体: "` prefix on node-name labels; `"事实信息:"`, `"相关实体:"` block headings).
    - Translating the section-heading labels prepended to context fragments by `_build_entity_context` (`"### 实体属性"`, `"### 相关事实和关系"`, `"### 关联实体信息"`, `"### Zep检索到的事实信息"`, `"### Zep检索到的相关节点"`, plus the inline `(相关实体)` placeholder in edge-direction fragments).
    - Translating the fallback persona templates (`f"{entity_name}是一个{entity_type}。"`) used when LLM JSON parsing fails or fields are missing.
    - Translating the console-output formatting in `_print_generated_profile` (the `【简介】`, `【详细人设】`, `【基本属性】` headings and the `用户名:`, `年龄:`, `性别:`, `MBTI:`, `职业:`, `国家:`, `兴趣话题:` row labels) and the surrounding `print` banners in `generate_profiles_from_entities` (`开始生成Agent人设...`, `人设生成完成！...`).
    - Translating the `'无'` sentinel emitted when `interested_topics` is empty in `_print_generated_profile`.
    - Preserving all functional contracts: f-string interpolations, JSON output schema, `get_language_instruction()` postfix call sites, `_normalize_gender` mappings (Chinese `男`/`女`/`机构`/`其他` keys remain — input data may still arrive in those forms), the `country: "中国"` rule-based default in `_generate_profile_rule_based`, the `OASIS 库要求字段名为 username（无下划线）` inline comments at lines 65 and 93 (these are code-level documentation, owned by issue #7), and the `# 可能被截断` / `# 机构虚拟年龄` etc. inline comments (owned by issue #7).
- **Out of scope**:
    - Logger calls in this file (covered by issue #6 and the in-flight #24/#25 backend-log work — the logger calls already use `t("log.profile_generator.*")` keys).
    - Module/class/method docstrings and inline code comments (covered by issue #7 — including the `# OASIS 库要求字段名为 username` and `# 机构虚拟年龄` style comments).
    - The `_normalize_gender` mapping table (it must continue to accept Chinese gender inputs that may still arrive from upstream LLM output or user-supplied data).
    - The hard-coded `"中国"` rule-based country default (this is a data value that downstream OASIS expects in a free-form `country` field; changing the default is a data migration, not a translation).
    - The Chinese identifier in the `ValueError("LLM_API_KEY 未配置")` raise — that is an exception message, not a prompt fragment, and will be translated under issue #6 (already partially in progress under #24).
    - Externalising prompt strings to `/locales/*.json` (out of scope per the `i18n-*-prompts` family of tickets — same pattern as issues #2/#3/#4/#5).
    - Editing call sites of `OasisProfileGenerator` (`api/simulation.py`, etc.).
    - Editing `backend/app/utils/locale.py`, the locale registries, or `/locales/`.
- **Adjacent expectations**:
    - The OASIS / CAMEL-OASIS simulation layer must continue to consume profile JSON unchanged. No coupling to prompt language exists in the OASIS adapter.
    - The locale resolution chain (`Accept-Language` header → `get_locale()` → `get_language_instruction()`) is owned by `backend/app/utils/locale.py` and is unchanged by this work. Translating the base prompt does not modify locale resolution semantics.
    - Companion i18n issues (#3, #4, #5, #6, #7, #9, #10, #23, #24, #26) operate on different files or scopes and should not be touched here.

## Requirements

### Requirement 1: English Translation of the Profile-Generation System Prompt

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the profile-generation system prompt to be authored in English, so that the LLM's persona output is not biased toward Chinese structure or word choice.

#### Acceptance Criteria

1. The OASIS Profile Generator shall define `base_prompt` (in `_get_system_prompt`) containing zero CJK characters in any string-literal content.
2. The OASIS Profile Generator shall preserve the system-prompt requirement that the model returns valid JSON whose string values do not contain unescaped newline characters.
3. The OASIS Profile Generator shall preserve the call to `get_language_instruction()` appended to `base_prompt`, exactly at the existing concatenation site, so locale steering continues to work for non-English locales.
4. The OASIS Profile Generator shall preserve the `is_individual` parameter of `_get_system_prompt` and continue to return a single concatenated system-prompt string of the form `"{base_prompt}\n\n{language_instruction}"`.

### Requirement 2: English Translation of the Individual-Persona User-Message Template

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the individual-persona user-message template constructed by `_build_individual_persona_prompt` to be authored in English, so that the rendered prompt does not interleave English instructions with Chinese section headings, and the LLM is not biased toward Chinese output.

#### Acceptance Criteria

1. The OASIS Profile Generator shall render the individual-persona user message with English field labels in place of `实体名称`, `实体类型`, `实体摘要`, `实体属性`, and `上下文信息`.
2. The OASIS Profile Generator shall render the JSON-field descriptions (the `请生成JSON，包含以下字段` enumeration) in English while preserving the eight required output keys verbatim by name (`bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`).
3. The OASIS Profile Generator shall preserve the requirement language that `gender` MUST be the literal English token `"male"` or `"female"` for individual entities, and that `age` MUST be a valid integer.
4. The OASIS Profile Generator shall preserve the trailing rules block (the `重要:` enumeration) in English, conveying the same constraints: all field values must be strings or numbers, no embedded newlines; persona must be a coherent single text block; the `gender` field uses English `male`/`female`; content must remain consistent with the entity information; `age` must be a valid integer.
5. The OASIS Profile Generator shall preserve the call to `get_language_instruction()` interpolated into the rules block.
6. The OASIS Profile Generator shall preserve all f-string interpolations verbatim by name and position: `{entity_name}`, `{entity_type}`, `{entity_summary}`, `{attrs_str}`, `{context_str}`, `{get_language_instruction()}`.
7. The OASIS Profile Generator shall replace the no-attributes placeholder `"无"` with the English `"None"` when `entity_attributes` is empty / falsy, and the no-context placeholder `"无额外上下文"` with an English equivalent (e.g. `"No additional context"`) when `context` is empty / falsy.
8. The OASIS Profile Generator shall return zero CJK characters across all string literals contributed by `_build_individual_persona_prompt`.
9. The OASIS Profile Generator shall preserve the existing `country` field instruction semantics (a free-form country name is requested) but replace the example `"中国"` with a locale-neutral English phrasing that does not bias the model toward any single country (e.g. `Free-form country name`).

### Requirement 3: English Translation of the Group/Institution-Persona User-Message Template

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the group-persona user-message template constructed by `_build_group_persona_prompt` to be authored in English, with the same scope and contract as Requirement 2 but for institutional entities.

#### Acceptance Criteria

1. The OASIS Profile Generator shall render the group-persona user message with English field labels in place of `实体名称`, `实体类型`, `实体摘要`, `实体属性`, and `上下文信息`.
2. The OASIS Profile Generator shall render the JSON-field descriptions (the `请生成JSON，包含以下字段` enumeration) in English while preserving the eight required output keys verbatim by name (`bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`).
3. The OASIS Profile Generator shall preserve the fixed-value requirements: `age` MUST be the integer literal `30`; `gender` MUST be the literal English token `"other"`.
4. The OASIS Profile Generator shall preserve the trailing rules block (the `重要:` enumeration) in English, conveying the same constraints: all field values must be strings or numbers (no nulls); persona must be a coherent single text block (no embedded newlines); the `gender` field uses English `"other"`; `age` must be the integer `30`; the institutional account's voice must match its identity.
5. The OASIS Profile Generator shall preserve the call to `get_language_instruction()` interpolated into the rules block.
6. The OASIS Profile Generator shall preserve all f-string interpolations verbatim by name and position: `{entity_name}`, `{entity_type}`, `{entity_summary}`, `{attrs_str}`, `{context_str}`, `{get_language_instruction()}`.
7. The OASIS Profile Generator shall use the same English placeholders as Requirement 2 for the no-attributes and no-context cases.
8. The OASIS Profile Generator shall return zero CJK characters across all string literals contributed by `_build_group_persona_prompt`.
9. The OASIS Profile Generator shall preserve the existing `country` field instruction with a locale-neutral English phrasing (matching Requirement 2.9).

### Requirement 4: English Translation of the Context-Builder Section Labels

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the section labels embedded in the context string by `_search_zep_for_entity` and `_build_entity_context` to be in English, so that the prompt context block interpolated into the user message is fully English and the LLM is not biased toward Chinese output by the context labels.

#### Acceptance Criteria

1. The OASIS Profile Generator shall render the related-node prefix (currently `"相关实体: "`) in English (e.g. `"Related entity: "`) in `_search_zep_for_entity`.
2. The OASIS Profile Generator shall render the facts block heading (currently `"事实信息:"`) in English (e.g. `"Facts:"`) in `_search_zep_for_entity`.
3. The OASIS Profile Generator shall render the related-entities block heading (currently `"相关实体:"`) in English (e.g. `"Related entities:"`) in `_search_zep_for_entity`.
4. The OASIS Profile Generator shall render the entity-attributes section heading (currently `"### 实体属性"`) in English (e.g. `"### Entity attributes"`) in `_build_entity_context`.
5. The OASIS Profile Generator shall render the related-facts/relationships section heading (currently `"### 相关事实和关系"`) in English (e.g. `"### Related facts and relationships"`) in `_build_entity_context`.
6. The OASIS Profile Generator shall render the related-entity-information section heading (currently `"### 关联实体信息"`) in English (e.g. `"### Related entity information"`) in `_build_entity_context`.
7. The OASIS Profile Generator shall render the Zep-retrieved facts section heading (currently `"### Zep检索到的事实信息"`) in English (e.g. `"### Facts retrieved from the graph"`) in `_build_entity_context`.
8. The OASIS Profile Generator shall render the Zep-retrieved related-nodes section heading (currently `"### Zep检索到的相关节点"`) in English (e.g. `"### Related nodes retrieved from the graph"`) in `_build_entity_context`.
9. The OASIS Profile Generator shall render the inline edge-direction placeholder (currently `(相关实体)`) in English (e.g. `(related entity)`) in both outgoing and incoming branches of `_build_entity_context`.
10. The OASIS Profile Generator shall return zero CJK characters across all section-label string literals contributed by `_search_zep_for_entity` and `_build_entity_context`.

### Requirement 5: English Translation of the Fallback Persona Templates

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, when the LLM JSON parse fails or returns missing fields and the code falls back to a synthesized persona template, I want the fallback persona to be in English so that the resulting profile JSON does not contain unintended Chinese strings.

#### Acceptance Criteria

1. The OASIS Profile Generator shall replace the fallback persona template `f"{entity_name}是一个{entity_type}。"` at every occurrence (currently at the persona-validation branch in `_generate_profile_with_llm` line 547, the regex-extraction branch in `_try_fix_json` line 644, and the catastrophic-failure branch line 659) with an English equivalent (e.g. `f"{entity_name} is a {entity_type}."`).
2. The OASIS Profile Generator shall preserve the priority order of the fallback chain (`entity_summary or template`).
3. The OASIS Profile Generator shall return zero CJK characters across all fallback persona literals.

### Requirement 6: English Translation of the Console-Output Formatting

**Objective:** As a MiroFish operator monitoring profile generation in the console under `Accept-Language: en`, I want the per-profile diagnostic banner and the start/end batch banners to be in English so that the entire console stream is consistent with the requested locale.

#### Acceptance Criteria

1. The OASIS Profile Generator shall render the per-profile section headings in English in `_print_generated_profile`: `【简介】` → `[Bio]`, `【详细人设】` → `[Persona]`, `【基本属性】` → `[Basic attributes]` (or equivalent English markers).
2. The OASIS Profile Generator shall render the per-profile row labels in English in `_print_generated_profile`: `用户名:` → `Username:`, `年龄:` → `Age:`, `性别:` → `Gender:`, `职业:` → `Profession:`, `国家:` → `Country:`, `兴趣话题:` → `Interested topics:`.
3. The OASIS Profile Generator shall replace the empty-topics sentinel `'无'` in `_print_generated_profile` with an English equivalent (e.g. `'None'`).
4. The OASIS Profile Generator shall render the start-of-batch and end-of-batch banners in `generate_profiles_from_entities` in English: `开始生成Agent人设 - 共 {total} 个实体，并行数: {parallel_count}` → `Generating agent profiles — {total} entities, parallel: {parallel_count}` (or equivalent); `人设生成完成！共生成 {len([p for p in profiles if p])} 个Agent` → `Profile generation complete — produced {n} agents` (or equivalent).
5. The OASIS Profile Generator shall preserve all f-string interpolations in the banners verbatim (`{total}`, `{parallel_count}`, the count expression).
6. The OASIS Profile Generator shall return zero CJK characters across all string literals contributed by `_print_generated_profile` and the surrounding `print(...)` banners in `generate_profiles_from_entities`.
7. The OASIS Profile Generator shall continue to use the existing `t('progress.profileGenerated', ...)` key for the per-profile heading row, since that key is already locale-keyed via the `t()` helper.

### Requirement 7: Locale Switching Continues to Work via `get_language_instruction()`

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: zh` (or any other configured non-English locale), I want the profile output to remain in the requested locale of equivalent quality, so that translating the base prompt does not regress non-English support.

#### Acceptance Criteria

1. The OASIS Profile Generator shall preserve the call to `get_language_instruction()` exactly at its existing locations (currently inside `_get_system_prompt` and inside both `_build_individual_persona_prompt` and `_build_group_persona_prompt` rules blocks), continuing to read locale via the existing thread-local / request-header resolution chain.
2. When the locale is `zh`, the OASIS Profile Generator shall produce profile JSON whose `bio` and `persona` fields are in Chinese, equivalent in quality to the pre-change behaviour.
3. When the locale is `en`, the OASIS Profile Generator shall produce profile JSON whose `bio` and `persona` fields are in English.
4. The OASIS Profile Generator shall not alter `backend/app/utils/locale.py`, the `_languages` registry, the `_translations` registries, or the locales under `/locales/`.

### Requirement 8: Public API and Call-Site Stability

**Objective:** As a developer maintaining the rest of the MiroFish backend pipeline, I want the public surface of `OasisProfileGenerator` to remain unchanged, so that the simulation pipeline and existing callers continue to work without modification.

#### Acceptance Criteria

1. The OASIS Profile Generator shall preserve the signatures of `OasisProfileGenerator.__init__`, `generate_profile_from_entity`, `generate_profiles_from_entities`, `set_graph_id`, `save_profiles`, and `save_profiles_to_json`.
2. The OASIS Profile Generator shall preserve the signatures of all private helpers, including `_generate_profile_with_llm`, `_build_individual_persona_prompt`, `_build_group_persona_prompt`, `_get_system_prompt`, `_build_entity_context`, `_search_zep_for_entity`, `_print_generated_profile`, `_normalize_gender`, `_save_twitter_csv`, `_save_reddit_json`, `_try_fix_json`, `_fix_truncated_json`, `_is_individual_entity`, `_is_group_entity`, `_generate_profile_rule_based`, `_generate_username`.
3. The OASIS Profile Generator shall preserve the return shape of `generate_profile_from_entity` (a populated `OasisAgentProfile` dataclass instance) and `generate_profiles_from_entities` (a `List[OasisAgentProfile]`).
4. The OASIS Profile Generator shall preserve the LLM invocation parameters (`response_format={"type": "json_object"}`, the `temperature=0.7 - (attempt * 0.1)` schedule, the absence of `max_tokens`) and the call to `self.client.chat.completions.create(...)`.
5. The OASIS Profile Generator shall preserve the `_normalize_gender` mapping table verbatim (the Chinese keys `男`, `女`, `机构`, `其他` continue to accept upstream Chinese input).
6. The OASIS Profile Generator shall preserve the rule-based `country: "中国"` default in `_generate_profile_rule_based` (this is a data value, not a prompt; changing it is out of scope per the boundary commitments).

### Requirement 9: Reasoning-Model Output Compatibility

**Objective:** As a MiroFish operator using a reasoning-model provider (e.g. MiniMax, GLM with `<think>` tags or markdown code fences), I want JSON parsing of the profile response to continue working, so that translating the base prompt does not regress provider compatibility.

#### Acceptance Criteria

1. The OASIS Profile Generator shall continue to call `self.client.chat.completions.create(...)` with `response_format={"type": "json_object"}` and parse the response via the existing `json.loads` / `_try_fix_json` / `_fix_truncated_json` chain unchanged.
2. The OASIS Profile Generator shall not introduce any new pre-processing of the LLM response that depends on prompt language.
3. The fallback persona templates from Requirement 5 shall be safe to embed in JSON (no embedded raw newlines, balanced quotes).

### Requirement 10: Out-of-Scope Surfaces Remain Untouched

**Objective:** As a reviewer of this PR, I want the change to remain narrowly scoped to prompt strings and the immediately-adjacent context labels and console output, so that translation responsibilities for adjacent surfaces (issues #6 and #7) are not absorbed into this change.

#### Acceptance Criteria

1. The change shall not modify any `logger.warning(...)`, `logger.info(...)`, `logger.error(...)`, or `logger.debug(...)` call in `oasis_profile_generator.py` (covered by issues #6 / #24 / #25-style backend-log work — the calls already use `t("log.profile_generator.*")`).
2. The change shall not modify the module docstring, class docstrings, method docstrings, or inline comments in `oasis_profile_generator.py` (covered by issue #7) — including the inline comments at lines 65, 93, 641, 804–807, 816–819, etc.
3. The change shall not modify the `_normalize_gender` mapping table (Chinese gender keys must remain to handle upstream input).
4. The change shall not modify the rule-based `country: "中国"` default in `_generate_profile_rule_based`.
5. The change shall not modify the `ValueError("LLM_API_KEY 未配置")` raise (covered by issue #6).
6. The change shall not edit any file outside `backend/app/services/oasis_profile_generator.py` for production code, except for adding test fixtures or scripts under a clearly-isolated directory if a verification harness is needed.
7. The change shall not introduce a new dependency or modify `backend/pyproject.toml` / `backend/uv.lock`.
