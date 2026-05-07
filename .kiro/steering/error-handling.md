# Error Handling Standards

Most errors in MiroFish originate from **LLM calls**, **graph
operations**, **subprocess simulation**, or **user-uploaded files** —
not classical 4xx/5xx web flows. These standards target those failure
modes specifically.

## Philosophy

- Fail fast in services; convert to a stable response envelope at the
  API layer.
- Long-running tasks must always reach a terminal state
  (`COMPLETED` or `FAILED`) — a stuck `PROCESSING` task is a bug.
- LLM responses are untrusted by default: validate, strip, parse, then
  use.
- Background-thread errors are silent unless explicitly captured —
  always wrap the work in `try/except`.

## Error Surfaces (where they appear, where they're handled)

| Surface              | Handle in                                  | Convert to                        |
| -------------------- | ------------------------------------------ | --------------------------------- |
| HTTP request errors  | `api/` handler `try/except` + envelope     | `{"success": false, "error": …}`  |
| Background task      | Worker thread `try/except` → `fail_task()` | `Task.status = FAILED` + `error`  |
| LLM call failures    | `retry_with_backoff` decorator             | Exception bubbles after retries   |
| Graph adapter errors | Caller catches & maps                      | Service-specific error or `Task.fail` |
| Simulation IPC       | `simulation_ipc.py` catches & logs         | Task fail or simulation cleanup   |
| File parsing         | `utils/file_parser.py`                     | Raised as `ValueError` to caller  |

A handler should never let an exception reach Flask's default 500
formatter — wrap and return the canonical envelope instead.

## LLM-Specific Failure Modes

These are recurring and worth handling explicitly:

### 1. Reasoning-model output contamination

Some providers (MiniMax, GLM, certain Qwen variants) emit `<think>…
</think>` blocks and/or markdown code fences (```` ```json ... ``` ````)
around JSON output.

**Rule:** Strip both before `json.loads(...)`. The fix lives in commit
`985f89f` for context. Any new LLM-output JSON parser must do the same
— do not call `json.loads` on raw model output.

### 2. Transient API errors

Network blips, rate limits, intermittent 5xx from the provider.

**Rule:** Use `utils/retry.py`:

```python
from app.utils.retry import retry_with_backoff

@retry_with_backoff(max_retries=3, exceptions=(SomeAPIError,))
def call_llm(...): ...
```

- Sync version: `retry_with_backoff`
- Async version: `retry_with_backoff_async`
- For batch processing where partial failure is acceptable, use
  `RetryableAPIClient.call_batch_with_retry(items, fn,
  continue_on_failure=True)`.

Don't write a hand-rolled retry loop — it'll drift from the project's
backoff/jitter conventions.

### 3. Schema mismatch in structured output

LLM returns valid JSON but missing/extra fields.

**Rule:** Validate with Pydantic v2 models where the call expects
structure. Fail loudly (raise) rather than silently coercing — better
to retry the LLM call than to feed bad data downstream.

## Background Task Errors

Inside a worker thread spawned from an API handler:

```python
def _worker(task_id, project_id, ...):
    try:
        # work
        TaskManager().update_task(task_id, progress=50, message=...)
        result = do_real_work(...)
        TaskManager().complete_task(task_id, result)
    except Exception as e:
        logger.exception(f"task {task_id} failed")
        TaskManager().fail_task(task_id, str(e))
```

Rules:

- The outer `except` must be broad (`Exception`) — the goal is "task
  always terminates," not "narrow down failures here."
- Log the full traceback (`logger.exception`), then store a concise
  `str(e)` on the task for the frontend to display.
- Never re-raise from the worker; the thread has no caller.
- Update related `Project` state (e.g. revert `GRAPH_BUILDING` →
  previous status) **inside** the except, before `fail_task`.

## Graph & Subprocess Errors

- **Graphiti / Neo4j errors:** caller decides — usually fail the task
  with a user-friendly message; for non-fatal search failures, log and
  return empty results.
- **OASIS subprocess crashes:** `simulation_ipc.py` is the single
  surface. It owns lifecycle, logging, and signaling task failure.
  Don't catch subprocess errors elsewhere.
- **Startup recovery:** `_recover_stuck_projects` re-classifies
  projects left `GRAPH_BUILDING` after a restart — see `database.md`.

## Logging

- Use `utils/logger.get_logger('mirofish.<module>')` — never
  `print` or `logging.getLogger` directly.
- Levels:
  - `ERROR` — task failure, unrecoverable exception
  - `WARNING` — retry triggered, transient failure, recovered state
  - `INFO` — task lifecycle (created, completed), pipeline milestones
  - `DEBUG` — payload shapes, intermediate counts, off by default
- User-visible log messages should go through `utils/locale.t(...)` so
  they translate; internal diagnostic logs stay in the file's existing
  language (English or Chinese — match the surrounding code).
- **Never log:** API keys, full LLM prompts containing user-uploaded
  text (truncate or hash), Neo4j credentials, full `.env` contents.

## What Not to Do

- Don't catch `Exception` inside an API handler just to log and
  continue — fail the request and return the envelope.
- Don't retry non-idempotent work (e.g. graph writes that may have
  partially completed).
- Don't translate exceptions into `success: true` responses with an
  embedded error message; use `success: false`.
- Don't surface raw stack traces or LLM internals to the frontend.

---
_Focus on patterns and decisions. No implementation details or exhaustive lists._
