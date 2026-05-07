# Research & Design Decisions — i18n-ontology-generator-prompts

## Summary

- **Feature**: `i18n-ontology-generator-prompts`
- **Discovery Scope**: Extension (string-literal localization within an existing service)
- **Key Findings**:
    - The `<think>` / markdown-fence stripping logic relied on by the ticket's R5 lives in `backend/app/utils/llm_client.py` (`LLMClient.chat` line 65 and `chat_json` lines 84–87), **not** in `ontology_generator.py`. R5 is therefore satisfied implicitly so long as the call to `self.llm_client.chat_json(...)` is preserved exactly.
    - The locale postfix (`get_language_instruction()`) is sourced from `/locales/languages.json` via `backend/app/utils/locale.py`; the English postfix and Chinese postfix are both already defined and resolved per request via `Accept-Language`. No locale-machinery changes are needed.
    - `_validate_and_process` in the same file enforces the `Person` / `Organization` fallback invariant in code (lines 344–393) regardless of prompt language. This means the prompt translation cannot break the post-validation invariants — the validator is the safety net.
    - The sole production caller is `backend/app/api/graph.py:223–228`, which consumes only the JSON shape (`entity_types`, `edge_types`, `analysis_summary`). It does not introspect prompt language. Stable.

## Research Log

### Locale resolution semantics

- **Context**: R3 requires `zh` to continue producing Chinese descriptions of equivalent quality after the base prompt is translated to English.
- **Sources Consulted**: `backend/app/utils/locale.py`, `/locales/languages.json` (referenced via `_languages` registry).
- **Findings**:
    - `get_locale()` returns the `Accept-Language` header value when in a request context (falling back to `zh`) and a thread-local otherwise.
    - `get_language_instruction()` returns `_languages[locale].llmInstruction`, defaulting to `请使用中文回答。`.
    - The system prompt at line 210 already concatenates `lang_instruction` plus an English directive locking identifier formats. Both stay byte-for-byte unchanged.
- **Implications**: Locale switching survives the translation; no code changes are needed in locale.py. The English base prompt + Chinese postfix is a known-working pattern (R3 acceptance criteria 3 stays valid).

### `<think>` and markdown-fence stripping path

- **Context**: R5 requires preservation of the `<think>` and markdown-fence stripping per `CLAUDE.md` (commit 985f89f).
- **Sources Consulted**: `backend/app/utils/llm_client.py` lines 50–93.
- **Findings**:
    - `LLMClient.chat` strips `<think>...</think>` after every response (line 65).
    - `LLMClient.chat_json` additionally strips ` ```json `, ` ``` `, and trailing fences (lines 84–87) before `json.loads`.
    - `ontology_generator.py` only invokes `chat_json` — it does not perform stripping itself.
- **Implications**: Translating the prompts in `ontology_generator.py` cannot break the stripping logic. The single call to `self.llm_client.chat_json(messages=messages, temperature=0.3, max_tokens=4096)` at lines 217–221 must be preserved verbatim.

### Caller surface and contract

- **Context**: R4 requires zero diff to call sites of these prompts.
- **Sources Consulted**: `backend/app/api/graph.py:223–228`, `backend/app/services/__init__.py`.
- **Findings**:
    - Only one production caller. It uses default constructor and the public `generate(document_texts, simulation_requirement, additional_context)` signature.
    - It reads `entity_types`, `edge_types`, `analysis_summary` from the result.
    - No tests or scripts under `backend/scripts/` reference the module.
- **Implications**: The translation is invisible to callers as long as we hold the public surface constant and continue to produce the same JSON shape (which the validator guarantees).

### Validator safety net

- **Context**: R1 / R5 acceptance: the post-validation invariant (10 entity types, ending in Person/Organization) must hold under both locales after translation.
- **Sources Consulted**: `_validate_and_process` lines 277–398.
- **Findings**:
    - `_to_pascal_case` normalizes entity names regardless of language.
    - `_validate_and_process` enforces `MAX_ENTITY_TYPES = 10`, `MAX_EDGE_TYPES = 10`, deduplicates by name, force-injects `Person` and `Organization` fallbacks if missing, and truncates `description` to 100 chars.
- **Implications**: Even if the LLM under an English prompt deviates from the count or fallback rules, the validator self-heals. Translation cannot break the JSON contract.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| In-place translation | Translate the constant and method strings; preserve all code structure. | Minimal diff; matches sibling-issue pattern (#3, #4, #5); no new abstractions. | English base biases output; mitigated by `get_language_instruction()` postfix and the trailing English directive at line 210. | Selected. |
| Externalize to locale files | Move prompts to `/locales/{en,zh}.json` keyed under `ontology.system_prompt`. | Eliminates cross-locale bias entirely; symmetric prompts. | Out of scope per ticket (#2 is file-internal); inconsistent with how the codebase currently handles LLM prompts; conflicts with #6 i18n track. | Rejected. |
| Hybrid (translate + extract postfix helper) | Translate in place; extract postfix concatenation into a helper. | Slightly cleaner. | Adds refactor outside ticket scope; ticket says "no diff to call sites" and "same function signatures". | Rejected. |

## Design Decisions

### Decision: Translate `ONTOLOGY_SYSTEM_PROMPT` and `_build_user_message` strings in place

- **Context**: Prompts in `ontology_generator.py` are Chinese, biasing model output toward Chinese structure under `Accept-Language: en`. The ticket scopes the work to this single file and excludes refactors.
- **Alternatives Considered**:
    1. Externalize to `/locales/*.json` keyed prompts (rejected; out of scope, inconsistent with codebase).
    2. Hybrid in-place translation + helper extraction (rejected; refactor outside scope).
- **Selected Approach**: Replace the body of `ONTOLOGY_SYSTEM_PROMPT` with an English translation that preserves section structure, JSON template, taxonomy lists, fallback rules, and reserved-name lists. Replace the four Chinese string literals in `_build_user_message` (section headings, additional-context block heading, trailing rules block, truncation notice) with English equivalents while preserving `f"..."` interpolations and the conditional inclusion of additional context.
- **Rationale**: Minimal-surface change; aligns with how sibling i18n issues are scoped; preserves the locale-postfix mechanism, the validator safety net, and all caller contracts.
- **Trade-offs**: An English base prompt biases the model toward English structure. Mitigations: the per-locale `llmInstruction` postfix instructs the model to respond in the requested language; the trailing English directive at line 210 already locks identifier formats; `_validate_and_process` self-heals invariants.
- **Follow-up**: Manual verification under both `en` and `zh` locales: assert valid JSON, assert exactly 10 entity types ending in `Person` and `Organization`, and assert description fields are in the expected language.

### Decision: Preserve all surrounding code unchanged

- **Context**: The ticket forbids changes to call sites and the surrounding code shape.
- **Alternatives Considered**:
    1. Refactor language-locking directive into the locale module (rejected; out of scope and crosses file boundary).
    2. Add a docstring or constant for "prompt version" (rejected; introduces unused state).
- **Selected Approach**: Translation-only diff. No new imports, no new constants, no signature changes, no logger or comment changes (those are #6 and #7 respectively).
- **Rationale**: Smallest possible review surface, fewest possible regression vectors, easiest possible PR to land.
- **Trade-offs**: None of consequence within the ticket's stated scope.
- **Follow-up**: Run the ontology generator round-trip locally; verify zero CJK characters in the patched literals via regex `[一-鿿]`.

## Risks & Mitigations

- **Risk: English prompt produces lower-quality Chinese ontology under `zh` locale** → Mitigation: The `llmInstruction` postfix already steers Chinese output. The trailing English directive at line 210 already locks identifier formats. If quality regresses in practice, future work (issue #6 / a follow-up) can externalize prompts to locale files.
- **Risk: Translator inadvertently changes the JSON template structure or a reserved attribute name** → Mitigation: Acceptance criteria R1.2–R1.6 enumerate the structural constants verbatim. Validator code already enforces `MAX_ENTITY_TYPES`, `MAX_EDGE_TYPES`, and fallback injection independently.
- **Risk: Logger or comment text gets translated as part of the same edit** → Mitigation: The change scope is explicit (R7); reviewer compares the diff against R7 acceptance criteria.

## References

- [.ticket/2.md](../../../.ticket/2.md) — ticket snapshot for issue #2.
- [CLAUDE.md](../../../CLAUDE.md) — project conventions, including reasoning-model output stripping.
- [/locales/languages.json](../../../locales/languages.json) — `llmInstruction` definitions per locale.
- `backend/app/utils/locale.py` — locale resolver implementation.
- `backend/app/utils/llm_client.py` — `<think>` / markdown-fence stripping.
- `backend/app/api/graph.py:223–228` — sole production caller.
