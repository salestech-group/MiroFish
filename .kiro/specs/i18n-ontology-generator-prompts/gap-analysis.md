# Gap Analysis — i18n-ontology-generator-prompts

## 1. Current State Investigation

### Domain assets

- **Subject file**: `backend/app/services/ontology_generator.py` (507 lines).
- **Module-level system prompt**: `ONTOLOGY_SYSTEM_PROMPT` (lines 30–173) — Chinese, ~140 lines of structured prompt content describing task, output format, design guidelines, entity reference list, relationship reference list.
- **User-message builder**: `OntologyGenerator._build_user_message` (lines 231–275) — Chinese section headings, truncation notice, and trailing rules block.
- **Locale postfix call site**: `get_language_instruction()` is invoked at line 209 and concatenated into the system prompt at line 210, alongside an English directive that locks identifier formats.
- **Locale resolver**: `backend/app/utils/locale.py` reads `Accept-Language` from request context, falls back to thread-local for background tasks, and ultimately defaults to `zh`. The English postfix lives in `/locales/languages.json` (`llmInstruction`).
- **LLM client**: `backend/app/utils/llm_client.py:LLMClient.chat_json` performs `<think>` stripping (line 65) and markdown-fence stripping (lines 84–87). This is **outside** `ontology_generator.py`, so the file does not own that logic — it just consumes it. Requirement R5 is satisfied trivially as long as we keep the `chat_json` call unchanged.

### Call sites (consumers)

- `backend/app/api/graph.py:223–228` — the only production caller. Uses `OntologyGenerator()` with no constructor args, calls `.generate(document_texts, simulation_requirement, additional_context)`, and reads `entity_types`, `edge_types`, `analysis_summary` from the result. The shape contract is what matters; language of `description` is not parsed.
- `backend/app/services/__init__.py` — re-exports the class.
- No tests currently reference this module (verified via `Grep ontology_generator|OntologyGenerator|ONTOLOGY_SYSTEM_PROMPT`).

### Conventions

- 4-space indentation, Python 3.11+, snake_case identifiers, type hints where present (matches surrounding file style).
- No linter/formatter — match existing style; existing file uses Chinese inline comments which are *out of scope* (issue #7).
- LLM prompts in this codebase are typically defined as module-level string constants and concatenated with `get_language_instruction()` for locale steering.
- Variable interpolation in user messages uses Python f-strings; the system prompt uses no interpolation today.

### Integration surfaces

- Output JSON schema (entity_types[], edge_types[], analysis_summary) is consumed by `_validate_and_process` (also in this file) and by Graphiti via the project's `ontology` field (set in `graph.py:235`).
- Reserved attribute names list (`name`, `uuid`, `group_id`, `created_at`, `summary`) is asserted in the prompt for the LLM to obey, not enforced by code in this file.
- Entity/edge fallback rules (`Person`, `Organization`) are *both* prompted and enforced by `_validate_and_process` lines 344–393. Code is the safety net; prompt is the steering.

## 2. Requirements → Asset Map

| Requirement | Existing Asset | Gap Type | Notes |
| --- | --- | --- | --- |
| R1 (system prompt EN) | `ONTOLOGY_SYSTEM_PROMPT` constant, lines 30–173 | **Missing — needs translation** | Mechanically a string-literal swap. Must preserve JSON template, taxonomy lists, fallback rules, count constraints, length constraint. |
| R2 (user message EN) | `_build_user_message`, lines 231–275 | **Missing — needs translation** | Three string literals: section headings, additional-context block, trailing rules block, plus the truncation notice. |
| R3 (locale switching) | `get_language_instruction()` call, line 209; trailing English directive, line 210 | **Constraint** | Must be preserved verbatim. No new code needed. |
| R4 (API stability) | `__init__`, `generate`, `generate_python_code`, `_to_pascal_case`, `_validate_and_process`, `MAX_TEXT_LENGTH_FOR_LLM`, `chat_json(temperature=0.3, max_tokens=4096)` | **Constraint** | No changes to signatures or constants. |
| R5 (reasoning-model compat) | `LLMClient.chat_json` (separate file) | **Constraint** | Already external; preservation is automatic if `chat_json` call is untouched. |
| R6 (graph build parity) | Graph build pipeline rooted in `graph.py` | **Verification** — manual run | Requires a sample seed file run; not a code change. |
| R7 (out-of-scope discipline) | Loggers (lines 297, 314, 341), docstrings, comments | **Constraint** | Translator must not touch them. |

### Gaps tagged

- **Missing**: prompt content needs human/operator-quality English translation (R1, R2).
- **Constraint**: signatures, JSON contract, taxonomy names, locale postfix, LLM-call parameters, comments/docstrings/loggers are immutable in this PR (R3, R4, R5, R7).
- **Verification**: locale `zh` and locale `en` end-to-end runs to confirm parity (R3, R6).
- **Research Needed**: none — locale machinery, JSON contract, and LLM client behaviour are all already understood from reading existing code in this repo.

### Complexity signals

- This is **string-literal localization with structural preservation**, not feature work. No data model, API, or workflow changes. No external integrations. No new patterns. The risk is content quality, not technical correctness.

## 3. Implementation Approach Options

### Option A — In-place translation of the existing constant and method (recommended)

Translate `ONTOLOGY_SYSTEM_PROMPT` and the three Chinese string literals inside `_build_user_message` directly. No new files, no new abstractions.

- ✅ Minimal diff, easy to review, matches the file's existing style.
- ✅ Preserves the locale-postfix mechanism unchanged (the postfix is what currently steers `zh` output and will continue to do so under an English base prompt).
- ✅ Aligns with how the analogous i18n issues for sibling files (#3, #4, #5) are framed in the epic.
- ❌ The English base prompt biases the model toward English structure for Chinese locale runs; mitigated by the existing trailing English directive that locks identifier formats and by the per-locale `llmInstruction` postfix.

### Option B — Externalize prompts to locale files

Move `ONTOLOGY_SYSTEM_PROMPT` content to `/locales/en.json` and `/locales/zh.json` and resolve at runtime via `t("ontology.system_prompt")`.

- ✅ Provides parallel zh/en prompts, eliminating cross-locale bias entirely.
- ❌ Out of scope per issue #2 — externalizing log messages is issue #6 and a similar pattern would expand this PR's surface beyond the ticket. Adopting it here would also risk merge conflicts with #6.
- ❌ Adds runtime indirection (file IO, key lookups) for a string that has not been externalized in any other prompt module. Inconsistent with current convention until a future i18n-prompt initiative.
- ❌ Requires authoring high-quality Chinese prompts as locale data, which is exactly what's being moved away from for English-bias reasons.

### Option C — Hybrid: translate in place, parameterize the locale postfix

Translate in place per Option A, and additionally factor `system_prompt = f"{ONTOLOGY_SYSTEM_PROMPT}\n\n{lang_instruction}\n..."` into a small helper.

- ✅ Slightly cleaner.
- ❌ Refactor outside the ticket's scope. Issue #2 is explicit: "No diff to call sites of these prompts — same function signatures and return shapes." A helper would change a private code shape unnecessarily.

## 4. Effort & Risk

- **Effort: S (1 day)** — string-literal translation with structural preservation. The bulk of the time is producing accurate, terminology-faithful English prose for the system prompt's design guidelines.
- **Risk: Low** — well-bounded change, no API surface impact, JSON contract preserved by validator code that already exists, no new dependencies. The single residual risk is qualitative (English prompt failing to elicit equivalent ontology quality), mitigated by:
    - The trailing English directive at line 210 already locks identifier formats.
    - `_validate_and_process` enforces fallback `Person` / `Organization` types in code regardless of prompt.
    - Manual verification under both `en` and `zh` locales is part of acceptance.

## 5. Recommendations for Design Phase

- **Preferred approach**: Option A — translate `ONTOLOGY_SYSTEM_PROMPT` and the four user-message string fragments in place. Preserve every code structure around them.
- **Key decisions for design**:
    1. Translation style for the system prompt: faithful, terminology-preserving English. Maintain the same section structure (`## Core Task Background`, `## Output Format`, `## Design Guidelines`, `## Entity Type Reference`, `## Relationship Type Reference`). Keep all Chinese-language gloss in the entity reference list intact in spirit but rendered in English (e.g. `Student: 学生` becomes `Student: a student`).
    2. Heading translations for user message: `## 模拟需求` → `## Simulation Requirement`; `## 文档内容` → `## Document Content`; `## 额外说明` → `## Additional Context`.
    3. Truncation notice: render in English, preserve both numeric interpolations (`{original_length}`, `{self.MAX_TEXT_LENGTH_FOR_LLM}`).
    4. Trailing rules block: render in English, preserve the five-rule enumeration semantics verbatim, and keep the call to action ("Based on the content above ...").
    5. The trailing English directive at line 210 (`IMPORTANT: Entity type names MUST be in English PascalCase ...`) is already English; leave it byte-for-byte unchanged.
    6. No code structure changes. No new imports. No changes to signatures, constants, or the `chat_json` call.
- **Verification plan for design**:
    - Static check: zero CJK characters in any prompt string literal post-edit (regex `[一-鿿]` over the patched constant and the patched method body).
    - Runtime check: under `LLM_API_KEY` configured to a test provider, run a small `OntologyGenerator().generate(...)` round-trip with locale `en` and locale `zh`, asserting JSON validity and the 10/Person+Organization invariant.
    - End-to-end check: run the Step 1 graph build on a representative seed file with locale `en`; compare node and edge counts to a recent `zh` baseline within operator tolerance.
- **Research items**: none open. All adjacent systems (locale resolver, LLM client, validator, graph build pipeline) are read-only and behave deterministically with respect to the changes proposed.
