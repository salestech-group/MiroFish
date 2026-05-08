# Design Document

## Overview

**Purpose**: Replace the last nine hard-coded Chinese log/print strings in three backend modules (`backend/app/api/graph.py`, `backend/app/services/oasis_profile_generator.py`, `backend/app/utils/retry.py`) with calls to the existing `t("log.<domain>.<key>", **kwargs)` helper, and add the corresponding entries to `locales/en.json` and `locales/zh.json`. The result is locale-correct backend logs with zero behavioural drift.

**Users**: Backend operators reading logs in English deployments; existing Chinese-locale operators (preserved verbatim).

**Impact**: Removes the last sources of Chinese-text leakage in backend logs under the `en` locale, completing the i18n coverage started by ticket #6.

### Goals

- Replace the nine f-string arguments listed in ticket #24 with `t("log.<domain>.<key>", **kwargs)` calls.
- Add eleven new locale entries (3 in `log.graph_api`, 2 in `log.profile_generator`, 4 in new `log.retry`) to both `locales/en.json` and `locales/zh.json` with key parity.
- Preserve all interpolated values, all log levels, all control flow, and all `print(...)` console banners.

### Non-Goals

- Translating other Chinese strings in the same files (docstrings, comments, `update_task` messages, `progress_callback` messages, `logger.warning` retry messages) — out of scope for ticket #24.
- Modifying the `t()` helper, the locale resolution logic, or the locale dictionary structure (other than adding the listed keys).
- Frontend `vue-i18n` translation work or schema changes to `locales/{en,zh}.json`.
- Adding test infrastructure, the `run_audit.sh` script, or any new dev dependency.

## Boundary Commitments

### This Spec Owns

- The string-literal contents of nine specific `logger.{info,error}` and `print(...)` call sites (exact `file:line` listed in Requirement 1).
- Eleven new translation entries in `locales/en.json` and `locales/zh.json`.
- The new `log.retry` sub-namespace under the existing top-level `log` key.

### Out of Boundary

- Other Chinese strings in the three modified files.
- Any change to public API contracts, log levels, or response payloads.
- Any change to the `t()` helper or the per-thread / per-request locale resolution logic.
- Frontend `zh.json` entries beyond the ones this spec must add for backend parity (i.e., none — frontend keys are untouched).

### Allowed Dependencies

- `backend/app/utils/locale.py` (`t`) — already in use, just import it where needed.
- The existing locale dictionaries `locales/{en,zh}.json` — extend, don't re-organise.
- `get_logger` from `backend/app/utils/logger.py` — already imported by `retry.py`.

### Revalidation Triggers

- Renaming `t()` or moving it to a different module.
- Changing the placeholder syntax in `t()` from `{name}` to anything else.
- Restructuring `locales/en.json` / `zh.json` (e.g., flattening `log.<domain>.m###` into a flat key tree).

## Architecture

### Existing Architecture Analysis

This spec extends a pattern already established by ticket #6 (`i18n-externalize-backend-logs`). The convention is:

1. Source-code call sites use `t("log.<domain>.m###", placeholder=value, …)` instead of `f"…{value}…"`.
2. Each `t()` key has matching entries in `locales/en.json` (English copy) and `locales/zh.json` (verbatim original Chinese).
3. Placeholders use `{name}` (replaced via `str.replace` inside `t()`).
4. The locale is resolved per request (`Accept-Language`) or per thread (`set_locale`); `'zh'` is the default fallback; missing keys return the key string and emit a deduped warning.

The constraint: only the nine listed call sites change. No new architecture, no new component, no new integration point.

### Architecture Pattern & Boundary Map

The change is a **pure string-externalisation extension** of the existing localisation pattern. No new components, no new flows, no new dependencies. The only structural addition is a new `log.retry` sub-namespace inside the existing top-level `log` key in the locale dictionaries.

```mermaid
flowchart LR
    A[graph.py:385/494/513<br/>build_logger.{info,error}] -->|t("log.graph_api.mNNN", ...)| L[t() helper<br/>backend/app/utils/locale.py]
    B[oasis_profile_generator.py:945/1001<br/>print(...)] -->|t("log.profile_generator.mNNN", ...)| L
    C[retry.py:55/108/179/227<br/>logger.error] -->|t("log.retry.mNNN", ...)| L
    L --> EN[locales/en.json<br/>log.graph_api.m027-m029<br/>log.profile_generator.m024-m025<br/>log.retry.m001-m004]
    L --> ZH[locales/zh.json<br/>same key paths<br/>verbatim Chinese values]
```

### Technology Stack

| Layer | Choice / Version | Role in Feature | Notes |
|-------|------------------|-----------------|-------|
| Backend / Services | Python ≥3.11 | Source-language change site | No version change |
| Backend / Services | `backend/app/utils/locale.py` (project-internal) | Provides `t(key, **kwargs)` | Reused as-is |
| Data / Storage | `locales/en.json`, `locales/zh.json` | Adds 11 new key/value pairs | Flat JSON, UTF-8 |
| Infrastructure / Runtime | Flask 3.0 / asyncio | Locale resolution context | No runtime change |

## File Structure Plan

### Modified Files

- `backend/app/api/graph.py` — Replace the f-string argument of three `build_logger.{info,error}` calls (lines 385, 494, 513) with `t("log.graph_api.<key>", **kwargs)`. No new imports (already imports `t` on line 21).
- `backend/app/services/oasis_profile_generator.py` — Replace the f-string argument of two `print(...)` calls (lines 945, 1001) with `t("log.profile_generator.<key>", **kwargs)`. No new imports (already imports `t` on line 23).
- `backend/app/utils/retry.py` — Add `from .locale import t` (or `from ..utils.locale import t`, matching the project's existing relative-import style). Replace the f-string argument of four `logger.error` calls (lines 55, 108, 179, 227) with `t("log.retry.<key>", **kwargs)`.
- `locales/en.json` — Append three keys to `log.graph_api`, two to `log.profile_generator`, and a new `log.retry` sub-namespace with four keys.
- `locales/zh.json` — Mirror the same key paths with verbatim original Chinese strings.

No new files. No deleted files.

## Requirements Traceability

| Requirement | Summary | Components | Interfaces | Flows |
|-------------|---------|------------|------------|-------|
| 1.1 | Replace `graph.py` log strings via `t()` | `graph.py` build-task closure | `t("log.graph_api.<key>", ...)` | Build pipeline log emission |
| 1.2 | Replace `oasis_profile_generator.py` banner prints via `t()` | `OasisProfileGenerator.generate_profiles_parallel` | `t("log.profile_generator.<key>", ...)` | Profile-generation banner |
| 1.3 | Replace `retry.py` errors via `t()` (new `log.retry` namespace) | `retry_with_backoff`, `retry_with_backoff_async`, `RetryableAPIClient` | `t("log.retry.<key>", ...)` | Retry-failure path |
| 1.4 | Preserve interpolated values via kwargs | All three modules | `t(key, name=value, ...)` with `{name}` placeholders | All log emission |
| 1.5 | Zero CJK in the listed lines after change | Same as 1.1–1.3 | n/a | n/a |
| 2.1, 2.2 | Add 11 new keys to `en.json` and `zh.json` | Locale dictionaries | JSON file edits | n/a |
| 2.3 | Use next available `m###` slot per namespace | Locale dictionaries | n/a | n/a |
| 2.4 | Structural parity across both files | Locale dictionaries | Verification script | n/a |
| 2.5 | No new top-level keys; no existing keys touched | Locale dictionaries | n/a | n/a |
| 3.1 | Graph build pipeline behaves identically | `graph.py` build-task closure | n/a | Build pipeline |
| 3.2 | Profile generator continues to print exactly two banners | `oasis_profile_generator.py` | n/a | Banner emission |
| 3.3 | Retry semantics unchanged (raise, sleep, level, position) | `retry.py` | n/a | Retry path |
| 3.4 | HTTP responses unchanged | All API endpoints | n/a | n/a |
| 4.1, 4.2, 4.3, 4.4 | Locale resolution works in all contexts | `t()` helper (unchanged) | n/a | n/a |
| 5.1 | CJK regex audit on the nine lines passes | Verification procedure | `grep -P "[一-鿿]"` | n/a |
| 5.2 | Key-parity audit passes | Verification procedure | Python `json.load` walk | n/a |
| 5.3 | Placeholder-integrity audit passes | Verification procedure | Python regex check | n/a |
| 5.4 | Only stock tooling | Verification procedure | `grep`, `python3` | n/a |
| 5.5 | `pytest` continues to pass | Backend test suite | `uv run python -m pytest` | n/a |

## Components and Interfaces

| Component | Domain/Layer | Intent | Req Coverage | Key Dependencies (P0/P1) | Contracts |
|-----------|--------------|--------|--------------|--------------------------|-----------|
| `graph.py` build-task closure | Backend / API | Log graph-build start/complete/fail in active locale | 1.1, 1.4, 1.5, 3.1 | `t()` (P0), `build_logger` (P0) | Behaviour-only |
| OASIS banner prints | Backend / Services | Print banner around parallel profile generation | 1.2, 1.4, 1.5, 3.2 | `t()` (P0) | Console-output |
| Retry error logs | Backend / Utils | Log final-failure errors after retry exhaustion | 1.3, 1.4, 1.5, 3.3 | `t()` (P0), `logger` (P0) | Behaviour-only |
| Locale dictionaries | Backend / Data | Provide en/zh strings for new keys | 2.1–2.5 | JSON parse (P0) | Data |

### Backend / Services

#### `graph.py` build-task closure

| Field | Detail |
|-------|--------|
| Intent | Emit "build started", "build completed", "build failed" log records using `t()` |
| Requirements | 1.1, 1.4, 1.5, 3.1 |

**Responsibilities & Constraints**

- Replace three f-string log arguments only.
- Do not change log level, log handler, control flow, or surrounding `task_manager.update_task(...)` calls.

**Dependencies**

- Inbound: called from `task_manager.run_task` (P0)
- Outbound: `t()` (P0), `build_logger.{info,error}` (P0)

**Contracts**: Service [ ] / API [ ] / Event [ ] / Batch [ ] / State [ ]  ← (none — purely behavioural)

**Key Mapping**

| Line | Existing source | New key | EN translation | ZH translation |
|------|-----------------|---------|----------------|----------------|
| 385 | `f"[{task_id}] 开始构建图谱..."` | `log.graph_api.m027` | `[{task_id}] Starting graph build...` | `[{task_id}] 开始构建图谱...` |
| 494 | `f"[{task_id}] 图谱构建完成: graph_id={graph_id}, 节点={node_count}, 边={edge_count}"` | `log.graph_api.m028` | `[{task_id}] Graph build completed: graph_id={graph_id}, nodes={node_count}, edges={edge_count}` | `[{task_id}] 图谱构建完成: graph_id={graph_id}, 节点={node_count}, 边={edge_count}` |
| 513 | `f"[{task_id}] 图谱构建失败: {str(e)}"` | `log.graph_api.m029` | `[{task_id}] Graph build failed: {e}` | `[{task_id}] 图谱构建失败: {e}` |

**Implementation Notes**

- `t` is already imported at `graph.py:21`.
- Use `e=str(e)` to maintain the existing exception-string semantics.

#### OASIS banner prints (`oasis_profile_generator.py`)

| Field | Detail |
|-------|--------|
| Intent | Wrap the two banner-print arguments in `t()` while leaving the surrounding `'='*60` separator prints intact |
| Requirements | 1.2, 1.4, 1.5, 3.2 |

**Responsibilities & Constraints**

- Replace only the *content* line of each banner (the line at 945 and the line at 1001). The two `'='*60` separator prints around them (lines 944/946 and 1000/1002) contain only ASCII and stay verbatim.
- Do not remove either `print(...)` call.
- Do not modify the existing `logger.info(t("log.profile_generator.m017", …))` at line 943.

**Key Mapping**

| Line | Existing source | New key | EN translation | ZH translation |
|------|-----------------|---------|----------------|----------------|
| 945 | `f"开始生成Agent人设 - 共 {total} 个实体，并行数: {parallel_count}"` | `log.profile_generator.m024` | `Starting agent profile generation — {total} entities, parallelism: {parallel_count}` | `开始生成Agent人设 - 共 {total} 个实体，并行数: {parallel_count}` |
| 1001 | `f"人设生成完成！共生成 {len([p for p in profiles if p])} 个Agent"` | `log.profile_generator.m025` | `Profile generation complete — generated {count} agents` | `人设生成完成！共生成 {count} 个Agent` |

**Implementation Notes**

- The expression `len([p for p in profiles if p])` becomes a kwarg: `count=len([p for p in profiles if p])`. This is a single name, easier for the locale dictionaries.
- `t` is already imported at `oasis_profile_generator.py:23`.

#### Retry error logs (`retry.py`)

| Field | Detail |
|-------|--------|
| Intent | Localise the four "final-failure" `logger.error` strings; introduce `log.retry` sub-namespace |
| Requirements | 1.3, 1.4, 1.5, 3.3, 4.1–4.4 |

**Responsibilities & Constraints**

- Add `from ..utils.locale import t` at the top of `retry.py` (matching the relative-import depth used by other `backend/app/utils/*` files).
- Replace four f-string `logger.error(...)` arguments only.
- Do not touch the `logger.warning(...)` retry-attempt messages (out of scope per ticket #24).
- Do not change exception handling, control flow, or the public decorator/class signatures.

**Key Mapping**

| Line | Existing source | New key | EN translation | ZH translation |
|------|-----------------|---------|----------------|----------------|
| 55 | `f"函数 {func.__name__} 在 {max_retries} 次重试后仍失败: {str(e)}"` | `log.retry.m001` | `Function {func_name} still failing after {max_retries} retries: {e}` | `函数 {func_name} 在 {max_retries} 次重试后仍失败: {e}` |
| 108 | `f"异步函数 {func.__name__} 在 {max_retries} 次重试后仍失败: {str(e)}"` | `log.retry.m002` | `Async function {func_name} still failing after {max_retries} retries: {e}` | `异步函数 {func_name} 在 {max_retries} 次重试后仍失败: {e}` |
| 179 | `f"API调用在 {self.max_retries} 次重试后仍失败: {str(e)}"` | `log.retry.m003` | `API call still failing after {max_retries} retries: {e}` | `API调用在 {max_retries} 次重试后仍失败: {e}` |
| 227 | `f"处理第 {idx + 1} 项失败: {str(e)}"` | `log.retry.m004` | `Failed processing item #{index}: {e}` | `处理第 {index} 项失败: {e}` |

**Implementation Notes**

- Use kwargs `func_name=func.__name__`, `max_retries=max_retries` (or `self.max_retries`), `index=idx + 1`, `e=str(e)`.
- Locale resolution at the call site: in Flask request scope → `Accept-Language`; in background tasks → `set_locale` per-thread; in async coroutines → per-thread (asyncio shares the OS thread). Default fallback is `'zh'`. No new wiring needed (Requirement 4).

### Backend / Data

#### Locale dictionaries

| Field | Detail |
|-------|--------|
| Intent | Provide en/zh strings for the eleven new keys with structural parity |
| Requirements | 2.1, 2.2, 2.3, 2.4, 2.5 |

**Responsibilities & Constraints**

- Append to existing `log.graph_api` and `log.profile_generator` sub-namespaces.
- Add a new `log.retry` sub-namespace as a sibling of the others.
- No top-level key additions; no modifications to any pre-existing key.
- Maintain UTF-8 encoding and the file's existing 2-space indent style.

**Implementation Notes**

- Use `python3 -m json.tool` (or equivalent) to round-trip the JSON files after editing, to ensure formatting consistency.
- Validate parity with a small Python script that recursively compares key paths.

## System Flows

(Skipped — no non-trivial flow change. The build / profile / retry call paths execute as before; only the message text source language differs.)

## Error Handling

### Error Strategy

This spec changes only message-string sources. Error-handling semantics in the touched code are preserved:

- `graph.py:513` continues to set `project.status = ProjectStatus.FAILED` and call `task_manager.update_task(..., status=TaskStatus.FAILED, ...)` after the `build_logger.error(...)` call.
- `retry.py` continues to `raise` the underlying exception after the final `logger.error(...)`.
- The `t()` helper does not raise on missing keys — it returns the key string and emits a deduped warning. This contract is unchanged.

### Error Categories and Responses

Out of scope — no new error category is introduced.

## Testing Strategy

### Unit / Integration Tests

The project does not currently maintain a comprehensive backend unit-test suite for these modules. The change is verified mechanically rather than via new pytest tests:

1. **CJK absence on the touched lines** — `grep -nP "[一-鿿]"` against the nine specific lines must return no matches.
2. **JSON parse + key parity** — a small inline Python check that loads `locales/{en,zh}.json` and asserts every newly-added key path exists in both files.
3. **Placeholder integrity** — for each new key, every `{name}` placeholder in the `zh` value must also appear in the `en` value (and vice versa).
4. **Existing test suite** — `uv run python -m pytest` continues to pass; ticket #6's tests at `backend/scripts/test_profile_format.py` are not affected by this work.

### Manual Smoke Test

After implementation:

- Set `Accept-Language: en` and run an end-to-end graph build via the local Flask app (`npm run dev`); confirm the start / complete / fail log lines render in English.
- Run a profile generation flow and observe the banner prints in English.
- Force a retry exhaustion (e.g., temporarily lower `max_retries=0` and trigger an error) and confirm the `log.retry` message renders in English.

(Manual smoke is documentation-only; not a blocker for merging.)

## Optional Sections

### Security Considerations

None. No auth, no PII, no external integration changes. The exception text in log messages was already exposed via the previous f-string formatting; routing it through `t()` does not change the surface.

### Performance & Scalability

Negligible. `t()` is an in-memory dict lookup with `str.replace` for placeholders; cost is below noise floor for log emission.
