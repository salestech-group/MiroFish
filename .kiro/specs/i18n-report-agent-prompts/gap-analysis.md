# Gap Analysis — i18n-report-agent-prompts

## 1. Current-State Investigation

### Domain assets

- **Target file**: `backend/app/services/report_agent.py` (2572 lines).
- **Tool description constants** (LLM-facing, injected via `_get_tools_description`):
    - `TOOL_DESC_INSIGHT_FORGE` (lines 476–492)
    - `TOOL_DESC_PANORAMA_SEARCH` (lines 494–509)
    - `TOOL_DESC_QUICK_SEARCH` (lines 511–521)
    - `TOOL_DESC_INTERVIEW_AGENTS` (lines 523–548)
- **PLAN-phase prompts** (`plan_outline`, line ~1137):
    - `PLAN_SYSTEM_PROMPT` (lines 552–589) — `system_prompt = f"{PLAN_SYSTEM_PROMPT}\n\n{get_language_instruction()}"` at line 1166.
    - `PLAN_USER_PROMPT_TEMPLATE` (lines 591–611).
- **EXEC-phase prompts** (`_generate_section_react`, line ~1221):
    - `SECTION_SYSTEM_PROMPT_TEMPLATE` (lines 615–767) — appended postfix at line 1262.
    - `SECTION_USER_PROMPT_TEMPLATE` (lines 769–792).
- **ReACT loop conversation templates** (consumed inside `_generate_section_react`):
    - `REACT_OBSERVATION_TEMPLATE` (796–806)
    - `REACT_INSUFFICIENT_TOOLS_MSG` (808–811)
    - `REACT_INSUFFICIENT_TOOLS_MSG_ALT` (813–816)
    - `REACT_TOOL_LIMIT_MSG` (818–821)
    - `REACT_UNUSED_TOOLS_HINT` (823)
    - `REACT_FORCE_FINAL_MSG` (825)
- **CHAT-phase prompts** (`chat`, line ~1766):
    - `CHAT_SYSTEM_PROMPT_TEMPLATE` (829–855) — appended postfix at line 1808.
    - `CHAT_OBSERVATION_SUFFIX` (857).
- **Inline LLM-visible Chinese strings** (sent into `messages`):
    - `_define_tools` parameter-description dict values (925–952).
    - `_get_tools_description` leader `"可用工具："` (1129).
    - `_execute_tool` error returns `f"未知工具: {tool_name}..."` (1058) and `f"工具执行失败: {str(e)}"` (1062).
    - `_generate_section_react`: `report_context = f"章节标题: ...\n模拟需求: ..."` (1294); empty-response messages `"（响应为空）"` / `"请继续生成内容。"` (1316–1317); conflict-handling block (1342–1346); inline `unused_hint` literals at 1380 and 1476.
    - `chat`: report-truncated marker `"\n\n... [报告内容已截断] ..."` (1799); no-report fallback `"（暂无报告）"` (1805); observation joiner `f"[{r['tool']}结果]\n{r['result']}"` (1861).
- **Default / fallback outline content** in `plan_outline()`:
    - Success-path default title `"模拟分析报告"` (1197).
    - Exception-path fallback `ReportOutline` title `"未来预测报告"`, summary `"基于模拟预测的未来趋势与风险分析"`, three section titles (1212–1218).
- **Locale resolution**: `backend/app/utils/locale.py` `get_locale`/`get_language_instruction`/`t` resolves locale from `Accept-Language` header (or thread-local in background threads). `languages.json` registers `zh`, `en`, `es`, `fr`, `pt`, `ru`, `de`.

### Counts (verified, in-scope only)

| Region | Approx Chinese chars |
| --- | --- |
| `TOOL_DESC_INSIGHT_FORGE` | 110 |
| `TOOL_DESC_PANORAMA_SEARCH` | 95 |
| `TOOL_DESC_QUICK_SEARCH` | 50 |
| `TOOL_DESC_INTERVIEW_AGENTS` | 215 |
| `PLAN_SYSTEM_PROMPT` | 250 |
| `PLAN_USER_PROMPT_TEMPLATE` | 130 |
| `SECTION_SYSTEM_PROMPT_TEMPLATE` | 950 |
| `SECTION_USER_PROMPT_TEMPLATE` | 150 |
| `REACT_*` templates | 130 |
| `CHAT_SYSTEM_PROMPT_TEMPLATE` + `CHAT_OBSERVATION_SUFFIX` | 130 |
| `_define_tools` parameter dict values | 110 |
| `_execute_tool` error returns | 30 |
| `_generate_section_react` inline messages | 230 |
| `chat` inline messages | 60 |
| `plan_outline` defaults | 50 |
| **In-scope total** | **~2680** |

The ticket's "~609 Chinese characters" undercounts — it apparently only counted the three system-prompt blocks. The full LLM-message-stream Chinese surface is ~4× that. Logger calls (~17), docstrings, and module/class/method/inline `#` comments are out of scope (covered by #6 / #7).

### Conventions (extracted)

- Sister specs `i18n-ontology-generator-prompts` (commit `0806832`, issue #2), `i18n-oasis-profile-generator-prompts` (commit `9d1d29b`, issue #3), and `i18n-simulation-config-generator-prompts` (commit `6c2a412`, issue #4) established the pattern: **in-place translation of all LLM-facing string literals in a single file; preserve `get_language_instruction()` call sites; preserve all interpolations; do not touch logger, docstrings, comments, or other files.**
- 4-space indent, snake_case, double quotes for strings, `f"""..."""` for multi-line prompts. Existing Chinese-then-English mix is acceptable in comments/docstrings (steering tech.md: "preserve both; do not translate one into the other unless asked").
- No linter/formatter — match surrounding style.
- File mixes top-level constant prompts (e.g. `PLAN_SYSTEM_PROMPT`) with inline f-strings and `.format()` templates inside method bodies. Translation must respect both placement conventions.

### Integration surfaces

- `ReportAgent.generate_report(...)` is called from the report API blueprint (`api/report.py`). The returned `Report.to_dict()` payload is consumed by the frontend report panel; field shapes and types must remain unchanged.
- `ReportAgent.chat(...)` is called from the chat endpoint; the returned `{"response", "tool_calls", "sources"}` shape is consumed by the frontend chat UI.
- The four primary tools (`insight_forge`, `panorama_search`, `quick_search`, `interview_agents`) are dispatched in `_execute_tool` to `self.zep_tools.*` — those callees are unchanged.
- `_parse_tool_calls` matches the literal `<tool_call>...</tool_call>` XML tag and a fallback bare-JSON form via regex. Translation must preserve those literals byte-for-byte.
- `chat()` strips `<tool_call>` blocks from the user-visible response via `re.sub(r'<tool_call>.*?</tool_call>', '', ...)` (lines 1838, 1874). Translation does not affect this.
- `_clean_section_content` and `_post_process_report` post-process generated section content under the assumption that the LLM does not emit Markdown headings (`#`, `##`, `###`, etc.) inside section bodies. The translated `SECTION_SYSTEM_PROMPT_TEMPLATE` must continue to forbid headings.
- Locale-switching contract: when locale = `zh`, `get_language_instruction()` returns `请使用中文回答。`; when `en`, `Please respond in English.` — verified.

## 2. Requirement-to-Asset Map

| Requirement | Existing asset | Gap | Tag |
| --- | --- | --- | --- |
| R1 — PLAN prompts EN | `PLAN_SYSTEM_PROMPT` (552), `PLAN_USER_PROMPT_TEMPLATE` (591) | Translate text; preserve JSON schema (`title`, `summary`, `sections[]` w/ `title`, `description`); preserve 2–5 section count; preserve all interpolations | Missing (translation) |
| R2 — EXEC prompts EN | `SECTION_SYSTEM_PROMPT_TEMPLATE` (615), `SECTION_USER_PROMPT_TEMPLATE` (769) | Translate text; preserve `Final Answer:` / `<tool_call>` literals; preserve no-headings instruction; preserve language-consistency rule; preserve interpolation tokens | Missing (translation) |
| R3 — CHAT prompts EN | `CHAT_SYSTEM_PROMPT_TEMPLATE` (829), `CHAT_OBSERVATION_SUFFIX` (857) | Translate text; preserve `<tool_call>` literal; preserve `MAX_TOOL_CALLS_PER_CHAT` semantics | Missing (translation) |
| R4 — ReACT loop templates EN | `REACT_OBSERVATION_TEMPLATE` and 5 message constants (796–825) | Translate text; preserve `Final Answer:` literal; preserve emoji/box-drawing visuals; reconcile `"、".join(...)` separator | Missing (translation) |
| R5 — Tool-description constants EN | 4 `TOOL_DESC_*` blocks (476–548); `_define_tools` parameter dict (925–952); `_get_tools_description` leader (1129) | Translate text; preserve tool-name literals; preserve parameter dict keys; preserve OASIS-running warning | Missing (translation) |
| R6 — Inline LLM-visible strings EN | 7 inline strings across `_generate_section_react` and `chat` (1294, 1316–1317, 1342–1346, 1380, 1476, 1799, 1805, 1861) | Translate text; preserve `{section.title}`, `{self.simulation_requirement}`, `{r['tool']}`, `{r['result']}`, `{', '.join(unused_tools)}` interpolations | Missing (translation) |
| R7 — `_execute_tool` error returns EN | 2 f-strings (1058, 1062) | Translate text; preserve `{tool_name}` and `{str(e)}` interpolations; remain locale-agnostic | Missing (translation) |
| R8 — `plan_outline` defaults EN | 1 success-path default (1197), 5 exception-path strings (1212–1218) | Translate text; remain locale-agnostic; preserve `ReportOutline` shape (3 sections) | Missing (translation) |
| R9 — Locale switching preserved | `get_language_instruction()` calls at 1166, 1262, 1808 | None — keep call sites untouched | Constraint |
| R10 — Public API stable | Class/method/dataclass surface | None — text-only changes | Constraint |
| R11 — End-to-end parity | API blueprint, frontend report panel, OASIS interview API | Verification only — `Report.to_dict()` shape unchanged | Constraint |
| R12 — Out-of-scope guardrails | logger calls (~17 in this file), docstrings, comments, all other files | None — leave untouched | Constraint |

### Unknown / Research-needed

- **R11 verification feasibility**: Running an end-to-end report generation flow under `Accept-Language: en` and `Accept-Language: zh` requires Neo4j, an LLM key, a populated graph, and a running OASIS simulation (for `interview_agents`). In a sandboxed CI-like environment, this is not practical. Defer to a lightweight fixture-based check, matching the precedent set by issues #2/#3/#4: (a) `python -m py_compile` lint pass on `report_agent.py`; (b) zero-Chinese assertion on the in-scope string set via a script that imports the module and inspects each constant + a regex sweep over the module source; (c) shape parity by constructing a mock `ReportAgent` and confirming `_get_tools_description()`, `system_prompt`, and `user_prompt` render to the expected interpolation set without raising. **Decision (autonomous run)**: adopt option (c) — reviewer-trust is the precedent for issues #2/#3/#4 and the scope here is identical (single-file translation).
- **`logger.debug(f"LLM响应: {response[:200]}...")` at line 1322**: This is the one raw-Chinese logger call in this file (all others use `t('...')`). It is OUT OF SCOPE for issue #5 — it falls under issue #6 (logger translation). Note for the reviewer: this leaves one Chinese f-string in `report_agent.py` after this PR; the acceptance criterion in the ticket explicitly carves out logger lines.
- **`SECTION_SYSTEM_PROMPT_TEMPLATE` includes a "正确示例" / "错误示例" code block (lines 678–703) with embedded Chinese sample text** (`微博`, `抖音`, `校方` etc.). These are example illustrations of the formatting contract, not data. Translating them to English is required (R2 acceptance criterion 1: "zero Chinese characters"). The translated examples should still illustrate the same format rule (use `**bold**` not `##`, use `>` for block quotes, no headings).

## 3. Implementation Approach Options

### Option A — In-place translation (recommended)

**What**: Edit every Chinese string-literal in `backend/app/services/report_agent.py` directly, in place. No new files.

**Trade-offs**:
- ✅ Matches the precedent set by commits `0806832` (issue #2), `9d1d29b` (issue #3), and `6c2a412` (issue #4) — same file scope, same approach. Reviewer pattern recognition is the lowest possible.
- ✅ Smallest possible diff at the file system level (1 file).
- ✅ No new abstractions, no new files, no dependency churn.
- ❌ Translations are baked in — switching to `es`/`fr`/`pt`/`ru`/`de` still relies on the `get_language_instruction()` postfix to bias the model. (This is also true under the current Chinese-base baseline; not a regression.)
- ❌ The diff is non-trivial (~2680 chars to retranslate plus structural rewriting of the section system prompt). Reviewer must read the prompts side-by-side; line counts shift.

### Option B — Externalize prompts to `/locales/`

**What**: Move all prompt content to `locales/en.json` / `locales/zh.json` and look them up via `t('prompts.report.plan.system')` etc.

**Trade-offs**:
- ✅ Genuinely locale-agnostic prompts; could deliver native-quality Spanish, French, etc. with future translation work.
- ✅ Separates content from code, easing future prompt edits without code review.
- ❌ Diverges from the established pattern of issues #2/#3/#4 — those translated in place. Adopting a new pattern for the same kind of work re-opens architectural design questions and inflates this PR's blast radius.
- ❌ Touches `backend/app/utils/locale.py` (or its caller surface) and `/locales/`, which the spec's R12 and the ticket's "Out of scope" boundary explicitly forbid.
- ❌ Increases JSON-escape-hell risk for the section system prompt's literal `{{` and `}}` braces and triple-quote contents.

### Option C — Hybrid (top-level constants stay externalized; inline strings stay in code)

**What**: Externalize only the seven top-level prompt constants (`PLAN_*`, `SECTION_*`, `CHAT_*`, `TOOL_DESC_*`) to `/locales/`; translate inline f-strings in code in place.

**Trade-offs**:
- ✅ Captures the largest blocks (highest character count) in a localizable way.
- ❌ Two-tier inconsistency: some prompt content in `/locales/`, some in code. Future maintainers must trace both.
- ❌ Same R12 violation as Option B (touches `/locales/`).
- ❌ No precedent in the four sibling i18n efforts already in flight.

## 4. Implementation Complexity & Risk

- **Effort**: **M** (3–5 days for one focused engineer). Larger than the 247-char ticket estimate suggested, but smaller than a typical M because the work is mechanical translation with strict guardrails. Most of the work is high-quality English rewriting of the section system prompt (~950 Chinese chars, the largest block in the file), getting reviewer-acceptable phrasing for the "上帝视角" / "未来预演" framing, and verifying that the no-headings instruction stays semantically equivalent.
- **Risk**: **Low**. Familiar tech, established sibling-spec precedent, clear guardrails (R9–R12), single file, no new dependencies, no API changes. The only non-trivial risk is a regression in `zh` quality if a translated prompt drops a structural cue the Chinese version was carrying — mitigated by preserving every interpolation, the JSON schema, the format-contract instructions, and the `get_language_instruction()` postfix.

## 5. Recommendations for Design Phase

- **Preferred approach**: **Option A — in-place translation in `backend/app/services/report_agent.py`.** Rationale: matches the four sibling i18n PRs, smallest blast radius, respects R12.
- **Key decisions to lock in design**:
    1. Translation of the Chinese **examples inside** `SECTION_SYSTEM_PROMPT_TEMPLATE` (lines 678–703): replace with semantically equivalent English illustrations of the same formatting contract (use `**bold**`, `>` block quotes, no headings).
    2. Treatment of the `"、".join(unused_tools)` separator at line 1454 → switch to `", ".join(...)` for natural English rendering, since the join result is interpolated into now-English `REACT_OBSERVATION_TEMPLATE` and `REACT_UNUSED_TOOLS_HINT`.
    3. Standard English phrasing for the recurring framing terms: `上帝视角` → "all-seeing observer", `未来预演` → "future rehearsal" (or "forecast simulation"), `模拟需求` → "simulation prompt" / "scenario brief", `上下文` → "context". Pick once, use everywhere.
    4. Handling of the `_get_tools_description` leader (1129): English equivalent `"Available tools:"` (verified by precedent in `_build_context` translation in #4).
    5. Treatment of the conflict-handling message (lines 1342–1346): keep the same two-mode contract, but rephrase in English while preserving the literal `<tool_call>` tag and `'Final Answer:'` mentions.
- **Research items to carry forward**:
    1. Confirm that the `Final Answer:` literal is matched case-sensitively in `_generate_section_react` (it is — line 1327: `"Final Answer:" in response`). Translation must keep it byte-for-byte.
    2. Confirm that no tooling outside this file consumes the Chinese fallback outline strings as keys (e.g. translation tables, frontend lookups). Quick grep confirms none do — the strings flow into `Report.title` / `ReportOutline.title` only.
    3. Verify after translation that `python -m py_compile backend/app/services/report_agent.py` passes and that the file's net Chinese-character count drops to the 17 logger lines + docstrings + comments scope (i.e. zero Chinese in any string literal that is sent into an LLM messages array).
