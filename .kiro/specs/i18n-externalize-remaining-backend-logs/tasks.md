# Implementation Plan

- [x] 1. Add three new keys to `log.graph_api` in both locale files
  - In `locales/en.json`, append `m027`, `m028`, `m029` under `log.graph_api` with the English translations from the design's key-mapping table
  - In `locales/zh.json`, append the same three keys under `log.graph_api` with the verbatim original Chinese text (rewriting `f"...{var}..."` as `"...{var}..."`)
  - Confirm via `python3 -m json.tool` that both files round-trip without reformatting other keys
  - Observable completion: `python3 -c "import json; en=json.load(open('locales/en.json'))['log']['graph_api']; zh=json.load(open('locales/zh.json'))['log']['graph_api']; assert {'m027','m028','m029'} <= set(en) <= set(zh) | set(en); print('ok')"` exits zero
  - _Requirements: 2.1, 2.2, 2.3, 2.5_

- [x] 2. Replace the three Chinese f-strings in `backend/app/api/graph.py` with `t()` calls
  - Line 385: replace `f"[{task_id}] 开始构建图谱..."` with `t("log.graph_api.m027", task_id=task_id)`
  - Line 494: replace the build-completion f-string with `t("log.graph_api.m028", task_id=task_id, graph_id=graph_id, node_count=node_count, edge_count=edge_count)`
  - Line 513: replace the build-failure f-string with `t("log.graph_api.m029", task_id=task_id, e=str(e))`
  - Do not change log levels, surrounding `task_manager.update_task` calls, or control flow
  - Observable completion: `grep -nP "[一-鿿]" backend/app/api/graph.py | grep -E "^(385|494|513):"` returns no matches; `python3 -c "import ast; ast.parse(open('backend/app/api/graph.py').read())"` succeeds
  - _Requirements: 1.1, 1.4, 1.5, 3.1, 3.4_
  - _Depends: 1_

- [x] 3. Add two new keys to `log.profile_generator` in both locale files
  - In `locales/en.json`, append `m024` and `m025` under `log.profile_generator` per the design table
  - In `locales/zh.json`, mirror with the verbatim original Chinese banner text (using `{count}` placeholder where the source had `len([p for p in profiles if p])`)
  - Observable completion: same key-presence assertion as Task 1 but for `m024`, `m025`
  - _Requirements: 2.1, 2.2, 2.3, 2.5_

- [x] 4. Replace the two `print(...)` banner strings in `backend/app/services/oasis_profile_generator.py` with `t()` calls
  - Line 945: replace `f"开始生成Agent人设 - 共 {total} 个实体，并行数: {parallel_count}"` with `t("log.profile_generator.m024", total=total, parallel_count=parallel_count)`
  - Line 1001: replace `f"人设生成完成！共生成 {len([p for p in profiles if p])} 个Agent"` with `t("log.profile_generator.m025", count=len([p for p in profiles if p]))`
  - Keep the surrounding `print(f"\n{'='*60}")` separator lines exactly as they are; keep both `print(...)` calls (do not collapse into the existing `logger.info` at line 943)
  - Observable completion: `grep -nP "[一-鿿]" backend/app/services/oasis_profile_generator.py | grep -E "^(945|1001):"` returns no matches; the file still parses with `ast.parse`
  - _Requirements: 1.2, 1.4, 1.5, 3.2_
  - _Depends: 3_

- [x] 5. Add a new `log.retry` sub-namespace with four keys to both locale files
  - In `locales/en.json`, add `log.retry` as a peer of the other `log.<domain>` sub-namespaces, with keys `m001`–`m004` per the design table
  - In `locales/zh.json`, mirror the same `log.retry` sub-namespace with verbatim original Chinese
  - Use placeholder names `func_name`, `max_retries`, `index`, `e` consistently across both files (note: the source `idx + 1` is bound to `index=idx + 1` at the call site — placeholder names cannot contain `+`)
  - Observable completion: `python3 -c "import json; en=json.load(open('locales/en.json'))['log']['retry']; zh=json.load(open('locales/zh.json'))['log']['retry']; assert set(en)==set(zh)=={'m001','m002','m003','m004'}; print('ok')"` exits zero
  - _Requirements: 2.1, 2.2, 2.3, 2.5_

- [x] 6. Externalise the four `logger.error` strings in `backend/app/utils/retry.py`
  - Add `from .locale import t` at the top of `retry.py` (use the same relative-import depth as `from ..utils.logger import get_logger` already in the file — i.e., `from .locale import t`)
  - Line 55: replace `f"函数 {func.__name__} 在 {max_retries} 次重试后仍失败: {str(e)}"` with `t("log.retry.m001", func_name=func.__name__, max_retries=max_retries, e=str(e))`
  - Line 108: replace `f"异步函数 {func.__name__} 在 {max_retries} 次重试后仍失败: {str(e)}"` with `t("log.retry.m002", func_name=func.__name__, max_retries=max_retries, e=str(e))`
  - Line 179: replace `f"API调用在 {self.max_retries} 次重试后仍失败: {str(e)}"` with `t("log.retry.m003", max_retries=self.max_retries, e=str(e))`
  - Line 227: replace `f"处理第 {idx + 1} 项失败: {str(e)}"` with `t("log.retry.m004", index=idx + 1, e=str(e))`
  - Do not modify the `logger.warning(...)` retry-attempt messages or the docstrings (out of scope for #24)
  - Observable completion: `grep -nP "[一-鿿]" backend/app/utils/retry.py | grep -E "^(55|108|179|227):"` returns no matches; `python3 -c "import ast; ast.parse(open('backend/app/utils/retry.py').read())"` succeeds; `python3 -c "from backend.app.utils import retry; print(retry.t)"` resolves the import
  - _Requirements: 1.3, 1.4, 1.5, 3.3, 4.1, 4.2, 4.3, 4.4_
  - _Depends: 5_

- [x] 7. Run mechanical verification across the change
  - From the repo root, verify zero CJK on the nine affected lines:
    ```
    grep -nP "[一-鿿]" backend/app/api/graph.py | grep -E "^(385|494|513):" || echo OK_graph
    grep -nP "[一-鿿]" backend/app/services/oasis_profile_generator.py | grep -E "^(945|1001):" || echo OK_profile
    grep -nP "[一-鿿]" backend/app/utils/retry.py | grep -E "^(55|108|179|227):" || echo OK_retry
    ```
    Each should print `OK_*`.
  - Run a Python parity check that asserts every newly-added key path exists in both `locales/en.json` and `locales/zh.json` and that every `{name}` placeholder in the `zh` value also appears in the `en` value (and vice versa).
  - Run `cd backend && uv run python -m pytest` and confirm no new failures relative to the pre-change baseline.
  - Observable completion: all three grep assertions print `OK_*`; the parity Python check exits zero; the pytest run reports the same pass/fail count as on `main` for these files.
  - _Requirements: 1.5, 2.4, 5.1, 5.2, 5.3, 5.4, 5.5_
  - _Depends: 2, 4, 6_
