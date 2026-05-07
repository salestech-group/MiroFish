# Gap Analysis — i18n-e2e-english-verification

## 1. Current state investigation

### Domain-relevant assets in the repo

| Concern | Location | Notes |
|---|---|---|
| Locale catalogues | `locales/en.json`, `locales/zh.json`, `locales/languages.json` | Flat-namespaced JSON, loaded by `vue-i18n` and the backend logger. |
| Frontend i18n loader | `frontend/src/i18n/` | Provides `useI18n()` to components. |
| Frontend UI surface | `frontend/src/views/`, `frontend/src/components/` | Step1–5 components + `Process.vue` orchestrator. |
| Backend logger | `backend/app/utils/logger.py` (per CLAUDE.md) | Externalised log messages (#6 work). |
| Locale helpers | `backend/app/utils/` | Per CLAUDE.md, locale propagation lives here. |
| Prompt assets that emit user-visible text | `backend/app/services/ontology_generator.py` (#2, #3?), `oasis_profile_generator.py` (#3), `simulation_config_generator.py` (#4), `report_agent.py` (#5) | Prompts are inline Python strings, not separate files. |
| Pipeline boundaries | `backend/app/api/*.py` (Flask), `services/simulation_runner.py` + `simulation_ipc.py` (subprocess), `services/report_agent.py` (ReACT) | Locale must propagate across all of these. |

### Project conventions surfaced

- `Task` model used for any long-running operation (CLAUDE.md). Verification doesn't introduce one — it is a one-shot batch.
- Reasoning-model output stripping convention exists, irrelevant here.
- Per-project `group_id` isolation in Neo4j — verification queries should NOT touch Neo4j; we run a static audit only.
- "Match the surrounding file's style" (no enforced formatter).

### Live audit baseline (commit `9dcaecd`)

```
git grep -nP "[\x{4e00}-\x{9fff}]" -- backend/app frontend/src locales/en.json | wc -l
→ 2918 lines across 36 files
```

Bucketed:

| Bucket | Files | Lines | Notes |
|---|---|---|---|
| `locales/en.json` | 0 | 0 | ✅ clean |
| `frontend/src/views/Process.vue` | 1 | 65 | hard-coded UI strings (template + JS literals), not i18n keys |
| `frontend/src/components/Step{2,3,4,5}*.vue` | 4 | ~50 (mostly Step4Report.vue regex parsers) | depends-on-backend regex parsers + a few literals |
| `backend/app/services/*.py` | 13 | majority | docstrings + comments + a few prompt assembly fragments + agent context labels (e.g. `"事实信息:"` in `oasis_profile_generator.py`) |
| `backend/app/api/*.py` | 4 | many | docstrings + comments + log-message Chinese (`build_logger.info(f"[{task_id}] 开始构建图谱...")` etc) |
| `backend/app/utils/*.py` | 7 | many | docstrings + comments + log strings (e.g. `retry.py` "函数 {func} 在 N 次重试后仍失败") |
| `backend/app/models/*.py` | 3 | docstrings | docstrings only (probably) |

### Locale catalogue parity (Python check)

```
en keys: 953
zh keys: 953
symmetric diff: 0
```

→ R2 (parity) passes. ZH backfill (#8) closed the gap and en/zh are now lock-step.

### Boundary review surface (R4)

- `backend/app/api/graph.py` `build_logger.info(f"[{task_id}] 开始构建图谱...")` shows the backend logger is still emitting Chinese on the build path — this is exactly the kind of leak #6 was supposed to externalise.
- `backend/app/utils/retry.py` `logger.error(f"函数 {func.__name__} 在 {max_retries} 次重试后仍失败...")` — same: log strings remain hard-coded Chinese.
- ReACT/agent context labels in `oasis_profile_generator.py` (`"事实信息:"`, `"相关实体:"`) feed directly into the LLM prompt — these will bias the model toward Chinese output.

## 2. Requirements feasibility

### Mapping requirements → existing assets

| Req | Need | Existing asset | Gap tag |
|---|---|---|---|
| R1 (static audit) | run `git grep` and capture output | git, ripgrep | None — straightforward |
| R1.5 (`en.json` CJK check) | inspect catalogue | already at 0 hits | None — passes |
| R2 (parity) | enumerate keys recursively, diff | small Python script | None — already passes |
| R3 (prompt verification) | read prompt strings in `services/*.py` | inline Python strings | **Constraint** — prompts are inline, not standalone files; verification must read source not assets |
| R4 (propagation) | trace locale across Flask → Task → OASIS → ReACT | source code review | **Research needed** in design phase: where exactly is locale stored today? CLAUDE.md hints `set_locale` thread-local exists but path not yet read |
| R5 (post comment) | `gh issue comment 10` | `gh` CLI | None |
| R6 (ZH regression) | confirm zh values are non-English | small Python script | None |
| R7 (file follow-ups) | `gh issue create` | `gh` CLI | None |
| R8 (capture & idempotence) | write under `.kiro/specs/.../audit/` | filesystem | None |

### Complexity signals

- Algorithmic: trivial — grep + count + diff.
- Workflow: post a comment + open follow-up issues — one-shot.
- External integrations: GitHub via `gh`. No DB, no Neo4j, no LLM calls.

### Constraints from existing architecture

- **No code edits to `backend/app/`, `frontend/src/`, `locales/`** — the spec is verification-only. The change-set is confined to `.kiro/specs/i18n-e2e-english-verification/` (audit captures, gap report, follow-up issue list) and any commit message / PR description.
- Manual UI walkthrough is not feasible in a sandboxed CLI — must be marked `manual-pending` per R5.3.
- Live `docker-compose up` likewise unavailable — same handling.

## 3. Implementation approach options

### Option A — Pure shell + Python script kept under `.kiro/specs/.../audit/`

- A single Bash + Python pipeline that emits `audit/cjk-grep.txt`, `audit/parity.txt`, `audit/gap-report.md`.
- Posts the comment via `gh` and opens follow-ups via `gh issue create`.
- Scripts are read-only against production source.

✅ Simplest, no production-code touch.
✅ Easy to re-run.
❌ Scripts only relevant to this ticket — scoped to `.kiro/specs/.../audit/scripts/`, not promoted to a reusable `tools/`.

### Option B — Build a reusable `tools/i18n-audit/` checker

- Create a permanent CLI under `tools/` so future verifiers can re-run.
- Integrates with CI (could become a check that fails when `en.json` contains CJK).

❌ Adds a tool & directory the project doesn't have. Scope creep — the spec is for one verification pass, not a CI check.
❌ A reusable tool wants its own ticket; ramming it in here violates the "no inline fixes" rule.

### Option C — Hybrid: ad-hoc script for this run, plus open a follow-up issue requesting the reusable CI check

- Run the verification with disposable scripts (Option A) AND file a follow-up issue asking for the reusable CI check (Option B as a future ticket).

✅ Keeps current ticket scoped.
✅ Captures the value of B without bloating this PR.

## 4. Out-of-scope items deferred

- Any **production code edits** that would close gaps. R7 makes this explicit.
- Live UI walkthrough / dynamic verification — captured as `manual-pending` in the report.

## 5. Effort & risk

- **Effort**: S (1 day) — auditing scripts + report writing + issue filings.
- **Risk**: Low — read-only operations, no architectural change, the failure mode (`gh` lacking permissions) is handled by R7.5 (fallback inline list).

## 6. Recommendations for design phase

- **Preferred approach**: Option C (hybrid).
- **Key decisions to make in design**:
  - Concrete script layout under `.kiro/specs/i18n-e2e-english-verification/audit/`.
  - Format of `audit/gap-report.md` (the artefact echoed into the issue comment).
  - Exact follow-up issue grouping rule (R7.2): one issue per pipeline step? per file? per category (UI / logs / prompts / docstrings)?
  - Reproducibility (R8.2): do we keep `audit/<commit-sha>/` per run, or `audit/latest/` + `audit/previous/`?
  - Whether the scripts are committed to the repo (they live under `.kiro/specs/...` — yes by default) or only the captured outputs.
- **Research items to carry forward**:
  - Read `backend/app/utils/` to confirm whether a locale helper / `set_locale` exists today (R4 detail).
  - Read `backend/app/utils/logger.py` to confirm where externalised log keys live and how the locale is selected at log time (R4 + Step-1 logs checklist item).
  - Confirm whether any `services/*.py` Chinese match is part of an LLM **prompt** vs a comment — only prompt matches block R3.
