# Research & Design Decisions — i18n-frontend-comments

## Summary

- **Feature**: `i18n-frontend-comments`
- **Discovery Scope**: Simple Addition (documentation-only translation pass; no architectural change)
- **Key Findings**:
  - 20 files in `frontend/src/` contain Chinese characters (902 total occurrences). Concentration follows file size: `Process.vue` (191), `Step4Report.vue` (176), `HistoryDatabase.vue` (124), `GraphPanel.vue` (84), `Step2EnvSetup.vue` (76), `Step3Simulation.vue` (52). The remaining 14 files have ≤43 hits each.
  - Chinese appears in three comment shapes (JS line `//`, JSDoc `/** */`, Vue `<!-- -->`) and — unexpectedly — inside two flavors of string literal: `console.error('…')` developer logs (low risk to translate) and LLM prompt template strings in `Step5Interaction.vue` (behavior risk if translated, since the default LLM is Chinese-tuned).
  - The codebase has no enforced linter/formatter (per `tech.md`) and `dev-guidelines.md` already states "comment the *why*, not the *what*". The existing comment density skews toward restating-the-code in Chinese; a meaningful share will be deleted rather than translated.

## Research Log

### Inventory and shape of Chinese content

- **Context**: Need to decide whether one pass can mechanically translate or whether per-file judgment is required.
- **Sources Consulted**: `rg [\x{4e00}-\x{9fff}] frontend/src/` (full count) and content-mode samples of `api/index.js`, `api/simulation.js`, `views/Home.vue`, `components/Step1GraphBuild.vue`, `components/Step5Interaction.vue`.
- **Findings**:
  - Comments are syntactically standard (`//`, `/** */`, `<!-- -->`); no inline-Chinese identifiers.
  - JSDoc blocks in `api/simulation.js` (and likely `api/graph.js`, `api/report.js`) include `@returns`, `@param` annotations with Chinese descriptions — translate only the natural-language portion, keep tag structure.
  - `console.error` strings in `components/Step1GraphBuild.vue` (3 hits at lines 216, 237, 241) are dev-facing only, not user-facing.
  - LLM prompt template strings in `components/Step5Interaction.vue` (lines 725–727) are sent to a Chinese-tuned model; translation is a behavior change.
- **Implications**: Per-file judgment pass is required. String literals are out of scope by default (Req 4.4); only `console.*` Chinese strings are in scope as a documented exception (developer-facing).

### Tooling decision: manual vs scripted

- **Context**: ~900 occurrences across 20 files — would automation help?
- **Sources Consulted**: Steering `tech.md` ("No enforced linter or formatter in this repo by design… Discuss with the user before introducing ESLint/Prettier/Ruff/Black"); `dev-guidelines.md` ("comment the *why*"); gap-analysis Option B trade-offs.
- **Findings**: Automation undercuts Req 2 (drop redundant comments requires human judgment). The project explicitly disallows new tooling without discussion. The work fits an S-effort manual pass.
- **Implications**: No new scripts; no new dependencies; manual translation file-by-file.

### Verification path

- **Context**: How does the reviewer confirm acceptance?
- **Sources Consulted**: Ticket body acceptance criteria; project's Vite build (`npm run build`).
- **Findings**: A single ripgrep command confirms Req 1.1; `npm run build` confirms Req 4.1; manual smoke confirms Req 4.3. No new test harness is justified for a doc-only change (per steering "Don't add a heavy test harness without discussing scope").
- **Implications**: PR description carries the verification one-liner; the build is the proof.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A. Single-pass translation, no tooling | Translate all 20 files in one PR; manual judgment per comment | Simple, low overhead | Long diff for the largest 6 files | Matches "manual style" steering ethos |
| B. Automated LLM-driven script + manual review | Script extracts Chinese comments, LLM translates, dev reviews diff | Faster on long files | Adds dependency; undercuts judgment requirement; risk of touching strings/identifiers | Rejected — clashes with "no new tooling" steering |
| C. File-grouped manual pass (selected) | Same translation effort as A, but tasks split into file groups: high-touch / mid-touch / light | Reviewable progress, matches project's task-tracking pattern | A few extra task headings | Selected — pairs cleanly with `tasks.md` structure |

## Design Decisions

### Decision: Manual file-grouped translation, no tooling

- **Context**: 20 files, ~900 occurrences, mixed comment shapes plus a small set of in-scope dev-log strings.
- **Alternatives Considered**:
  1. Single mass pass (Option A) — workable but reviewer-unfriendly for the largest files
  2. Automated LLM translation script (Option B) — fast but loses per-comment judgment and adds tooling
  3. File-grouped manual pass (Option C) — same effort as A with clearer task decomposition
- **Selected Approach**: Group files into three batches by occurrence count and translate each batch as one task. After each batch, run the verification ripgrep to check progress.
- **Rationale**: Aligns with `tech.md` steering ("match the surrounding file's style"), `dev-guidelines.md` ("comment the *why*"), and lets `tasks.md` mirror the existing project task-tracking pattern. The S-effort estimate fits one work session.
- **Trade-offs**: A few extra task headings vs. cleaner reviewability. No infrastructure cost.
- **Follow-up**: Confirm `console.*` Chinese strings are translated; confirm LLM prompts in `Step5Interaction.vue` are documented as retained in PR description.

### Decision: String-literal scope rule

- **Context**: Some Chinese appears in string literals, not just comments.
- **Alternatives Considered**:
  1. Strict: comments only — leaves dev-facing `console.*` Chinese which any maintainer reading dev console would still see in Chinese
  2. Permissive: all string literals — translates LLM prompt templates, changing model behavior
  3. Targeted: comments + dev-facing log strings (`console.*`); retain LLM prompts as documented exceptions
- **Selected Approach**: Targeted (option 3). Translate `console.error`, `console.warn`, `console.log` strings whose content is Chinese. Leave LLM prompt template strings alone and list them in the PR description per Req 1.5.
- **Rationale**: Honors the spirit of the ticket ("English-readable code") while preserving Req 4 ("no runtime behavior change") for the LLM-bound strings. Matches Req 4.4 (string literals untouched *except* where dev-log translation is unambiguous).
- **Trade-offs**: Reviewer needs to verify the exception list in the PR description against the residual ripgrep matches. Mitigated by Req 5.1 (PR description must document residuals).
- **Follow-up**: During implementation, confirm there are no other categories of Chinese-string-literal beyond `console.*` and LLM prompts. If discovered, add to the documented exception list rather than expanding scope.

### Decision: TODO/FIXME ticket reference policy

- **Context**: Req 3 mandates ticket references on TODO/FIXME markers.
- **Alternatives Considered**:
  1. Skip the sweep entirely if no markers exist
  2. Sweep `frontend/src/` for `TODO|FIXME` once at the start; append `(#9)` only where missing
- **Selected Approach**: Run a single `rg 'TODO|FIXME' frontend/src/` sweep before the file-translation loop; record any matches; apply Req 3.1–3.3 inline with each file's translation.
- **Rationale**: Lightest-weight implementation of Req 3. If no markers exist (likely for `frontend/src/`), the requirement is satisfied vacuously and noted in the PR description.
- **Trade-offs**: None.
- **Follow-up**: If markers exist in non-Chinese form (English TODOs without ticket refs), the requirement says only to act on *Chinese* markers; out of scope to retrofit unrelated existing English TODOs.

## Risks & Mitigations

- **Risk**: Accidentally translating an LLM prompt string and shifting model behavior. **Mitigation**: Req 4.4 + Decision "String-literal scope rule"; document retained Chinese strings in PR.
- **Risk**: Misinterpreting a Chinese comment and translating to wrong meaning. **Mitigation**: Req 2.3 (conservative when ambiguous; keep + translate rather than delete).
- **Risk**: Reviewer churn over which comments to delete vs. translate. **Mitigation**: `dev-guidelines.md` is the rubric; Decision documents the rule (delete only when comment paraphrases the next statement; translate when the comment encodes intent).
- **Risk**: PR is too large to review (Process.vue alone has ~191 hits). **Mitigation**: File-grouped tasks + per-group ripgrep checkpoint; each group is reviewable as a unit.

## References

- `dev-guidelines.md` (project) — comment philosophy and Conventional Commits.
- `tech.md` (steering) — "No enforced linter or formatter… match the surrounding file's style."
- `structure.md` (steering) — `frontend/src/` directory layout (views/components/api/store).
- Ticket #9 body — acceptance criteria, branch and commit naming.
- Gap analysis (`gap-analysis.md`) — Option C trade-offs and effort/risk estimate.
