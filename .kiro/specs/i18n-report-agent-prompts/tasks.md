# Implementation Plan

## 1. Foundation: stage a verification harness

- [x] 1.1 Stage a one-shot verification harness for prompt-string content
  - Add a small, isolated verification script under `backend/scripts/` that, given the path to `report_agent.py`, asserts: (a) the file compiles via `py_compile`; (b) every in-scope LLM-facing string-literal contains zero `[一-鿿]` matches; (c) the literal trigger strings `Final Answer:` and `<tool_call>` are still present in the relevant translated templates; (d) the four primary tool names (`insight_forge`, `panorama_search`, `quick_search`, `interview_agents`) are still byte-equal in `_define_tools` and the four `TOOL_DESC_*` constants; (e) the three `get_language_instruction()` call sites are byte-equal at the same logical positions; (f) the only Chinese remaining in the module is in `logger.*` lines, `"""..."""` docstrings, or `#` comments (i.e. issue #6/#7 scope).
  - Wire the script to be runnable via `cd backend && uv run python scripts/verify_report_agent_prompts.py`.
  - Observable completion: running the script before any translation prints concrete failures (~2680 Chinese chars in in-scope regions); after translation it prints "all checks passed" and exits 0.
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2, 5.1, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 8.1, 8.2, 9.1, 12.1, 12.2_

## 2. Core: translate tool-description constants and `_define_tools` parameter hints

- [x] 2.1 Translate the four `TOOL_DESC_*` constants to English
  - Rewrite `TOOL_DESC_INSIGHT_FORGE`, `TOOL_DESC_PANORAMA_SEARCH`, `TOOL_DESC_QUICK_SEARCH`, `TOOL_DESC_INTERVIEW_AGENTS` to English while preserving the per-tool semantics: `insight_forge` is deep multi-angle analytical retrieval; `panorama_search` is breadth/timeline overview retrieval; `quick_search` is lightweight literal-keyword retrieval; `interview_agents` is a real OASIS dual-platform agent-interview API.
  - Preserve byte-for-byte the literal tool name mentions and the operational warning about needing a running OASIS environment in `TOOL_DESC_INTERVIEW_AGENTS`.
  - Observable completion: harness from 1.1 reports zero Chinese in the four constants; tool-name byte-equality check passes.
  - _Requirements: 5.1, 5.2, 5.3, 5.7_
  - _Boundary: report_agent module-scope TOOL_DESC_* constants_

- [x] 2.2 Translate `_define_tools` parameter dict values and `_get_tools_description` leader
  - Rewrite the parameter-description string values inside `_define_tools` (the values for `query`, `report_context`, `include_expired`, `limit`, `interview_topic`, `max_agents` per tool) to English. Preserve the parameter dict keys byte-for-byte.
  - Rewrite the leading literal `"可用工具："` in `_get_tools_description` to English (e.g. `"Available tools:"`).
  - Observable completion: harness reports zero Chinese in `_define_tools` parameter values and in the `_get_tools_description` leader; calling `_get_tools_description()` on a stub `ReportAgent` instance returns a string starting with the English leader.
  - _Requirements: 5.4, 5.5, 5.6_
  - _Boundary: report_agent.ReportAgent._define_tools, _get_tools_description_

## 3. Core: translate the PLAN-phase prompts

- [x] 3.1 (P) Translate `PLAN_SYSTEM_PROMPT` and `PLAN_USER_PROMPT_TEMPLATE` to English
  - Rewrite both constants to English while keeping the JSON output schema (`title`, `summary`, `sections[].title`, `sections[].description`), the 2–5 section count constraint, and the all-seeing-observer / forecast-simulation framing.
  - Preserve every variable interpolation: `{simulation_requirement}`, `{total_nodes}`, `{total_edges}`, `{entity_types}`, `{total_entities}`, `{related_facts_json}`. Leave the `system_prompt = f"{PLAN_SYSTEM_PROMPT}\n\n{get_language_instruction()}"` injection at line 1166 untouched.
  - Observable completion: harness reports zero Chinese in `PLAN_SYSTEM_PROMPT` and `PLAN_USER_PROMPT_TEMPLATE`; rendering `PLAN_USER_PROMPT_TEMPLATE.format(simulation_requirement="x", total_nodes=0, total_edges=0, entity_types=[], total_entities=0, related_facts_json="[]")` raises no `KeyError`.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 9.1_
  - _Boundary: report_agent module-scope PLAN_SYSTEM_PROMPT, PLAN_USER_PROMPT_TEMPLATE_

- [x] 3.2 Translate `plan_outline` default / fallback outline content to English
  - Replace the success-path default title `"模拟分析报告"` (line 1197) with a locale-agnostic English equivalent (e.g. `"Simulation Analysis Report"`).
  - Replace the exception-path fallback `ReportOutline` content (lines 1212–1218): title `"未来预测报告"` → e.g. `"Future Prediction Report"`; summary `"基于模拟预测的未来趋势与风险分析"` → e.g. `"Trend and risk analysis based on simulation predictions"`; three section titles `"预测场景与核心发现"`, `"人群行为预测分析"`, `"趋势展望与风险提示"` → e.g. `"Scenario and Key Findings"`, `"Population Behavior Predictions"`, `"Trend Outlook and Risk Notes"`.
  - Preserve the existing `ReportOutline` shape: 3 `ReportSection` items, no field additions/removals.
  - Observable completion: forcing `plan_outline()` into the exception path (e.g. by stubbing `self.llm.chat_json` to raise) returns a `ReportOutline` whose title, summary, and section titles are locale-agnostic English; harness reports zero Chinese in lines 1197, 1212–1218.
  - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - _Boundary: report_agent.ReportAgent.plan_outline_

## 4. Core: translate the EXEC-phase prompts (section ReACT)

- [x] 4.1 Translate `SECTION_SYSTEM_PROMPT_TEMPLATE` to English (incl. embedded examples)
  - Rewrite the template to English while preserving: every `{report_title}`, `{report_summary}`, `{simulation_requirement}`, `{section_title}`, `{tools_description}` interpolation; the no-headings rule (no `#`, `##`, `###`, `####`); the language-consistency rule for translating quoted tool output to the report language; the must-call-tools instruction with min 3 / max 5 calls; the two-mode reply contract; the literal `Final Answer:` trigger string; the literal `<tool_call>...</tool_call>` example block; the box-drawing `═` separators and the `⚠️` / `❌` / `✅` markers.
  - Translate the embedded "正确示例" / "错误示例" code blocks (lines 678–703) to semantically equivalent English illustrations: the "Correct Example" should show a sample paragraph using `**bold**`, `>` block quotes, and lists (no headings); the "Wrong Example" should show wrong English headings (`## Executive Summary`, `### 1. First Stage`, etc.) labelled as errors.
  - Leave the `system_prompt = f"{system_prompt}\n\n{get_language_instruction()}"` injection at line 1262 untouched.
  - Observable completion: harness reports zero Chinese in `SECTION_SYSTEM_PROMPT_TEMPLATE`; `Final Answer:` and `<tool_call>` literals are present byte-equal; rendering with stub interpolations raises no `KeyError`.
  - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 9.1_
  - _Boundary: report_agent module-scope SECTION_SYSTEM_PROMPT_TEMPLATE_

- [x] 4.2 (P) Translate `SECTION_USER_PROMPT_TEMPLATE` to English
  - Rewrite the template to English while preserving the `{previous_content}` and `{section_title}` interpolations. Note that `{section_title}` is referenced twice — once as a literal in the do-not-write-as-opening warning and once as a body reference; both must be retained.
  - Preserve the must-call-tools / mix-tools / no-headings reminders. Preserve the closing three-step instruction (think → call tool → output Final Answer).
  - Observable completion: harness reports zero Chinese in `SECTION_USER_PROMPT_TEMPLATE`; rendering `SECTION_USER_PROMPT_TEMPLATE.format(previous_content="x", section_title="t")` raises no `KeyError` and the rendered string contains `t` in two places.
  - _Requirements: 2.2, 2.3, 2.7_
  - _Boundary: report_agent module-scope SECTION_USER_PROMPT_TEMPLATE_

## 5. Core: translate the ReACT loop conversation templates

- [x] 5.1 Translate `REACT_OBSERVATION_TEMPLATE` and the five `REACT_*_MSG` constants to English
  - Rewrite `REACT_OBSERVATION_TEMPLATE`, `REACT_INSUFFICIENT_TOOLS_MSG`, `REACT_INSUFFICIENT_TOOLS_MSG_ALT`, `REACT_TOOL_LIMIT_MSG`, `REACT_UNUSED_TOOLS_HINT`, `REACT_FORCE_FINAL_MSG` to English.
  - Preserve the `{tool_name}`, `{result}`, `{tool_calls_count}`, `{max_tool_calls}`, `{used_tools_str}`, `{unused_hint}`, `{min_tool_calls}`, `{unused_list}` interpolations across these templates. Preserve the `Final Answer:` literal trigger inside `REACT_OBSERVATION_TEMPLATE` and `REACT_TOOL_LIMIT_MSG`.
  - Preserve the emoji and box-drawing characters (`💡`, `═`).
  - Observable completion: harness reports zero Chinese in the six `REACT_*` constants; `Final Answer:` substring check passes for the two templates that reference it; rendering `REACT_OBSERVATION_TEMPLATE.format(tool_name="x", result="y", tool_calls_count=1, max_tool_calls=5, used_tools_str="a, b", unused_hint="z")` raises no `KeyError`.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Boundary: report_agent module-scope REACT_* constants_

- [x] 5.2 Switch the `unused_tools_str` join separator at line 1454 from `"、"` to `", "`
  - Change `unused_tools_str = "、".join(unused_tools)` to `unused_tools_str = ", ".join(unused_tools)` so the result reads naturally inside the now-English `REACT_OBSERVATION_TEMPLATE`.
  - Observable completion: a grep over `report_agent.py` for `"、"` returns zero matches; `unused_tools_str` rendered with two stub tool names yields `"insight_forge, panorama_search"` (English-friendly).
  - _Requirements: 4.6_
  - _Boundary: report_agent.ReportAgent._generate_section_react_

## 6. Core: translate the CHAT-phase prompts

- [x] 6.1 Translate `CHAT_SYSTEM_PROMPT_TEMPLATE` and `CHAT_OBSERVATION_SUFFIX` to English
  - Rewrite both constants to English while preserving the `{simulation_requirement}`, `{report_content}`, `{tools_description}` interpolations and the literal `<tool_call>...</tool_call>` example block.
  - Preserve the chat tool-budget hint (`MAX_TOOL_CALLS_PER_CHAT` semantics: 1–2 per session) and the answer-style instructions (concise, lead with conclusion, use `>` for quoted material).
  - Leave the `system_prompt = f"{system_prompt}\n\n{get_language_instruction()}"` injection at line 1808 untouched.
  - Observable completion: harness reports zero Chinese in both constants; `<tool_call>` substring check passes; rendering `CHAT_SYSTEM_PROMPT_TEMPLATE.format(simulation_requirement="x", report_content="r", tools_description="d")` raises no `KeyError`.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 9.1_
  - _Boundary: report_agent module-scope CHAT_SYSTEM_PROMPT_TEMPLATE, CHAT_OBSERVATION_SUFFIX_

## 7. Core: translate inline LLM-visible strings inside `_generate_section_react` and `chat`

- [x] 7.1 Translate the inline strings in `_generate_section_react` to English
  - Replace `report_context = f"章节标题: {section.title}\n模拟需求: {self.simulation_requirement}"` (line 1294) with an English equivalent (e.g. `f"Section title: {section.title}\nSimulation requirement: {self.simulation_requirement}"`), preserving both interpolations.
  - Replace the empty-response retry messages `"（响应为空）"` (line 1316) and `"请继续生成内容。"` (line 1317) with English equivalents (e.g. `"(empty response)"` and `"Please continue generating content."`).
  - Replace the conflict-handling assistant→user message at lines 1342–1346 with an English equivalent that preserves the literal mention of `<tool_call>` and `'Final Answer:'` and the two-mode contract (call one tool OR output Final Answer; never both).
  - Replace the inline `unused_hint` literals at lines 1380 and 1476 (`f"（这些工具还未使用，推荐用一下他们: {', '.join(unused_tools)}）"`) with English equivalents (e.g. `f"(These tools have not been used yet, you may try them: {', '.join(unused_tools)})"`), preserving the `{', '.join(unused_tools)}` interpolation. Both sites should convey the same hint and remain syntactically equivalent.
  - Observable completion: harness reports zero Chinese in `_generate_section_react` outside of `logger.*`, docstrings, and `#` comments; the four targeted regions render with their interpolations intact.
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.7_
  - _Boundary: report_agent.ReportAgent._generate_section_react_

- [x] 7.2 (P) Translate the inline strings in `chat` to English
  - Replace `"\n\n... [报告内容已截断] ..."` (line 1799) with an English equivalent (e.g. `"\n\n... [report content truncated] ..."`).
  - Replace `"（暂无报告）"` (line 1805) with an English equivalent (e.g. `"(no report yet)"`).
  - Replace the observation joiner format `f"[{r['tool']}结果]\n{r['result']}"` (line 1861) with an English equivalent (e.g. `f"[{r['tool']} result]\n{r['result']}"`), preserving the `{r['tool']}` and `{r['result']}` interpolations.
  - Observable completion: harness reports zero Chinese in `chat` outside of `logger.*`, docstrings, and `#` comments; the three targeted regions render with their interpolations intact.
  - _Requirements: 6.5, 6.6, 6.7_
  - _Boundary: report_agent.ReportAgent.chat_

## 8. Core: translate `_execute_tool` error returns

- [x] 8.1 Translate the `_execute_tool` error returns to English
  - Replace `f"未知工具: {tool_name}。请使用以下工具之一: insight_forge, panorama_search, quick_search"` (line 1058) with an English equivalent (e.g. `f"Unknown tool: {tool_name}. Please use one of: insight_forge, panorama_search, quick_search"`), preserving the `{tool_name}` interpolation and the literal tool-name list.
  - Replace `f"工具执行失败: {str(e)}"` (line 1062) with an English equivalent (e.g. `f"Tool execution failed: {str(e)}"`), preserving the `{str(e)}` interpolation.
  - Both translated strings remain locale-agnostic English (no `get_language_instruction()` injection at this site).
  - Observable completion: harness reports zero Chinese in lines 1058 and 1062; both error returns are locale-agnostic English; the literal tool-name list is byte-equal.
  - _Requirements: 7.1, 7.2, 7.3_
  - _Boundary: report_agent.ReportAgent._execute_tool_

## 9. Validation: locale and integration checks

- [x] 9.1 Confirm `get_language_instruction()` call sites are byte-equal at lines 1166, 1262, 1808
  - After translation, run the harness from 1.1; it must verify that the three `system_prompt = f"{...}\n\n{get_language_instruction()}"` injection lines remain unchanged in syntactic form (the only allowed deltas are inside `{...}` itself, which the prompt-content checks already covered).
  - Observable completion: harness prints a "locale-postfix injection unchanged at lines 1166/1262/1808" line and exits 0.
  - _Requirements: 1.6, 2.4, 3.4, 9.1_
  - _Depends: 3.1, 4.1, 6.1_

- [x] 9.2 Confirm public-API and constants are byte-stable
  - Programmatically inspect the module after translation and confirm: `ReportAgent.__init__`, `plan_outline`, `generate_report`, `chat`, `_generate_section_react`, `_execute_tool`, `_define_tools`, `_get_tools_description`, `_parse_tool_calls`, `_is_valid_tool_call` all retain their existing parameter names and return annotations; the dataclass-equivalent definitions `Report`, `ReportOutline`, `ReportSection`, `ReportStatus` are unchanged; the class-level constants `MAX_TOOL_CALLS_PER_SECTION`, `MAX_REFLECTION_ROUNDS`, `MAX_TOOL_CALLS_PER_CHAT`, `REPORTS_DIR` are unchanged.
  - Inspection can be by `inspect.signature` checks plus `re.search` for the constant declarations.
  - Observable completion: a single signature/constant-stability check runs from the harness and prints "public surface stable" before exit.
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - _Depends: 3.1, 4.1, 6.1_

- [x] 9.3 Confirm out-of-scope guardrails: logger calls, docstrings, comments, adjacent files
  - Run a targeted check that confirms: every `logger.info`/`logger.warning`/`logger.error`/`logger.debug` call line retains its pre-existing Chinese content (no translation creep into #6's scope) — the line-1322 `logger.debug(f"LLM响应: ...")` is the canary; `"""..."""` docstrings (module, classes `ReportLogger`, `ReportConsoleLogger`, `Report`, `ReportOutline`, `ReportSection`, `ReportAgent`, `ReportManager`, dataclasses, methods) retain their pre-existing Chinese content (no translation creep into #7's scope); `git status` shows only `backend/app/services/report_agent.py` (and optionally `backend/scripts/verify_report_agent_prompts.py`) modified — no edits to `backend/app/config.py`, `backend/app/services/zep_tools.py`, `backend/app/utils/locale.py`, `backend/app/api/report.py`, `/locales/`, `backend/pyproject.toml`, or `backend/uv.lock`.
  - Observable completion: a check prints "out-of-scope guardrails respected" listing the count of Chinese chars remaining in logger lines (>0 expected) and in docstrings (>0 expected) as positive indicators; `git status` is clean except for the two allowed paths.
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_
  - _Depends: 3.1, 3.2, 4.1, 4.2, 5.1, 5.2, 6.1, 7.1, 7.2, 8.1_

- [x] 9.4 Locale-switching static evidence: `en` and `zh`
  - Sandbox lacks runtime dependencies for an end-to-end report run. Substitute runtime smoke with **static evidence** that locale switching is preserved: (a) harness check confirms `get_language_instruction()` call-site count is exactly 3 at the expected logical positions; (b) harness check confirms the three injection lines are syntactically byte-equal in form; (c) `git status` confirms `backend/app/utils/locale.py` and `locales/*.json` are unchanged. Together these guarantee that under `Accept-Language: en` the postfix `Please respond in English.` continues to be appended and under `Accept-Language: zh` the postfix `请使用中文回答。` continues to be appended at the same call sites with no semantic delta. Sister specs (#2, #3, #4) used the same static-only posture.
  - Observable completion: harness exits 0 with all three checks reported as PASS.
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - _Depends: 3.1, 4.1, 6.1_

- [ ] 9.5* Optional fixture-based render-shape parity check
  - Build a stub `ReportAgent` (with stubbed `zep_tools` and `llm`) and patch the LLM client to return well-shaped JSON for `plan_outline()` and well-shaped tool-call + Final-Answer responses for `_generate_section_react()`. Run `generate_report(...)` end-to-end against the stub. Assert that the returned `Report` has a non-empty title, non-empty summary, ≥2 and ≤5 sections, each section non-empty.
  - Confirms R11 functional coverage without depending on a live Neo4j / OASIS environment. Marked optional because R10 + R11.5 already lock the shape stability via guard checks (9.2) and design-level reasoning; this is auxiliary belt-and-braces test coverage.
  - Observable completion: a single fixture-based test prints the `Report.to_dict()` keys and asserts the non-emptiness invariants; exits 0.
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_
  - _Depends: 3.1, 3.2, 4.1, 4.2, 5.1, 5.2, 6.1, 7.1, 7.2, 8.1_

## 10. Cleanup

- [x] 10.1 Remove or move the verification harness as appropriate
  - If the verification harness from 1.1 is intended as a one-shot check, delete `backend/scripts/verify_report_agent_prompts.py` after the implementation passes its checks. If it is intended as a permanent regression test, keep it under `backend/scripts/` and ensure it is callable via `uv run python scripts/verify_report_agent_prompts.py` with no test framework required.
  - Decision rule: keep the harness only if it costs less than 30 lines and reads as a usable smoke check; otherwise remove it. Sister specs (#2, #3, #4) shipped without permanent harnesses, so the default is "remove."
  - Observable completion: `git status` shows only `backend/app/services/report_agent.py` modified, with no harness artefacts left behind (preferred); or, if kept, the harness lives under `backend/scripts/` with a one-line module docstring linking back to spec `i18n-report-agent-prompts`.
  - _Requirements: 12.4_
  - _Depends: 9.1, 9.2, 9.3, 9.4_
