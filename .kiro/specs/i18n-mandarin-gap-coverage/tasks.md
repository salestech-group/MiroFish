# Implementation Plan — i18n-mandarin-gap-coverage

## 1. Foundation — locale catalogue and shared key namespaces

- [ ] 1.1 Add the `zep_tools.output.*` namespace to both locale catalogues
  - Append a new nested object under the top level of `locales/en.json` and `locales/zh.json` covering every literal currently emitted by `SearchResult.to_text`, `NodeInfo.to_text`, `EdgeInfo.to_text`, `InsightForgeResult.to_text`, `PanoramaResult.to_text`, `AgentInterview.to_text`, and `InterviewResult.to_text` in `backend/app/services/zep_tools.py`.
  - English values follow the canonical phrasing listed in `design.md` (e.g., `"Search query: {query}"`, `"Found {count} relevant facts"`, `"### Relevant facts:"`, `"Entity: {name} (type: {type})\nSummary: {summary}"`, `"## In-depth prediction analysis"`, `"## Breadth-search result (full prediction landscape)"`, `"## In-depth interview report"`).
  - Chinese values byte-equal the current source literals (e.g., `"搜索查询: {query}"`, `"找到 {count} 条相关信息"`), so the `zh` rendering stays unchanged.
  - Observable: `python -c "import json; en=json.load(open('locales/en.json')); zh=json.load(open('locales/zh.json')); assert set(en['zep_tools']['output'])==set(zh['zep_tools']['output'])"` exits 0 and the same call lists ≥30 keys.
  - _Requirements: 1.3_

- [ ] 1.2 (P) Add the `zep_graph_memory_updater.action.*` and `zep_graph_memory_updater.platform.*` namespaces
  - Cover the 16 action verbs of `_describe_*` in `backend/app/services/zep_graph_memory_updater.py` plus the `create_post_empty`/`like_post_empty`/... fallbacks (≈20 keys per locale).
  - Cover the two `PLATFORM_DISPLAY_NAMES` values (`twitter`, `reddit`) under `zep_graph_memory_updater.platform.*`. English: `"World 1"`, `"World 2"`. Chinese byte-equal current strings.
  - Preserve every interpolation token (`{content}`, `{author}`, `{target}`, `{query}`, `{comment_content}`, `{comment_author}`).
  - Observable: parity check from 1.1 also passes for these new namespaces; manual diff shows both `en.json` and `zh.json` carry the same set of leaf keys.
  - _Requirements: 2.2, 2.3_
  - _Boundary: locales catalogue_

- [ ] 1.3 (P) Add the `scripts.*` namespace covering the four backend scripts
  - Add `scripts.run_twitter_simulation.*`, `scripts.run_reddit_simulation.*`, `scripts.run_parallel_simulation.*`, `scripts.test_profile_format.*` namespaces to both catalogues.
  - Each contains an entry for every `print()` and `argparse` description/help argument that currently embeds Chinese (≈140 keys total, audit-driven).
  - English values are natural-English equivalents; Chinese values byte-equal the current source literals.
  - Observable: running `python -c "import json; ..."` parity check confirms the four script sub-namespaces have identical key sets across `en.json` and `zh.json`.
  - _Requirements: 3.3_
  - _Boundary: locales catalogue_

## 2. Core — backend externalization

- [ ] 2.1 Route every `to_text()` and inline-return literal in `zep_tools.py` through `t()`
  - Replace every Han-character string literal in `SearchResult.to_text`, `NodeInfo.to_text`, `EdgeInfo.to_text`, `InsightForgeResult.to_text`, `PanoramaResult.to_text`, `AgentInterview.to_text`, and `InterviewResult.to_text` with a `t("zep_tools.output.<symbol>", **kwargs)` call.
  - Also externalize the operator-facing return strings inside `_call_with_retry`'s `operation_name=f"图谱搜索…"` argument and the `_local_search` keyword join, the InsightForge fallback variants at `:1129-1134`, the API-failure summary at `:1387`, the "no reply" markers at `:1413-1414`, the dual-platform combined-response wrapper at `:1415`, and the fallback summaries at `:1460, :1466`, plus the agent-fallback role and the interview-summary fallback at `:1685, :1729`.
  - Leave punctuation regex character classes intact (`[。！？]`, `[，,；;：:、]`, paired `「」`/`""` quote codepoints used in `re.findall`/`re.sub`).
  - Observable: `rg --line-number --no-heading -nP '[\p{Han}]' backend/app/services/zep_tools.py` returns only lines inside `re.split`, `re.sub`, `re.findall` argument literals and the unicode-escape-coded codepoint normalizer at `:307-313` (no natural-language strings).
  - _Requirements: 1.1, 1.2, 1.3, 1.5_
  - _Boundary: zep_tools.py_
  - _Depends: 1.1_

- [ ] 2.2 (P) Rewrite the four inline LLM prompt blocks in `zep_tools.py` in English
  - Translate the system + user prompts in `_generate_sub_queries` (around lines 1095–1111), the agent-selection planner (1574–1597), the interview-question generator (1638–1656), and the interview-summary writer (1692–1713) to English.
  - Append `get_language_instruction()` (imported from `backend.app.utils.locale`) to the system-message string of each block so the LLM responds in the active locale.
  - Preserve every JSON-schema key (`sub_queries`, `selected_indices`, `reasoning`, `questions`), numeric ranges, and example pairings byte-equal.
  - Observable: `rg -nP '[\p{Han}]' backend/app/services/zep_tools.py` after this and 2.1 returns zero hits outside the punctuation-regex char-classes; manual `diff` of the four blocks shows JSON keys unchanged.
  - _Requirements: 1.3, 1.5_
  - _Boundary: zep_tools.py — prompt blocks only_
  - _Depends: 2.1_

- [ ] 2.3 (P) Route the 16 action descriptions in `zep_graph_memory_updater.py` through `t()`
  - For each `_describe_*` method, replace the Chinese f-string return value with a `t("zep_graph_memory_updater.action.<verb>", **action_args)` call. Preserve the empty-arg / missing-arg fallback variants by using distinct keys (`create_post`, `create_post_empty`, …).
  - Remove the class-level `PLATFORM_DISPLAY_NAMES` dict and add a `GraphMemoryUpdater.display_name(platform)` classmethod that returns `t(f"zep_graph_memory_updater.platform.{platform}")`. Grep the workspace for every `PLATFORM_DISPLAY_NAMES[...]` consumer and migrate each call site in the same commit.
  - Observable: `rg -nP '[\p{Han}]' backend/app/services/zep_graph_memory_updater.py` returns zero hits; `rg -n PLATFORM_DISPLAY_NAMES backend frontend` returns zero hits (or only the class-method definition).
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Boundary: zep_graph_memory_updater.py_
  - _Depends: 1.2_

## 3. Core — backend script externalization

- [ ] 3.1 Add the module-top locale bootstrap to all four backend scripts
  - At the top of `backend/scripts/run_twitter_simulation.py`, `run_reddit_simulation.py`, `run_parallel_simulation.py`, and `test_profile_format.py`, add an **unconditional** `try / except ImportError` block that binds `t` and `set_locale` either from `app.utils.locale` (when on the import path) or from local no-op stubs that return the key string.
  - Under `if __name__ == "__main__":` (or the existing main entry), call `set_locale(os.environ.get("MIROFISH_LOCALE", "zh"))` once before any localized output is emitted.
  - Observable: each script can be imported (e.g., `python -c "import backend.scripts.test_profile_format"`) without raising; running each script under unset `MIROFISH_LOCALE` produces Chinese output, and under `MIROFISH_LOCALE=en` produces English output.
  - _Requirements: 3.2, 3.5_
  - _Boundary: scripts bootstrap_
  - _Depends: 1.3_

- [ ] 3.2 (P) Externalize `run_twitter_simulation.py` operator output
  - Replace every Chinese `print(...)` literal and every `argparse(description=..., help=...)` Chinese argument with the corresponding `t("scripts.run_twitter_simulation.<symbol>", ...)` call.
  - Preserve every f-string interpolation; map them onto `{...}` placeholders in the catalogue templates.
  - Observable: `rg -nP '[\p{Han}]' backend/scripts/run_twitter_simulation.py` returns zero hits.
  - _Requirements: 3.1, 3.3, 3.4_
  - _Boundary: run_twitter_simulation.py_
  - _Depends: 3.1_

- [ ] 3.3 (P) Externalize `run_reddit_simulation.py` operator output
  - Same treatment as 3.2 against `run_reddit_simulation.py`.
  - Observable: `rg -nP '[\p{Han}]' backend/scripts/run_reddit_simulation.py` returns zero hits.
  - _Requirements: 3.1, 3.3, 3.4_
  - _Boundary: run_reddit_simulation.py_
  - _Depends: 3.1_

- [ ] 3.4 (P) Externalize `run_parallel_simulation.py` operator output
  - Same treatment as 3.2 against `run_parallel_simulation.py`. Reddit and Twitter sub-prints inside this script use the corresponding `scripts.run_*_simulation.*` keys when phrased identically; otherwise add `scripts.run_parallel_simulation.*` keys.
  - Observable: `rg -nP '[\p{Han}]' backend/scripts/run_parallel_simulation.py` returns zero hits.
  - _Requirements: 3.1, 3.3, 3.4_
  - _Boundary: run_parallel_simulation.py_
  - _Depends: 3.1_

- [ ] 3.5 (P) Externalize `test_profile_format.py` operator output
  - Same treatment as 3.2 against `test_profile_format.py`. This file is short (~166 lines, 20 Han hits).
  - Observable: `rg -nP '[\p{Han}]' backend/scripts/test_profile_format.py` returns zero hits; `cd backend && uv run python -m pytest scripts/test_profile_format.py` continues to pass.
  - _Requirements: 3.1, 3.3, 3.4_
  - _Boundary: test_profile_format.py_
  - _Depends: 3.1_

## 4. Core — frontend marker alternation

- [ ] 4.1 Extend every `REPORT_MARKERS` regex in `Step4Report.vue` with English alternation branches
  - For each marker between lines 550–642, rewrite the literal label portion as a non-capturing alternation `(?:CN|EN)` where `CN` is the existing Chinese phrase and `EN` is the English phrasing chosen in the matching `zep_tools.output.*` catalogue key.
  - Update `noReply.is(value)` to accept the English form `"(no reply on this platform)"` in addition to the existing three Chinese variants.
  - Leave `logSeverity.isError`/`isWarning` unchanged (they already dual-token).
  - Keep the `i18n-allow-block` annotation comments intact at lines 549 and 643 so the CJK CI guard recognizes the block.
  - Observable: open the running stack with an English-locale generated report and confirm every Step 4 section (analysis query, prediction scenario, sub-queries, key facts, core entities, relation chain, panorama totals, active/historical facts, interview topic/count, twitter/reddit answers, key quotes, interview summary, related facts) populates without empty placeholders.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Boundary: Step4Report.vue — REPORT_MARKERS block_
  - _Depends: 2.1_

## 5. Validation — cross-layer English-verification test

- [ ] 5.1 Build the standalone English-marker verification test
  - Add a Python entry-point at `.kiro/specs/i18n-e2e-english-verification/audit/scripts/verify_step4_markers.py` that:
    1. Reads `frontend/src/components/Step4Report.vue` lines 550–642 verbatim, extracts every `regex: /.../` literal, and translates each into a Python `re.compile(...)` (skipping markers that use JS-only syntax and recording each skip in `<sha>/markers-skipped.txt`).
    2. Imports the four result dataclasses from `backend.app.services.zep_tools`, calls `set_locale("en")`, instantiates each with fixture data captured at `.kiro/specs/i18n-e2e-english-verification/audit/fixtures/zep_tools_en/` (one JSON per result type), invokes `to_text()`, and concatenates the outputs.
    3. Asserts every translated marker matches at least one section of the concatenated text.
  - Print one `marker not matched: <key>` line per failure; exit code is the failure count.
  - The script must not import Neo4j, Graphiti, or any LLM client.
  - Observable: running `cd backend && uv run python ../.kiro/specs/i18n-e2e-english-verification/audit/scripts/verify_step4_markers.py` from repo root after task 4.1 has landed exits `0`; reverting task 4.1 (or task 2.1) causes the script to exit non-zero with at least one `marker not matched:` line.
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - _Boundary: english-verification audit harness_
  - _Depends: 2.1, 4.1_

## 6. Validation — prompt-coverage audit

- [ ] 6.1 Produce the prompt-coverage audit artefact and follow-up tasks
  - Create `.kiro/specs/i18n-mandarin-gap-coverage/prompt-coverage-audit.md`. For each of the three prompt-generator specs (`i18n-oasis-profile-generator-prompts`, `i18n-ontology-generator-prompts`, `i18n-simulation-config-generator-prompts`), list every Han-character literal currently present in the corresponding generator source (`oasis_profile_generator.py`, `ontology_generator.py`, `simulation_config_generator.py`), annotate each with `covered` (existing task in that spec's `tasks.md` claims it) or `uncovered` (no task references it).
  - For every `uncovered` line, append a new unchecked task to the originating spec's `tasks.md` describing the file:line and the externalization action required.
  - Do not modify any generator source file.
  - Observable: `prompt-coverage-audit.md` lists every Han line from the three generator files (cross-checked against `rg -nP '[\p{Han}]' backend/app/services/{oasis_profile,ontology,simulation_config}_generator.py`); each of the three spec `tasks.md` files has at least the number of new tasks recorded in the audit's "uncovered" column.
  - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - _Boundary: spec docs only — no source code touched_

## 7. Validation — CJK CI guard regression check

- [ ] 7.1 Confirm the CJK CI guard scans the six in-scope files and passes
  - Inspect `scripts/check_i18n_logs.py` (or the equivalent guard implementation under `scripts/ci/`) and verify its scan-set covers `backend/app/services/zep_tools.py`, `backend/app/services/zep_graph_memory_updater.py`, and the four `backend/scripts/*` files. If any is excluded, add it.
  - Run the guard locally: `python scripts/check_i18n_logs.py` (or the documented invocation). Capture stdout/exit code.
  - The guard's `i18n-allow-block` recognition must still treat `frontend/src/components/Step4Report.vue` lines 549–643 as an exception. Verify by introducing a transient Chinese literal outside the block and confirming the guard fails; remove the transient change after the check.
  - Observable: guard exits `0` against the working tree after tasks 2.x, 3.x, and 4.1 have landed; introducing a Chinese literal in any of the six files (or outside the allow-block in Step4Report.vue) causes the guard to fail with a file:line message.
  - _Requirements: 7.1, 7.2, 7.3_
  - _Boundary: CJK guard configuration — read/verify only, modify only if scan-set is incomplete_
  - _Depends: 2.1, 2.3, 3.2, 3.3, 3.4, 3.5_

## 8. Integration — smoke and final regression

- [ ] 8.1 End-to-end smoke under both locales
  - Boot the full stack (`docker-compose up` or `npm run dev` with a local Neo4j) and walk through the 5-step workflow once with `Accept-Language: en` and once with `Accept-Language: zh` (or the equivalent locale-selection UI).
  - On the English run, confirm that the Step 4 report view populates every section without empty placeholders and that no rendered text contains either the literal `zep_tools.output.<…>` key string (which would indicate a missing-key fallback) or stray Han characters.
  - On the Chinese run, confirm the existing user experience is byte-equal to pre-change (visual regression).
  - Observable: a screenshot of the Step 4 view from each locale-run is captured in the PR description; the backend logs show no `missing translation key:` warnings emitted from the new namespaces.
  - _Requirements: 1.1, 1.2, 2.1, 4.1_
  - _Depends: 4.1, 5.1, 7.1_
