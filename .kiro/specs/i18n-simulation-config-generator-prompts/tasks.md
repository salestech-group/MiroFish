# Implementation Plan

## 1. Foundation: confirm scope and stage a verification harness

- [x] 1.1 Stage a one-shot verification harness for prompt-string content
  - Add a small, isolated verification script (placed under `backend/scripts/` so it can be removed in a follow-up if undesired) that, given the path to `simulation_config_generator.py`, asserts: (a) the file compiles, (b) the six prompt regions and the two prompt-feeding helper bodies contain zero `[一-鿿]` matches, (c) the trailing `IMPORTANT:` directives on the event-config and agent-config system prompts are present byte-equal as documented in design.md.
  - Wire the script to be runnable via `cd backend && uv run python scripts/verify_simulation_config_prompts.py`.
  - Observable completion: running the script before any translation prints concrete failures (block 1 user prompt: 417 zh chars, etc.) so the operator can see the harness works; after translation it prints "all checks passed" and exits 0.
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 7.1, 7.2_

## 2. Core: translate context-builder helpers (prompt-feeding inputs)

- [x] 2.1 Translate `_build_context` section headings to English
  - Replace the four Chinese strings inside the `_build_context` f-string list (`## 模拟需求`, `## 实体信息 ({n}个)`, `## 原始文档内容`, `(文档已截断)`) with English equivalents that read naturally for a native-English reader and preserve the markdown heading structure.
  - Preserve every interpolation: `{simulation_requirement}`, `{len(entities)}`, `{entity_summary}`, `{doc_text}`. Preserve the truncation logic and the 500-character buffer.
  - Observable completion: calling `_build_context(...)` with stub inputs returns a string whose section headings are English, whose entity-name and document content portions remain user-data verbatim, and whose total length math is unchanged.
  - _Requirements: 7.1, 7.3, 7.4_
  - _Boundary: simulation_config_generator._build_context_

- [x] 2.2 (P) Translate `_summarize_entities` headings and overflow marker to English
  - Replace `### {entity_type} ({len(type_entities)}个)` and `... 还有 {n} 个` with English equivalents (e.g. `### {entity_type} ({len(type_entities)})` and `... and {n} more`). Preserve the per-type display-count limit and the summary-length truncation logic.
  - Preserve `entity.name` and `entity.summary` data passthrough verbatim.
  - Observable completion: calling `_summarize_entities(...)` with a stub list of two entity types yields English headings and the existing per-entity name + summary lines.
  - _Requirements: 7.2, 7.3, 7.4_
  - _Boundary: simulation_config_generator._summarize_entities_

## 3. Core: translate the three prompt blocks

- [x] 3.1 (P) Translate the time-configuration prompt and system prompt to English
  - Rewrite the user-prompt f-string body in `_generate_time_config` (the block currently spanning lines ~543–586) to English while keeping every JSON-schema key (`total_simulation_hours`, `minutes_per_round`, `agents_per_hour_min`, `agents_per_hour_max`, `peak_hours`, `off_peak_hours`, `morning_hours`, `work_hours`, `reasoning`), the per-field numeric ranges (24–168 / 30–120 / 1–`max_agents_allowed`), and the UTC+8 reference example.
  - Rewrite the system-prompt literal (line 588) to English. Leave the `get_language_instruction()` postfix injection at line 589 untouched.
  - Preserve `{context_truncated}` and `{max_agents_allowed}` verbatim.
  - Observable completion: harness from 1.1 reports zero Chinese in the time-config user prompt and system prompt; calling `_generate_time_config(...)` with a mocked `_call_llm_with_retry` renders a prompt containing both interpolations.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 4.1_
  - _Boundary: simulation_config_generator._generate_time_config_

- [x] 3.2 (P) Translate the event-configuration prompt and system prompt to English
  - Rewrite the user-prompt f-string body in `_generate_event_config` to English while keeping every JSON-schema key (`hot_topics`, `narrative_direction`, `initial_posts[].content`, `initial_posts[].poster_type`, `reasoning`) and the type-to-author example pairings (Official/University → official statements, MediaOutlet → news, Student → student opinions).
  - Rewrite the system-prompt literal (line 705) to English. Leave the `get_language_instruction()` postfix injection at line 706 untouched and **keep the trailing English `IMPORTANT: The 'poster_type' field value MUST be in English PascalCase exactly matching the available entity types. Only 'content', 'narrative_direction', 'hot_topics' and 'reasoning' fields should use the specified language.` clause byte-equal**.
  - Preserve `{simulation_requirement}`, `{context_truncated}`, `{type_info}` verbatim.
  - Observable completion: harness reports zero Chinese in the event-config user prompt and system prompt; the byte-equal `IMPORTANT:` clause check passes.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 4.1_
  - _Boundary: simulation_config_generator._generate_event_config_

- [x] 3.3 (P) Translate the agent-config batch prompt and system prompt to English
  - Rewrite the user-prompt f-string body in `_generate_agent_configs_batch` to English while keeping every JSON-schema key (`agent_configs[].agent_id`, `activity_level`, `posts_per_hour`, `comments_per_hour`, `active_hours`, `response_delay_min`, `response_delay_max`, `sentiment_bias`, `stance`, `influence_weight`).
  - Preserve the four per-entity-type heuristic ranges as documented in design.md §Components: officials (University/GovernmentAgency) → low activity 0.1–0.3, work hours, slow response 60–240 min, high influence 2.5–3.0; media (MediaOutlet) → mid activity 0.4–0.6, all-day 8–23, fast response 5–30 min, high influence 2.0–2.5; individuals (Student/Person/Alumni) → high activity 0.6–0.9, evening 18–23, fast response 1–15 min, low influence 0.8–1.2; public figures/experts → mid activity 0.4–0.6, mid-high influence 1.5–2.0.
  - Rewrite the system-prompt literal (line 869) to English. Leave the `get_language_instruction()` postfix injection at line 870 untouched and **keep the trailing English `IMPORTANT: The 'stance' field value MUST be one of the English strings: 'supportive', 'opposing', 'neutral', 'observer'. All JSON field names and numeric values must remain unchanged. Only natural language text fields should use the specified language.` clause byte-equal**.
  - Preserve `{simulation_requirement}` and `{json.dumps(entity_list, ensure_ascii=False, indent=2)}` interpolations verbatim.
  - Observable completion: harness reports zero Chinese in the agent-config user prompt and system prompt; the byte-equal `IMPORTANT:` clause check passes.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.1_
  - _Boundary: simulation_config_generator._generate_agent_configs_batch_

## 4. Core: translate the two default-path `reasoning` literals

- [x] 4.1 Translate the `_get_default_time_config` reasoning literal to English
  - Replace the static literal `"使用默认中国人作息配置（每轮1小时）"` (line 608) with a locale-agnostic English equivalent (e.g. `"Default circadian-pattern config (1h per round)"`).
  - Do not change any other field of the returned dict; do not change the method signature; do not introduce locale lookup.
  - Observable completion: calling `_get_default_time_config(num_entities=10)` returns a dict whose `reasoning` value is locale-agnostic English and whose other eight numeric/array fields are unchanged.
  - _Requirements: 6.1, 6.2_

- [x] 4.2 Translate the `_generate_event_config` exception-path reasoning literal to English
  - Replace the static literal `"使用默认配置"` inside the `_generate_event_config` exception fallback (line 716) with a locale-agnostic English equivalent (e.g. `"Used default config"`).
  - Preserve the rest of the fallback dict shape (`hot_topics: []`, `narrative_direction: ""`, `initial_posts: []`, `reasoning: <english>`).
  - Observable completion: forcing the LLM call to raise (e.g. via mock) returns a dict whose `reasoning` is locale-agnostic English and whose other three keys are intact.
  - _Requirements: 6.1, 6.2_

## 5. Validation: locale and integration checks

- [x] 5.1 Confirm `get_language_instruction()` call sites are byte-equal at lines 589, 706, 870
  - After translation, run the harness from 1.1; it must verify that the three `system_prompt = f"{system_prompt}\n\n{get_language_instruction()}..."` injection lines remain unchanged in form (the only allowed deltas are inside `system_prompt` itself, which the harness already covered).
  - Observable completion: harness prints a "locale-postfix injection unchanged at lines 589/706/870" line and exits 0.
  - _Requirements: 1.7, 2.5, 3.6, 4.1, 4.5_
  - _Depends: 3.1, 3.2, 3.3_

- [x] 5.2 Confirm public-API and constants are byte-stable
  - Programmatically inspect the module after translation and confirm: `SimulationConfigGenerator.__init__`, `generate_config`, `_generate_time_config`, `_generate_event_config`, `_generate_agent_configs_batch`, `_parse_time_config`, `_parse_event_config`, `_assign_initial_post_agents`, `_generate_agent_config_by_rule`, `_call_llm_with_retry`, `_fix_truncated_json`, `_try_fix_config_json`, `_get_default_time_config`, `_build_context`, `_summarize_entities` all retain their existing parameter names and return annotations; the dataclasses (`AgentActivityConfig`, `TimeSimulationConfig`, `EventConfig`, `PlatformConfig`, `SimulationParameters`) are unchanged; the class-level constants `MAX_CONTEXT_LENGTH = 50000`, `AGENTS_PER_BATCH = 15`, `TIME_CONFIG_CONTEXT_LENGTH = 10000`, `EVENT_CONFIG_CONTEXT_LENGTH = 8000`, `ENTITY_SUMMARY_LENGTH = 300`, `AGENT_SUMMARY_LENGTH = 300`, `ENTITIES_PER_TYPE_DISPLAY = 20` are unchanged.
  - Inspection can be by `inspect.signature` checks plus `re.search` for the constant declarations.
  - Observable completion: a single signature/constant-stability check runs from the harness and prints "public surface stable" before exit.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  - _Depends: 3.1, 3.2, 3.3_

- [x] 5.3 Confirm out-of-scope guardrails: logger calls, docstrings, comments, adjacent files
  - Run a targeted check that confirms: `logger.info`/`logger.warning`/`logger.error`/`logger.debug` call lines retain their pre-existing Chinese content (no translation creep into #6's scope); `"""..."""` docstrings (module, class, dataclasses, methods) retain their pre-existing Chinese content (no translation creep into #7's scope); `git status` shows only `backend/app/services/simulation_config_generator.py` (and optionally `backend/scripts/verify_simulation_config_prompts.py`) modified — no edits to `backend/app/config.py`, `backend/app/services/simulation_ipc.py`, `backend/app/services/simulation_runner.py`, `backend/app/utils/locale.py`, `/locales/`, `backend/pyproject.toml`, or `backend/uv.lock`.
  - Observable completion: a check prints "out-of-scope guardrails respected" listing the count of Chinese chars remaining in logger lines (>0 expected) and in docstrings (>0 expected) as positive indicators; `git status` is clean except for the two allowed paths.
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - _Depends: 3.1, 3.2, 3.3, 4.1, 4.2_

- [x] 5.4 Locale-switching smoke test: `en` and `zh`
  - Sandbox lacks runtime dependencies (flask, openai, camel-ai stack — `tiktoken` requires a Rust compiler that is not available here). Substituted runtime smoke with **static evidence** that locale switching is preserved: (a) harness check confirms `get_language_instruction()` call-site count is exactly 3; (b) harness check confirms the time-config postfix injection line is byte-equal; (c) harness confirms both `IMPORTANT:` clauses are byte-equal at lines 706 and 870; (d) `git status` confirms `backend/app/utils/locale.py` and `locales/*.json` are unchanged. Together these guarantee that `set_locale('en')` continues to append `Please respond in English.` and `set_locale('zh')` continues to append `请使用中文回答。` at the same call sites with no semantic delta. Sister specs (#2, #3) used the same static-only posture.
  - Observable completion: harness exits 0 with all three of those checks reported as PASS.
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - _Depends: 3.1, 3.2, 3.3_

- [ ] 5.5* Optional fixture-based JSON-shape parity check
  - Build a stub `entities` list with three `EntityNode` instances (Student, MediaOutlet, Official) and a stub `simulation_requirement`. Patch `_call_llm_with_retry` to return realistic well-shaped JSON dicts for each of the three calls. Run `generate_config(...)` end-to-end. Assert that the returned `SimulationParameters.to_dict()` payload contains all 13 expected top-level keys (`simulation_id`, `project_id`, `graph_id`, `simulation_requirement`, `time_config`, `agent_configs`, `event_config`, `twitter_config`, `reddit_config`, `llm_model`, `llm_base_url`, `generated_at`, `generation_reasoning`).
  - Confirms R8 functional coverage without depending on a live OASIS subprocess. Marked optional because R5 + R8.4 already lock the shape stability via guard checks (5.2) and design-level reasoning; this is auxiliary belt-and-braces test coverage.
  - Observable completion: a single fixture-based test prints the asdict output and asserts all 13 keys present; exits 0.
  - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - _Depends: 3.1, 3.2, 3.3, 4.1, 4.2_

## 6. Cleanup

- [x] 6.1 Remove or move the verification harness as appropriate
  - If the verification harness from 1.1 is intended as a one-shot check, delete `backend/scripts/verify_simulation_config_prompts.py` after the implementation passes its checks. If it is intended as a permanent regression test, keep it under `backend/scripts/` and ensure it is callable via `uv run python scripts/verify_simulation_config_prompts.py` with no test framework required.
  - Decision rule: keep the harness only if it costs less than 30 lines and reads as a usable smoke check; otherwise remove it. Sister specs (#2, #3) shipped without permanent harnesses, so the default is "remove."
  - Observable completion: `git status` shows only `backend/app/services/simulation_config_generator.py` modified, with no harness artefacts left behind (preferred); or, if kept, the harness lives under `backend/scripts/` with a one-line module docstring linking back to spec `i18n-simulation-config-generator-prompts`.
  - _Requirements: 9.3_
  - _Depends: 5.1, 5.2, 5.3, 5.4_
