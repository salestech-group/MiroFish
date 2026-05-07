# Implementation Plan

- [x] 1. Translate the ontology system-prompt constant to English
  - Replace the body of `ONTOLOGY_SYSTEM_PROMPT` with an English rendering that preserves the section structure (core task background, output format JSON template, design guidelines, entity-type reference list, relationship-type reference list, attribute reserved-name rules)
  - Preserve the JSON template keys verbatim: `entity_types`, `edge_types`, `analysis_summary`, and the entity sub-keys `name`, `description`, `attributes`, `examples`, the edge sub-keys `name`, `description`, `source_targets`, `attributes`, plus the `source_targets` sub-keys `source` and `target`
  - Preserve the entity-type reference list verbatim by name (`Student`, `Professor`, `Journalist`, `Celebrity`, `Executive`, `Official`, `Lawyer`, `Doctor`, `Person`, `University`, `Company`, `GovernmentAgency`, `MediaOutlet`, `Hospital`, `School`, `NGO`, `Organization`)
  - Preserve the relationship-type reference list verbatim by name (`WORKS_FOR`, `STUDIES_AT`, `AFFILIATED_WITH`, `REPRESENTS`, `REGULATES`, `REPORTS_ON`, `COMMENTS_ON`, `RESPONDS_TO`, `SUPPORTS`, `OPPOSES`, `COLLABORATES_WITH`, `COMPETES_WITH`)
  - Preserve the reserved-attribute-name list verbatim (`name`, `uuid`, `group_id`, `created_at`, `summary`)
  - Express the same numeric constraints in English: exactly 10 entity types, last 2 are `Person` and `Organization` fallbacks, 6–10 relationship types, 1–3 attributes per entity, descriptions ≤ 100 characters
  - Observable completion: `ONTOLOGY_SYSTEM_PROMPT` is an English-only string with zero CJK characters and identical structural keys/values to the original
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

- [x] 2. Translate the user-message template strings to English
  - Replace the section headings `## 模拟需求`, `## 文档内容`, and `## 额外说明` with English equivalents (`## Simulation Requirement`, `## Document Content`, `## Additional Context`)
  - Replace the trailing rules block (the Chinese `请根据以上内容...` / `必须遵守的规则` enumeration) with an English block that conveys the same five rules: 10 entity types total; last 2 are `Person` and `Organization` fallbacks; first 8 are concrete types from the document; entities must be real-world social-media-capable subjects (not abstract concepts); reserved attribute names cannot be used
  - Replace the truncation notice (the Chinese `(原文共...字，已截取前...字用于本体分析)`) with an English equivalent that retains both numeric interpolations
  - Preserve every f-string interpolation by name and position: `{simulation_requirement}`, `{combined_text}`, `{additional_context}`, `{original_length}`, `{self.MAX_TEXT_LENGTH_FOR_LLM}`
  - Preserve the conditional inclusion of the `## Additional Context` block — it appears only when `additional_context` is truthy
  - Observable completion: `_build_user_message` produces an English-only message body for any input combination, with zero CJK characters in any string literal it contributes; under the same inputs as before, all interpolated values still appear in the rendered output
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 3. Confirm boundary commitments around the translation
  - Confirm the call to `get_language_instruction()` and the assembled `system_prompt` line remain at their existing position with their existing arguments (no rename, no relocation)
  - Confirm the trailing English identifier-format directive (`IMPORTANT: Entity type names MUST be in English PascalCase ...`, `Relationship type names MUST be in English UPPER_SNAKE_CASE ...`, `Attribute names MUST be in English snake_case ...`, `Only description fields and analysis_summary should use the specified language above.`) remains byte-for-byte identical
  - Confirm the public signatures of `OntologyGenerator.__init__`, `generate`, `generate_python_code`, the private `_to_pascal_case`, and `_validate_and_process` are unchanged
  - Confirm the constant `MAX_TEXT_LENGTH_FOR_LLM = 50000` is unchanged
  - Confirm the LLM invocation parameters `temperature=0.3, max_tokens=4096` and the `self.llm_client.chat_json(...)` call site are unchanged
  - Confirm `backend/app/utils/locale.py`, `/locales/languages.json`, `/locales/en.json`, and `/locales/zh.json` are not modified
  - Confirm `logger.warning(...)`, `logger.info(...)`, module/class/method docstrings, and inline comments in `ontology_generator.py` are not modified (these are owned by issues #6 and #7)
  - Confirm `backend/pyproject.toml`, `backend/uv.lock`, and any file outside `backend/app/services/ontology_generator.py` are not modified
  - Observable completion: a `git diff` review against `main` shows changes only inside `backend/app/services/ontology_generator.py`, only inside `ONTOLOGY_SYSTEM_PROMPT` and `_build_user_message`, and the surrounding lines are byte-identical
  - _Requirements: 3.1, 3.2, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.1, 5.3, 7.1, 7.2, 7.3, 7.4_

- [x] 4. Verify reasoning-model output compatibility and JSON shape stability
  - Inspect `LLMClient.chat_json` to confirm `<think>` tag stripping (in `chat`) and markdown-fence stripping (in `chat_json`) are still the only post-processors applied to the LLM response, and that no new pre-processing has been added in `ontology_generator.py`
  - Run an in-process round-trip: instantiate `OntologyGenerator`, call `generate(...)` with a small representative `document_texts` list and `simulation_requirement`, and assert the returned dict has keys `entity_types` (length 10), `edge_types`, `analysis_summary`; assert the last two entity-type names are `Person` and `Organization`
  - Repeat the round-trip under simulated reasoning-model output to confirm the existing stripping path still parses cleanly (e.g. by patching `chat` to wrap a known-good JSON in `<think>...</think>` and triple-fenced code, then asserting `chat_json` still parses)
  - Observable completion: a short verification script under `backend/scripts/` (or an inline `python -c` recorded in the PR description) demonstrates the round-trip succeeds with both clean and `<think>`/fenced LLM outputs
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ] 5. Verify locale-driven output language under both `en` and `zh`
  - Set the thread-local locale to `en` via `set_locale("en")`, run `OntologyGenerator().generate(...)` against the configured LLM, and confirm the returned `description` fields and `analysis_summary` contain no CJK characters and read as natural English
  - Set the thread-local locale to `zh` via `set_locale("zh")`, run the same round-trip, and confirm the returned `description` fields and `analysis_summary` contain CJK characters of equivalent quality to the pre-change baseline
  - Observable completion: both runs succeed; the `en` run is CJK-free in description fields, the `zh` run continues to produce Chinese descriptions; results are recorded in the PR description
  - _Requirements: 3.3, 3.4_

- [ ] 6. Verify Step 1 graph-build parity end-to-end under `en` locale
  - Using a representative seed file, exercise the full Step 1 graph-build pipeline (upload → ontology → Graphiti → Neo4j) under `Accept-Language: en`
  - Confirm the run completes without raising an exception attributable to ontology output
  - Compare the resulting Neo4j node and edge counts against a recent `zh`-locale baseline; confirm they are within an operator-acceptable tolerance (no doubling, no zeroing)
  - Observable completion: the pipeline reaches `GRAPH_COMPLETED`, and the comparison numbers are recorded in the PR description
  - _Requirements: 6.1, 6.2, 6.3_

- [x]* 7. Add a static guard against CJK regression in this file's prompt strings
  - Add a small one-shot script under `backend/scripts/` that loads `ONTOLOGY_SYSTEM_PROMPT` and the rendered output of `_build_user_message(...)` for representative inputs, and asserts zero matches against the regex `[一-鿿]` over those strings
  - Optional: extend the existing `pytest`-style harness if a thin assertion fits the project's minimal test surface
  - Observable completion: running the script exits 0 against the patched module; running it against a hypothetical revert of the patch exits non-zero
  - _Requirements: 1.1, 2.6_
