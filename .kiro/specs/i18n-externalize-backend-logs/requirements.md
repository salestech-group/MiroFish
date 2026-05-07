# Requirements Document

## Introduction
The MiroFish backend currently emits Chinese strings directly from `logger.{info,warning,error,debug,exception}` calls and from a number of `jsonify({"error|message": ...})` API responses. These hardcoded strings bypass the existing `t()` localization helper in `backend/app/utils/locale.py`, so log aggregators receive unreadable messages for English-speaking operators and API responses ignore the active locale. This spec defines the work required to externalize every Chinese log message and user-facing API error/message string in the listed backend modules into the locale dictionaries (`locales/en.json` and `locales/zh.json`), so logs and responses honor the request locale and English operators get a fully readable pipeline.

## Boundary Context
- **In scope**:
  - Replace Chinese string literals inside `logger.{info,warning,error,debug,exception}` calls in:
    - `backend/app/services/report_agent.py`
    - `backend/app/services/zep_tools.py`
    - `backend/app/services/simulation_runner.py`
    - `backend/app/services/oasis_profile_generator.py`
    - `backend/app/services/simulation_config_generator.py`
    - `backend/app/services/zep_graph_memory_updater.py`
    - `backend/app/services/ontology_generator.py`
    - `backend/app/services/simulation_manager.py`
    - `backend/app/services/zep_entity_reader.py`
    - `backend/app/services/simulation_ipc.py`
    - `backend/app/services/graph_builder.py`
    - `backend/app/api/simulation.py`
    - `backend/app/api/report.py`
    - `backend/app/api/graph.py`
  - Replace Chinese string literals inside user-facing `jsonify({"error": ...})` and `jsonify({"message": ...})` (or equivalent response builders) in those API modules.
  - Add the corresponding keys to both `locales/en.json` (English translation) and `locales/zh.json` (preserve original Chinese verbatim) under a domain-grouped namespace (`log.<domain>.<key>`, `api.error.<scope>`, `api.message.<scope>`).
  - Preserve existing interpolation by passing values through `t(key, **kwargs)` (using the helper's `{name}` placeholder syntax) instead of f-strings or `%`-formatting around the call.
  - Ensure `t()` returns a safe fallback (and emits a warning, not a crash) when a key is missing.
- **Out of scope**:
  - Prompt template strings (handled by tickets #2/#3/#4/#5; the report-agent prompts work is already on the current branch).
  - Chinese docstrings and inline comments (handled by ticket #7).
  - Re-architecting the `t()` helper, switching i18n libraries, or introducing pluralization/ICU formatting.
  - Changing log levels, log structure, or response status codes beyond the string content.
  - Frontend `zh.json` parity beyond the new keys this work introduces.
- **Adjacent expectations**:
  - The `t()` helper at `backend/app/utils/locale.py` already exposes `set_locale`, `get_locale`, and `t` and is wired up at request time and at background-thread entry; new code must reuse the existing helper.
  - Locale files (`locales/en.json`, `locales/zh.json`) currently coexist with frontend `vue-i18n` consumption; new keys must not collide with existing top-level frontend keys (`menu`, `process`, `step1`, etc.). All new backend keys live under the new top-level namespaces `log` and `api` (or extend them if already present).
  - Sibling spec `i18n-report-agent-prompts` covered the *prompt* portion of `report_agent.py`; this spec must not regress those translations.

## Requirements

### Requirement 1: Externalize Chinese Logger Messages
**Objective:** As a backend operator viewing logs in an English log aggregator, I want every Chinese log message in the listed backend modules to be emitted in the active locale, so that I can read and triage logs without translation tooling.

#### Acceptance Criteria
1. The Backend Logging Layer shall emit log records whose message text is produced by `t("log.<domain>.<key>", **fmt)` for every `logger.{info,warning,error,debug,exception}` call in the listed in-scope modules that previously contained Chinese characters.
2. When the active locale is `en`, the Backend Logging Layer shall emit the English translation defined in `locales/en.json` for each externalized log key.
3. When the active locale is `zh`, the Backend Logging Layer shall emit the original Chinese text as preserved in `locales/zh.json` for each externalized log key.
4. The Backend Logging Layer shall preserve all interpolated values (entity counts, identifiers, exception text) by passing them as keyword arguments to `t()` rather than concatenating or formatting them around the `t()` call.
5. The Backend Logging Layer shall not contain any Chinese character (`U+4E00`–`U+9FFF`) inside the string-literal argument of any `logger.{info,warning,error,debug,exception}` call within the listed in-scope modules.

### Requirement 2: Externalize Chinese API Response Strings
**Objective:** As a frontend client (or external API consumer) reading the `Accept-Language` header, I want backend error and message responses in the listed API modules to be returned in the active locale, so that user-facing error surfaces match the rest of the localized UI.

#### Acceptance Criteria
1. The Backend API Layer shall produce the `error` and `message` field values of `jsonify({...})` responses in the listed in-scope API modules (`backend/app/api/{simulation,report,graph}.py`) by calling `t("api.error.<scope>", **fmt)` or `t("api.message.<scope>", **fmt)`.
2. When the request `Accept-Language` header is `en`, the Backend API Layer shall return the English translation for the corresponding response key.
3. When the request `Accept-Language` header is `zh` or absent, the Backend API Layer shall return the original Chinese string as preserved in `locales/zh.json`.
4. The Backend API Layer shall not contain any Chinese character inside the string value of an `error` or `message` field in any `jsonify(...)` (or equivalent response builder) call within the listed in-scope API modules.
5. The Backend API Layer shall keep the HTTP status code, response key set, and (for non-i18n keys) value structure of every modified response unchanged.

### Requirement 3: Locale Dictionary Parity and Structure
**Objective:** As a translator or developer adding a new locale, I want every backend log/API key to exist in both `en.json` and `zh.json` with identical nested structure, so that the locale files can be diffed and validated mechanically.

#### Acceptance Criteria
1. The Locale Dictionary shall contain, in `locales/en.json`, every key introduced by Requirements 1 and 2 with an English translation.
2. The Locale Dictionary shall contain, in `locales/zh.json`, every key introduced by Requirements 1 and 2 with the original Chinese text preserved verbatim from the previous source code.
3. The Locale Dictionary shall organize new backend keys under the top-level namespaces `log` (grouped by domain: `graph`, `simulation`, `report`, `agent`, `pipeline`, etc.) and `api` (grouped as `api.error.<scope>` / `api.message.<scope>`).
4. The Locale Dictionary shall expose a structurally identical key tree across `en.json` and `zh.json`, such that recursively diffing the key paths (ignoring values) of the two files produces an empty difference.
5. The Locale Dictionary shall not collide with or overwrite any pre-existing top-level frontend i18n key when the new namespaces are added.

### Requirement 4: Safe Fallback for Missing Keys
**Objective:** As a backend service author who may ship code ahead of a translation update, I want missing translation keys to produce a visible warning without crashing the request or background task, so that incomplete locale dictionaries degrade gracefully.

#### Acceptance Criteria
1. If a `t(key, ...)` call references a key that exists in neither the active locale nor the `zh` fallback, the Locale Helper shall return a non-empty string (the key itself or an explicit placeholder) rather than `None` or raising.
2. If a `t(key, ...)` call references a missing key, the Locale Helper shall emit a single warning-level log record identifying the missing key, the active locale, and (when available) the call site context.
3. The Locale Helper shall not raise `KeyError`, `AttributeError`, or `TypeError` for any key lookup, irrespective of nesting depth or invalid path segments.
4. When `t()` is invoked from a background thread that called `set_locale(...)` at entry, the Locale Helper shall resolve the locale set on that thread for the entire call chain.

### Requirement 5: Verification and Regression Guards
**Objective:** As a reviewer of this PR, I want repeatable mechanical checks that prove the in-scope files are clean of stray Chinese log/response strings, so that the acceptance criteria can be re-validated on every future change.

#### Acceptance Criteria
1. The Verification Script shall, when run against the repository, report zero matches for the regular expression `logger\.[a-z]+\(["'][^"']*[一-鿿]` across the listed in-scope modules.
2. The Verification Script shall, when run against the repository, report zero matches for any `jsonify({"error": "<chinese>"})` or `jsonify({"message": "<chinese>"})` literal in the listed in-scope API modules.
3. The Verification Script shall, when run against `locales/en.json` and `locales/zh.json`, confirm that every newly introduced key path exists in both files (structural-key parity) and exit non-zero if a key is present in only one file.
4. The Verification Script shall be runnable from the repository root using only tools already available in the dev environment (`grep`, `python`, or `jq` — no new dependencies introduced).
5. The Backend Test Suite shall continue to pass (`uv run python -m pytest`) after the externalization changes, with no new failures introduced by the rename of message strings.
