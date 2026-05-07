# Requirements Document

## Introduction

This specification covers the English translation of all LLM-facing prompt content in `backend/app/services/report_agent.py`. This module is the highest-impact prompt source for end-user output: it produces the final analytical report (Step 4 of the MiroFish pipeline) and powers the Report-Agent / Interview chat (Step 5). The runtime locale is steered by appending `get_language_instruction()` to each system prompt, but the base-prompt language biases the model's structural and lexical output. Today every prompt block in this file is authored in Chinese; even with the English postfix, the model's reasoning, sectioning, and tone skew Chinese under `Accept-Language: en`. Translating the base prompts to English removes that bias while preserving the existing locale-switching mechanism for non-English locales (verified: `get_language_instruction()` returns the Chinese postfix `请使用中文回答。` when locale is `zh`).

This work tracks GitHub issue [#5](https://github.com/salestech-group/MiroFish/issues/5).

## Boundary Context

- **In scope**:
    - Translating to English the four tool-description constants exposed to the LLM via `_define_tools()` / `_get_tools_description()`:
      - `TOOL_DESC_INSIGHT_FORGE` (lines ~476–492)
      - `TOOL_DESC_PANORAMA_SEARCH` (lines ~494–509)
      - `TOOL_DESC_QUICK_SEARCH` (lines ~511–521)
      - `TOOL_DESC_INTERVIEW_AGENTS` (lines ~523–548)
    - Translating the per-tool `parameters` dict values inside `_define_tools()` (lines ~925–952) — these strings are concatenated into the `tools_description` interpolated into both the section and chat system prompts.
    - Translating the leading literal `"可用工具："` in `_get_tools_description()` (line ~1129).
    - Translating the PLAN-phase prompts:
      - `PLAN_SYSTEM_PROMPT` (lines ~552–589)
      - `PLAN_USER_PROMPT_TEMPLATE` (lines ~591–611)
    - Translating the EXEC-phase / section-generation prompts:
      - `SECTION_SYSTEM_PROMPT_TEMPLATE` (lines ~615–767)
      - `SECTION_USER_PROMPT_TEMPLATE` (lines ~769–792)
    - Translating the ReACT loop conversation templates:
      - `REACT_OBSERVATION_TEMPLATE` (lines ~796–806)
      - `REACT_INSUFFICIENT_TOOLS_MSG` (lines ~808–811)
      - `REACT_INSUFFICIENT_TOOLS_MSG_ALT` (lines ~813–816)
      - `REACT_TOOL_LIMIT_MSG` (lines ~818–821)
      - `REACT_UNUSED_TOOLS_HINT` (line ~823)
      - `REACT_FORCE_FINAL_MSG` (line ~825)
    - Translating the SUMMARIZE / Interview chat prompts:
      - `CHAT_SYSTEM_PROMPT_TEMPLATE` (lines ~829–855)
      - `CHAT_OBSERVATION_SUFFIX` (line ~857)
    - Translating the inline Chinese strings emitted into the LLM message stream by `_generate_section_react` and `chat`, specifically:
      - `report_context = f"章节标题: ...\n模拟需求: ..."` (line ~1294)
      - The empty-response placeholder `"（响应为空）"` and follow-up `"请继续生成内容。"` (lines ~1316–1317)
      - The conflict-handling assistant→user message block at lines ~1342–1346
      - The two inline `unused_hint` strings `f"（这些工具还未使用，推荐用一下他们: {...}）"` (lines ~1380 and ~1476)
      - The chat default-path placeholders `"（暂无报告）"` (line ~1805) and `"\n\n... [报告内容已截断] ..."` (line ~1799)
      - The chat observation joiner format `f"[{r['tool']}结果]\n{r['result']}"` (line ~1861)
    - Translating the `_execute_tool` user-visible error returns `f"未知工具: {tool_name}..."` and `f"工具执行失败: {str(e)}"` (lines ~1058 and ~1062) — these strings are returned as observations and re-fed into the LLM message stream.
    - Translating the default / fallback outline content emitted by `plan_outline()`:
      - The success-path default title `"模拟分析报告"` (line ~1197) used when the LLM returns a successful payload missing `title`.
      - The exception-path fallback outline title/summary/section titles `"未来预测报告"`, `"基于模拟预测的未来趋势与风险分析"`, `"预测场景与核心发现"`, `"人群行为预测分析"`, `"趋势展望与风险提示"` (lines ~1212–1218).
    - Preserving every `get_language_instruction()` call site exactly as today (line ~1166, ~1262, ~1808 — the three postfix injections that follow each system prompt).
    - Preserving every variable interpolation token by name and position: `{simulation_requirement}`, `{total_nodes}`, `{total_edges}`, `{entity_types}`, `{total_entities}`, `{related_facts_json}`, `{report_title}`, `{report_summary}`, `{section_title}`, `{tools_description}`, `{previous_content}`, `{report_content}`, `{tool_name}`, `{result}`, `{tool_calls_count}`, `{max_tool_calls}`, `{used_tools_str}`, `{unused_hint}`, `{min_tool_calls}`, `{unused_list}`.
    - Preserving the JSON output contract of `PLAN_SYSTEM_PROMPT` verbatim by key name: `title`, `summary`, `sections[]` with sub-keys `title`, `description`.
    - Preserving the chat prefix-injection convention noted in `CLAUDE.md` — the section and chat loops strip `<tool_call>...</tool_call>` blocks from the user-visible response in `chat()` and reject mixed tool-call/Final-Answer outputs in `_generate_section_react`. The translated prompts must continue to instruct the model to obey this two-mode behavior.
    - Preserving the `Final Answer:` literal English trigger string used to demarcate the final section content (the prompts already use this English literal; the translation must keep it byte-for-byte identical).
    - Preserving the `<tool_call>` XML literal exactly (the parser in `_parse_tool_calls` matches it literally; the translation must keep it byte-for-byte identical).
    - Preserving the tool names exactly: `insight_forge`, `panorama_search`, `quick_search`, `interview_agents` (and the legacy aliases `search_graph`, `get_graph_statistics`, `get_entity_summary`, `get_simulation_context`, `get_entities_by_type` referenced in `_execute_tool`).
- **Out of scope**:
    - Logger messages (`logger.info`, `logger.warning`, `logger.error`, `logger.debug`) inside `report_agent.py` — covered by issue #6. (Most of these already use `t('...')` i18n keys; the few raw f-strings in the file are not in this PR.)
    - Module docstring (lines 1–11), class docstrings (`ReportLogger`, `ReportConsoleLogger`, `Report`, `ReportOutline`, `ReportSection`, `ReportAgent`, `ReportManager`), method docstrings, and inline `#` comments — covered by issue #7.
    - The post-processing markdown helpers `_clean_section_content` (line ~2132) and `_post_process_report` (line ~2301), which manipulate already-generated user-facing text; their `#` comments are #7 scope and they contain no Chinese string literals to translate.
    - Refactoring the prompt structure, the JSON output schema of `PLAN_SYSTEM_PROMPT`, the ReACT loop control flow in `_generate_section_react`, the conflict-resolution branches, the chat `MAX_TOOL_CALLS_PER_CHAT` limit, or the tool-name-set validation in `_is_valid_tool_call`.
    - Changing tool function names, signatures, return shapes, or the `zep_tools` adapter surface. The four primary tools (`insight_forge`, `panorama_search`, `quick_search`, `interview_agents`) remain identical in name, parameter schema, and return-text format.
    - Changing `Report`, `ReportOutline`, `ReportSection`, `ReportStatus`, or `ReportManager` (persistence layer) — JSON shapes and file paths under `reports/<id>/` are unchanged.
    - The `t('...')` i18n keys consumed by `progress_callback(...)` and `logger.*` calls — those already route through the locale registry and are #6 scope.
- **Adjacent expectations**:
    - The locale resolution chain (`Accept-Language` header → `get_locale()` → `get_language_instruction()`) lives in `backend/app/utils/locale.py` and is unchanged.
    - The `zep_tools` service (`backend/app/services/zep_tools.py`) and the OASIS interview API consumed by `interview_agents` are unchanged; only the prompt-side description of these tools is translated.
    - Companion i18n issues (#2 closed, #3 closed, #4 closed/in-flight, #6, #7, #8, #9, #10, #11, #12) operate on different files or scopes and must not be touched here.

## Requirements

### Requirement 1: English Translation of the PLAN-Phase Prompts (Outline Planning)

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the outline-planning system prompt and user prompt to be authored in English, so that the LLM's outline title, summary, and section titles are not biased toward Chinese sectioning conventions or word choice.

#### Acceptance Criteria

1. The Report Agent shall render `PLAN_SYSTEM_PROMPT` containing zero Chinese characters in any string-literal content.
2. The Report Agent shall render `PLAN_USER_PROMPT_TEMPLATE` containing zero Chinese characters in any string-literal content.
3. The Report Agent shall preserve the JSON output contract of the plan prompt verbatim by key name: `title`, `summary`, `sections` (a list of objects with sub-keys `title` and `description`).
4. The Report Agent shall preserve the section-count constraint as expressed in the prompt: minimum 2 sections, maximum 5 sections.
5. The Report Agent shall preserve the variable interpolations `{simulation_requirement}`, `{total_nodes}`, `{total_edges}`, `{entity_types}`, `{total_entities}`, `{related_facts_json}` verbatim by name and position.
6. The Report Agent shall preserve the `get_language_instruction()` call exactly at the line where it is appended to the plan system prompt (currently line ~1166), in the same syntactic form: `system_prompt = f"{PLAN_SYSTEM_PROMPT}\n\n{get_language_instruction()}"`.
7. The Report Agent shall preserve the prompt's framing of the model as an "all-seeing observer" of the simulated world (`上帝视角` → "God's-eye view" or equivalent neutral English) producing a forecast/prediction report rather than an analysis of present-day events. The translated wording shall convey the same framing without changing the semantic distinction between "future prediction" and "current-state analysis".

### Requirement 2: English Translation of the EXEC-Phase Prompts (Per-Section ReACT Generation)

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the per-section ReACT system prompt and user prompt to be authored in English, so that the section content the model produces (including embedded quotations and structural markers) is not biased toward Chinese phrasing or sectioning.

#### Acceptance Criteria

1. The Report Agent shall render `SECTION_SYSTEM_PROMPT_TEMPLATE` containing zero Chinese characters in any string-literal content.
2. The Report Agent shall render `SECTION_USER_PROMPT_TEMPLATE` containing zero Chinese characters in any string-literal content.
3. The Report Agent shall preserve the variable interpolations `{report_title}`, `{report_summary}`, `{simulation_requirement}`, `{section_title}`, `{tools_description}`, `{previous_content}` verbatim by name and position.
4. The Report Agent shall preserve the `get_language_instruction()` call exactly at the line where it is appended to the section system prompt (currently line ~1262), in the same syntactic form: `system_prompt = f"{system_prompt}\n\n{get_language_instruction()}"`.
5. The Report Agent shall preserve the per-section tool-call budget contract (≥3 calls, ≤5 calls per section) as expressed in the translated prompt, matching the runtime values `min_tool_calls = 3` and `MAX_TOOL_CALLS_PER_SECTION = 5`.
6. The Report Agent shall preserve the two-mode response contract: each LLM reply is either a single `<tool_call>...</tool_call>` block OR a single `Final Answer:`-prefixed body, never both. The translated prompt shall continue to instruct the model on this contract using the literal English trigger words `Final Answer:` and the literal XML tag `<tool_call>` exactly.
7. The Report Agent shall preserve the no-Markdown-headings instruction in section content (no `#`, `##`, `###`, `####`) and the recommendation to use `**bold**` plus `>` block-quotes for sub-emphasis. The translated prompt shall continue to forbid the model from emitting headings, since the post-processor `_clean_section_content` depends on this contract.
8. The Report Agent shall preserve the language-consistency instruction that quoted tool output be translated to the report language before being included in the section. The translated prompt shall convey the same instruction with reference to the active locale rather than a fixed language.
9. The Report Agent shall preserve the instruction that the model must call retrieval tools and may not author content from prior knowledge. The translated prompt shall preserve the literal tool-call format example block.

### Requirement 3: English Translation of the SUMMARIZE / Interview Chat Prompts

**Objective:** As a MiroFish operator chatting with the Report Agent under `Accept-Language: en`, I want the chat system prompt and observation suffix to be authored in English, so that the agent's chat replies are not biased toward Chinese tone or phrasing.

#### Acceptance Criteria

1. The Report Agent shall render `CHAT_SYSTEM_PROMPT_TEMPLATE` containing zero Chinese characters in any string-literal content.
2. The Report Agent shall render `CHAT_OBSERVATION_SUFFIX` containing zero Chinese characters in any string-literal content.
3. The Report Agent shall preserve the variable interpolations `{simulation_requirement}`, `{report_content}`, `{tools_description}` verbatim by name and position.
4. The Report Agent shall preserve the `get_language_instruction()` call exactly at the line where it is appended to the chat system prompt (currently line ~1808), in the same syntactic form: `system_prompt = f"{system_prompt}\n\n{get_language_instruction()}"`.
5. The Report Agent shall preserve the chat tool-call budget contract (`MAX_TOOL_CALLS_PER_CHAT`, currently 1–2 per session) as expressed in the translated prompt.
6. The Report Agent shall preserve the literal `<tool_call>...</tool_call>` block format example used by the parser in `_parse_tool_calls`.
7. The Report Agent shall continue to strip `<tool_call>` blocks from the user-visible response via the existing regex in `chat()` (lines ~1838–1839 and ~1874–1875). The translated prompts shall not change this prefix-injection / suppression contract.

### Requirement 4: English Translation of the ReACT-Loop Conversation Templates

**Objective:** As a MiroFish operator running the section-generation loop, I want the user-role messages re-injected into the LLM during the ReACT loop to be authored in English, so that the loop does not re-introduce a Chinese language bias mid-conversation after a successful tool call.

#### Acceptance Criteria

1. The Report Agent shall render `REACT_OBSERVATION_TEMPLATE` containing zero Chinese characters in any string-literal content.
2. The Report Agent shall render `REACT_INSUFFICIENT_TOOLS_MSG`, `REACT_INSUFFICIENT_TOOLS_MSG_ALT`, `REACT_TOOL_LIMIT_MSG`, `REACT_UNUSED_TOOLS_HINT`, and `REACT_FORCE_FINAL_MSG` each containing zero Chinese characters in any string-literal content.
3. The Report Agent shall preserve the variable interpolations `{tool_name}`, `{result}`, `{tool_calls_count}`, `{max_tool_calls}`, `{used_tools_str}`, `{unused_hint}`, `{min_tool_calls}`, `{unused_list}` verbatim by name and position across these templates.
4. The Report Agent shall preserve the literal English trigger string `Final Answer:` exactly inside `REACT_OBSERVATION_TEMPLATE` and `REACT_TOOL_LIMIT_MSG` so that the existing parser branch `"Final Answer:" in response` continues to work.
5. The Report Agent shall preserve the existing emoji and box-drawing characters (`💡`, `═`) used as visual separators in these templates; only the surrounding natural-language Chinese tokens shall be translated.
6. The Report Agent shall preserve the joining separator used by `unused_tools_str = "、".join(unused_tools)` (line ~1454). If the translated `REACT_OBSERVATION_TEMPLATE` and the inline `unused_hint` literals (lines ~1380 and ~1476) are reformatted, the join separator may be replaced with a locale-agnostic English-friendly equivalent (e.g. `", "`) so long as the rendered output reads naturally in English; the existing `set` / `string.join` semantics shall not change.

### Requirement 5: English Translation of the Tool-Description Constants and `_define_tools` Parameter Hints

**Objective:** As a MiroFish operator running the report or chat loops, I want the four tool-description blocks injected into every section / chat system prompt to be authored in English, so that the model's choice of which tool to call is informed by English semantics matching the rest of the prompt.

#### Acceptance Criteria

1. The Report Agent shall render `TOOL_DESC_INSIGHT_FORGE`, `TOOL_DESC_PANORAMA_SEARCH`, `TOOL_DESC_QUICK_SEARCH`, and `TOOL_DESC_INTERVIEW_AGENTS` each containing zero Chinese characters in any string-literal content.
2. The Report Agent shall preserve the per-tool semantics as conveyed by each description: `insight_forge` is a deep multi-angle analytical retrieval; `panorama_search` is a breadth/timeline overview retrieval; `quick_search` is a lightweight literal-keyword retrieval; `interview_agents` is a real OASIS dual-platform agent-interview API. The translation may rephrase but shall not change which tool is best for which use case.
3. The Report Agent shall preserve the literal tool name strings `insight_forge`, `panorama_search`, `quick_search`, `interview_agents` byte-for-byte across all four description blocks and inside `_define_tools()`.
4. The Report Agent shall render the parameter-description string values inside `_define_tools()` (the values for `query`, `report_context`, `include_expired`, `limit`, `interview_topic`, `max_agents` per tool) in English with zero Chinese characters.
5. The Report Agent shall render the leading literal `"可用工具："` in `_get_tools_description()` in English (e.g. `"Available tools:"`).
6. The Report Agent shall preserve the parameter dict keys (`query`, `report_context`, `include_expired`, `limit`, `interview_topic`, `max_agents`) byte-for-byte; only the value strings are translated.
7. The Report Agent shall preserve the operational-warning content in `TOOL_DESC_INTERVIEW_AGENTS` that flags the requirement for a running OASIS simulation environment.

### Requirement 6: English Translation of Inline LLM-Visible Strings in `_generate_section_react` and `chat`

**Objective:** As a MiroFish operator running either the section-generation loop or the chat loop, I want every Chinese string literal that is appended to the LLM `messages` array to be authored in English, so that the message stream the model sees is monolingual under `Accept-Language: en`.

#### Acceptance Criteria

1. The Report Agent shall render the `report_context` interpolation in `_generate_section_react` (currently `f"章节标题: {section.title}\n模拟需求: {self.simulation_requirement}"`, line ~1294) in English with zero Chinese characters, preserving the embedded `{section.title}` and `{self.simulation_requirement}` interpolations.
2. The Report Agent shall render the empty-response retry assistant placeholder `"（响应为空）"` (line ~1316) and the follow-up user prompt `"请继续生成内容。"` (line ~1317) in English with zero Chinese characters.
3. The Report Agent shall render the conflict-handling assistant→user message at lines ~1342–1346 (`"【格式错误】..."`) in English with zero Chinese characters, preserving the literal mention of `<tool_call>` and `'Final Answer:'`.
4. The Report Agent shall render the two inline `unused_hint` strings `f"（这些工具还未使用，推荐用一下他们: {', '.join(unused_tools)}）"` (lines ~1380 and ~1476) in English with zero Chinese characters, preserving the `{', '.join(unused_tools)}` interpolation. The two sites shall remain syntactically equivalent (either both retain f-strings or both use `.format()`); they are not required to be byte-for-byte identical to each other but they shall convey the same hint.
5. The Report Agent shall render the chat default-path placeholders `"\n\n... [报告内容已截断] ..."` (line ~1799) and `"（暂无报告）"` (line ~1805) in English with zero Chinese characters.
6. The Report Agent shall render the chat observation joiner format `f"[{r['tool']}结果]\n{r['result']}"` (line ~1861) in English with zero Chinese characters, preserving the `{r['tool']}` and `{r['result']}` interpolations.
7. The Report Agent shall preserve the relative ordering of `messages.append(...)` calls in `_generate_section_react` and `chat`. No new messages shall be added or removed by this translation work.

### Requirement 7: English Translation of `_execute_tool` Error Returns

**Objective:** As a MiroFish operator hitting an unknown-tool or tool-execution-error code path during section generation or chat, I want the returned error string to be authored in English, so that the LLM's downstream observation is monolingual and the user-visible error trail is consistent under `Accept-Language: en`.

#### Acceptance Criteria

1. The Report Agent shall render `f"未知工具: {tool_name}。请使用以下工具之一: insight_forge, panorama_search, quick_search"` (line ~1058) in English with zero Chinese characters, preserving the `{tool_name}` interpolation and the literal tool-name list.
2. The Report Agent shall render `f"工具执行失败: {str(e)}"` (line ~1062) in English with zero Chinese characters, preserving the `{str(e)}` interpolation.
3. The translated error returns shall remain locale-agnostic English under both `en` and `zh` locales — they are not gated by `get_language_instruction()` and surface to the LLM identically regardless of locale.

### Requirement 8: English Translation of Default / Fallback Outline Content in `plan_outline()`

**Objective:** As a MiroFish operator running the pipeline when the LLM either returns a successful payload missing a `title` or raises an exception during outline planning, I want the default report title, summary, and section titles to be authored in English, so that the surfaced fallback report does not display Chinese under an `en` locale.

#### Acceptance Criteria

1. The Report Agent shall render the success-path default title (currently `"模拟分析报告"`, line ~1197) in English with zero Chinese characters.
2. The Report Agent shall render the exception-path fallback `ReportOutline` title, summary, and section titles (currently `"未来预测报告"`, `"基于模拟预测的未来趋势与风险分析"`, and `"预测场景与核心发现"`, `"人群行为预测分析"`, `"趋势展望与风险提示"` at lines ~1212–1218) in English with zero Chinese characters.
3. The translated fallback outline shall remain a single locale-agnostic English block — it shall not be conditioned on `get_locale()`. Rationale: the fallback is reached only on hard failure or schema gap; downstream report assembly under `Accept-Language: zh` will still display these strings, and that is acceptable because (a) the fallback is rare, and (b) the simulation_config_generator companion spec applied the same convention (issue #4) for its default-path strings.
4. The translated fallback outline shall preserve the existing structural shape: a `ReportOutline` with three `ReportSection` items (no field additions, removals, or count changes).

### Requirement 9: Locale Switching Continues to Work via `get_language_instruction()`

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: zh` (or any other configured non-English locale), I want the report and chat output to remain in the requested locale of equivalent quality, so that translating the base prompts does not regress non-English support.

#### Acceptance Criteria

1. The Report Agent shall preserve the three call sites of `get_language_instruction()` at the same logical positions (relative to each prompt block: PLAN line ~1166, SECTION line ~1262, CHAT line ~1808) and in the same syntactic form: `system_prompt = f"{system_prompt}\n\n{get_language_instruction()}"`.
2. When the locale is `zh`, the Report Agent shall produce a final report whose section titles, section bodies, embedded quotations (translated from any language to Chinese as instructed by the prompt's language-consistency rule), and chat replies are in Chinese, equivalent in quality to the pre-change behaviour.
3. When the locale is `en`, the Report Agent shall produce the same set of natural-language fields in English.
4. The Report Agent shall not alter `backend/app/utils/locale.py`, the `_languages` registry, the `_translations` registry, or any file under `/locales/`.
5. Where a tool returns content in a language different from the active locale, the existing prompt-level instruction to translate quotations into the report language shall continue to apply unchanged.

### Requirement 10: Public API and Call-Site Stability

**Objective:** As a developer maintaining the rest of the MiroFish backend pipeline, I want the public surface of `ReportAgent` and `ReportManager` to remain unchanged, so that the report API blueprint (`api/report.py`) and the chat endpoint continue to work without modification.

#### Acceptance Criteria

1. The Report Agent shall preserve the signature of `ReportAgent.__init__(self, graph_id, simulation_id, simulation_requirement, llm_client=None, zep_tools=None, ...)`.
2. The Report Agent shall preserve the signatures of `ReportAgent.plan_outline(...)`, `ReportAgent.generate_report(...)`, `ReportAgent.chat(...)`, `ReportAgent._generate_section_react(...)`, `ReportAgent._execute_tool(...)`, `ReportAgent._define_tools(...)`, `ReportAgent._get_tools_description(...)`, `ReportAgent._parse_tool_calls(...)`, `ReportAgent._is_valid_tool_call(...)`.
3. The Report Agent shall preserve the dataclass-equivalent definitions `Report`, `ReportOutline`, `ReportSection`, `ReportStatus` and their `to_dict()` / `to_markdown()` shapes (no field additions, removals, renames, or default-value changes).
4. The Report Agent shall preserve the class-level constants `MAX_TOOL_CALLS_PER_SECTION`, `MAX_REFLECTION_ROUNDS`, `MAX_TOOL_CALLS_PER_CHAT`, `REPORTS_DIR` exactly.
5. The Report Agent shall preserve the LLM invocation parameters in `plan_outline()` (`temperature=0.3`), `_generate_section_react()` (`temperature=0.5`, `max_tokens=4096`), and `chat()` (`temperature=0.5`).

### Requirement 11: End-to-End Step 4 / Step 5 Parity

**Objective:** As a MiroFish operator validating the change, I want the report-generation and chat flows to produce coherent output under both `en` and `zh` locales, so that the translation does not silently degrade the analytical-report or interview-chat experience.

#### Acceptance Criteria

1. When a representative seed simulation requirement is processed end-to-end with locale `en`, `ReportAgent.generate_report(...)` shall return a `Report` with a non-empty title, non-empty summary, ≥2 and ≤5 sections, each section non-empty.
2. When the same flow is run with locale `zh`, `ReportAgent.generate_report(...)` shall return a `Report` whose natural-language fields are in Chinese and whose structural quality (section count, length, quotation presence) is at parity with the pre-change behaviour.
3. When `ReportAgent.chat(...)` is invoked with locale `en` against a generated report, the returned `response` field shall be in English and shall continue to suppress `<tool_call>` blocks in user-visible output.
4. When `ReportAgent.chat(...)` is invoked with locale `zh`, the returned `response` field shall be in Chinese.
5. The tool-call payload format observed by `zep_tools` (the parsed `{"name": ..., "parameters": ...}` dict) shall be unchanged by this work.

### Requirement 12: Out-of-Scope Surfaces Remain Untouched

**Objective:** As a reviewer of this PR, I want the change to remain narrowly scoped to LLM-facing prompt strings and the directly related inline message strings, so that translation responsibilities for adjacent surfaces (issues #6 and #7) and refactoring concerns are not absorbed into this change.

#### Acceptance Criteria

1. The change shall not modify any `logger.info(...)`, `logger.warning(...)`, `logger.error(...)`, or `logger.debug(...)` call in `report_agent.py` (covered by issue #6).
2. The change shall not modify the module docstring (lines 1–11), the class docstrings on `ReportLogger`, `ReportConsoleLogger`, `Report`, `ReportOutline`, `ReportSection`, `ReportAgent`, `ReportManager`, the dataclass docstrings, the method docstrings, or any inline `#` comment in `report_agent.py` (covered by issue #7).
3. The change shall not modify the persistence-layer methods in `ReportManager` (`_clean_section_content`, `_post_process_report`, `assemble_full_report`, `save_section`, `save_report`, `get_report`, `get_console_log`, `get_agent_log`, `update_progress`, `get_progress`, `get_generated_sections`, `delete_report`, `list_reports`, `get_report_by_simulation`).
4. The change shall not modify any file outside `backend/app/services/report_agent.py` for production code, except for adding test fixtures or scripts under a clearly-isolated directory if a verification harness is needed.
5. The change shall not introduce a new dependency or modify `backend/pyproject.toml` / `backend/uv.lock`.
6. The change shall not edit `backend/app/config.py`, `backend/app/services/zep_tools.py`, `backend/app/services/zep_entity_reader.py`, `backend/app/services/zep_graph_memory_updater.py`, `backend/app/utils/locale.py`, `backend/app/api/report.py`, or any file under `/locales/`.
