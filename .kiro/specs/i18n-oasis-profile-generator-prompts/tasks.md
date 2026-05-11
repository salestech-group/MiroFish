# Implementation Plan

- [ ] 1. Translate the system-prompt base string in `_get_system_prompt`
  - Replace the body of `base_prompt` (currently `"你是社交媒体用户画像生成专家。生成详细、真实的人设用于舆论模拟,最大程度还原已有现实情况。必须返回有效的JSON格式，所有字符串值不能包含未转义的换行符。"`) with an English equivalent that preserves the same intent: define the LLM as an expert social-media-persona generator; require detailed, realistic personas grounded in supplied context; require valid JSON output; forbid unescaped newlines in string values
  - Preserve the trailing `f"{base_prompt}\n\n{get_language_instruction()}"` concatenation site exactly
  - Preserve the `is_individual` parameter (still accepted, still unused — no signature change)
  - Observable completion: `_get_system_prompt(...)` returns an English-only base prompt followed by the locale-appropriate `get_language_instruction()` postfix
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 2. Translate the individual-persona user-message template in `_build_individual_persona_prompt`
  - Replace the introductory line (`"为实体生成详细的社交媒体用户人设,..."`) with an English equivalent
  - Replace the field-label rows (`实体名称`, `实体类型`, `实体摘要`, `实体属性`, `上下文信息`) with English equivalents
  - Replace the `请生成JSON，包含以下字段:` enumeration block with an English equivalent that preserves the eight required output keys verbatim by name (`bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`)
  - Translate the per-field guidance: `bio` is a 200-character social-media bio; `persona` is a coherent ~2000-character text containing basic info, background, personality (with MBTI), social-media behavior, stance, distinctive traits, and event-specific memories; `age` must be an integer; `gender` must be the literal English token `"male"` or `"female"`; `mbti` is an MBTI four-letter code; `country` is a free-form country name; `profession` is a free-form occupation; `interested_topics` is a list of topics
  - Replace the trailing `重要:` rules block with an English equivalent: all field values must be strings or numbers, no embedded newlines; persona must be a coherent single text block; `gender` must use English `male`/`female`; content must remain consistent with the entity information; `age` must be a valid integer
  - Preserve the call to `get_language_instruction()` interpolated into the rules block
  - Replace the `attrs_str` no-attributes placeholder `"无"` with `"None"` (or English equivalent) at line 677
  - Replace the `context_str` no-context placeholder `"无额外上下文"` with `"No additional context"` (or English equivalent) at line 678
  - Preserve every f-string interpolation by name and position: `{entity_name}`, `{entity_type}`, `{entity_summary}`, `{attrs_str}`, `{context_str}`, `{get_language_instruction()}`
  - Observable completion: `_build_individual_persona_prompt(...)` produces an English-only message body for any input combination, with zero CJK characters in any string literal it contributes; under the same inputs as before, all interpolated values still appear in the rendered output
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_

- [ ] 3. Translate the group-persona user-message template in `_build_group_persona_prompt`
  - Replace the introductory line (`"为机构/群体实体生成详细的社交媒体账号设定,..."`) with an English equivalent
  - Replace the field-label rows (`实体名称`, `实体类型`, `实体摘要`, `实体属性`, `上下文信息`) with English equivalents (matching task 2)
  - Replace the `请生成JSON，包含以下字段:` enumeration block with an English equivalent that preserves the eight required output keys verbatim by name (`bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`)
  - Translate the per-field guidance: `bio` is a polished ~200-character official-account bio; `persona` is a coherent ~2000-character text covering institutional background, account positioning, voice, content patterns, official stance, distinctive traits, and event-specific memories; `age` must be the integer literal `30`; `gender` must be the literal English token `"other"`; `mbti` describes account voice; `country` is a free-form country name; `profession` is the institution's role; `interested_topics` is a list of focus areas
  - Replace the trailing `重要:` rules block with an English equivalent: all field values must be strings or numbers (no nulls); persona must be a coherent single text block (no embedded newlines); `gender` must use English `"other"`; `age` must be the integer `30`; the institutional account's voice must match its identity
  - Preserve the call to `get_language_instruction()` interpolated into the rules block
  - Replace the `attrs_str` and `context_str` placeholders the same way as in task 2 (lines 726, 727)
  - Preserve every f-string interpolation by name and position
  - Observable completion: `_build_group_persona_prompt(...)` produces an English-only message body for any input combination, with zero CJK characters; under the same inputs as before, all interpolated values still appear in the rendered output
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

- [ ] 4. Translate the section labels in `_search_zep_for_entity` and `_build_entity_context`
  - Replace the related-node prefix `f"相关实体: {node.name}"` with an English equivalent (e.g. `f"Related entity: {node.name}"`) at line 384
  - Replace the facts block heading `"事实信息:\n"` with `"Facts:\n"` (or equivalent) at line 390
  - Replace the related-entities block heading `"相关实体:\n"` with `"Related entities:\n"` (or equivalent) at line 392
  - Replace the entity-attributes section heading `"### 实体属性\n"` with `"### Entity attributes\n"` (or equivalent) at line 422
  - Replace the inline edge-direction placeholder `(相关实体)` with `(related entity)` (or equivalent) at lines 438 and 440 (both outgoing and incoming branches)
  - Replace the related-facts/relationships section heading `"### 相关事实和关系\n"` with `"### Related facts and relationships\n"` (or equivalent) at line 443
  - Replace the related-entity-information section heading `"### 关联实体信息\n"` with `"### Related entity information\n"` (or equivalent) at line 463
  - Replace the Zep-retrieved facts section heading `"### Zep检索到的事实信息\n"` with `"### Facts retrieved from the graph\n"` (or equivalent) at line 472
  - Replace the Zep-retrieved related-nodes section heading `"### Zep检索到的相关节点\n"` with `"### Related nodes retrieved from the graph\n"` (or equivalent) at line 475
  - Preserve the structure (heading + bulleted body, joined by `"\n".join(...)`)
  - Observable completion: the context string returned by `_build_entity_context(...)` contains zero CJK characters in section labels for any input
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10_

- [ ] 5. Translate the fallback persona templates
  - Replace `f"{entity_name}是一个{entity_type}。"` with `f"{entity_name} is a {entity_type}."` (or equivalent) at line 547 (`_generate_profile_with_llm`, missing-persona branch)
  - Replace the same template at line 644 (`_try_fix_json`, regex-extraction branch)
  - Replace the same template at line 659 (`_try_fix_json`, catastrophic-failure branch)
  - Preserve the `entity_summary or template` priority order at every site
  - Observable completion: when the LLM fails JSON parse and the fallback template is invoked, the resulting `persona` value is English
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 6. Translate the console-output formatting in `_print_generated_profile` and the surrounding banners
  - Replace the section headings in `_print_generated_profile`: `f"【简介】"` → English equivalent (e.g. `"[Bio]"`), `f"【详细人设】"` → English equivalent (e.g. `"[Persona]"`), `f"【基本属性】"` → English equivalent (e.g. `"[Basic attributes]"`)
  - Replace the row labels in `_print_generated_profile`: `f"用户名:"` → `f"Username: {profile.user_name}"`, `f"年龄: {profile.age} | 性别: {profile.gender} | MBTI: {profile.mbti}"` → `f"Age: {profile.age} | Gender: {profile.gender} | MBTI: {profile.mbti}"`, `f"职业: {profile.profession} | 国家: {profile.country}"` → `f"Profession: {profile.profession} | Country: {profile.country}"`, `f"兴趣话题: {topics_str}"` → `f"Interested topics: {topics_str}"`
  - Replace the empty-topics sentinel `'无'` with `'None'` (or equivalent) at line 1011
  - Replace the start-of-batch banner in `generate_profiles_from_entities` (currently `f"开始生成Agent人设 - 共 {total} 个实体，并行数: {parallel_count}"` at line 945) with an English equivalent (e.g. `f"Generating agent profiles — {total} entities, parallel: {parallel_count}"`)
  - Replace the end-of-batch banner (currently `f"人设生成完成！共生成 {len([p for p in profiles if p])} 个Agent"` at line 1001) with an English equivalent (e.g. `f"Profile generation complete — produced {len([p for p in profiles if p])} agents"`)
  - Preserve all f-string interpolations
  - Preserve the existing `t('progress.profileGenerated', name=entity_name, type=entity_type)` call (already locale-keyed)
  - Observable completion: the console output stream contains zero CJK characters in literals contributed by `_print_generated_profile` and the two batch banners (the entity name itself may still contain CJK because it is data, not a literal)
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [ ] 7. Confirm boundary commitments around the translation
  - Confirm `logger.warning(...)`, `logger.info(...)`, `logger.error(...)`, `logger.debug(...)` calls and their `t("log.profile_generator.*")` keys in this file are unchanged
  - Confirm the module/class/method docstrings and inline comments are unchanged (including lines 65, 93, 641, 804–807, 816–819)
  - Confirm `_normalize_gender` mapping table (Chinese keys `男`/`女`/`机构`/`其他`) is unchanged
  - Confirm the rule-based `country: "中国"` default at lines 807, 819 is unchanged
  - Confirm the `ValueError("LLM_API_KEY 未配置")` raise at line 194 is unchanged
  - Confirm public signatures (`__init__`, `generate_profile_from_entity`, `generate_profiles_from_entities`, `set_graph_id`, `save_profiles`, `save_profiles_to_json`) and private helper signatures are unchanged
  - Confirm the `OasisAgentProfile` dataclass schema is unchanged
  - Confirm the LLM call (`response_format={"type": "json_object"}`, `temperature=0.7 - (attempt * 0.1)`, no `max_tokens`) is unchanged
  - Confirm `backend/app/utils/locale.py`, `/locales/languages.json`, `/locales/en.json`, `/locales/zh.json` are not modified
  - Confirm `backend/pyproject.toml`, `backend/uv.lock`, and any file outside `backend/app/services/oasis_profile_generator.py` are not modified
  - Observable completion: a `git diff` review against `main` shows changes only inside `backend/app/services/oasis_profile_generator.py`, only inside the seven owned regions
  - _Requirements: 7.1, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

- [ ] 8. Verify CJK-free invariant in the seven owned regions
  - Run a one-shot script that imports `OasisProfileGenerator`, calls `_build_individual_persona_prompt(...)`, `_build_group_persona_prompt(...)`, `_get_system_prompt(...)`, and `_build_entity_context(...)` with representative inputs that contain no CJK in the inputs themselves, and asserts the rendered output contains zero matches against the regex `[一-鿿]`
  - Manually inspect the seven owned regions in the patched file with a CJK regex (`grep -nP '[\x{4e00}-\x{9fff}]'`) and confirm there are no remaining matches inside the owned regions
  - Observable completion: the inspection passes; if it fails, fix the offending region and re-run before completing this task
  - _Requirements: 1.1, 2.8, 3.8, 4.10, 5.3, 6.6_

- [ ] 9. Verify locale-driven output language under both `en` and `zh`
  - Set the thread-local locale to `en` via `set_locale("en")`, run `OasisProfileGenerator().generate_profile_from_entity(...)` against the configured LLM with a small representative entity, and confirm the returned `bio` and `persona` are in English
  - Set the thread-local locale to `zh` via `set_locale("zh")`, run the same round-trip, and confirm the returned `bio` and `persona` are in Chinese, equivalent in quality to the pre-change baseline
  - Observable completion: both runs succeed; the `en` run is CJK-free in `bio` and `persona`; the `zh` run continues to produce Chinese; results recorded in the PR description
  - _Requirements: 7.2, 7.3_
