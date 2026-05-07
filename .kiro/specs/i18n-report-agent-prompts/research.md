# Research & Design Decisions — i18n-report-agent-prompts

## Summary

- **Feature**: `i18n-report-agent-prompts`
- **Discovery Scope**: Extension (single-file in-place translation, established sibling-spec precedent)
- **Key Findings**:
  - The full LLM-message-stream Chinese surface in `report_agent.py` is ~2680 chars across 7 top-level prompt constants, 4 tool-description blocks, ~10 inline f-strings/templates inside `_generate_section_react` and `chat`, the `_execute_tool` error returns, and the `plan_outline` defaults — ~4× the ticket's "~609 char" estimate.
  - The four sibling i18n PRs (#2/#3/#4 commits `0806832`, `9d1d29b`, `6c2a412`) established in-place translation in a single file as the pattern; reviewer expectations and PR shape are already locked in.
  - Two cross-cutting literals must be preserved byte-for-byte: the trigger string `Final Answer:` (matched by `_generate_section_react` line 1327) and the XML tag `<tool_call>` (matched by `_parse_tool_calls` regex). All translated prompts continue to reference these literals exactly.

## Research Log

### Topic: How does locale switching work today and what guarantees does it give?

- **Context**: R9 of requirements depends on `get_language_instruction()` continuing to bias the model into the requested locale even after the base prompt is English.
- **Sources Consulted**: `backend/app/utils/locale.py`; `locales/languages.json`; `locales/en.json`; `locales/zh.json`; sibling-spec gap-analysis for issue #4 (`.kiro/specs/i18n-simulation-config-generator-prompts/gap-analysis.md`).
- **Findings**:
  - `get_language_instruction()` resolves locale from the Flask `Accept-Language` header (or thread-local in background threads) and returns a per-locale postfix string (`Please respond in English.` for `en`, `请使用中文回答。` for `zh`, etc.).
  - `languages.json` registers `zh`, `en`, `es`, `fr`, `pt`, `ru`, `de`. All non-`zh` postfixes are already in English.
  - Sibling spec #4 verified that an English-base prompt + `请使用中文回答。` postfix produces Chinese output of equivalent quality to the prior Chinese-base prompt for the simulation-config flow. The same mechanism applies here — there is no report-agent-specific locale path.
- **Implications**: The translation does not need to touch `locale.py` or `/locales/*`. Preserving the three `get_language_instruction()` call sites verbatim is sufficient for R9.

### Topic: Which literal trigger strings does the ReACT loop parser match?

- **Context**: R2 acceptance criterion 6 and R4 acceptance criterion 4 require that translated prompts continue to use literal trigger strings the parser depends on.
- **Sources Consulted**: `backend/app/services/report_agent.py` lines 1067–1126 (`_parse_tool_calls`, `_is_valid_tool_call`); 1327 (`has_final_answer = "Final Answer:" in response`); 1838, 1874 (chat regex `<tool_call>.*?</tool_call>`).
- **Findings**:
  - `Final Answer:` is matched as a Python literal substring (case-sensitive). Translation must keep this English token byte-for-byte.
  - `<tool_call>` and `</tool_call>` are matched by `re.search(r'<tool_call>(.*?)</tool_call>', response, re.DOTALL)` (line 1080-ish, in `_parse_tool_calls`). Translation must keep these XML tags byte-for-byte.
  - `_is_valid_tool_call` accepts both `{"name": ..., "parameters": ...}` and `{"tool": ..., "params": ...}` shapes, normalizing to `name`/`parameters`. Translation does not affect this.
- **Implications**: Translated prompts continue to instruct the model using the same literal example block; only the surrounding natural-language Chinese is rewritten in English.

### Topic: Are there Chinese illustrations embedded inside the section system prompt that must also translate?

- **Context**: `SECTION_SYSTEM_PROMPT_TEMPLATE` (615–767) contains code-fenced "正确示例" / "错误示例" blocks with Chinese sample text. These are formatting-contract illustrations, not data.
- **Sources Consulted**: `report_agent.py` lines 678–703.
- **Findings**:
  - The "正确示例" block (lines 678–694) shows a sample paragraph using `**bold**`, `>` block quotes, and lists — Chinese text demonstrating the no-headings rule.
  - The "错误示例" block (lines 696–703) shows wrong patterns (`## 执行摘要`, `### 一、首发阶段`, etc.) with Chinese text labeled as errors.
  - These are illustrative only — the model uses them to internalize the format contract. Translating them to semantically equivalent English (sample paragraph about, e.g., a generic event using English bold/quotation/list patterns; wrong patterns showing English headings labeled as errors) preserves the contract.
- **Implications**: The section system prompt translation must rewrite both example blocks in English while keeping the structural rule (use `**bold**`, `>`, lists; do not use `#`, `##`, `###`, `####`).

### Topic: Are there Chinese strings that flow through `t(...)` keys (vs raw literals)?

- **Context**: R12 carves out `logger.*` calls already routed via `t('...')` (issue #6). Need to confirm we are not double-counting strings.
- **Sources Consulted**: `report_agent.py`; `locales/en.json`; `locales/zh.json`.
- **Findings**:
  - 47 of 48 `logger.*` calls in `report_agent.py` already use `t('report.*')` or `t('progress.*')` keys — those are out of scope.
  - One raw Chinese f-string remains: `logger.debug(f"LLM响应: {response[:200]}...")` at line 1322. This is a logger call (not a prompt string sent to the LLM). It belongs to issue #6, and leaving it untouched is consistent with the ticket boundary "logger calls in this file are covered by #6".
  - `progress_callback(...)` calls receive `t('progress.*')` localized strings — those flow to the frontend, not to the LLM, and are out of scope.
- **Implications**: After translation, a single Chinese f-string in `report_agent.py` remains (line 1322 logger.debug). This is acceptable per the ticket's R12 carve-out.

### Topic: How do consumers downstream of `Report.to_dict()` and `chat()` deal with localized output?

- **Context**: R10 / R11 — preserving the public surface so the report API and the chat endpoint continue to work unchanged.
- **Sources Consulted**: `backend/app/api/report.py`; `frontend/src/api/report.js`; `frontend/src/components/Step5*.vue`.
- **Findings**:
  - The report API blueprint hands `Report.to_dict()` and the chat response payload to the frontend without locale-specific post-processing. The frontend renders `report.title`, `report.summary`, and `report.sections[*].title/content` as plain text/Markdown.
  - There are no string-equality checks against Chinese substrings on the consumer side. Translating the fallback outline to English is safe.
- **Implications**: R8 (translate fallback outline) and R10 (preserve surface) are independently verifiable — no consumer-side adaptation required.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| In-place translation (A) | Edit Chinese string-literals in `report_agent.py` directly | Matches precedent of #2/#3/#4; minimal blast radius; no new files | Translations are baked in; non-`zh`/`en` locales still rely on postfix bias | **Selected** — same pattern, same scope |
| Externalize to `/locales/` (B) | Move all prompt content to `locales/en.json` / `locales/zh.json` and resolve via `t(...)` | Genuinely locale-agnostic; could later support es/fr/pt/ru/de natively | Touches `/locales/` (forbidden by R12); diverges from sibling pattern; brace-escape risk in JSON | Rejected — breaks R12 |
| Hybrid externalization (C) | Externalize top-level constants; keep inline f-strings in code | Captures largest blocks in localizable form | Two-tier inconsistency; same R12 violation; no precedent | Rejected — same R12 issue |

## Design Decisions

### Decision: In-place translation in a single file

- **Context**: Translate ~2680 Chinese characters across all LLM-facing string-literals in `backend/app/services/report_agent.py`.
- **Alternatives Considered**:
  1. Externalize all prompts to `/locales/*.json` and resolve via `t(...)`.
  2. Hybrid: externalize the seven top-level constants only.
- **Selected Approach**: In-place translation in `report_agent.py`. Edit each string-literal directly. No new files, no new abstractions.
- **Rationale**: Four sibling i18n PRs (issues #2/#3/#4) used the same pattern. Precedent is locked in; reviewer expectations are clear; PR shape is predictable. R12 explicitly forbids `/locales/` edits.
- **Trade-offs**: ✅ smallest blast radius, ✅ matches reviewer pattern. ❌ es/fr/pt/ru/de still rely on postfix bias (already true today; not a regression).
- **Follow-up**: Run `python -m py_compile backend/app/services/report_agent.py` post-edit; run a regex sweep verifying zero Chinese chars in any LLM-facing string-literal (the line-1322 `logger.debug` is exempt — issue #6).

### Decision: Translate embedded Chinese examples in `SECTION_SYSTEM_PROMPT_TEMPLATE`

- **Context**: The section system prompt contains "正确示例" / "错误示例" code blocks (lines 678–703) with Chinese sample text. R2 AC1 demands zero Chinese in any string-literal content.
- **Alternatives Considered**:
  1. Drop the example blocks entirely (shorter prompt, less guidance for the model).
  2. Translate to semantically equivalent English illustrations.
  3. Keep Chinese examples and append an English translation in parallel.
- **Selected Approach**: Translate to English. The "Correct Example" shows a sample paragraph about a generic scenario using `**bold**`, `>` block quotes, lists, and no headings. The "Wrong Example" shows wrong English headings (`## Executive Summary`, `### 1. First Stage`, etc.) labeled as errors.
- **Rationale**: The examples drive the model's understanding of the no-headings format contract. Removing them risks regressing format compliance. Parallel Chinese-then-English bloats the prompt and re-introduces Chinese tokens. English-only is the cleanest match for an English-base prompt.
- **Trade-offs**: ✅ preserves format contract, ✅ single-language base prompt. ❌ slight prompt-length growth (negligible vs total context).
- **Follow-up**: Spot-check a single end-to-end report run under `Accept-Language: en` to confirm the model still avoids Markdown headings in section bodies.

### Decision: Switch `"、".join(unused_tools)` to `", ".join(...)`

- **Context**: Line 1454 currently does `unused_tools_str = "、".join(unused_tools)`, where `、` is the Chinese enumeration comma. This list flows into `REACT_OBSERVATION_TEMPLATE` and into the inline f-strings at lines 1380 and 1476.
- **Alternatives Considered**:
  1. Keep `"、"` (Chinese punctuation).
  2. Switch to `", "` (English-friendly).
  3. Keep `"、"` for `zh`, `", "` for `en` (locale-conditional).
- **Selected Approach**: Switch to `", "` unconditionally.
- **Rationale**: The join result is interpolated into the now-English ReACT templates. Keeping the Chinese enumeration comma in English context reads as a typo. Locale-conditional behavior here would re-introduce Chinese tokens into the message stream when `zh` is the locale (acceptable but inconsistent with the rest of the message). The model already follows `get_language_instruction()` for output, so the join punctuation does not need to localize.
- **Trade-offs**: ✅ natural English rendering, ✅ single code path. ❌ a `zh`-locale developer reading the code might find the all-English separator slightly off — minor stylistic concern only.
- **Follow-up**: None — this is a one-line change.

### Decision: Standard English phrasing for recurring framing terms

- **Context**: The Chinese prompts use recurring framing tokens that need consistent English equivalents. Inconsistent translations (e.g. "scenario" in one place, "brief" in another) hurt the prompt's coherence.
- **Selected Approach**: Pick once, use everywhere:
  - 上帝视角 → "all-seeing observer's perspective" / "god's-eye view" (use the latter; shorter, more idiomatic)
  - 未来预演 → "forecast simulation" / "simulated future"
  - 模拟需求 → "simulation requirement" (matches the variable name `simulation_requirement`)
  - 上下文 → "context"
  - 章节 → "section"
  - 报告 → "report"
  - 大纲 → "outline"
  - 正确示例 → "Correct Example"
  - 错误示例 → "Wrong Example"
  - 重要 → "IMPORTANT"
  - 注意 → "Note"
  - 工具 → "tool"
  - 检索 → "retrieval"
  - 章节标题 → "section title"
  - 模拟世界 → "simulated world"
  - 引用 → "quote" / "quotation"
- **Rationale**: Internal consistency lets the model build a coherent mental model of the task vocabulary. Aligning with variable names (e.g. `simulation_requirement`) reduces translation surface ambiguity.
- **Trade-offs**: ✅ consistent vocabulary across translated regions. ❌ none.
- **Follow-up**: None — list serves as a glossary for the implementer.

## Risks & Mitigations

- **Risk**: Translated section system prompt drops a structural cue the Chinese version was carrying, regressing `zh` quality. **Mitigation**: Preserve all interpolations, the JSON schema, the no-headings rule, the language-consistency rule, the format-contract examples (now in English), and the `get_language_instruction()` postfix. Spot-check a `zh` run if feasible.
- **Risk**: A Chinese substring slips through (e.g. inside a hard-to-spot ReACT message). **Mitigation**: Run a regex sweep `re.findall(r'[一-鿿]', source)` after the edit; the only allowed remaining match is the line-1322 `logger.debug` Chinese f-string.
- **Risk**: Reformatting `SECTION_SYSTEM_PROMPT_TEMPLATE` damages the literal `<tool_call>` example or shifts the `Final Answer:` token. **Mitigation**: Use targeted `Edit` replacements that preserve the surrounding code block; verify after edit that `"Final Answer:" in response` still triggers the parser branch.
- **Risk**: The `"、".join(...)` separator change leaks into a Chinese-language render path. **Mitigation**: The separator only flows into ReACT templates that are already monolingually English in this PR; no `zh`-specific render path consumes it.

## References

- Issue #5 ticket body: `.ticket/5.md`.
- Sibling spec: `.kiro/specs/i18n-simulation-config-generator-prompts/{requirements,design,gap-analysis}.md`.
- Sibling commits: `0806832` (#2 ontology), `9d1d29b` (#3 oasis profile), `6c2a412` (#4 simulation config).
- Locale module: `backend/app/utils/locale.py`.
- Locale registry: `locales/languages.json`, `locales/en.json`, `locales/zh.json`.
