# Gap Analysis — i18n-frontend-comments

## 1. Current State Investigation

### Scope discovery (ground truth)

Ripgrep `[\x{4e00}-\x{9fff}]` over `frontend/src/` returns **20 files, 902 occurrences**:

| File | Hits |
| --- | ---: |
| `views/Process.vue` | 191 |
| `components/Step4Report.vue` | 176 |
| `components/HistoryDatabase.vue` | 124 |
| `components/GraphPanel.vue` | 84 |
| `components/Step2EnvSetup.vue` | 76 |
| `components/Step3Simulation.vue` | 52 |
| `views/Home.vue` | 43 |
| `components/Step5Interaction.vue` | 34 |
| `api/simulation.js` | 29 |
| `views/SimulationView.vue` | 22 |
| `views/SimulationRunView.vue` | 18 |
| `api/graph.js` | 10 |
| `api/index.js` | 8 |
| `api/report.js` | 8 |
| `views/InteractionView.vue` | 6 |
| `views/ReportView.vue` | 6 |
| `components/Step1GraphBuild.vue` | 5 |
| `App.vue` | 4 |
| `views/MainView.vue` | 4 |
| `store/pendingUpload.js` | 2 |

No `.css` files exist under `frontend/src/`; styles live inside Vue SFC `<style>` blocks.

### Comment shapes encountered

Sampling representative files confirms three syntactic forms — all already English-syntax, only the natural-language content is Chinese:

- **JS line comments**: `// 创建axios实例`, `timeout: 300000, // 5分钟超时（本体生成可能需要较长时间）`
- **JSDoc blocks** in `api/simulation.js`: `/** * 创建模拟 */`, `* @returns {Promise} 返回配置信息，包含元数据和配置内容`
- **Vue template comments** in `views/Home.vue`: `<!-- 顶部导航栏 -->`, `<!-- 上半部分：Hero 区域 -->`

### String literals containing Chinese (NOT comments)

A naive regex for Chinese inside quoted strings flags **8 files**. Spot-checks reveal two distinct categories that the ticket body did not explicitly anticipate:

- **Developer-facing log strings** — e.g. `Step1GraphBuild.vue:216` `console.error('缺少项目或图谱信息')`. These print to the browser dev console and are not part of the i18n locale surface. Translating them does not change runtime behavior.
- **LLM prompt template strings** — e.g. `Step5Interaction.vue:725-727` `\`以下是我们之前的对话：\n${historyContext}\n\n现在我的新问题是：${message}\``. These are sent to a Chinese-tuned LLM (default Qwen). Translating them *would* change the model's input and could shift output behavior.

The ticket says **"no UI string changes (those are already in `locales/en.json`)"** and **"Out of scope: Translating user-facing strings"**. Neither category above is user-facing UI text — `locales/*.json` already covers user-facing strings via `vue-i18n`. The ticket's acceptance criterion #1 (`grep returns no files, or only files with deliberately-kept bilingual comments listed in PR`) leaves room to retain the LLM prompt strings as documented exceptions.

### Conventions to respect (from steering)

- `tech.md`: 4-space indent, no enforced linter, "match the surrounding file's style". Existing files mix English and Chinese in comments/docstrings — preserve both *unless asked*. **This ticket is the explicit ask.**
- `structure.md`: `frontend/src/api/*.js` services use Axios with 5-min timeout + exponential retry. The translation pass must not touch the retry/timeout logic.
- `dev-guidelines.md` (project-level): "Don't comment the obvious — comment the *why*." JSDoc on all exported functions, classes, interfaces (so JSDoc blocks must be **kept** in JSDoc form when translating, not deleted as redundant).
- `commits.md`: Conventional Commits, lowercase, imperative, max 72 chars, no `Co-Authored-By:` footer. Branch `<type>/<ticket>-<desc>` — ticket dictates `docs/i18n-9-translate-frontend-comments`.

### Existing i18n-related precedent

Recent merged PRs in the same epic (#11):

- `feat/i18n-2-translate-ontology-generator-prompts` → backend prompt translation, full content swap.
- `feat/i18n-4-translate-sim-config-prompts`, `feat/i18n-5-translate-report-agent-prompts` → similar backend prompt swaps.
- `feat/i18n-6-externalize-backend-logs` → moved log strings out of code into i18n keys.
- `fix/i18n-8-backfill-zh-json` (current branch base) → backfilled missing zh translations.

**Pattern**: prior i18n work changed both content *and* infrastructure (locale-keying logs). This ticket explicitly does not — it is a documentation-only pass without re-keying anything.

## 2. Requirements ↔ Asset Map

| Req | Asset to change | Gap tag | Note |
| --- | --- | --- | --- |
| 1.1–1.4 (translate comments incl. JSDoc) | All 20 files listed above | — (clear) | Largely mechanical; respect SFC block boundaries (`<script>` vs `<template>` vs `<style>`). |
| 1.5 (deliberately bilingual) | LLM prompt strings in `Step5Interaction.vue` (and any others discovered) | **Constraint** | Keep Chinese, document in PR. Behavior-risk if translated. |
| 2.x (drop redundant) | Files with `// 获取数据`-style restate-the-code comments | — | Apply per case during the pass; conservative when ambiguous. |
| 3.x (TODO/FIXME ticket refs) | Search `frontend/src/` for `TODO\|FIXME` | **Unknown** | No matches noted in spot checks; will sweep during implementation. If none found, requirement is satisfied vacuously. |
| 4.x (no behavior change) | Confirmed by `npm run build` exit 0 + manual smoke | — | Vite build is the reference; keep all string-literal content (other than developer-log strings) untouched; identifiers and imports are off-limits. |
| 5.x (PR hand-off) | PR description, branch name, commit message | — | Branch name from ticket: `docs/i18n-9-translate-frontend-comments`. |

### Discovered scope ambiguity → decision needed

Two boundary calls that the requirements should sharpen before design:

- **`console.error` / `console.warn` / `console.log` strings with Chinese content** — translate (developer-facing, not in locales) or leave (string-literal change risks scope creep)? Recommended: **translate**, since they are dev-facing comments-by-other-means and the ticket's spirit is "English-readable code". This is a design decision to be encoded in the design doc, not a new requirement.
- **LLM prompt template strings** — leave as-is and list in PR (per Req 1.5). This is the safer call: the LLM is Chinese-tuned by default and translating a system prompt is a behavior change.

Both decisions stay inside the requirements as currently written (specifically Req 1.5 + Req 4.4, which already excludes string literals from the translation pass except where developer-log strings are concerned). The design phase will document the rule explicitly.

## 3. Implementation Approach Options

### Option A — Single-pass translation per file, no tooling

**Approach**: Open each of the 20 files, translate every Chinese comment in place, drop redundant ones, append `(#9)` to bare TODO/FIXME, leave Chinese string literals (LLM prompts) and translate `console.*` Chinese strings. Verify with `rg [\x{4e00}-\x{9fff}] frontend/src/`.

- ✅ Lowest overhead, no new tools or scripts
- ✅ Fits a one-shot doc-only PR
- ✅ Maximally aligns with `dev-guidelines.md` "comment the *why*" — judgment per comment
- ❌ ~900 occurrences spread across 20 files — most concentrated in 6 files (>50 hits each) which are large (`Process.vue` is 2067 lines, `Step4Report.vue`, `HistoryDatabase.vue`)
- ❌ Manual judgment for redundant-vs-meaningful adds reviewer load

### Option B — Automated translation script + manual pass

**Approach**: Write a Node/Python script that walks files, extracts Chinese comments, runs them through an LLM, and writes back. Then a manual pass on the diff.

- ✅ Faster on long files
- ❌ Adds a dependency (LLM call) and a scratch script, neither delivered
- ❌ The translation needs *judgment* (drop vs translate per Req 2) — automation undercuts the "comment the *why*" rule
- ❌ Risk of touching string literals or identifiers if regex is loose
- ❌ Out of step with the steering "no enforced tooling without discussion" principle

### Option C — File-by-file with task batching

**Approach**: Group the 20 files into work units by size: (a) high-touch (Process, Step4Report, HistoryDatabase, GraphPanel, Step2EnvSetup, Step3Simulation), (b) mid-touch (Home, Step5Interaction, simulation.js, SimulationView, SimulationRunView), (c) light (api/{graph,index,report}.js, the 4–8 hit views, App.vue, store/pendingUpload.js, Step1GraphBuild.vue). Implementation tasks mirror these groups. Verify after each group with the ripgrep check.

- ✅ Same translation effort as A but with checkpointable progress (matches the project's task-tracking pattern from steering — "background tasks expose progress")
- ✅ Reviewer can read the PR file-group-by-file-group instead of all-at-once
- ✅ If the PR needs to land partial (rare), the light + mid groups still ship a valuable subset
- ❌ A few extra task headings in `tasks.md` vs Option A's "do the thing"

## 4. Effort & Risk

- **Effort**: **S (1–2 days)**. Mechanical translation, plus judgment calls. ~900 occurrences but no architectural work.
- **Risk**: **Low**. Doc-only change. The only real risks are (a) accidentally editing a string literal that affects the LLM prompt or a hardcoded user-visible string, and (b) deleting a comment whose intent the translator misread. Both are mitigated by Req 4.4 ("leave string literals unchanged") and Req 2.3 (conservative-when-ambiguous).

## 5. Recommendations for Design Phase

- **Preferred approach**: **Option C** — file-grouped translation pass, no tooling, no script. It matches the project's manual-style ethos and the existing pipeline-aligned task structure, and produces a reviewable PR.
- **Encode in design**:
  - The translation rule for each comment shape (`//`, `/* */`, JSDoc, `<!-- -->`).
  - The decision matrix for string literals: translate `console.*` Chinese strings; retain LLM prompt strings (in `Step5Interaction.vue`) and list them in the PR per Req 1.5.
  - The TODO/FIXME sweep approach (single ripgrep pass before the file loop).
  - The verification command and acceptance check sequence.
- **Research items carried forward**: none — the codebase has been inspected enough to commit to Option C without further investigation.
