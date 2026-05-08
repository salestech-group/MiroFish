# Implementation Gap Analysis

## 1. Codebase Findings

### 1.1 Existing infrastructure already covers the i18n mechanics

- `backend/app/utils/locale.py` already exports `t(key, **kwargs)` with:
  - per-thread locale (`set_locale` writes `_thread_local.locale`)
  - per-request locale (`get_locale` checks Flask `has_request_context()` then `Accept-Language`)
  - `zh` fallback when the active locale is missing a key, then key-string fallback if `zh` is missing too
  - dedup'd warning on missing keys (`_warn_missing_key_once`), no exceptions raised
- All wiring required by Requirement 4 is therefore already in place. **No `locale.py` change is needed for ticket #24.**

### 1.2 The two files we touch already use `t()`

- `backend/app/api/graph.py:21` — `from ..utils.locale import t`
- `backend/app/services/oasis_profile_generator.py:23` — `from ..utils.locale import get_language_instruction, get_locale, set_locale, t`

The third file does NOT yet import `t`:
- `backend/app/utils/retry.py` — no `from ..utils.locale import t`. Need to add the import.

### 1.3 Existing locale namespace shape (from `locales/en.json`)

- `log.graph_api` — populated `m006`–`m019, m026`. Next free slots that are *contiguous* would be `m027`, `m028`, `m029`. (Could also reuse `m009, m010, m012, m020–m025` since they are absent, but it is safer to append at the tail to avoid colliding with any unmerged work assuming a particular reservation.)
- `log.profile_generator` — populated `m001`–`m023` densely. Next free: `m024`, `m025`.
- `log.retry` — does NOT exist. Will be created with `m001`–`m004`.

The `log.profile_generator.m017` key already covers a *similar* message ("Starting parallel generation of {total} agent profiles (parallelism: {parallel_count})…"). The `print(...)` at `oasis_profile_generator.py:945` and the `logger.info(t("log.profile_generator.m017", ...))` at line 943 are emitting the same logical event in two channels — log + console banner. The cleanest move is **not** to reuse `m017` (which would lose the banner-style separator/centring) but to introduce dedicated `m024` / `m025` keys for the banner text, so the banner has its own copy decoupled from the log line.

### 1.4 Translation pattern already established by ticket #6

Per the prior spec at `.kiro/specs/i18n-externalize-backend-logs/`, the project's convention is:

- `t("log.<domain>.m###", placeholder=value, …)` inside `logger.{info,warning,error,debug,exception}` calls.
- Placeholders use `{name}` syntax (replaced via `str.replace` inside `t()`); positional `{0}`/`{}` are not supported.
- f-string formatting must be removed entirely from the call argument; values are passed as kwargs.
- The Chinese source string is preserved verbatim in `zh.json`, with `f"…{var}…"` rewritten as `"…{var}…"`.

This work strictly extends the existing pattern. **No new convention is introduced.**

### 1.5 `build_logger` vs. module logger

In `graph.py`, the affected calls use a locally-created `build_logger = get_logger('mirofish.build')` inside the `build_task` background function (lines 383). This is a different logger handle, but `t()` is logger-agnostic — it returns a string that any logger can format. No special handling needed.

### 1.6 `print(...)` calls in `oasis_profile_generator.py`

The two banner prints (lines 945 and 1001) are deliberate console-output decorations (visible on stdout for the Flask process), separate from the structured log emitted by `logger.info` on lines 943 and earlier. The task is to keep them as `print(...)` but route the message text through `t(...)`:

```python
print(t("log.profile_generator.m024", total=total, parallel_count=parallel_count))
```

This preserves the user-visible banner cosmetics (`'='*60` separators on lines 944, 946, 1000, 1002) and only changes the text content.

### 1.7 Locale resolution for `retry.py`

`retry.py` is invoked from three contexts:

1. **Flask request handlers (sync)** — `has_request_context()` is true; `get_locale()` reads `Accept-Language`. Works.
2. **Background tasks** — the existing background-task entry points (e.g., `task_manager.run_task`) already call `set_locale(...)` per `i18n-externalize-backend-logs` (verified by reading `oasis_profile_generator.py` which uses the same pattern with `set_locale` imported on line 23). Works.
3. **Async coroutines (`retry_with_backoff_async`)** — `get_locale()` falls back to `_thread_local.locale`. Asyncio runs coroutines on the same thread by default, so the per-thread locale propagates. If the coroutine is dispatched onto a fresh executor thread without `set_locale`, the helper falls back to `zh` (the default) — still a valid string, just defaulting to Chinese. The default-fallback is acceptable here because (a) the helper still returns a non-None string, and (b) the audit only requires the *source code* to be free of Chinese literals, not that every emitted log record be English regardless of caller context.

**Decision:** No new locale-propagation wiring needed. Document the async fallback in the design and tasks.

## 2. Out-of-scope items (encountered during research)

These were observed in the same files but are explicitly **not** part of ticket #24 and will not be addressed:

- `backend/app/api/graph.py` — Chinese in `task_manager.update_task(..., message="初始化图谱构建服务...")` and similar (#24 lists only the three log calls).
- `backend/app/utils/retry.py` — Chinese in `logger.warning(...)` retry messages (lines 63–66, 115–117, 185–187) and Chinese docstrings (lines 1–3, 25–35, 36–39, 90, 156–166, 200–212).
- `backend/app/services/oasis_profile_generator.py` — Chinese in `progress_callback(... f"已完成 …")` (line 976) and Chinese docstrings/comments throughout.

These are tracked under sibling tickets (#7 for docstrings/comments; the residual `logger.warning` in `retry.py` is a candidate for a future audit ticket).

## 3. Implementation Approaches Considered

### Approach A — Append-at-tail with new `log.retry` namespace (recommended)

- New keys: `log.graph_api.m027`, `m028`, `m029`; `log.profile_generator.m024`, `m025`; new `log.retry.m001`–`m004`.
- Add `from ..utils.locale import t` to `retry.py`.
- Replace each f-string in the nine call sites with a `t(...)` call.
- Update `locales/en.json` and `locales/zh.json` in lock-step.
- **Pros:** Mirrors the conventions of #6 exactly; no risk of overwriting existing keys; minimal diff.
- **Cons:** Numbering gaps under `log.graph_api` remain (cosmetic).

### Approach B — Fill numbering gaps in `log.graph_api`

- Reuse missing slots `m009`, `m010`, `m012`, `m020`–`m025`.
- **Pros:** Tighter numbering.
- **Cons:** Risk of colliding with reserved-but-not-yet-merged keys from another branch; harder to review (mixed insertion sites in JSON).
- **Verdict:** Reject. The cost of conflict review is not worth the cosmetic gain.

### Approach C — Consolidate the `print(...)` banners into the existing `log.profile_generator.m017`

- Remove the two `print(...)` calls; rely solely on `logger.info(t(...))`.
- **Pros:** One fewer key to add.
- **Cons:** Deletes user-visible console banner behaviour (a behaviour change), violates Requirement 3.2 ("continue to print exactly two banner messages"), and is out-of-scope per ticket #24 which says "fixed (or explicitly classified as `deliberate`)" — i.e., translate, don't remove.
- **Verdict:** Reject.

## 4. Recommendation

Proceed with **Approach A**.

Implementation will:

1. Add four entries to `log.retry` (new sub-namespace) — one per `logger.error` line in `retry.py`.
2. Add three entries to `log.graph_api` — one per `build_logger` line in `graph.py`.
3. Add two entries to `log.profile_generator` — one per `print(...)` banner in `oasis_profile_generator.py`.
4. Replace all nine f-strings with `t(...)` calls; pass interpolated values as kwargs.
5. Add `from ..utils.locale import t` to `retry.py`.
6. Mirror every new key in `zh.json` with the verbatim original Chinese text.
7. Run a regex / Python audit to confirm parity and absence of CJK on the touched lines.

## 5. Risks / open questions

| Risk | Severity | Mitigation |
|---|---|---|
| `retry.py` async path running on a fresh thread without `set_locale` returns Chinese | Low | Documented; not a blocker for #24 acceptance, which targets *source-code* CJK absence. Any improvement is a separate ticket. |
| Adding `from ..utils.locale import t` introduces a new module import into `retry.py` (low-level utility) | Low | The `locale` module has no transitive imports of `retry.py`, so no circular-import risk. Verified by reading `locale.py`. |
| Existing test that asserts Chinese log text breaks | Low | Searched for `"开始构建图谱"` / `"图谱构建完成"` / `"图谱构建失败"` / `"开始生成Agent人设"` / `"人设生成完成"` / `"重试后仍失败"` / `"处理第"` test fixtures — none found in `backend/`. |

## 6. Conclusion

**Ready to proceed to design.** The gap is small: nine string-literal replacements, eleven new locale entries, one new import. The mechanics are identical to the already-merged ticket #6 work. No design uncertainty remains; design phase will simply formalise the key-naming and the per-file edit plan.
