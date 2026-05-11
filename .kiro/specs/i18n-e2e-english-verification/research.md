# Research & Design Decisions — i18n-e2e-english-verification

## Summary

- **Feature**: `i18n-e2e-english-verification`
- **Discovery Scope**: Extension (verification-only against existing i18n surface)
- **Key Findings**:
  - `locales/en.json` is already CJK-clean (0 hits) and `locales/zh.json` is at perfect parity (953/953 keys).
  - Bulk of remaining CJK is in backend Python source (~26 files across `services/`, `api/`, `utils/`, `models/`) — overwhelmingly docstrings, comments, and a non-trivial number of log strings + LLM-prompt context labels. This is blocked by issue #7 (translate Chinese docstrings/comments).
  - Frontend `Process.vue` still has ~65 hard-coded Chinese strings in template/JS literals (not routed through `t()` keys); 4 step components have a smaller surface (mainly Step4Report's regex parsers that match Chinese backend output).
  - Live UI/full-stack walkthrough is not feasible in this sandboxed CLI environment — that portion of the verification will be reported as `manual-pending` with reproduction steps.

## Research Log

### Audit baseline

- **Context**: R1 requires running the canonical `git grep` audit and bucketing the matches.
- **Sources consulted**: ripgrep / `git grep -P` against the working tree at `9dcaecd` (HEAD of `docs/i18n-9-translate-frontend-comments`).
- **Findings**:
  - Total CJK lines: **2918** across **36** files (counting 2 binary `.jpeg` false positives that ripgrep matches when scanning the assets folder).
  - Bucket distribution: `locales/en.json` 0 / `frontend/src` 7 files (5 source + 2 binary) / `backend/app` 29 files.
  - The shell-style regex `[\x{4e00}-\x{9fff}]` in the issue body must be passed to `git grep` with `-P` (PCRE) — POSIX ERE rejects `\x{...}` ranges. The verification scripts must use `-P` or document the deviation.
- **Implications**: The audit script must use PCRE; binary files should be excluded explicitly so the `.jpeg` false positives do not pollute the gap report.

### Locale-catalogue parity

- **Context**: R2 demands key-set parity between `en.json` and `zh.json`.
- **Sources consulted**: small Python diff over the catalogues (recursive nested-dict key flattening).
- **Findings**: 953 keys each, symmetric difference 0. Already passing.
- **Implications**: R2.1, R2.2 will trivially pass; R2.4 (untranslated-but-identical entries) still needs running.

### Locale propagation surface

- **Context**: R4 requires confirming that locale survives Flask handler → `Task` → OASIS subprocess → ReACT agent.
- **Sources consulted**: `backend/app/api/graph.py`, `backend/app/services/` skim, CLAUDE.md (mentions `set_locale` thread-local).
- **Findings**:
  - `backend/app/api/graph.py` line 385 etc still emit Chinese log strings inline (`build_logger.info(f"[{task_id}] 开始构建图谱...")`) — the log externalisation work (#6) didn't reach these call sites.
  - `backend/app/utils/retry.py` log strings are still hard-coded Chinese (`logger.error(f"函数 {func.__name__} ...")`).
  - `oasis_profile_generator.py` LLM-prompt context labels (`"事实信息:"`, `"相关实体:"`) feed into the agent prompt verbatim — these will bias the LLM toward Chinese output even under EN locale.
- **Implications**: R4.3 (locale discarded silently → defaults non-EN) has live evidence; multiple `gap` items will be filed.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Pure shell + Python script (Option A) | One-shot scripts in `.kiro/specs/.../audit/scripts/` produce `audit/<sha>/*.txt` and `audit/<sha>/gap-report.md` | Simplest; no production-code touch; easy to re-run; fits R8 capture format | Scoped to this ticket — not a permanent CI guard | Selected |
| Reusable `tools/i18n-audit/` CLI (Option B) | Promote the audit to a permanent project tool wired into CI | Long-term safety net; future PRs would fail on regressions | Out of scope per R7.3 (verification-only); adds new top-level directory | Filed as a follow-up issue, not implemented here |
| Hybrid (Option C) | Run Option A now; file an issue requesting Option B as future work | Captures B's value without bloating this PR | None material | Adopted |

## Design Decisions

### Decision: Audit lives entirely under `.kiro/specs/i18n-e2e-english-verification/`

- **Context**: R7.3 forbids modifying production source in this ticket; the verification artefacts (scripts and captures) need a home.
- **Alternatives considered**:
  1. Top-level `tools/i18n-audit/` — rejected (creates a long-lived asset out of a one-shot ticket).
  2. `scripts/` next to existing project scripts — rejected (project has no convention for verification scripts; `.kiro/specs/` is the canonical home for spec-scoped work).
  3. `.kiro/specs/.../audit/` — selected.
- **Selected approach**: Scripts at `.kiro/specs/i18n-e2e-english-verification/audit/scripts/` and outputs at `.kiro/specs/.../audit/<commit-sha>/`.
- **Rationale**: Co-locates spec, requirements, design, and the artefacts a future verifier needs to re-run the pass. Honours the steering rule that the spec dir is the source of truth for spec-scoped state.
- **Trade-offs**: Scripts aren't reused beyond this ticket. Re-runs require checking out the spec dir (which is committed).
- **Follow-up**: File a follow-up issue suggesting Option B (a permanent CI guard) for the next iteration of the i18n epic.

### Decision: Manual UI walkthrough → `manual-pending`, not `gap`

- **Context**: R5.3 already permits `manual-pending` when a checklist item requires running the live stack. This run is sandboxed CLI — no browser, no Docker.
- **Alternatives considered**:
  1. Mark UI items `gap` because they weren't proven — rejected (a `gap` is a *known* failure; UI items are simply untested in this run).
  2. Skip them silently — rejected (R5.1 requires every checklist item to have a status).
  3. Mark `manual-pending` with reproduction steps — selected.
- **Rationale**: Honest about the verification environment's limits. Future verifiers can flip `manual-pending` to `pass` or `gap` after running the live walkthrough.
- **Trade-offs**: Issue #10 cannot be fully closed by this run alone; the verification-pass comment will say so explicitly.

### Decision: Gap classification = (deliberate / gap / non-applicable / review-needed)

- **Context**: R1.2 lists three classes; R2.4 introduces a fourth (`review-needed`).
- **Alternatives considered**:
  1. Three-class only — rejected (forces premature decisions on identical en/zh values).
  2. Four-class with explicit semantics — selected.
- **Rationale**: A four-class scheme keeps the `gap` count truthful (it counts only known-bad lines), and `review-needed` is a soft signal that a human should re-check.
- **Trade-offs**: Slightly more complex schema; mitigated by documenting the four labels at the top of `gap-report.md`.

### Decision: Follow-up grouping by category, not by file

- **Context**: R7.2 allows consolidation. There are too many CJK-bearing files (29) to file one issue each.
- **Alternatives considered**:
  1. One issue per file — rejected (29 micro-issues).
  2. One issue per pipeline step (R1.3 step tag) — feasible but cross-cuts existing per-component issues like #7.
  3. One issue per **gap category** — selected: (a) frontend hard-coded UI strings, (b) backend log strings, (c) backend LLM-prompt context labels, (d) recommend a permanent CI check.
- **Rationale**: Categories already align with how the i18n epic broke down work (#3, #4, #5, #6 = LLM-prompts; #7 = docstrings/comments; #9 = frontend comments). Categories also map cleanly to single PRs, which is how subsequent fixes will land.
- **Trade-offs**: Some files appear in multiple categories. Mitigated by listing `file:line` evidence inside each category issue.

### Decision: Issue-comment fallback when `gh` is unavailable

- **Context**: R7.5 mandates a fallback if `gh` permissions are missing.
- **Selected approach**: If `gh` posts fail, the script writes the comment body to `audit/<sha>/PENDING-issue-10-comment.md` and the would-be follow-up issue bodies to `audit/<sha>/PENDING-followups/*.md` so a human can paste them.
- **Rationale**: Keeps the audit re-runnable offline; keeps the artefact set faithful to what *would* have been posted.
- **Trade-offs**: Verification doesn't truly close until a human posts. Surfaced loudly in the run-summary.

## Risks & Mitigations

- **Risk**: A `gap` is mis-classified as `non-applicable` (e.g. a regex character class versus a real Chinese label) → Mitigation: classification tracked in a small CSV alongside the raw grep, so re-classification is auditable.
- **Risk**: `gh` rate limits hit when filing follow-ups → Mitigation: file at most 4 follow-ups (one per category) — far below any rate limit.
- **Risk**: Re-running the audit on a divergent branch produces a noisy diff → Mitigation: `audit/<commit-sha>/` directories preserve history; comparison is opt-in via `diff -ru`.
- **Risk**: Live walkthrough never happens, leaving #10 in `manual-pending` indefinitely → Mitigation: the verification report comment names a concrete "next reviewer" reproduction script; `manual-pending` items have explicit acceptance criteria.

## References

- Issue #10 — https://github.com/salestech-group/MiroFish/issues/10
- Epic #11 — https://github.com/salestech-group/MiroFish/issues/11
- `gap-analysis.md` — bucketed audit baseline
- `requirements.md` — EARS acceptance criteria for this spec
