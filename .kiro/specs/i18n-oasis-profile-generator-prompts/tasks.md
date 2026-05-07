# Implementation Plan

- [x] 1. Translate the system prompt to English
  - Replace the `base_prompt` literal in `_get_system_prompt` with an English rendering ("You are a social-media user-profile generation expert. Produce detailed, realistic personas for opinion-simulation, faithfully reflecting the existing real-world situation. You must return valid JSON; string values must not contain unescaped newline characters.")
  - Preserve the directive that the response must be a valid JSON object whose string values do not contain unescaped newlines
  - Preserve the call to `get_language_instruction()` at its current site (the line returning `f"{base_prompt}\n\n{get_language_instruction()}"`)
  - Preserve the `is_individual` argument and the function signature `_get_system_prompt(self, is_individual: bool) -> str`
  - Observable completion: `_get_system_prompt` returns an English-only base prompt followed by the locale-postfix; zero CJK characters in the `base_prompt` literal
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - _Boundary: OasisProfileGenerator → `_get_system_prompt`_

- [x] 2. Translate the individual-persona user-message template to English
  - Replace the f-string body of `_build_individual_persona_prompt` with English equivalents of the instruction headings (`实体名称`, `实体类型`, `实体摘要`, `实体属性`, `上下文信息`, `请生成JSON，包含以下字段`, `重要`)
  - Translate the field-by-field schema description while preserving each field's identifier verbatim (`bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`) and the documented constraints (200-char bio, ~2000-char persona, integer age, gender enum `male` / `female`, MBTI types like `INTJ`/`ENFP`)
  - Translate the seven `persona` sub-categories (basic information, background, personality, social-media behavior, stance, distinctive traits, personal memory) into English bullets that map 1-to-1 to the original
  - Translate the trailing "重要" rules block to English ("Important:") preserving the rules: string-or-number values, no unescaped newlines, single-paragraph persona, gender enum constraint, content consistency, integer age
  - Replace the country instruction `国家（使用中文，如"中国"）` with a locale-neutral instruction (e.g., `country`) so `get_language_instruction()` drives the country-name language
  - Translate the inline gloss after `{get_language_instruction()}` (currently `(gender字段必须用英文male/female)`) into English while preserving the `{get_language_instruction()}` interpolation in place
  - Preserve every f-string interpolation verbatim by name: `{entity_name}`, `{entity_type}`, `{entity_summary}`, `{attrs_str}`, `{context_str}`, `{get_language_instruction()}`
  - Observable completion: `_build_individual_persona_prompt` produces an English-only message body for any input combination, with zero CJK characters in any string literal it contributes; under the same inputs as before, all interpolated values still appear in the rendered output
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_
  - _Boundary: OasisProfileGenerator → `_build_individual_persona_prompt`_

- [x] 3. Translate the group-persona user-message template to English
  - Replace the f-string body of `_build_group_persona_prompt` with English equivalents of the instruction headings (parallel to task 2's headings)
  - Translate the field-by-field schema description while preserving the fixed-value contracts: `age = 30` (institutional virtual age), `gender = "other"` (non-individual accounts), MBTI types describing account style with `ISTJ` representing rigorous/conservative, and the JSON keys `bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`
  - Translate the seven institutional `persona` sub-categories (institution basics, account positioning, voice/style, content patterns, stance, special notes, institutional memory) into English bullets that map 1-to-1 to the original
  - Translate the trailing "重要" rules block to English ("Important:") preserving the rules: string-or-number values (no nulls), single-paragraph persona without unescaped newlines, `gender = "other"`, `age = 30`, voice aligned with institutional identity
  - Replace the country instruction `国家（使用中文，如"中国"）` with a locale-neutral instruction (parallel to task 2)
  - Translate the inline gloss after `{get_language_instruction()}` (currently `(gender字段必须用英文"other")`) into English while preserving the `{get_language_instruction()}` interpolation in place
  - Preserve every f-string interpolation verbatim by name: `{entity_name}`, `{entity_type}`, `{entity_summary}`, `{attrs_str}`, `{context_str}`, `{get_language_instruction()}`
  - Observable completion: `_build_group_persona_prompt` produces an English-only message body for any input combination, with zero CJK characters in any string literal it contributes; under the same inputs as before, all interpolated values still appear in the rendered output
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_
  - _Boundary: OasisProfileGenerator → `_build_group_persona_prompt`_

- [x] 4. Translate context-building strings inlined into the prompts
  - In `_build_entity_context`, replace the section headings `### 实体属性`, `### 相关事实和关系`, `### 关联实体信息`, `### Zep检索到的事实信息`, and `### Zep检索到的相关节点` with English equivalents (`### Entity Attributes`, `### Related Facts and Relationships`, `### Connected Entities`, `### Zep-Retrieved Facts`, `### Zep-Retrieved Related Nodes`)
  - In `_build_entity_context`, replace the Chinese placeholder `(相关实体)` emitted on either side of the `--[edge_name]-->` arrow (when an edge has only an `edge_name` but no `fact`) with `(related entity)`
  - In `_search_zep_for_entity`, replace the Chinese inline labels `事实信息:\n` and `相关实体:\n` (used when assembling `results["context"]`) with English equivalents (`Facts:\n` and `Related entities:\n`)
  - In `_search_zep_for_entity`, replace the Chinese inline label `f"相关实体: {node_name}"` (emitted when iterating over node summaries) with an English equivalent (`f"Related entity: {node_name}"`)
  - In `_build_individual_persona_prompt` and `_build_group_persona_prompt`, replace the empty-state fallbacks `"无"` (used by `attrs_str = json.dumps(...) if entity_attributes else "无"`) and `"无额外上下文"` (used by `context_str = context[:3000] if context else "无额外上下文"`) with English equivalents (`"None"` and `"No additional context"`)
  - Preserve the conditional inclusion of each context section (`if entity.attributes`, `if entity.related_edges`, `if entity.related_nodes`, `if zep_results.get("facts")`, `if zep_results.get("node_summaries")`) and the existing caps (`new_facts[:15]`, `node_summaries[:10]`, `results["facts"][:20]`, `results["node_summaries"][:10]`)
  - Observable completion: `_build_entity_context` and the prompt-feeding portions of `_search_zep_for_entity` emit English-only headings and inline labels; the `attrs_str`/`context_str` fallbacks render in English; logger-call literals in the same functions are unchanged
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11_
  - _Boundary: OasisProfileGenerator → `_build_entity_context`, `_search_zep_for_entity` (prompt-feeding literals only)_

- [x] 5. Add a static AST-based guard against CJK regression in the prompt-bearing literals
  - Add a new script `backend/scripts/test_oasis_profile_prompts_no_cjk.py` mirroring the structure of `backend/scripts/test_ontology_prompts_no_cjk.py`
  - Parse `backend/app/services/oasis_profile_generator.py` via `ast.parse` (no production-code import; runs without `LLM_API_KEY` or Neo4j configured)
  - For each in-scope function (`_get_system_prompt`, `_build_individual_persona_prompt`, `_build_group_persona_prompt`, `_build_entity_context`, `_search_zep_for_entity`), extract every `ast.Constant` (str) and the static `ast.Constant` children of `ast.JoinedStr` (f-string), excluding the function's own docstring
  - When walking the function body, exclude entire subtrees rooted at any `ast.Call` whose `func` is an attribute access on `logger` (i.e., skip everything inside `logger.warning(...)`, `logger.info(...)`, `logger.error(...)`, `logger.debug(...)`); this guarantees logger-call argument literals — including Chinese ones owned by issue #6 — are not inspected by the guard
  - Assert zero matches for regex `[一-鿿]` across the collected literals; print a clear failure message naming each offending literal and its function; exit 0 on success, non-zero on regression
  - Observable completion: running `uv run python backend/scripts/test_oasis_profile_prompts_no_cjk.py` exits 0 against the translated module; running it against the pre-translation file would exit non-zero with at least the system prompt and both user-message templates flagged
  - _Requirements: 1.1, 2.8, 3.8, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_
  - _Boundary: backend/scripts/test_oasis_profile_prompts_no_cjk.py (new file)_

- [x] 6. Confirm boundary commitments around the translation
  - Confirm the calls to `get_language_instruction()` remain at all three current sites (`_get_system_prompt`, `_build_individual_persona_prompt`, `_build_group_persona_prompt`) and the `set_locale(current_locale)` call inside `generate_single_profile` (line 914 region) is unchanged
  - Confirm the calls to `t('progress.zepSearchQuery', name=entity_name)` (in `_search_zep_for_entity`) and `t('progress.profileGenerated', name=entity_name, type=entity_type)` (in `_print_generated_profile`) are unchanged
  - Confirm the public/private signatures are unchanged: `__init__`, `generate_profile_from_entity`, `generate_profiles_from_entities`, `save_profiles`, `save_profiles_to_json`, `_save_twitter_csv`, `_save_reddit_json`, `set_graph_id`, `_get_system_prompt`, `_build_individual_persona_prompt`, `_build_group_persona_prompt`, `_build_entity_context`, `_search_zep_for_entity`, `_is_individual_entity`, `_is_group_entity`, `_normalize_gender`, `_fix_truncated_json`, `_try_fix_json`, `_generate_profile_with_llm`, `_generate_profile_rule_based`, `_generate_username`, `_print_generated_profile`
  - Confirm the dataclass `OasisAgentProfile` fields and the methods `to_reddit_format`, `to_twitter_format`, `to_dict` are unchanged
  - Confirm the OpenAI SDK call shape in `_generate_profile_with_llm` is unchanged: `response_format={"type": "json_object"}`, retry count `max_attempts = 3`, temperature schedule `0.7 - (attempt * 0.1)`, exponential-backoff sleep `time.sleep(1 * (attempt + 1))`, no `max_tokens` set
  - Confirm `_normalize_gender` and its Chinese-to-English mapping (`男`, `女`, `机构`, `其他` → `male`, `female`, `other`, `other`) are unchanged
  - Confirm the `MBTI_TYPES`, `COUNTRIES`, `INDIVIDUAL_ENTITY_TYPES`, `GROUP_ENTITY_TYPES` lists are unchanged
  - Confirm the rule-based fallback strings in `_generate_profile_rule_based` (including `"中国"` defaults), the Chinese-language fallback persona strings (`f"{entity_name}是一个{entity_type}。"`) at the JSON-repair sites, and the `"中国"` default in `_save_reddit_json` are unchanged (out of scope per #6/#7)
  - Confirm `logger.warning(...)`, `logger.info(...)`, `logger.error(...)`, `logger.debug(...)`, `print(...)` console-progress strings, the section labels in `_print_generated_profile` (`【简介】`, `【详细人设】`, `【基本属性】`, `用户名`, `年龄`, `性别`, `MBTI`, `职业`, `国家`, `兴趣话题`, `无`), module/class/method docstrings, and inline comments are unchanged (out of scope per #6/#7)
  - Confirm `backend/app/utils/locale.py`, `/locales/languages.json`, `/locales/en.json`, `/locales/zh.json`, `backend/pyproject.toml`, `backend/uv.lock`, and any file outside `backend/app/services/oasis_profile_generator.py` and the new `backend/scripts/test_oasis_profile_prompts_no_cjk.py` are unmodified
  - Observable completion: a `git diff` review against `main` shows changes only inside `backend/app/services/oasis_profile_generator.py` (within the five in-scope literal regions) and the addition of `backend/scripts/test_oasis_profile_prompts_no_cjk.py`; the surrounding lines and the out-of-scope literals are byte-identical
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9_
  - _Boundary: OasisProfileGenerator (full module diff audit)_

- [x] 7. Verify reasoning-model output compatibility and JSON-repair flow stability
  - Inspect `_fix_truncated_json` and `_try_fix_json` to confirm no logic changes were introduced and no new pre-processing of the LLM response was added in `_generate_profile_with_llm`
  - Run an in-process round-trip: instantiate `OasisProfileGenerator`, call `generate_profile_from_entity(...)` against a small representative `EntityNode` (with name, summary, attributes, related_edges, related_nodes), and assert the returned `OasisAgentProfile` has non-empty `bio` and `persona`, and `gender ∈ {male, female, other}` after `_normalize_gender`
  - Repeat the round-trip under simulated reasoning-model output (e.g. by stubbing the OpenAI client to return a `<think>...</think>` tag wrapping a known-good JSON, or a markdown-fenced JSON, or a truncated JSON that triggers `_fix_truncated_json`) to confirm the existing repair path still extracts a usable profile
  - Observable completion: a short verification script (or inline `python -c` recorded in the PR description) demonstrates the round-trip succeeds with both clean and degraded LLM outputs and produces a valid `OasisAgentProfile`
  - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - _Boundary: OasisProfileGenerator (full module behavioral check)_

- [ ] 8. Verify locale-driven persona-content language under both `en` and `zh`
  - Set the thread-local locale to `en` via `set_locale("en")`, run `OasisProfileGenerator().generate_profile_from_entity(...)` against the configured LLM with both an individual-type entity (e.g., `entity_type="student"`) and a group-type entity (e.g., `entity_type="university"`), and confirm the returned `bio`, `persona`, `profession`, and `interested_topics` contain no CJK characters and read as natural English; confirm `gender ∈ {male, female}` for individuals and `gender == "other"` for groups
  - Set the thread-local locale to `zh` via `set_locale("zh")`, run the same round-trip, and confirm the returned `bio`, `persona`, `profession`, and `interested_topics` contain CJK characters of equivalent quality to the pre-change baseline; confirm the gender enum still matches (`male`/`female` for individuals, `other` for groups)
  - Observable completion: both runs succeed; the `en` run is CJK-free in `bio`/`persona`/`profession`/`interested_topics`, the `zh` run continues to produce Chinese persona content; results are recorded in the PR description
  - _Requirements: 5.8, 5.9_
  - _Boundary: OasisProfileGenerator + Locale (runtime check)_

- [ ] 9. Verify Step 2 environment-setup parity end-to-end and OASIS-subprocess acceptance
  - Run the existing schema check `uv run python backend/scripts/test_profile_format.py` and confirm it still passes (the saver helpers `_save_reddit_json` and `_save_twitter_csv` are unchanged by this PR; this is a regression sanity check)
  - Using a representative project, exercise the full Step 2 environment-setup pipeline (entities → profiles → Reddit JSON / Twitter CSV) under `Accept-Language: en`
  - Confirm every produced profile has `gender ∈ {male, female, other}`, `age` is an integer, and the Reddit JSON contains `user_id`, `username`, `name`, `bio`, `persona`, `karma`, `created_at`, `age`, `gender`, `mbti`, `country` for every entry; the Twitter CSV contains the OASIS-required header `user_id, name, username, user_char, description` with one row per profile
  - Confirm the OASIS subprocess (Step 3 simulation start-up) accepts the produced files without schema errors
  - Observable completion: `test_profile_format.py` exits 0; an end-to-end Step 2 → Step 3 launch under `en` locale succeeds without OASIS-side schema errors; the verification result is recorded in the PR description
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  - _Boundary: OasisProfileGenerator + simulation_runner.py (end-to-end check; no edits to simulation_runner.py)_
