# Requirements Document

## Introduction

This specification covers the English translation of the prompt strings in `backend/app/services/ontology_generator.py`. The file produces the project ontology (entity types, relationship types, schema commentary) that drives the Graphiti graph build (Step 1 of the MiroFish pipeline). Today, the system prompt and user-message templates are written in Chinese; the language is steered at runtime by appending `get_language_instruction()` to the system message. While that postfix instructs the model *which* language to respond in, the base-prompt language biases the model's structural and lexical output. As a result, ontology descriptions, reasoning, and schema commentary skew Chinese under `Accept-Language: en`. Translating the base prompt to English removes that bias while preserving the existing locale-switching mechanism for non-English locales (verified: `get_language_instruction()` returns the Chinese postfix `请使用中文回答。` when locale is `zh`, so a Chinese model response remains achievable from an English base prompt).

This work tracks GitHub issue [#2](https://github.com/salestech-group/MiroFish/issues/2).

## Boundary Context

- **In scope**:
    - Translating `ONTOLOGY_SYSTEM_PROMPT` (the module-level system prompt constant) from Chinese to English.
    - Translating the user-message template constructed in `OntologyGenerator._build_user_message` (Chinese section headings and instruction list) to English.
    - Translating the truncation notice string emitted when input text exceeds `MAX_TEXT_LENGTH_FOR_LLM`.
    - Translating the trailing instruction string appended to the user message ("必须遵守的规则" block).
    - Preserving all functional contracts: JSON schema, key names, entity-type taxonomy, relationship-type taxonomy, attribute reserved-word list, fallback rules, variable interpolation, and the `get_language_instruction()` postfix call site.
- **Out of scope**:
    - Logger messages, including warnings emitted by `_validate_and_process` (covered by issue #6).
    - Module docstring, class docstrings, method docstrings, and inline comments (covered by issue #7).
    - Refactoring the ontology JSON schema, validation flow, or extraction strategy.
    - Changing the entity-type or relationship-type reference taxonomies (the categories themselves remain — only their description language changes).
    - Editing call sites of `OntologyGenerator.generate` or `generate_python_code`.
    - Translating the auto-generated Python code emitted by `generate_python_code` (the comment headers there are documentation, covered by #7).
- **Adjacent expectations**:
    - The Graphiti adapter (`graphiti_adapter`) and Step 1 graph build pipeline must continue to consume the ontology output unchanged. No coupling to prompt language exists in the adapter; this is verified via the JSON schema contract being preserved.
    - The locale resolution chain (`Accept-Language` header → `get_locale()` → `get_language_instruction()`) is owned by `backend/app/utils/locale.py` and is unchanged by this work. Translating the base prompt does not modify locale resolution semantics.
    - Companion i18n issues (#3, #4, #5, #6, #7, #8, #9, #10) operate on different files or scopes and should not be touched here.

## Requirements

### Requirement 1: English Translation of the Ontology System Prompt

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the ontology-generation system prompt to be authored in English, so that the LLM's ontology descriptions, reasoning, and schema commentary are not biased toward Chinese structure or word choice.

#### Acceptance Criteria

1. The Ontology Generator shall define `ONTOLOGY_SYSTEM_PROMPT` containing zero Chinese characters in any string-literal content.
2. The Ontology Generator shall preserve the JSON output contract of the system prompt verbatim: the keys `entity_types`, `edge_types`, `analysis_summary`, and the entity sub-keys `name`, `description`, `attributes`, `examples`, and the edge sub-keys `name`, `description`, `source_targets`, `attributes`, plus the `source_targets` sub-keys `source` and `target`.
3. The Ontology Generator shall preserve the entity-type reference list verbatim by name (`Student`, `Professor`, `Journalist`, `Celebrity`, `Executive`, `Official`, `Lawyer`, `Doctor`, `Person`, `University`, `Company`, `GovernmentAgency`, `MediaOutlet`, `Hospital`, `School`, `NGO`, `Organization`).
4. The Ontology Generator shall preserve the relationship-type reference list verbatim by name (`WORKS_FOR`, `STUDIES_AT`, `AFFILIATED_WITH`, `REPRESENTS`, `REGULATES`, `REPORTS_ON`, `COMMENTS_ON`, `RESPONDS_TO`, `SUPPORTS`, `OPPOSES`, `COLLABORATES_WITH`, `COMPETES_WITH`).
5. The Ontology Generator shall preserve the reserved-attribute-name list verbatim (`name`, `uuid`, `group_id`, `created_at`, `summary`).
6. The Ontology Generator shall preserve the fallback-type rule that exactly two fallback entity types — `Person` and `Organization` — must appear at the end of a 10-item list.
7. The Ontology Generator shall preserve the entity-count constraint (exactly 10 entity types) and the edge-count constraint (6–10 relationship types).
8. The Ontology Generator shall preserve the description-length constraint (entity and edge `description` ≤ 100 characters).

### Requirement 2: English Translation of the User-Message Template

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: en`, I want the user-message template constructed by `_build_user_message` to be authored in English, so that the rendered prompt does not interleave English `get_language_instruction()` directives with Chinese section headings.

#### Acceptance Criteria

1. The Ontology Generator shall render the user message with English section headings in place of `## 模拟需求`, `## 文档内容`, and `## 额外说明`.
2. The Ontology Generator shall render the trailing rules block in English (replacing `请根据以上内容...` and the `必须遵守的规则` enumeration), preserving the rule semantics: 10 entity types total, last 2 are `Person`/`Organization` fallbacks, first 8 are concrete types, all entities must be real-world social-media-capable subjects (not abstract concepts), and reserved attribute names cannot be used.
3. The Ontology Generator shall render the truncation notice in English when the combined document text exceeds `MAX_TEXT_LENGTH_FOR_LLM`, including the original character count and the truncation length.
4. The Ontology Generator shall preserve all variable interpolations verbatim by name (`simulation_requirement`, `combined_text`, `additional_context`, and the `{original_length}` / `{self.MAX_TEXT_LENGTH_FOR_LLM}` interpolations in the truncation notice).
5. The Ontology Generator shall preserve the conditional inclusion of the `## Additional Context` section only when `additional_context` is truthy.
6. The Ontology Generator shall return zero Chinese characters across all string literals contributed to the assembled user message.

### Requirement 3: Locale Switching Continues to Work via `get_language_instruction()`

**Objective:** As a MiroFish operator running the pipeline under `Accept-Language: zh` (or any other configured non-English locale), I want the ontology output to remain in the requested locale of equivalent quality, so that translating the base prompt does not regress non-English support.

#### Acceptance Criteria

1. The Ontology Generator shall preserve the call to `get_language_instruction()` exactly at the existing location (currently the line above `system_prompt = f"{ONTOLOGY_SYSTEM_PROMPT}\n\n{lang_instruction}\n..."`), continuing to read locale via the existing thread-local / request-header resolution chain.
2. The Ontology Generator shall preserve the trailing English directive that locks identifier formats (`Entity type names MUST be in English PascalCase ...`, `Relationship type names MUST be in English UPPER_SNAKE_CASE ...`, `Attribute names MUST be in English snake_case ...`, `Only description fields and analysis_summary should use the specified language above.`).
3. When the locale is `zh`, the Ontology Generator shall produce a JSON ontology whose `description` and `analysis_summary` fields are in Chinese, equivalent in quality to the pre-change behaviour.
4. When the locale is `en`, the Ontology Generator shall produce a JSON ontology whose `description` and `analysis_summary` fields are in English.
5. The Ontology Generator shall not alter `backend/app/utils/locale.py`, the `_languages`, the `_translations` registries, or the locales under `/locales/`.

### Requirement 4: Public API and Call-Site Stability

**Objective:** As a developer maintaining the rest of the MiroFish backend pipeline, I want the public surface of `OntologyGenerator` to remain unchanged, so that the graph-build flow and existing callers continue to work without modification.

#### Acceptance Criteria

1. The Ontology Generator shall preserve the signature of `OntologyGenerator.__init__(self, llm_client: Optional[LLMClient] = None)`.
2. The Ontology Generator shall preserve the signature of `OntologyGenerator.generate(self, document_texts: List[str], simulation_requirement: str, additional_context: Optional[str] = None) -> Dict[str, Any]`.
3. The Ontology Generator shall preserve the signature of `OntologyGenerator.generate_python_code(self, ontology: Dict[str, Any]) -> str`.
4. The Ontology Generator shall preserve the return-shape contract of `generate()`: a `Dict[str, Any]` with keys `entity_types`, `edge_types`, `analysis_summary` matching the existing JSON schema, post-validation.
5. The Ontology Generator shall preserve the signature of the private helper `_to_pascal_case(name: str) -> str` and the validator `_validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]`.
6. The Ontology Generator shall preserve the constant `MAX_TEXT_LENGTH_FOR_LLM = 50000`.
7. The Ontology Generator shall preserve the LLM invocation parameters (`temperature=0.3`, `max_tokens=4096`) and the call to `self.llm_client.chat_json(...)`.

### Requirement 5: Reasoning-Model Output Compatibility

**Objective:** As a MiroFish operator using a reasoning-model provider (e.g. MiniMax, GLM with `<think>` tags or markdown code fences), I want JSON parsing of the ontology response to continue working, so that translating the base prompt does not regress provider compatibility.

#### Acceptance Criteria

1. The Ontology Generator shall delegate JSON parsing to `LLMClient.chat_json` exactly as today (the call at the existing site is unchanged in name and arguments).
2. If a reasoning-model provider returns `<think>`-tagged or markdown-fenced output, then the existing stripping logic in `LLMClient.chat_json` shall continue to apply unchanged.
3. The Ontology Generator shall not introduce any new pre-processing of the LLM response that depends on prompt language.
4. After translation, the Ontology Generator shall continue to round-trip a sample seed file through `generate()` and `_validate_and_process()` and produce a non-empty `entity_types` list of length 10 with the `Person` and `Organization` fallbacks present at indices 8 and 9 (or earlier, in the order produced).

### Requirement 6: Step 1 Graph Build Parity

**Objective:** As a MiroFish operator validating the change, I want the Graphiti / Neo4j Step 1 graph build to complete with comparable structure under the English ontology, so that the translation does not silently degrade graph quality.

#### Acceptance Criteria

1. When a representative seed file is processed end-to-end with locale `en`, the Step 1 graph build shall complete without raising an exception attributable to the ontology output.
2. When a representative seed file is processed end-to-end with locale `en`, the resulting Neo4j graph shall contain a node count and edge count comparable to the pre-change Chinese-prompt baseline within an operator-acceptable tolerance (a small percentage variance is acceptable; doubling or zeroing is not).
3. The Ontology Generator shall not change the function signatures or call sequence used by the Step 1 graph build pipeline (verified by Requirement 4).

### Requirement 7: Out-of-Scope Surfaces Remain Untouched

**Objective:** As a reviewer of this PR, I want the change to remain narrowly scoped to prompt strings, so that translation responsibilities for adjacent surfaces (issues #6 and #7) are not absorbed into this change.

#### Acceptance Criteria

1. The change shall not modify any `logger.warning(...)`, `logger.info(...)`, `logger.error(...)`, or `logger.debug(...)` call in `ontology_generator.py` (covered by issue #6).
2. The change shall not modify the module docstring, class docstring, method docstrings, or inline comments in `ontology_generator.py` (covered by issue #7).
3. The change shall not edit any file outside `backend/app/services/ontology_generator.py` for production code, except for adding test fixtures or scripts under a clearly-isolated directory if a verification harness is needed.
4. The change shall not introduce a new dependency or modify `backend/pyproject.toml` / `backend/uv.lock`.
