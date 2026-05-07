# Requirements Document

## Introduction

This specification covers the English translation of the three LLM prompt blocks in `backend/app/services/simulation_config_generator.py`. The file produces the simulation parameters consumed by the OASIS subprocess (Step 3 of the MiroFish pipeline): time/event/agent/platform configuration, hot-topic extraction, narrative direction, and stance assignment. Today, all three prompts are written in Chinese; the language is steered at runtime by appending `get_language_instruction()` to each system prompt. While that postfix instructs the model *which* language to respond in, the base-prompt language biases the model's structural and lexical output. As a result, the natural-language output fields (`content`, `narrative_direction`, `hot_topics`, `reasoning`) skew Chinese under `Accept-Language: en`. Translating the base prompts to English removes that bias while preserving the existing locale-switching mechanism for non-English locales (verified: `get_language_instruction()` returns the Chinese postfix `请使用中文回答。` when locale is `zh`).

This work tracks GitHub issue [#4](https://github.com/salestech-group/MiroFish/issues/4).

## Boundary Context

- **In scope**:
    - Translating the time-configuration prompt and its system prompt in `_generate_time_config` (block 1, lines ~543–588).
    - Translating the event-configuration prompt and its system prompt in `_generate_event_config` (block 2, lines ~676–705).
    - Translating the per-batch agent-configuration prompt and its system prompt in `_generate_agent_configs_batch` (block 3, lines ~833–869).
    - Preserving every `get_language_instruction()` call site exactly as today (lines 589, 706, 870 — the three postfix injections that follow each system prompt).
    - Preserving the existing English-only constraint directives that already follow `get_language_instruction()`: `poster_type` PascalCase English (block 2), `stance` ∈ {`supportive`, `opposing`, `neutral`, `observer`} (block 3).
    - Preserving every variable interpolation (`{context_truncated}`, `{simulation_requirement}`, `{type_info}`, `{max_agents_allowed}`, `{json.dumps(entity_list, ...)}`, etc.) verbatim by name and position.
    - Preserving the JSON output contract of each prompt (key names, value types, required fields).
- **Out of scope**:
    - Logger messages (`logger.info`, `logger.warning`, `logger.error`) inside the same file — covered by issue #6.
    - Module docstring, class docstrings, method docstrings, and inline comments — covered by issue #7.
    - Refactoring the prompt structure, JSON output schema, retry/repair logic in `_call_llm_with_retry`, or any data-class definitions.
    - Changing default simulation parameters (rounds count, action lists, etc. — owned by `app/config.py`).
    - The fallback string in `_get_default_time_config` (`"使用默认中国人作息配置（每轮1小时）"`) and the fallback `"使用默认配置"` in `_generate_event_config` exception handler — these are returned as `reasoning` values, not prompt content. Translation of these is closer to log/comment scope (#6/#7); for symmetry with the prompt translation goal they SHOULD be translated to English when locale-agnostic, but only as long as no behavioural side effects are introduced (see Requirement 6).
    - The `_build_context` Chinese section headings (`## 模拟需求`, `## 实体信息`, `## 原始文档内容`, `...(文档已截断)`) and `_summarize_entities` headings (`### {entity_type} ({len(type_entities)}个)`, `... 还有 {n} 个`) — these are interpolated into prompts as part of `{context_truncated}` and bias the model's output language. Translation of these section headings is in scope (see Requirement 7) because they contribute to the same model-output language bias the three prompt blocks address.
- **Adjacent expectations**:
    - The OASIS simulation subprocess and IPC layer (`services/simulation_ipc.py`) consume the resulting `SimulationParameters` payload. No coupling to prompt language exists in that consumer; the JSON shape of `SimulationParameters.to_dict()` is unchanged by this work.
    - The locale resolution chain (`Accept-Language` header → `get_locale()` → `get_language_instruction()`) lives in `backend/app/utils/locale.py` and is unchanged.
    - Companion i18n issues (#2 closed, #3 closed, #5, #6, #7) operate on different files or scopes and must not be touched here.

## Requirements

### Requirement 1: English Translation of the Time-Configuration Prompt (Block 1)

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the time-configuration prompt and system prompt to be authored in English, so that the LLM's `reasoning` field for time configuration is not biased toward Chinese structure or word choice.

#### Acceptance Criteria

1. The Simulation Config Generator shall render the user prompt inside `_generate_time_config` containing zero Chinese characters in any string-literal content.
2. The Simulation Config Generator shall render the system prompt inside `_generate_time_config` containing zero Chinese characters in any string-literal content.
3. The Simulation Config Generator shall preserve the JSON output contract of the time-config prompt verbatim by key name: `total_simulation_hours`, `minutes_per_round`, `agents_per_hour_min`, `agents_per_hour_max`, `peak_hours`, `off_peak_hours`, `morning_hours`, `work_hours`, `reasoning`.
4. The Simulation Config Generator shall preserve the field-level numeric constraints currently described in the prompt: `total_simulation_hours` ∈ 24–168, `minutes_per_round` ∈ 30–120 (recommend 60), `agents_per_hour_min`/`max` ∈ 1–`max_agents_allowed`.
5. The Simulation Config Generator shall preserve the variable interpolations `{context_truncated}` and `{max_agents_allowed}` verbatim by name and position.
6. The Simulation Config Generator shall preserve the prompt's guidance that the model should infer the target user group's timezone and circadian habits from the simulation scenario, with the UTC+8 reference example retained as illustrative guidance.
7. The Simulation Config Generator shall preserve the call to `get_language_instruction()` exactly at line ~589, appended after the translated system prompt.

### Requirement 2: English Translation of the Event-Configuration Prompt (Block 2)

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the event-configuration prompt and system prompt to be authored in English, so that generated `hot_topics`, `narrative_direction`, initial-post `content`, and `reasoning` fields are not biased toward Chinese structure or word choice.

#### Acceptance Criteria

1. The Simulation Config Generator shall render the user prompt inside `_generate_event_config` containing zero Chinese characters in any string-literal content.
2. The Simulation Config Generator shall render the system prompt inside `_generate_event_config` containing zero Chinese characters in any string-literal content.
3. The Simulation Config Generator shall preserve the JSON output contract of the event-config prompt verbatim by key name: `hot_topics` (list of strings), `narrative_direction` (string), `initial_posts` (list of objects with keys `content` and `poster_type`), `reasoning` (string).
4. The Simulation Config Generator shall preserve the variable interpolations `{simulation_requirement}`, `{context_truncated}`, and `{type_info}` verbatim by name and position.
5. The Simulation Config Generator shall preserve the call to `get_language_instruction()` exactly at line ~706 appended after the translated system prompt.
6. The Simulation Config Generator shall preserve verbatim the trailing English-only directive on `poster_type` formatting (currently: `IMPORTANT: The 'poster_type' field value MUST be in English PascalCase exactly matching the available entity types. Only 'content', 'narrative_direction', 'hot_topics' and 'reasoning' fields should use the specified language.`). The wording may be lightly normalized so it reads cleanly after a now-English system prompt, but the constraint semantics shall not change.
7. The Simulation Config Generator shall preserve the prompt's example list mapping entity types to expected post authors (Official/University → official statements, MediaOutlet → news, Student → student opinions) — translated to English while keeping each pairing intact.
8. When the locale is `zh`, the Simulation Config Generator shall produce `hot_topics`, `narrative_direction`, initial-post `content`, and `reasoning` fields in Chinese, equivalent in quality to the pre-change behaviour.

### Requirement 3: English Translation of the Agent-Config Batch Prompt (Block 3)

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the agent-config batch prompt and system prompt to be authored in English, so that the LLM's per-agent configuration emission is not biased by Chinese-specific behavioural priors when the seed scenario is non-Chinese.

#### Acceptance Criteria

1. The Simulation Config Generator shall render the user prompt inside `_generate_agent_configs_batch` containing zero Chinese characters in any string-literal content.
2. The Simulation Config Generator shall render the system prompt inside `_generate_agent_configs_batch` containing zero Chinese characters in any string-literal content.
3. The Simulation Config Generator shall preserve the JSON output contract of the agent-config batch prompt verbatim by key name: `agent_configs` (list) with sub-keys `agent_id`, `activity_level`, `posts_per_hour`, `comments_per_hour`, `active_hours`, `response_delay_min`, `response_delay_max`, `sentiment_bias`, `stance`, `influence_weight`.
4. The Simulation Config Generator shall preserve the variable interpolations `{simulation_requirement}` and the embedded `json.dumps(entity_list, ensure_ascii=False, indent=2)` rendering of the entity list verbatim.
5. The Simulation Config Generator shall preserve the per-entity-type heuristic ranges currently embedded in the prompt: officials (University/GovernmentAgency) — low activity 0.1–0.3, work hours, slow response 60–240 min, high influence 2.5–3.0; media (MediaOutlet) — mid activity 0.4–0.6, all-day 8–23, fast response 5–30 min, high influence 2.0–2.5; individuals (Student/Person/Alumni) — high activity 0.6–0.9, evening 18–23, fast response 1–15 min, low influence 0.8–1.2; public figures/experts — mid activity 0.4–0.6, mid-high influence 1.5–2.0.
6. The Simulation Config Generator shall preserve the call to `get_language_instruction()` exactly at line ~870, appended after the translated system prompt.
7. The Simulation Config Generator shall preserve verbatim the trailing English-only directive on `stance` and JSON-key formatting (currently: `IMPORTANT: The 'stance' field value MUST be one of the English strings: 'supportive', 'opposing', 'neutral', 'observer'. All JSON field names and numeric values must remain unchanged. Only natural language text fields should use the specified language.`). The wording may be lightly normalized so it reads cleanly after a now-English system prompt, but the constraint semantics shall not change.

### Requirement 4: Locale Switching Continues to Work via `get_language_instruction()`

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: zh` (or any other configured non-English locale), I want the simulation-config output to remain in the requested locale of equivalent quality, so that translating the base prompts does not regress non-English support.

#### Acceptance Criteria

1. The Simulation Config Generator shall preserve the three call sites of `get_language_instruction()` at the same line positions (relative to each prompt block) and in the same syntactic form: `system_prompt = f"{system_prompt}\n\n{get_language_instruction()}..."`.
2. When the locale is `zh`, the Simulation Config Generator shall produce a `time_config.reasoning`, `event_config.narrative_direction`, `event_config.hot_topics`, `event_config.initial_posts[*].content`, and a final `generation_reasoning` whose natural-language portions are in Chinese.
3. When the locale is `en`, the Simulation Config Generator shall produce the same set of natural-language fields in English.
4. The Simulation Config Generator shall not alter `backend/app/utils/locale.py`, the `_languages` registry, the `_translations` registry, or any file under `/locales/`.
5. Where a locale produces JSON output that is structurally invalid (e.g. a reasoning model emits `<think>` tags), the existing JSON repair logic in `_fix_truncated_json` and `_try_fix_config_json` shall continue to apply unchanged, regardless of prompt language.

### Requirement 5: Public API and Call-Site Stability

**Objective:** As a developer maintaining the rest of the MiroFish backend pipeline, I want the public surface of `SimulationConfigGenerator` to remain unchanged, so that the simulation pipeline (Step 3) continues to work without modification.

#### Acceptance Criteria

1. The Simulation Config Generator shall preserve the signature of `SimulationConfigGenerator.__init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model_name: Optional[str] = None)`.
2. The Simulation Config Generator shall preserve the signature of `SimulationConfigGenerator.generate_config(...)` including all parameters and return type.
3. The Simulation Config Generator shall preserve the signatures of the private methods `_generate_time_config`, `_generate_event_config`, `_generate_agent_configs_batch`, `_parse_time_config`, `_parse_event_config`, `_assign_initial_post_agents`, `_generate_agent_config_by_rule`, `_call_llm_with_retry`, `_fix_truncated_json`, `_try_fix_config_json`, `_get_default_time_config`, `_build_context`, `_summarize_entities`.
4. The Simulation Config Generator shall preserve the dataclass definitions `AgentActivityConfig`, `TimeSimulationConfig`, `EventConfig`, `PlatformConfig`, `SimulationParameters` exactly (no field additions, removals, renames, or default-value changes).
5. The Simulation Config Generator shall preserve the class-level constants `MAX_CONTEXT_LENGTH = 50000`, `AGENTS_PER_BATCH = 15`, `TIME_CONFIG_CONTEXT_LENGTH = 10000`, `EVENT_CONFIG_CONTEXT_LENGTH = 8000`, `ENTITY_SUMMARY_LENGTH = 300`, `AGENT_SUMMARY_LENGTH = 300`, `ENTITIES_PER_TYPE_DISPLAY = 20`.
6. The Simulation Config Generator shall preserve the LLM invocation parameters in `_call_llm_with_retry`: `response_format={"type": "json_object"}`, `temperature=0.7 - (attempt * 0.1)`, `max_attempts = 3`, no `max_tokens` setting.

### Requirement 6: Default-Path Output Compatibility

**Objective:** As a MiroFish operator hitting an LLM-failure fallback path, I want the default `reasoning` strings to remain compatible with downstream consumers, so that translating prompts does not silently break the `generation_reasoning` join or any downstream display.

#### Acceptance Criteria

1. The Simulation Config Generator shall continue to produce a non-empty `reasoning` field on the default path returned by `_get_default_time_config` and the exception path of `_generate_event_config`.
2. The Simulation Config Generator may translate the two literal default-path `reasoning` strings (`"使用默认中国人作息配置（每轮1小时）"` and `"使用默认配置"`) to English. If translated, both translations shall be locale-agnostic English (no Chinese characters), and both shall remain non-empty.
3. The Simulation Config Generator shall preserve the join semantics of `generation_reasoning = " | ".join(reasoning_parts)` — a `" | "` separator with the existing label prefixes contributed by `t('progress.timeConfigLabel')`, `t('progress.eventConfigLabel')`, etc.

### Requirement 7: Context-Builder Section Headings Translated

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the section headings injected into prompts via `_build_context` and `_summarize_entities` to be authored in English, so that the assembled prompt does not interleave English instruction blocks with Chinese section markers, which would otherwise re-introduce the same model-output language bias the prompt translations seek to eliminate.

#### Acceptance Criteria

1. The Simulation Config Generator shall render the section headings emitted by `_build_context` in English: replacing `## 模拟需求` with an English equivalent (e.g. `## Simulation Requirement`), `## 实体信息 ({n}个)` with `## Entities ({n})`, `## 原始文档内容` with `## Source Document Content`, and the truncation marker `(文档已截断)` with an English equivalent (e.g. `(document truncated)`).
2. The Simulation Config Generator shall render the per-entity-type breakdown in `_summarize_entities` in English: replacing `### {entity_type} ({n}个)` with `### {entity_type} ({n})` and the trailing overflow marker `... 还有 {n} 个` with an English equivalent (e.g. `... and {n} more`).
3. The Simulation Config Generator shall preserve `entity.name` and `entity.summary` data verbatim in the rendered context (no translation of user-provided content).
4. The change to context-builder headings shall not modify the public signatures of `_build_context` or `_summarize_entities`.

### Requirement 8: End-to-End Step 3 Parity

**Objective:** As a MiroFish operator validating the change, I want the OASIS subprocess to start cleanly and run at least one round under the English-prompt configuration, so that the translation does not silently degrade the simulation pipeline.

#### Acceptance Criteria

1. When a representative seed simulation requirement is processed end-to-end with locale `en`, `SimulationConfigGenerator.generate_config(...)` shall return a fully-populated `SimulationParameters` object (non-empty `agent_configs`, populated `time_config`, populated `event_config`).
2. When the resulting `SimulationParameters` is handed to the OASIS subprocess via `simulation_ipc.py`, the subprocess shall start without raising a schema or validation error attributable to the translated prompts.
3. When the resulting `SimulationParameters` is handed to the OASIS subprocess, the subprocess shall execute at least one simulation round without erroring on a `stance` not being one of `supportive`/`opposing`/`neutral`/`observer`, or a `poster_type` not matching an available entity type.
4. The Simulation Config Generator shall not change the `SimulationParameters.to_dict()` payload shape consumed by the IPC layer (verified via Requirement 5).

### Requirement 9: Out-of-Scope Surfaces Remain Untouched

**Objective:** As a reviewer of this PR, I want the change to remain narrowly scoped to prompt-content strings (and the directly related context-builder headings of Requirement 7), so that translation responsibilities for adjacent surfaces (issues #6 and #7) are not absorbed into this change.

#### Acceptance Criteria

1. The change shall not modify any `logger.info(...)`, `logger.warning(...)`, `logger.error(...)`, or `logger.debug(...)` call in `simulation_config_generator.py` (covered by issue #6).
2. The change shall not modify the module docstring at lines 1–11, the class docstring on `SimulationConfigGenerator`, the dataclass docstrings (`AgentActivityConfig`, `TimeSimulationConfig`, `EventConfig`, `PlatformConfig`, `SimulationParameters`), or any inline `#` comment in `simulation_config_generator.py` (covered by issue #7).
3. The change shall not modify any file outside `backend/app/services/simulation_config_generator.py` for production code, except for adding test fixtures or scripts under a clearly-isolated directory if a verification harness is needed.
4. The change shall not introduce a new dependency or modify `backend/pyproject.toml` / `backend/uv.lock`.
5. The change shall not edit `backend/app/config.py`, `backend/app/services/simulation_ipc.py`, `backend/app/services/simulation_runner.py`, `backend/app/utils/locale.py`, or any file under `/locales/`.
