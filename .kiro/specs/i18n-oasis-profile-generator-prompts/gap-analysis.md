# Gap Analysis — i18n-oasis-profile-generator-prompts

## 1. Current State Investigation

### Domain assets

- **Subject file**: `backend/app/services/oasis_profile_generator.py` (1196 lines).
- **System prompt builder**: `OasisProfileGenerator._get_system_prompt` (lines 662–665). The `base_prompt` literal is Chinese: `"你是社交媒体用户画像生成专家。生成详细、真实的人设用于舆论模拟,最大程度还原已有现实情况。必须返回有效的JSON格式，所有字符串值不能包含未转义的换行符。"`. It is concatenated with `get_language_instruction()` and returned. The `is_individual` argument is currently unused in the prompt body (the system prompt is identical for individual and group personas) but the parameter is preserved on the public-helper signature.
- **Individual user-message builder**: `OasisProfileGenerator._build_individual_persona_prompt` (lines 667–714). One Chinese f-string literal of ~700 characters covering instruction headings, an 8-field schema description, a 7-bullet `persona` sub-schema, and a 6-rule "重要" trailing block. Inline `{get_language_instruction()}` interpolation appears at line 711 with a Chinese gloss `(gender字段必须用英文male/female)` after it.
- **Group/institution user-message builder**: `OasisProfileGenerator._build_group_persona_prompt` (lines 716–762). One Chinese f-string literal of ~700 characters, structurally parallel to the individual builder, with `age=30` and `gender="other"` constants embedded as instructions. Inline `{get_language_instruction()}` interpolation appears at line 760 with a Chinese gloss `(gender字段必须用英文"other")` after it.
- **Context builder**: `OasisProfileGenerator._build_entity_context` (lines 404–477). Emits Chinese section headings (`### 实体属性`, `### 相关事实和关系`, `### 关联实体信息`, `### Zep检索到的事实信息`, `### Zep检索到的相关节点`) and Chinese inline placeholders (`(相关实体)` on either side of the `--[edge_name]-->` arrow when a fact is missing). The output of this method is interpolated as `{context_str}` into both prompt builders.
- **Zep search context strings**: `_search_zep_for_entity` (lines 278–402) emits two Chinese inline labels into `results["context"]` — `事实信息:\n` and `相关实体:\n` — and a Chinese inline label inside the iteration over node summaries: `f"相关实体: {node_name}"`.
- **Empty-state fallbacks inside the prompt builders**: `attrs_str = json.dumps(...) if entity_attributes else "无"` and `context_str = context[:3000] if context else "无额外上下文"` — both Chinese, both interpolated into the prompts.
- **Locale postfix call site**: `get_language_instruction()` is invoked at three sites: `_get_system_prompt` (line 665), `_build_individual_persona_prompt` (line 711), `_build_group_persona_prompt` (line 760). All three must be preserved.
- **Locale resolver**: `backend/app/utils/locale.py` — same as for issue #2 — reads `Accept-Language`, falls back to thread-local for background tasks, defaults to `zh`. The English postfix lives in `/locales/languages.json` under `llmInstruction`. The thread-local locale is propagated into worker threads at line 914 via `set_locale(current_locale)`.
- **LLM client**: this module uses the OpenAI SDK directly (`self.client.chat.completions.create(...)`) — it does **not** route through `LLMClient.chat_json`. The truncated-JSON repair logic (`_fix_truncated_json`, `_try_fix_json`) is **owned by this module** (lines 573–660). That distinction matters for Requirement 7: provider-output stripping for reasoning models is handled here, in this file, not delegated.
- **Three Chinese fallback persona strings**: `f"{entity_name}是一个{entity_type}。"` appears at lines 547, 644, 659 (the JSON-repair fallback path inside `_generate_profile_with_llm` and `_try_fix_json`). Per the requirements, these are **out of scope** for issue #3 (they are output values, not prompt strings, and changing them touches the persona-generation flow).

### Call sites (consumers)

- `backend/app/services/__init__.py` — re-exports `OasisProfileGenerator` and `OasisAgentProfile`.
- `backend/app/services/simulation_runner.py` — instantiates `OasisProfileGenerator()` and calls `generate_profiles_from_entities(...)` for Step 2. Uses the JSON/CSV files written by `save_profiles`.
- `backend/scripts/test_profile_format.py` — instantiates a Profile manually and asserts `_save_twitter_csv` and `_save_reddit_json` produce files with the expected schema. Does **not** exercise prompts. (Note: the script asserts a `realname` field that the actual code emits as `name` — that mismatch is a pre-existing project oddity, not within scope here.)
- No tests currently exercise the prompt-generation path directly.

### Conventions

- 4-space indentation, Python 3.11+, snake_case identifiers, type hints sparsely used (existing file mixes typed and untyped methods — match local style).
- No linter/formatter — match existing style. The existing file uses Chinese inline comments and Chinese docstrings, both *out of scope* (issue #7).
- LLM prompts in this codebase are typically defined inline as f-strings inside builder methods (in contrast to `ontology_generator.py` which uses a module-level constant for the system prompt). Match the local pattern: keep the system prompt in `_get_system_prompt` and the user prompts inline in their builders.
- The single-string `base_prompt` in `_get_system_prompt` is a local variable, not a module-level constant.

### Integration surfaces

- LLM JSON output keys consumed downstream: `bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`. These are accessed via `result.get("bio", default)` etc. inside `generate_profile_from_entity` (lines 252–263).
- The `gender` enum (`male`, `female`, `other`) is enforced by `_normalize_gender` (lines 1111–1134) downstream of generation. Code is the safety net; prompt is the steering.
- The `MBTI_TYPES`, `COUNTRIES`, `INDIVIDUAL_ENTITY_TYPES`, `GROUP_ENTITY_TYPES` lists are class-level and untouched by this work.
- The `country: "中国"` defaults in `_generate_profile_rule_based` and `_save_reddit_json` are output-value defaults, not prompt content. Out of scope.
- The `t('progress.zepSearchQuery', name=entity_name)` and `t('progress.profileGenerated', ...)` calls source from `/locales/*.json` and are owned by issue #6.

## 2. Requirements → Asset Map

| Requirement | Existing Asset | Gap Type | Notes |
| --- | --- | --- | --- |
| R1 (system prompt EN) | `_get_system_prompt`, lines 662–665 | **Missing — needs translation** | Single Chinese string-literal swap. Preserve `get_language_instruction()` postfix and `is_individual` parameter. |
| R2 (individual user prompt EN) | `_build_individual_persona_prompt`, lines 667–714 | **Missing — needs translation** | One ~700-char f-string. Preserve all `{var}` interpolations (`entity_name`, `entity_type`, `entity_summary`, `attrs_str`, `context_str`, `get_language_instruction()`). Locale-neutralize the country instruction. Preserve gender enum, JSON keys, and the field-by-field schema semantics. |
| R3 (group user prompt EN) | `_build_group_persona_prompt`, lines 716–762 | **Missing — needs translation** | Same shape as R2. Preserve `age=30` and `gender="other"` constants in the prompt instructions. |
| R4 (context strings EN) | `_build_entity_context` lines 422/443/463/472/475; `_search_zep_for_entity` lines 384/390/392 | **Missing — needs translation** | Five `### …` headings, two Chinese inline labels in Zep search results, one `相关实体: {node_name}` template, two `(相关实体)` placeholders, and the `"无"` / `"无额外上下文"` fallbacks inside the prompt builders. |
| R5 (locale switching) | `get_language_instruction()` calls at lines 665, 711, 760; `set_locale(current_locale)` at line 914; `t(...)` at lines 309, 1015 | **Constraint** | Must be preserved verbatim. No new code needed. |
| R6 (API stability) | All `OasisProfileGenerator` and `OasisAgentProfile` public/private signatures, dataclass fields, retry/temperature schedule | **Constraint** | No changes to signatures or constants. |
| R7 (reasoning-model compat) | `_fix_truncated_json` (lines 573–594) and `_try_fix_json` (lines 596–660) — **owned by this file** | **Constraint** | No changes to either helper. They operate on byte-level JSON repair and are language-agnostic. |
| R8 (Step 2 parity) | `_save_reddit_json`, `_save_twitter_csv`, OASIS subprocess | **Verification** — runtime spot-check | Schema is preserved by R6; the verification asserts the OASIS subprocess accepts the produced files. |
| R9 (out-of-scope discipline) | Loggers, `print`s, docstrings, comments, fallback persona strings, `_normalize_gender` Chinese keys, lists | **Constraint** | Translator must not touch them. |

### Gaps tagged

- **Missing**: prompt content needs human/operator-quality English translation (R1, R2, R3, R4).
- **Constraint**: signatures, JSON contract, gender enum, locale postfix, retry/temperature schedule, normalize-gender map, comments/docstrings/loggers, lists, fallback persona strings are immutable in this PR (R5, R6, R7, R9).
- **Verification**: locale `zh` and locale `en` end-to-end runs to confirm parity (R5, R8); `backend/scripts/test_profile_format.py` continues to pass (R8).
- **Research Needed**: none — locale machinery, JSON contract, OASIS profile schema, and the (existing) sibling translation pattern from `i18n-ontology-generator-prompts` are all already understood.

### Complexity signals

- This is **string-literal localization with structural preservation**, parallel to the just-merged `i18n-ontology-generator-prompts` work (PR #14, commit `0806832`). No data model, API, or workflow changes. No external integrations. No new patterns. No new dependencies. The risk is content quality, not technical correctness.

## 3. Implementation Approach Options

### Option A — In-place translation of the existing builders (recommended)

Translate the four affected functions' Chinese string literals directly:

- `_get_system_prompt` — swap the `base_prompt` literal to English.
- `_build_individual_persona_prompt` — swap the f-string body to English; locale-neutralize the country line; translate the gloss after `{get_language_instruction()}`.
- `_build_group_persona_prompt` — same treatment as the individual builder, preserving `age=30` and `gender="other"` constants.
- `_build_entity_context` and `_search_zep_for_entity` — swap the `###` section headings and the inline labels (`事实信息`, `相关实体`, `(相关实体)`) to English. Swap `"无"` and `"无额外上下文"` to English equivalents (`"None"` / `"No additional context"`).

No new files, no new abstractions.

- ✅ Minimal diff, easy to review, matches the file's existing style.
- ✅ Preserves the locale-postfix mechanism unchanged. Under `zh` locale, `get_language_instruction()` returns `请使用中文回答。` and persona content remains Chinese — the small set of English structural labels (section headings inside the context block, "重要" rules block) is not visible to the persona output, only to the LLM as instruction context.
- ✅ Consistent with the just-merged sibling spec `i18n-ontology-generator-prompts` (commit `0806832`). The `t()` calls for `progress.zepSearchQuery` and `progress.profileGenerated` are already locale-aware and remain so.
- ❌ The English base prompt biases the model toward English structure for `zh` locale runs; mitigated by `get_language_instruction()` at three sites (system prompt + each user prompt) and by the explicit gender-enum gloss after the postfix.

### Option B — Externalize prompts to locale files

Move the prompt content to `/locales/en.json` and `/locales/zh.json` and resolve via `t("oasis_profile.system_prompt")`, `t("oasis_profile.individual_user_prompt")`, etc.

- ✅ Provides parallel zh/en prompts, eliminating cross-locale bias entirely.
- ❌ Out of scope per issue #3 — externalizing log messages is issue #6 and a similar pattern would expand this PR's surface beyond the ticket. Adopting it here would also conflict with the just-merged sibling pattern, which kept prompts inline.
- ❌ Adds runtime indirection (file IO, key lookups) for strings that have not been externalized in any other prompt module. Inconsistent with current convention.
- ❌ Requires authoring high-quality Chinese prompts as locale data, which is exactly what the i18n initiative is moving away from for English-bias reasons.

### Option C — Hybrid: translate in place plus a small static guard test

Translate in place per Option A, **and** add a static AST-based guard at `backend/scripts/test_oasis_profile_prompts_no_cjk.py` that asserts zero CJK characters in:

- the `base_prompt` local-variable literal in `_get_system_prompt`,
- every static string fragment inside the f-strings of `_build_individual_persona_prompt` and `_build_group_persona_prompt`,
- the targeted heading literals in `_build_entity_context` and `_search_zep_for_entity` (the in-scope ones — not the Chinese log strings).

This mirrors the pattern already established by `backend/scripts/test_ontology_prompts_no_cjk.py` (sibling test for issue #2).

- ✅ Adds a regression guard at low cost (~80 lines, AST-only, no Flask import chain), matching the project's existing test pattern for sibling i18n issue #2.
- ✅ Provides automated verification of Acceptance Criterion "No Chinese characters in any prompt string literal", reducing reliance on visual review.
- ✅ Skirts complexity: AST walk filters by function name, so logger calls and comments (out of scope per #6/#7) are untouched.
- ❌ Adds a script to maintain. Mitigated by the precedent: the sibling spec adopted the same approach and the script is small and self-contained.

## 4. Effort & Risk

- **Effort: S (1 day)** — string-literal translation with structural preservation. Three prompt builders + one context builder + one Zep search helper. The bulk of the time is producing accurate, terminology-faithful English prose for the persona schema bullets in `_build_individual_persona_prompt` and `_build_group_persona_prompt`. Adding the static guard test is ~30 minutes given the sibling template.
- **Risk: Low** — well-bounded change, no API surface impact, JSON output keys preserved, gender enum preserved, no new dependencies. The single residual risk is qualitative (English prompt failing to elicit equivalent persona quality under `zh` locale), mitigated by:
    - `get_language_instruction()` is called at three sites (system + each user prompt), each appending the per-locale postfix.
    - The explicit gender-enum gloss after each postfix locks the gender output to the OASIS enum regardless of language.
    - `_normalize_gender` is the code-level safety net for gender (preserves `zh` mapping for Chinese gender words).
    - Manual verification under both `en` and `zh` locales is part of acceptance.

## 5. Recommendations for Design Phase

- **Preferred approach**: **Option C** — translate the four affected functions in place per Option A, **and** add `backend/scripts/test_oasis_profile_prompts_no_cjk.py` mirroring `backend/scripts/test_ontology_prompts_no_cjk.py`. This matches the just-merged sibling pattern from issue #2 and adds an automated regression guard for the "no CJK in prompt strings" acceptance criterion.
- **Key decisions for design**:
    1. Translation style for the system prompt: faithful, terminology-preserving English. Phrasing: "You are a social-media user-profile generation expert. Produce detailed, realistic personas for opinion-simulation, faithfully reflecting the existing real-world situation. You must return valid JSON; string values must not contain unescaped newline characters."
    2. Translation style for the persona schema bullets: render the seven persona sub-categories as English bullets that map 1-to-1 to the Chinese sub-categories (basic information, background, personality, social-media behavior, stance, distinctive traits, personal/institutional memory). Preserve the implicit per-bullet semantics.
    3. Country instruction: replace `国家（使用中文，如"中国"）` with `country` (no language qualifier). Let `get_language_instruction()` drive the language. This locale-neutralizes the field per Requirements R2.7 and R3.7.
    4. The "重要" (Important) trailing block: render as `Important:` in English. Preserve the rule semantics: string-or-number values, no unescaped newlines, single-paragraph persona, gender enum constraint, content consistency, integer age for individuals, fixed `age=30` and `gender="other"` for institutions.
    5. Inline gloss after `{get_language_instruction()}`: render in English, e.g., `(the gender field must use the English value male or female)` and `(the gender field must use the English value "other")`.
    6. Heading translations for context: `### 实体属性` → `### Entity Attributes`; `### 相关事实和关系` → `### Related Facts and Relationships`; `### 关联实体信息` → `### Connected Entities`; `### Zep检索到的事实信息` → `### Zep-Retrieved Facts`; `### Zep检索到的相关节点` → `### Zep-Retrieved Related Nodes`. Inline labels: `事实信息` → `Facts`; `相关实体` → `Related entities` (heading) / `Related entity` (single); `(相关实体)` → `(related entity)`. Empty-state fallbacks: `"无"` → `"None"`; `"无额外上下文"` → `"No additional context"`.
    7. No code structure changes. No new imports. No changes to public/private signatures, dataclass fields, retry/temperature schedule, OpenAI SDK call shape, or the JSON-repair helpers.
    8. Static guard test: AST-based, walks `_get_system_prompt`, `_build_individual_persona_prompt`, `_build_group_persona_prompt`, `_build_entity_context`, and (the in-scope literals only of) `_search_zep_for_entity`. Uses the same `[一-鿿]` regex from `test_ontology_prompts_no_cjk.py`. Excludes docstrings and (in `_search_zep_for_entity`) the logger-call literals via function-scope filtering.
- **Verification plan for design**:
    - Static check: zero CJK characters in the targeted prompt-bearing literals (regex `[一-鿿]`), enforced by the new `test_oasis_profile_prompts_no_cjk.py` script.
    - Existing test: `uv run python backend/scripts/test_profile_format.py` continues to pass.
    - Runtime check: under `LLM_API_KEY` configured to a test provider, run a small `generate_profile_from_entity(...)` round-trip with locale `en` and locale `zh`, asserting JSON validity and `gender ∈ {male, female, other}`.
    - End-to-end check: run Step 2 (env setup) on a representative project with locale `en`; assert the produced Reddit JSON / Twitter CSV is accepted by the OASIS subprocess (this is the Step 3 simulation start-up).
- **Research items**: none open. All adjacent systems (locale resolver, OpenAI SDK, JSON-repair helpers, OASIS profile schema, test_profile_format.py) are read-only and behave deterministically with respect to the changes proposed.
