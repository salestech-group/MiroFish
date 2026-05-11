# Requirements Document

## Introduction

After ticket #6 externalised most backend log/print messages into the project's `t()` localization helper, a small set of call sites in three modules still emit hard-coded Chinese strings. As a result, English operators reading backend logs under the `en` locale see Chinese text leaking from these residual sites. This spec finishes the job for ticket #24 by routing every remaining hard-coded Chinese log/print string in `backend/app/api/graph.py`, `backend/app/services/oasis_profile_generator.py`, and `backend/app/utils/retry.py` through `t("log.<domain>.<key>", **fmt)` and adding the corresponding entries to `locales/en.json` and `locales/zh.json`. The goal is locale-correct backend logs with zero behavioural drift in HTTP responses, control flow, or interpolated values.

## Boundary Context

- **In scope**:
  - Replace the Chinese string literals in the nine call sites listed by ticket #24:
    - `backend/app/api/graph.py:385` — `build_logger.info(f"[{task_id}] 开始构建图谱...")`
    - `backend/app/api/graph.py:494` — `build_logger.info(f"[{task_id}] 图谱构建完成: graph_id={graph_id}, 节点={node_count}, 边={edge_count}")`
    - `backend/app/api/graph.py:513` — `build_logger.error(f"[{task_id}] 图谱构建失败: {str(e)}")`
    - `backend/app/services/oasis_profile_generator.py:945` — `print(f"开始生成Agent人设 - 共 {total} 个实体，并行数: {parallel_count}")`
    - `backend/app/services/oasis_profile_generator.py:1001` — `print(f"人设生成完成！共生成 {len([p for p in profiles if p])} 个Agent")`
    - `backend/app/utils/retry.py:55` — `logger.error(f"函数 {func.__name__} 在 {max_retries} 次重试后仍失败: {str(e)}")`
    - `backend/app/utils/retry.py:108` — `logger.error(f"异步函数 {func.__name__} 在 {max_retries} 次重试后仍失败: {str(e)}")`
    - `backend/app/utils/retry.py:179` — `logger.error(f"API调用在 {self.max_retries} 次重试后仍失败: {str(e)}")`
    - `backend/app/utils/retry.py:227` — `logger.error(f"处理第 {idx + 1} 项失败: {str(e)}")`
  - Add new locale keys for the externalised strings to both `locales/en.json` (English) and `locales/zh.json` (verbatim original Chinese) under the existing top-level `log.<domain>` namespaces (`log.graph_api`, `log.profile_generator`, and a new `log.retry`).
  - Pass interpolated values (`task_id`, `graph_id`, `node_count`, `edge_count`, `total`, `parallel_count`, `func_name`, `max_retries`, `idx`, exception text, etc.) through `t()` keyword arguments using the helper's `{name}` placeholder syntax.
- **Out of scope**:
  - Other Chinese strings in the same files that are not on the ticket's evidence list (Chinese docstrings, Chinese inline comments, the `task_manager.update_task(... message="...")` Chinese values in `graph.py`, the `logger.warning("…重试…")` calls in `retry.py`, and the in-loop `progress_callback(... f"已完成 …")` and `print(f"-" * 70 …)` decorations in `oasis_profile_generator.py`). Those are tracked elsewhere (#7 for docstrings/comments; #25 for prompt/context labels; future audit may pick up the remaining warning-level retry strings under a separate ticket).
  - Any change to log levels, response status codes, control flow, public API surface, or to the `t()` helper itself.
  - Adding a new locale or changing the per-thread / per-request locale resolution.
  - Frontend `vue-i18n` files; this spec touches only backend usage of `t()` and the shared `locales/{en,zh}.json`.
- **Adjacent expectations**:
  - The `t()` helper at `backend/app/utils/locale.py` already covers `set_locale`, `get_locale`, missing-key fallback, and per-thread locale (verified by ticket #6). New code reuses it without modification.
  - The two top-level `log` sub-namespaces `log.graph_api` and `log.profile_generator` already exist in `locales/en.json` / `locales/zh.json` with `m###` numeric suffixes; new keys must use the next available `m###` slot in each existing namespace and must not collide with or overwrite any existing key.
  - `retry.py` is module-level shared infrastructure used from request handlers, background tasks, and async coroutines — locale resolution must continue to work in each of these contexts without new wiring (Requirement 4 below documents this explicitly so behaviour is mechanically verified).
  - Ticket #24's acceptance criterion mentions a verification script under `.kiro/specs/i18n-e2e-english-verification/audit/scripts/run_audit.sh`. That script is not present in the repository at this commit; this spec substitutes a deterministic regex audit (see Requirement 5) that is runnable from the repo root with `grep` + `python` only and that any future `run_audit.sh` can incorporate.

## Requirements

### Requirement 1: Externalise Remaining Chinese Log/Print Strings via `t()`

**Objective:** As a backend operator viewing logs under the `en` locale, I want every Chinese log/print string in the nine listed call sites to be emitted via the existing `t()` helper, so that backend logs no longer leak Chinese text in English deployments.

#### Acceptance Criteria

1. The Backend Logging Layer shall replace the f-string argument of each of the three `build_logger.{info,error}` calls in `backend/app/api/graph.py` at lines 385, 494, and 513 with `t("log.graph_api.<key>", task_id=task_id, ...)`, where the key is a new entry under the existing `log.graph_api` namespace.
2. The Backend Logging Layer shall replace the f-string argument of each of the two `print(...)` calls in `backend/app/services/oasis_profile_generator.py` at lines 945 and 1001 with `print(t("log.profile_generator.<key>", ...))`, keeping the `print` call (so console-output behaviour is preserved) but routing the message text through `t()` under the existing `log.profile_generator` namespace.
3. The Backend Logging Layer shall replace the f-string argument of each of the four `logger.error` calls in `backend/app/utils/retry.py` at lines 55, 108, 179, and 227 with `t("log.retry.<key>", **kwargs)`, introducing a new top-level sub-namespace `log.retry` that mirrors the structure of the other `log.<domain>` sub-namespaces.
4. The Backend Logging Layer shall preserve every interpolated value (`task_id`, `graph_id`, `node_count`, `edge_count`, `total`, `parallel_count`, `func.__name__`, `max_retries`, `idx`, exception text) by passing them as keyword arguments to `t(...)` and referencing them via `{name}` placeholders inside the locale dictionaries; no `f"..."` formatting, `%`-formatting, or string concatenation shall remain around the call.
5. The Backend Logging Layer shall not contain any Chinese character (Unicode range `U+4E00`–`U+9FFF`) inside the string-literal argument of any `logger.{info,warning,error,debug,exception}`, `build_logger.{info,warning,error,debug,exception}`, or `print(...)` call at the nine listed line locations after the change.

### Requirement 2: Locale Dictionary Parity for the New Keys

**Objective:** As a translator or developer adding a new locale, I want every newly externalised key to exist in both `locales/en.json` and `locales/zh.json` with identical nested structure, so that the locale files remain mechanically diffable.

#### Acceptance Criteria

1. The Locale Dictionary shall add, in `locales/en.json`, an English translation for every key introduced by Requirement 1, placed under the relevant `log.<domain>` sub-namespace (`log.graph_api`, `log.profile_generator`, or the new `log.retry`).
2. The Locale Dictionary shall add, in `locales/zh.json`, the original Chinese text (verbatim, with `{placeholder}` substitutions where the source had `f"…{var}…"`) for every key introduced by Requirement 1, under the same key path used in `en.json`.
3. The Locale Dictionary shall use the next available `m###` numeric suffix per existing sub-namespace (so it does not overwrite or shadow any pre-existing `log.graph_api.m###` or `log.profile_generator.m###` key); the new `log.retry` sub-namespace shall start its keys at `m001`.
4. The Locale Dictionary shall expose a structurally identical key tree across `locales/en.json` and `locales/zh.json` for every newly added key path: a recursive comparison of the two files' key paths (ignoring values) shall produce an empty difference for the keys this spec introduces.
5. The Locale Dictionary shall not introduce a new top-level key (the only addition is the new `log.retry` sub-key under the existing top-level `log` namespace) and shall not modify, remove, or re-order any existing key already present in `locales/{en,zh}.json`.

### Requirement 3: Behavioural and Functional Equivalence

**Objective:** As a reviewer, I want to confirm that swapping the message strings does not change runtime behaviour, so that this PR is purely a localisation change.

#### Acceptance Criteria

1. The Graph Build Pipeline shall, after the change, continue to: update `project.status` to `GRAPH_BUILDING` then `GRAPH_COMPLETED` (or `FAILED` on error), call `task_manager.update_task(...)` with the same status/progress/result payloads, and emit one log record at each of the three pre-existing log points (start, completion, failure) with identical level (`info`/`info`/`error`) and identical interpolated values; only the human-readable text and its language source shall differ.
2. The Profile Generator shall, after the change, continue to print exactly two banner messages around `concurrent.futures.ThreadPoolExecutor`-driven generation (one before, one after), retain the surrounding `'='*60` separator lines verbatim, and not emit additional log records or alter the order of `logger.info`/`logger.warning` calls.
3. The Retry Utility shall, after the change, continue to: raise the original exception after the final retry, sleep for the same backoff durations, and emit exactly one `logger.error` per call site at the same control-flow position; the helper's signature, decorator behaviour, and async/sync split shall be unchanged.
4. The Backend HTTP Layer shall return the same HTTP status code, response key set, and (for non-translated keys) value structure for `/api/graph/build` and any other endpoint that transitively triggers the touched code paths; no `jsonify(...)` payload shape shall change as a side-effect of this work.

### Requirement 4: Locale Resolution in Background and Async Contexts

**Objective:** As a backend service author, I want the new `t()` calls to resolve to the correct locale even when invoked from background threads or async coroutines, so that operators see consistent log language regardless of where the call originates.

#### Acceptance Criteria

1. When `t("log.graph_api.<key>", ...)` is called from the `build_task` background thread inside `backend/app/api/graph.py` (started via `task_manager.run_task`), the Locale Helper shall resolve to the locale that was established for that thread (per the existing per-thread / `set_locale` mechanism), not silently fall back to the default `zh`.
2. When `t("log.retry.<key>", ...)` is called from the synchronous `retry_with_backoff` decorator wrapping a Flask request handler, the Locale Helper shall resolve via the active Flask request context (`Accept-Language` header), consistent with how request-scoped `t()` calls behave elsewhere in the codebase.
3. When `t("log.retry.<key>", ...)` is called from the asynchronous `retry_with_backoff_async` decorator under `asyncio`, the Locale Helper shall resolve via whichever locale source is in scope for that coroutine (request context if present; otherwise the per-thread fallback set by the caller), without raising and without requiring any new locale-propagation wiring inside `retry.py`.
4. If a `t()` call introduced by this spec references a key that is missing from both the active locale and the `zh` fallback, the Locale Helper shall continue to behave per the existing contract: emit a single deduped warning naming the key and locale, and return the key string itself (never `None`, never raise).

### Requirement 5: Verification and Regression Guards

**Objective:** As a reviewer of this PR, I want repeatable mechanical checks that prove the in-scope files are clean of stray hard-coded Chinese log/print strings on those nine lines, so that the acceptance criteria can be re-validated on every future change.

#### Acceptance Criteria

1. The Verification Procedure shall, when run against the repository, report zero matches of any Unicode CJK character (range `U+4E00`–`U+9FFF`) on the nine specific lines covered by Requirement 1 in their post-change form (i.e., `grep -P "[一-鿿]"` against the replaced lines returns no hits).
2. The Verification Procedure shall, when run against `locales/en.json` and `locales/zh.json`, confirm via a Python `json.load` + recursive key walk that every newly introduced key path exists in both files, and exit non-zero if a key path is present in only one of them.
3. The Verification Procedure shall confirm via Python that for each new key in `locales/zh.json` whose source f-string contained an `{var}` placeholder, the same `{var}` placeholder appears in the new English translation in `locales/en.json` (so interpolation is not silently dropped during translation).
4. The Verification Procedure shall require only tools already available in the dev environment (`grep`, `python3`, optional `jq`) — no new runtime or dev dependencies shall be added by this spec.
5. The Backend Test Suite shall continue to pass (`uv run python -m pytest`) after the change, with no new failures introduced; in particular, any pre-existing tests that assert the prior Chinese log/print text shall be updated to assert via the same `t()` lookup or an English translation rather than removed.
