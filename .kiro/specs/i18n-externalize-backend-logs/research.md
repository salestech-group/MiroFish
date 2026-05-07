# Gap Analysis — i18n-externalize-backend-logs

## 1. Current State Investigation

### Locale infrastructure already in place
- `backend/app/utils/locale.py` exposes `set_locale(locale)`, `get_locale()`, `t(key, **kwargs)`, and `get_language_instruction()`. Translations are loaded once at import time from every `*.json` in `/locales/` (excluding `languages.json`).
- `t()` resolves a dotted key, falls back to the `zh` dictionary if the active locale lacks the key, then returns the raw key string if both are missing. **No warning is emitted on miss.**
- Interpolation uses `{name}` placeholders applied via `str.replace`. There is no support for `%s`/`%d`/`{}` (numeric) — call sites must use named placeholders.
- Locale is request-scoped via the `Accept-Language` header, and background-thread-scoped via `set_locale(...)` / `_thread_local.locale`. A few entry points already call `set_locale(...)` (e.g. `report.py`, `graph_builder.py`, `simulation_runner.py`, `oasis_profile_generator.py`, `zep_graph_memory_updater.py`).

### Locale dictionaries
- `locales/en.json` and `locales/zh.json` already share top-level namespaces `log` and `api` — but every existing `log.*` / `api.*` key currently lives **at depth 2** (e.g. `log.preparingGoBack`, `api.projectNotFound`). Existing `log.*` keys are exclusively consumed by the **frontend** (`frontend/src/views/*.vue`, `frontend/src/components/Step*.vue`).
- Existing `api.*` keys are already used by the backend (`backend/app/api/report.py` uses 27 of them — `api.requireSimulationId`, `api.simulationNotFound`, etc.). So `api.*` is a shared backend/frontend namespace.
- Both files are 665 lines, structurally identical (same line count and JSON shape), so adding new sub-namespaces (`log.graph.*`, `log.simulation.*`, `api.error.*`) will not collide with the existing flat keys.

### In-scope file inventory (Chinese-character occurrences)

Counted by regex over `logger.{info,warning,error,debug,exception}(...)` and `jsonify(...)` call expressions:

| File | logger w/ ZH | jsonify w/ ZH | Notes |
| --- | ---: | ---: | --- |
| `backend/app/services/zep_tools.py` | 51 | 0 | Largest single contributor. Many `f"..."` interpolations. |
| `backend/app/services/simulation_runner.py` | 40 | 0 | Background runner; `set_locale` already wired. |
| `backend/app/services/oasis_profile_generator.py` | 23 | 0 | `set_locale` already wired. |
| `backend/app/services/simulation_config_generator.py` | 14 | 0 | |
| `backend/app/services/zep_graph_memory_updater.py` | 14 | 0 | `set_locale` already wired. |
| `backend/app/services/zep_entity_reader.py` | 10 | 0 | |
| `backend/app/services/simulation_ipc.py` | 5 | 0 | |
| `backend/app/services/simulation_manager.py` | 3 | 0 | `t()` already imported. |
| `backend/app/services/report_agent.py` | 1 | 0 | Sibling spec already covered prompts. |
| `backend/app/services/ontology_generator.py` | 0 | 0 | Already clean. |
| `backend/app/services/graph_builder.py` | 0 | 0 | Already clean. |
| `backend/app/api/simulation.py` | 55 | 59 | Largest API surface; **many** error responses still in Chinese. |
| `backend/app/api/report.py` | 19 | 0 | jsonify side already i18n-ized; logger calls remain. |
| `backend/app/api/graph.py` | 15 | 20 | |
| **Totals** | **250** | **79** | |

### Conventions observed
- Loggers are obtained via `from ..utils.logger import get_logger; logger = get_logger('mirofish.<area>')`.
- Many existing log lines use f-strings: `logger.info(f"加载了 {n} 个agent")`. These need to become `t("log.<…>", n=n)` with `{n}` placeholder syntax (not `{0}` or `%s`).
- A few occurrences shadow `t` as a loop/comprehension variable (`[t.strip() for t in ...]`, `for t, examples in ...`). In Python 3 these comprehension scopes are local and won't collide with the module-level `t()` import — safe to leave alone.
- Existing `report.py` already imports `from ..utils.locale import t, get_locale, set_locale` — this is the canonical import shape for API modules.
- `models/task.py` and `services/simulation_manager.py` already use `t()` in places — extend, don't reinvent.

### Out-of-scope traffic on the same files
- The sibling spec `i18n-report-agent-prompts` (already merged into the current branch's history) externalized **prompts** in `report_agent.py`. This spec must keep its hands off prompt strings and only touch the residual `logger.*` / `jsonify({"error|message": …})` literals.
- `#7` covers Chinese docstrings/comments — leave alone.
- `#2/#3/#4/#5` cover ontology/profile/config/report **prompt** text — leave alone.

## 2. Requirements Feasibility Map

| Requirement | Existing Asset | Gap | Tag |
| --- | --- | --- | --- |
| **R1** Externalize logger ZH messages | `t()` helper, `logger` factory | ~250 call sites to rewrite + ~250 new keys | Missing translations |
| **R2** Externalize API jsonify ZH messages | `t()` helper, partial `report.py` precedent | ~79 call sites in `simulation.py` / `graph.py` + ~80 new keys | Missing translations |
| **R3** Locale dict parity (en/zh same shape) | `en.json` and `zh.json` already structurally identical | New nested namespaces `log.<domain>.<key>`, `api.error.<scope>`, `api.message.<scope>` to add to both | Missing namespace + needs verifier |
| **R4** Safe missing-key fallback (warns, doesn't crash) | `t()` returns the raw key on miss | **Missing**: a `logger.warning(...)` on miss path; verify thread-local locale propagation | Missing capability (small) |
| **R5** Verification guards | None today | Need `grep`/`python` script(s) that report 0 ZH in scope and assert key parity | Missing tooling |

## 3. Implementation Approach Options

### Option A — Pure file-by-file inline rewrite (recommended)
- For each in-scope file: import `t` from `..utils.locale`, walk every Chinese `logger.*` and `jsonify(...)` call, replace with `t("log.<domain>.<key>", **fmt)` / `t("api.error.<scope>", **fmt)`, and add the matching key to both locale JSONs.
- Group keys under the existing `log` and `api` top-level namespaces but **one level deeper** (`log.zep_tools.*`, `log.simulation.*`, `log.runner.*`, `api.error.simulation.*`, `api.error.graph.*`) to avoid colliding with the flat frontend keys already in `en.json`/`zh.json`.
- Implement R4 inside `t()` itself (single function — minimal blast radius): emit a `logging.getLogger(...).warning("missing translation key: %s (locale=%s)", key, locale)` on miss, **memoized per (locale, key)** so warnings don't spam.
- Add verification: a small `scripts/check_i18n_logs.py` (or just a docs snippet using `grep` + `jq`) per R5.

**Trade-offs**
- ✅ Smallest delta, fits the project's "no new framework" constraint, mirrors existing `report.py` precedent.
- ✅ Easy to PR-split per area if PR grows.
- ❌ ~330 mechanical edits across 12 files. Tedious, easy to leave a stray ZH literal — mitigated by R5 verification.

### Option B — AST-driven codemod
- Write a one-shot `libcst`/`ast` pass that walks each file, extracts every Chinese string literal under a `logger.*` / `jsonify({"error|message": ...})` Call node, generates a key, rewrites in place, and emits the locale JSON entries.
- Run once, commit the result.

**Trade-offs**
- ✅ Mechanical correctness — no missed call sites.
- ❌ Adds a one-shot dep (`libcst`) the project doesn't currently use; conflicts with the "no new dep without justification" rule.
- ❌ Generated keys tend to be ugly (`log.zep_tools.line_142`); we'd post-process anyway.
- ❌ Existing f-strings (`f"加载了 {n} 个agent"`) need manual conversion to `t("…", n=n)` because the AST has to understand the f-string AST and reverse-engineer placeholder names — non-trivial.

### Option C — Hybrid (manual rewrites + small verifier)
- Manual rewrites per Option A, but use a tiny disposable script during the work (`scripts/scan_zh.py`) to enumerate every remaining ZH-bearing logger/jsonify line so the human (or me) doesn't miss any. The script becomes the verifier guard required by R5.

**Trade-offs**
- ✅ Same outcome as Option A but with continuous progress tracking and a re-runnable guard at the end.
- ✅ The verifier doubles as the R5 deliverable.
- ❌ Slightly more upfront work (writing the scanner) — but the script is also a CI-friendly artefact.

## 4. Effort & Risk

- **Effort: M (3–7 days for a human; ~1 session at this scale for an autonomous run)** — ~330 mechanical edits + 330 locale entries + small `t()` enhancement + verifier. No architectural changes.
- **Risk: Low/Medium** —
  - Low for the locale-helper edit (small, well-isolated).
  - Medium for the bulk rewrite: easy to leave stray ZH literals, easy to break interpolation by passing positional args. Mitigated by the R5 verifier and a final regex sweep.
  - Watch: `t` shadowing in comprehensions (cosmetic, no functional issue thanks to comprehension scope), preserving HTTP status codes on jsonify rewrites, keeping `success`/`traceback`/etc. fields intact.

## 5. Recommendations for Design Phase

- **Adopt Option C.** A small `scripts/check_i18n_logs.py` doubles as both the R5 acceptance check and a working aid during the rewrite. No new runtime deps.
- **Key namespace decision** to lock in during design:
  - `log.<module_short>.<snake_case_summary>` for logger calls (e.g. `log.zep_tools.entity_count_loaded`, `log.simulation_runner.platform_completed`).
  - `api.error.<module>.<scope>` for `jsonify({"error": …})`.
  - `api.message.<module>.<scope>` for `jsonify({"message": …})`.
  - Keep the existing flat `api.*` keys (used heavily by `report.py`) untouched.
- **`t()` helper extension**: emit a single deduplicated warning per missing `(locale, key)` pair. Use `logging.getLogger("mirofish.locale")`. Add a unit test (or a smoke check inside the verifier) that exercises a known-missing key and asserts the warning fires without raising.
- **Locale dictionary mechanics**: maintain alphabetical ordering inside each new sub-namespace and re-sort on update so diffs stay reviewable.
- **Research carried into design**:
  - Confirm every background-task entry point that may emit logs from the in-scope modules calls `set_locale(...)` at thread start (current coverage looks complete — worth a quick re-scan).
  - Decide whether to include the verifier in `package.json`/`Makefile` invocation or leave it as a documented one-liner. The ticket only asks that it be runnable from existing tools, so the lighter touch is fine.
