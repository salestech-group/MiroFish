# Implementation Plan — i18n-externalize-backend-logs

## 1. Foundation: extend the locale helper and the verifier tooling

- [x] 1.1 Add deduplicated missing-key warning and test-reset hook to the locale helper
  - Extend the existing translation lookup so that, when a key is unresolved in both the active locale and the `zh` fallback, a single `logger.warning(...)` is emitted per `(locale, key)` pair (deduplicated for the lifetime of the process).
  - Use the existing logger factory under a `mirofish.locale` logger name; the warning record must include the missing key string and the active locale.
  - Preserve the existing return contract: a missing key still resolves to the raw key string, never raises.
  - Expose a private reset entry point so unit tests can clear the dedup memoization between cases.
  - Observable completion: invoking the helper with a known-missing key returns the key string, emits exactly one warning record, and a second invocation of the same key emits no additional warning until the reset hook is called.
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 1.2 Build the i18n verification script with AST-aware Chinese-literal scanning and locale parity check
  - Implement a single Python script that runs from the repo root using only the standard library (`json`, `re`, `pathlib`, `argparse`, `ast`).
  - Mode A (`--logs`): walk the embedded list of in-scope backend modules and report every Chinese character (`U+4E00`–`U+9FFF`) found inside the string-literal arguments of `logger.{info,warning,error,debug,exception}(...)` calls and inside the `error` / `message` field values of `jsonify({...})` calls. Use the AST so that multi-line `jsonify(...)` calls are detected reliably.
  - Mode B (`--parity`): load every `*.json` in `/locales/` (excluding `languages.json`), recursively diff the key paths pairwise, and report any path that exists in some files but not others.
  - Default invocation runs both modes; CLI flags select either alone. Exit status: `0` when both pass, `1` otherwise. Each finding line is `<file>:<line>: <reason>: <snippet>`; final line is `OK` or `N issues`.
  - Observable completion: running the script against the unmodified repo prints the current findings list and exits non-zero; running it after the rewrite tasks below prints `OK` and exits `0`.
  - _Requirements: 1.5, 2.4, 3.4, 5.1, 5.2, 5.3, 5.4_
  - _Boundary: I18nLogVerifier_

## 2. Core: rewrite Chinese log strings in the backend service modules

> Each sub-task here is mechanically isolated to one file and only touches `logger.{info,warning,error,debug,exception}(...)` lines plus the matching `log.<module>.*` namespace in both locale files. Sub-tasks 2.1–2.9 are parallel-safe: they operate on disjoint file boundaries and only append (never overwrite) keys to the locale dictionaries. Locale-file edits are append-only sub-namespaces, so concurrent edits do not collide as long as the namespace per task is unique.

- [x] 2.1 (P) Externalize Chinese logger messages in the Zep tools service
  - Replace every Chinese string literal inside `logger.*` calls in the Zep tools service with translation lookups under the `log.zep_tools.*` sub-namespace.
  - Move every dynamic value into a `{name}` placeholder kwarg passed through the translation helper (no f-strings or string concatenation around the helper call).
  - Add the matching keys to `locales/en.json` (English translation) and `locales/zh.json` (original Chinese verbatim) in alphabetical order inside the new sub-namespace.
  - Observable completion: the verifier `--logs` mode reports zero Chinese matches inside the Zep tools service file.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.5_
  - _Boundary: BackendLogTranslations (zep_tools), LocaleDictionary_

- [x] 2.2 (P) Externalize Chinese logger messages in the simulation runner service
  - Same rewrite/locale pattern under the `log.simulation_runner.*` sub-namespace.
  - Confirm the runner's existing background-thread `set_locale(...)` call still happens at thread entry so the helper resolves the right locale for these messages.
  - Observable completion: verifier `--logs` mode reports zero Chinese matches inside the simulation runner service file.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.5_
  - _Boundary: BackendLogTranslations (simulation_runner), LocaleDictionary_

- [x] 2.3 (P) Externalize Chinese logger messages in the OASIS profile generator service
  - Same rewrite/locale pattern under the `log.profile_generator.*` sub-namespace.
  - Observable completion: verifier `--logs` mode reports zero Chinese matches inside the OASIS profile generator service file.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.5_
  - _Boundary: BackendLogTranslations (oasis_profile_generator), LocaleDictionary_

- [x] 2.4 (P) Externalize Chinese logger messages in the simulation config generator service
  - Same rewrite/locale pattern under the `log.simulation_config.*` sub-namespace.
  - Observable completion: verifier `--logs` mode reports zero Chinese matches inside the simulation config generator service file.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.5_
  - _Boundary: BackendLogTranslations (simulation_config_generator), LocaleDictionary_

- [x] 2.5 (P) Externalize Chinese logger messages in the Zep graph memory updater service
  - Same rewrite/locale pattern under the `log.zep_graph_memory_updater.*` sub-namespace.
  - Observable completion: verifier `--logs` mode reports zero Chinese matches inside the Zep graph memory updater service file.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.5_
  - _Boundary: BackendLogTranslations (zep_graph_memory_updater), LocaleDictionary_

- [x] 2.6 (P) Externalize Chinese logger messages in the Zep entity reader service
  - Same rewrite/locale pattern under the `log.zep_entity_reader.*` sub-namespace.
  - Observable completion: verifier `--logs` mode reports zero Chinese matches inside the Zep entity reader service file.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.5_
  - _Boundary: BackendLogTranslations (zep_entity_reader), LocaleDictionary_

- [x] 2.7 (P) Externalize Chinese logger messages in the simulation IPC service
  - Same rewrite/locale pattern under the `log.simulation_ipc.*` sub-namespace.
  - Observable completion: verifier `--logs` mode reports zero Chinese matches inside the simulation IPC service file.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.5_
  - _Boundary: BackendLogTranslations (simulation_ipc), LocaleDictionary_

- [x] 2.8 (P) Externalize Chinese logger messages in the simulation manager service
  - Same rewrite/locale pattern under the `log.simulation_manager.*` sub-namespace.
  - Observable completion: verifier `--logs` mode reports zero Chinese matches inside the simulation manager service file.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.5_
  - _Boundary: BackendLogTranslations (simulation_manager), LocaleDictionary_

- [x] 2.9 (P) Externalize the residual Chinese logger message in the report agent service
  - Replace the single residual Chinese `logger.*` call in the report agent service with a translation lookup under the `log.report_agent.*` sub-namespace.
  - Do not touch prompt strings — those remain owned by the sibling spec already merged on this branch.
  - Observable completion: verifier `--logs` mode reports zero Chinese matches inside the report agent service file.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.5_
  - _Boundary: BackendLogTranslations (report_agent), LocaleDictionary_

## 3. Core: rewrite Chinese strings in the backend API blueprints

> The API sub-tasks rewrite both `logger.*` calls and the `error` / `message` field values of `jsonify(...)` responses in the same file. Each blueprint owns disjoint `log.<api_module>.*` and `api.{error,message}.<scope>.*` sub-namespaces, so they remain parallel-safe.

- [x] 3.1 (P) Externalize Chinese strings in the simulation API blueprint
  - Rewrite Chinese `logger.*` strings under the `log.simulation_api.*` sub-namespace.
  - Rewrite Chinese `error` / `message` field values inside `jsonify({...})` responses under the `api.error.simulation.*` / `api.message.simulation.*` sub-namespaces. Preserve every other field (`success`, `data`, `traceback`, `progress`, `status`) and the HTTP status code unchanged.
  - Move dynamic values into `{name}` placeholder kwargs (e.g. `id=<value>`); never embed Chinese in the surrounding f-string.
  - Add the matching keys to `locales/en.json` and `locales/zh.json` in alphabetical order under the new sub-namespaces.
  - Observable completion: verifier `--logs` mode reports zero Chinese matches inside the simulation API blueprint and the blueprint's existing endpoints continue to return the same HTTP status codes and response field shape.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.5_
  - _Boundary: BackendLogTranslations (simulation_api), BackendApiResponseTranslations (simulation), LocaleDictionary_

- [x] 3.2 (P) Externalize Chinese strings in the report API blueprint
  - Rewrite Chinese `logger.*` strings under the `log.report_api.*` sub-namespace.
  - Leave the existing flat `api.<existing>` keys already in use by the blueprint untouched (they are part of the existing contract and shared with the frontend).
  - For any *new* `error` / `message` translations introduced by this rewrite, place them under `api.error.report.*` / `api.message.report.*`.
  - Observable completion: verifier `--logs` mode reports zero Chinese matches inside the report API blueprint and the blueprint's existing endpoints continue to return the same HTTP status codes and response field shape.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.5_
  - _Boundary: BackendLogTranslations (report_api), BackendApiResponseTranslations (report), LocaleDictionary_

- [x] 3.3 (P) Externalize Chinese strings in the graph API blueprint
  - Rewrite Chinese `logger.*` strings under the `log.graph_api.*` sub-namespace.
  - Rewrite Chinese `error` / `message` field values inside `jsonify({...})` responses under `api.error.graph.*` / `api.message.graph.*`.
  - Observable completion: verifier `--logs` mode reports zero Chinese matches inside the graph API blueprint and the blueprint's existing endpoints continue to return the same HTTP status codes and response field shape.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.5_
  - _Boundary: BackendLogTranslations (graph_api), BackendApiResponseTranslations (graph), LocaleDictionary_

## 4. Validation: end-to-end checks and regression coverage

- [x] 4.1 Add focused locale-helper tests for the missing-key warning path
  - Add unit tests that exercise the locale helper's missing-key behavior: a missing key returns the raw key string, emits exactly one warning record per `(locale, key)` pair, and never raises for any input string (including invalid nested paths).
  - Tests use the private reset hook from task 1.1 to clear the dedup memoization between cases.
  - Add a single integration-style test asserting that an API endpoint rendering a translated `error` field returns the English string when the request carries `Accept-Language: en` and the original Chinese when the header is `zh` or absent.
  - Observable completion: `uv run python -m pytest` runs the new tests green alongside the existing test in the repository.
  - _Depends: 1.1, 3.1_
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.5_

- [x] 4.2 Run the verifier and the full pytest sweep against the rewritten codebase
  - Execute `python scripts/check_i18n_logs.py` from the repo root and confirm both the source scan and the parity check pass with exit `0`.
  - Re-run the regex acceptance check from the ticket (`grep -rEn "logger\.[a-z]+\([\"'][^\"']*[一-鿿]" backend/app/`) and confirm zero matches.
  - Re-run `uv run python -m pytest` and confirm the suite is green (no new failures introduced by the rewrite).
  - Spot-check one log line per modified file by setting the locale to `en` and tailing the formatted message — confirm the `{placeholder}` substitution works for messages with dynamic values.
  - Observable completion: all three commands above exit `0` and the spot-checked log lines render in English under the `en` locale.
  - _Depends: 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.1, 3.2, 3.3_
  - _Requirements: 1.5, 2.4, 3.4, 5.1, 5.2, 5.3, 5.5_
