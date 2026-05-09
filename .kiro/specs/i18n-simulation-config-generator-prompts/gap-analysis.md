# Gap Analysis — i18n-simulation-config-generator-prompts

## 1. Current-State Investigation

### Domain assets

- **Target file**: `backend/app/services/simulation_config_generator.py` (~991 lines).
- **Three prompt blocks**:
    - **Block 1** — `_generate_time_config` (lines ~535–595). User prompt at lines 543–586 (f-string), system prompt at line 588, `get_language_instruction()` postfix at 589.
    - **Block 2** — `_generate_event_config` (lines ~646–717). User prompt at lines 676–703, system prompt at 705, `get_language_instruction()` postfix at 706 (already followed by an English `IMPORTANT:` directive on `poster_type`).
    - **Block 3** — `_generate_agent_configs_batch` (lines ~813–906). User prompt at lines 833–867, system prompt at 869, `get_language_instruction()` postfix at 870 (already followed by an English `IMPORTANT:` directive on `stance`).
- **Indirect prompt content** (interpolated via `{context_truncated}`):
    - `_build_context` (lines 381–407) emits Chinese section headings: `## 模拟需求`, `## 实体信息 ({n}个)`, `## 原始文档内容`, truncation marker `(文档已截断)`.
    - `_summarize_entities` (lines 409–432) emits per-type headings `### {entity_type} ({n}个)` and overflow marker `... 还有 {n} 个`.
- **Locale resolution**: `backend/app/utils/locale.py` (`get_locale`, `get_language_instruction`, `t`) resolves locale from `Accept-Language` header in a request context, or thread-local in background threads. `languages.json` exposes `zh`, `en`, `es`, `fr`, `pt`, `ru`, `de` — all but `zh` already use English `llmInstruction` postfixes.

### Counts (verified)

| Region | Chinese chars |
| --- | --- |
| Block 1 user prompt | 417 |
| Block 1 system prompt | 38 |
| Block 2 user prompt | 173 |
| Block 2 system prompt | 27 |
| Block 3 user prompt | 207 |
| Block 3 system prompt | 36 |
| `_build_context` body | 46 |
| `_summarize_entities` body | 29 |
| File total (incl. logger, docstrings, comments) | 2415 |

The ticket's "~247 Chinese characters" undercounts the in-prompt total by ~3.6×. The actual prompt-string count is ~898; with context-builder headings (~75 more), the in-scope total is ~973. Logger lines, docstrings, and comments are out of scope (covered by #6/#7).

### Conventions (extracted)

- Sister specs `i18n-ontology-generator-prompts` (commit `0806832`) and `i18n-oasis-profile-generator-prompts` (commit `9d1d29b`) established the exact pattern: in-place translation; preserve `get_language_instruction()` call sites; preserve all interpolations and the trailing identifier-format `IMPORTANT:` directives; do not touch logger, docstrings, comments, or any other file.
- 4-space indent, snake_case, double quotes for strings, `f"""..."""` for multi-line prompts. Existing Chinese-then-English mix is acceptable in comments/docstrings (steering-tech.md: "preserve both; do not translate one into the other unless asked").
- No linter/formatter — match surrounding style.

### Integration surfaces

- `SimulationConfigGenerator.generate_config(...)` is called from `services/simulation_runner.py` and the simulation API blueprint. The returned `SimulationParameters.to_dict()` is consumed by the OASIS subprocess via `services/simulation_ipc.py`. The JSON payload shape and field semantics must remain unchanged.
- `_build_context` and `_summarize_entities` are private helpers used only inside this file — translating their headings is local-only.
- Locale-switching contract: when locale = `zh`, `get_language_instruction()` returns `请使用中文回答。`; when `en`, `Please respond in English.` — verified.

## 2. Requirement-to-Asset Map

| Requirement | Existing asset | Gap | Tag |
| --- | --- | --- | --- |
| R1 — Block 1 prompt EN | f-string at line 543, system_prompt at 588 | Translate text; preserve `{context_truncated}`, `{max_agents_allowed}`, JSON keys, field constraints, UTC+8 reference example | Missing (translation) |
| R2 — Block 2 prompt EN | f-string at line 676, system_prompt at 705 | Translate text; preserve `{simulation_requirement}`, `{context_truncated}`, `{type_info}`, JSON keys, type-to-author examples, the `IMPORTANT: poster_type ... PascalCase ...` directive | Missing (translation) |
| R3 — Block 3 prompt EN | f-string at line 833, system_prompt at 869 | Translate text; preserve `{simulation_requirement}` and the `json.dumps(entity_list, ensure_ascii=False, indent=2)` interpolation, JSON keys, per-entity-type heuristic ranges, the `IMPORTANT: stance ... supportive/opposing/neutral/observer` directive | Missing (translation) |
| R4 — Locale switching preserved | `get_language_instruction()` calls at lines 589, 706, 870 | None — keep call sites untouched | Constraint |
| R5 — Public API stable | Class/method/dataclass surface | None — text-only changes | Constraint |
| R6 — Default reasoning strings | `_get_default_time_config` line 608, `_generate_event_config` exception at line 716 | Optional translation of two `reasoning` literals; non-empty contract preserved | Optional gap |
| R7 — Context-builder headings EN | `_build_context` 393–406, `_summarize_entities` 422–430 | Translate Chinese section headings inside f-strings; preserve interpolations | Missing (translation) |
| R8 — Step 3 parity | OASIS subprocess + `simulation_ipc.py` | Verification only — the change should not alter `SimulationParameters.to_dict()` shape | Constraint |
| R9 — Out-of-scope guardrails | logger calls (≥17 occurrences), docstrings, comments | None — leave untouched | Constraint |

### Unknown / Research-needed

- **R8 verification feasibility**: Running an end-to-end OASIS simulation requires Neo4j, an LLM key, and a representative seed. In a sandboxed CI-like environment, this is not practical. Defer to a lightweight fixture-based check: (a) lint pass — `python -m py_compile`, (b) zero-Chinese assertion on the three prompt strings via `re.findall(r'[一-鿿]', ...)`, (c) shape parity by constructing a fake `entity_list` and confirming the prompts render to the expected interpolation set without raising. **Research item**: confirm with the user whether a smoke-test run of `services/simulation_runner` is required for PR acceptance, or whether the pattern of #2/#3 (no end-to-end run, reviewer-trust) is acceptable here.

## 3. Implementation Approach Options

### Option A — In-place translation (recommended)

**What**: Edit the six prompt string literals plus the two context-builder helper bodies directly in `simulation_config_generator.py`. No new files.

**Trade-offs**:
- ✅ Matches the precedent set by commits `0806832` (issue #2) and `9d1d29b` (issue #3) — same file, same approach. Reviewer pattern recognition is the lowest possible.
- ✅ Smallest possible diff, smallest possible blast radius.
- ✅ No new abstractions, no new files, no dependency churn.
- ❌ Translations are baked in — switching to `es`/`fr`/`pt`/`ru`/`de` still relies on the `get_language_instruction()` postfix to bias the model. (This is also true under the current Chinese-base baseline; not a regression.)

### Option B — Externalize prompts to `/locales/`

**What**: Move all six prompt strings to `locales/en.json` / `locales/zh.json` and use `t('prompts.simConfig.timeConfig.user')` etc. to look them up.

**Trade-offs**:
- ✅ Genuinely locale-agnostic prompts; richer non-`zh`/`en` support.
- ❌ Departs from the pattern set by #2 and #3 — those translations are in-line. Inconsistency between sister files.
- ❌ Significant new surface area in `/locales/` JSON; brittle keys for f-string substitution (need to encode `{topic}`, `{n_agents}`, `{json.dumps(...)}` in JSON values).
- ❌ Requires either templating-engine choice (Jinja, Python `str.format`) or fragile string concatenation.
- ❌ Out of scope per the ticket's "Out of scope: refactoring prompt structure or output JSON schema" guardrail (the structure is the prompt; moving it to JSON is a refactor).

### Option C — Hybrid: in-place EN translation + introduce a thin prompt-loader for future extraction

**What**: Translate in-place now; also add a no-op `_load_prompt(...)` helper that just returns the literal, with a comment hinting at future externalization.

**Trade-offs**:
- ✅ Sets a future migration path.
- ❌ Adds an indirection that has no caller variance today — premature abstraction. Steering-tech.md explicitly discourages this style.
- ❌ Larger diff, more reviewer surface, no behavioural benefit over Option A.

## 4. Effort & Risk

- **Effort**: **S** (1–3 days). Six string literals plus two helper bodies; no schema, no API, no dependency changes. Sister-spec implementations completed in single commits (`0806832`, `9d1d29b`).
- **Risk**: **Low**. Translation is text-only; the JSON output contract, public API, and `get_language_instruction()` mechanism are all preserved. The only behavioural risk is the LLM emitting different lexical choices for the same fields — this is the *intended* effect (English-flavoured output under `Accept-Language: en`).

## 5. Recommendation for Design Phase

- **Preferred approach**: Option A. Match the sister-spec pattern (`0806832`, `9d1d29b`) for reviewer continuity.
- **Key decisions to lock in design**:
    1. **Wording style**: Mirror the conversational/imperative style of `oasis_profile_generator` and `ontology_generator` post-translation prompts — e.g. `"You are a social-media simulation expert. ..."` rather than direct word-for-word ports of the Chinese.
    2. **Default-path `reasoning` strings (R6)**: Translate the two literals to English ("Default circadian-pattern config (1h per round)" and "Used default config"). Keep them locale-agnostic since they only fire on LLM failure, where locale is moot. This avoids a forever-Chinese leak into a `generation_reasoning` joined with English content.
    3. **Verification harness (R8)**: Use a lightweight fixture-only check (compile, regex for Chinese in prompt strings, render the prompts with stub data and assert interpolation completeness). No end-to-end OASIS run unless the reviewer requests it.
    4. **Wording for the `IMPORTANT:` directives**: Keep the constraint semantics identical; allow light wording polish so the directive flows naturally after a now-English system prompt (e.g. drop the `IMPORTANT:` redundancy if the translated system prompt already encodes the constraint, or move the directive to be inline with the rest of the system prompt).

- **Research items to carry**: confirm verification scope (fixture vs. live) with implementation reviewer; if live is required, the sandboxed environment must have `LLM_API_KEY`, Neo4j, and a seed file available — none of which are guaranteed in this run.
