# Research & Design Decisions — i18n-simulation-config-generator-prompts

## Summary

- **Feature**: `i18n-simulation-config-generator-prompts`
- **Discovery Scope**: Extension (in-place translation of three prompt blocks plus two helpers in a single file)
- **Key Findings**:
    - Two near-identical sister specs (#2, #3) have already established an in-place translation pattern. Following Option A (in-place) keeps reviewer continuity and matches commits `0806832` and `9d1d29b`.
    - The actual in-prompt Chinese-character footprint (~898 chars across six string literals + ~75 in two context-builder helpers ≈ 973) is ~3.6× the ticket's "~247 chars" estimate. The ticket undercounted by ignoring system prompts and the `_build_context`/`_summarize_entities` headings that flow into prompts via `{context_truncated}`.
    - Locale-switching contract (`Accept-Language` → `get_locale()` → `get_language_instruction()`) is unaffected by base-prompt translation; `zh` postfix is `请使用中文回答。`, all other supported locales already use English postfixes. No change to `backend/app/utils/locale.py` or `/locales/*.json` needed.

## Research Log

### Topic: Sister-spec implementation patterns (#2, #3)

- **Context**: Issue #4 explicitly references the same rationale as #5 ("translate prompts even though `get_language_instruction()` exists") and is one of a family of i18n issues. Sister specs already shipped — what pattern did they use?
- **Sources Consulted**: `git show 0806832` (issue #2, ontology_generator), `git show 9d1d29b` (issue #3, oasis_profile_generator), `.kiro/specs/i18n-ontology-generator-prompts/requirements.md`, `.kiro/specs/i18n-oasis-profile-generator-prompts/`.
- **Findings**:
    - Both sister specs translated in-place: edit prompt string literals, leave `get_language_instruction()` postfix call sites intact, leave logger/docstrings/comments alone (those are owned by #6/#7).
    - Both preserved the trailing English `IMPORTANT:` directives that lock identifier formats (`PascalCase`, `snake_case`, `UPPER_SNAKE_CASE`).
    - Both kept module/class docstrings in Chinese (out of scope per #7).
- **Implications**: Use the same pattern. No deviation, no new abstractions, no externalization.

### Topic: Locale resolution & non-`zh` postfix verification

- **Context**: R4 requires that locale switching to `zh` continues to produce Chinese output, and to other locales continues to produce locale-appropriate output. Verify that `get_language_instruction()` returns useful postfixes for all supported locales.
- **Sources Consulted**: `backend/app/utils/locale.py:66-69`, `locales/languages.json`.
- **Findings**:
    - `languages.json` has 7 locales: `zh`, `en`, `es`, `fr`, `pt`, `ru`, `de`. Each provides a `llmInstruction` postfix in its native language (e.g. `de` → `Bitte antworten Sie auf Deutsch.`).
    - `get_locale()` reads `Accept-Language` header in request context, or thread-local in background threads; falls back to `zh`. Confirms the existing fallback semantics.
- **Implications**: Translating the base prompts to English does not regress non-English support — every other locale already gets a native postfix that biases the model away from English. (Today, every other locale fights *against* a Chinese base prompt. After this change, `zh` is the only locale fighting the base.)

### Topic: OASIS subprocess JSON contract

- **Context**: R8 requires Step 3 parity. What does the OASIS subprocess actually consume from `SimulationParameters.to_dict()`?
- **Sources Consulted**: `backend/app/services/simulation_config_generator.py:176-197` (`SimulationParameters.to_dict`), grep for `simulation_ipc` consumers.
- **Findings**:
    - `SimulationParameters.to_dict()` returns a flat dict with `simulation_id`, `project_id`, `graph_id`, `simulation_requirement`, `time_config` (dict), `agent_configs` (list of dicts), `event_config` (dict with `initial_posts`, `scheduled_events`, `hot_topics`, `narrative_direction`), `twitter_config`, `reddit_config`, `llm_model`, `llm_base_url`, `generated_at`, `generation_reasoning`.
    - Field types and shapes are entirely structural — no language-conditioned parsing exists in the consumer side.
- **Implications**: Translation only changes the **content** of natural-language string fields; **shape** is untouched. Step 3 parity is a verification concern, not a design concern.

### Topic: Verification depth — fixture vs. live

- **Context**: R8 acceptance is "OASIS subprocess starts cleanly and runs at least one round." Sandboxed run unlikely to have the live infra (Neo4j, LLM key, OASIS workers).
- **Sources Consulted**: Sister-spec PRs (no live e2e captured in their commit messages or test additions); steering-tech.md (test posture: "coverage is intentionally minimal — don't add a heavy test harness without discussing scope").
- **Findings**:
    - Sister specs shipped without live e2e tests. The verification was static: zero-Chinese assertion in the touched strings, plus reviewer trust on the JSON shape preservation.
    - The repo intentionally avoids heavy test scaffolding.
- **Implications**: Use a fixture-based static verification:
    1. `python -m py_compile backend/app/services/simulation_config_generator.py` (compile pass).
    2. Regex `[一-鿿]` over the six prompt-string literals and the two context-builder f-strings — must yield zero matches.
    3. Construct stub entities and call `_build_context`, `_summarize_entities`, plus the three prompt-rendering paths (mocking the LLM client) — confirm every expected interpolation is present in the rendered prompt and no `KeyError` on missing variables.
- This avoids depending on live infra while still catching every regression mode the requirements care about.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A — In-place translation | Edit string literals directly in `simulation_config_generator.py` | Matches sister-spec precedent (#2, #3); minimum diff; minimum risk | Translations baked in; harder to localize beyond `zh`/`en` later (but `get_language_instruction()` postfix already handles that) | **Selected** |
| B — Externalize prompts to `/locales/` | Move prompts into JSON locale files | Genuine multi-locale prompt support | Departs from sister-spec pattern; out-of-scope per ticket guardrails ("no refactoring"); requires templating choice; brittle for `json.dumps`-shaped interpolations | Rejected |
| C — Hybrid: in-place + indirection helper | Translate in-place, add a thin `_load_prompt()` indirection for future externalization | Sets future migration path | Premature abstraction; larger diff; no caller variance today | Rejected |

## Design Decisions

### Decision: Adopt Option A (in-place translation)

- **Context**: How to translate three Chinese prompt blocks plus two context-builder helpers without breaking locale switching, public API, or downstream OASIS consumption.
- **Alternatives Considered**:
    1. Option A — In-place translation (sister-spec pattern).
    2. Option B — Externalize to `/locales/`.
    3. Option C — Hybrid with a no-op indirection.
- **Selected Approach**: Option A. Translate the six prompt literals and the two context-builder helper bodies directly. Leave `get_language_instruction()` call sites and the trailing English `IMPORTANT:` directives intact (light wording polish allowed for grammatical flow but constraint semantics unchanged). Logger calls, docstrings, comments untouched.
- **Rationale**: Pattern-consistent with #2 and #3, minimum-risk text edit, preserves all behavioural contracts, and produces the smallest reviewable diff.
- **Trade-offs**: Future locales beyond `en`/`zh` continue to rely on the `get_language_instruction()` postfix to bias output — same as the current state, not a regression.
- **Follow-up**: Confirm via fixture that prompt rendering produces no `KeyError` and zero Chinese in the targeted regions; reviewer self-check on prompt wording quality.

### Decision: Translate context-builder section headings (R7)

- **Context**: `_build_context` and `_summarize_entities` emit Chinese section headings (`## 模拟需求`, `### {entity_type} ({n}个)`, etc.) that are interpolated into all three prompts via `{context_truncated}`. Leaving them Chinese re-introduces the bias the prompt translations are designed to remove.
- **Alternatives Considered**:
    1. Translate only the six prompt literals (literal interpretation of ticket scope).
    2. Translate prompts + context-builder headings (functional interpretation of ticket goal).
- **Selected Approach**: Option 2 — translate context-builder headings as part of this spec. The headings have no public surface; they are internal to prompt assembly.
- **Rationale**: Acceptance criterion 1 of issue #4 (no Chinese characters in any prompt string literal) is interpreted strictly only at the prompt-block level by the literal text of the ticket — but the spirit of the ticket (English output under `Accept-Language: en`) demands the helpers be translated too. Sister specs (#2, #3) made the same call for their analogous helpers.
- **Trade-offs**: Slightly larger diff than the literal ticket scope; offset by avoiding a follow-up "we missed this" issue.
- **Follow-up**: Note in the PR body that R7 expands literal ticket scope by ~75 chars across two helpers, with the rationale above.

### Decision: Translate the two default-path `reasoning` strings (R6)

- **Context**: `_get_default_time_config` emits `"使用默认中国人作息配置（每轮1小时）"` as a `reasoning` value, and the `_generate_event_config` exception path emits `"使用默认配置"`. These are static literals (not LLM output) and are joined into the user-visible `generation_reasoning`.
- **Alternatives Considered**:
    1. Leave both Chinese (literal scope per #6/#7 split).
    2. Translate both to locale-agnostic English.
    3. Wire both through `t('progress.*')` for full i18n.
- **Selected Approach**: Option 2 — translate to locale-agnostic English literals (`"Default circadian-pattern config (1h per round)"` and `"Used default config"`). They are not log lines (those are #6's domain) — they are user-facing string values returned in a JSON payload. Wiring them through `t()` is a refactor and likely belongs to a future broader i18n pass.
- **Rationale**: Avoids a forever-Chinese leak into a `generation_reasoning` joined with otherwise-English content. Locale-agnostic English is the lowest-overhead solution for a fallback-only path.
- **Trade-offs**: Under `zh`, these two strings appear in English in `generation_reasoning` only on the failure path. Acceptable: the failure path is rare and the rest of the joined `reasoning` already mixes label-translated and LLM-output content.
- **Follow-up**: None.

### Decision: Light wording polish of the `IMPORTANT:` directive lines

- **Context**: Lines 706 and 870 currently glue an English `IMPORTANT:` directive onto a Chinese system prompt with `f"{system_prompt}\n\n{get_language_instruction()}\nIMPORTANT: ..."`. After translating the system prompts to English, the `IMPORTANT:` directive can either remain verbatim or be merged into the system prompt for cleaner flow.
- **Alternatives Considered**:
    1. Keep the directive lines exactly as-is (preserves byte-for-byte behaviour).
    2. Lightly polish wording for grammatical flow with the now-English system prompt.
    3. Merge the directive into the system prompt body.
- **Selected Approach**: Option 1 with a small caveat — keep the directives verbatim, including the existing English wording. The constraint semantics (PascalCase `poster_type`; `stance` ∈ {`supportive`, `opposing`, `neutral`, `observer`}) MUST not change. If a reviewer requests Option 2, the wording polish can be applied with the constraint semantics held constant.
- **Rationale**: Minimum-diff principle. The directives already work; touching them adds risk for no functional gain.
- **Trade-offs**: Slight grammatical awkwardness from concatenating an English system prompt with another English directive. Cosmetic only.
- **Follow-up**: None unless a reviewer flags wording.

## Risks & Mitigations

- **Risk**: Reviewer interprets ticket scope strictly and rejects the context-builder translation (R7). **Mitigation**: Document the rationale explicitly in the PR body and reference the sister-spec precedent. If rejected, revert just the helper changes — they are isolated edits.
- **Risk**: LLM produces lower-quality output for `zh` locale because the base prompt is now English (model has to do more work to honour the `请使用中文回答。` postfix). **Mitigation**: Sister specs (#2, #3) shipped without observed regressions. If a regression is reported, the fix is to expand the postfix's locale instruction, not to revert this spec.
- **Risk**: Light wording polish of the `IMPORTANT:` directive accidentally drops the `'supportive'/'opposing'/'neutral'/'observer'` enum or the PascalCase requirement, causing the OASIS subprocess to reject `stance` or `poster_type` values. **Mitigation**: R3.7 and R2.6 explicitly forbid changing constraint semantics; the implementation will keep these directives as verbatim string literals.
- **Risk**: A new prompt-time interpolation is missed during translation, producing a `KeyError` at runtime. **Mitigation**: Fixture-based render check (Decision: verification depth) will catch this before commit.

## References

- Sister-spec implementations:
    - `git show 0806832` — `feat(i18n): translate ontology_generator prompts to english` (#2).
    - `git show 9d1d29b` — `feat(i18n): translate oasis_profile_generator prompts to english` (#3).
- Sister-spec planning artefacts: `.kiro/specs/i18n-ontology-generator-prompts/`, `.kiro/specs/i18n-oasis-profile-generator-prompts/`.
- Locale layer: `backend/app/utils/locale.py`, `locales/languages.json`, `locales/en.json`, `locales/zh.json`.
- Steering: `.kiro/steering/tech.md` (i18n notes; "no enforced linter or formatter; preserve mixed Chinese/English in comments unless asked"); `.kiro/steering/structure.md`.
