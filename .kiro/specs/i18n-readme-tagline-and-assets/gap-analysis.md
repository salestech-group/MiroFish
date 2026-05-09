# Gap Analysis — i18n-readme-tagline-and-assets

## 1. Current State Investigation

### Scope ground truth

Ripgrep `[\x{4e00}-\x{9fff}]` over `README.md`, `README-EN.md`, `package.json`, and `backend/pyproject.toml` returns the following Chinese-character lines that fall under this feature's mandate:

| File | Line | Content (excerpt) | Category |
| --- | ---: | --- | --- |
| `README.md` | 7 | `简洁通用的群体智能引擎，预测万物` | Tagline |
| `README.md` | 23 | `[English](./README.md) \| [中文文档](./README-ZH.md)` | Language switcher (allowed) |
| `README.md` | 52–61 | `./static/image/Screenshot/运行截图{1..6}.png` (×6) | Asset path |
| `README.md` | 71 | `./static/image/武大模拟演示封面.png` | Asset path |
| `README.md` | 79 | `./static/image/红楼梦模拟推演封面.jpg` | Asset path |
| `README.md` | 220 | `./static/image/QQ群.png` | Asset path (not listed in ticket scope, see Gap §3) |
| `README-EN.md` | 7, 23, 52–61, 71, 79, 220 | identical structure to README.md | Same categories |
| `package.json` | 4 | `"description": "MiroFish - 简洁通用的群体智能引擎，预测万物"` | Tagline |
| `backend/pyproject.toml` | 4 | `description = "MiroFish - 简洁通用的群体智能引擎，预测万物"` | Tagline (twin string, not in original ticket) |

`README-ZH.md` carries Chinese body text by design (out of scope) but its asset paths must still be updated to point at the renamed ASCII files.

### Tracked image files (`git ls-files static/image/`)

```
static/image/MiroFish_logo.jpeg
static/image/MiroFish_logo_compressed.jpeg
static/image/QQ群.png
static/image/Screenshot/运行截图{1..6}.png
static/image/shanda_logo.png
static/image/武大模拟演示封面.png
static/image/红楼梦模拟推演封面.jpg
```

Nine files have Chinese names: six screenshots + `QQ群.png` + `武大模拟演示封面.png` + `红楼梦模拟推演封面.jpg`.

### Tagline structure observation

`README.md` lines 7–9 currently read:

```
简洁通用的群体智能引擎，预测万物
</br>
<em>A Simple and Universal Swarm Intelligence Engine, Predicting Anything</em>
```

The English equivalent already exists immediately below the Chinese as italic subtitle. Naive replacement would produce a duplicate (English in plain text + the same English in italic). The natural i18n collapse is to delete the Chinese line plus the `</br>` separator and let the existing `<em>` line stand alone. `README-EN.md` has the identical structure.

### Conventions to respect (from steering)

- `tech.md`: 4-space indent, no enforced linter, "match the surrounding file's style". Shell scripts must quote paths with spaces / non-ASCII characters per `.claude/rules/file-paths.md`.
- `commits.md`: Conventional Commits, lowercase, imperative, max 72 chars, no `Co-Authored-By:` footer. Branch `<type>/<ticket>-<desc>` — ticket dictates `chore/i18n-12-readme-tagline-and-assets` (or similar).
- `dev-guidelines.md`: kebab-case filenames for assets is consistent with the project's frontend file conventions.

### Existing precedent in the same i18n epic

Recently merged child issues of epic #11 (`#7`, `#9`, `#3`, `#5`, `#6`) have all been small, focused docs/tooling PRs. This is consistent with treating #12 as an S-effort docs cleanup.

## 2. Requirements Feasibility Analysis

### Per-requirement asset map

| Req | What it needs | Where it lives | Gap |
| --- | --- | --- | --- |
| R1 (tagline) | English tagline | `README.md:7-9`, `README-EN.md:7-9`, `package.json:4`, `backend/pyproject.toml:4` | **Editorial** — straight string edit. No code paths affected. |
| R2 (asset rename) | Rename 8 files (6 screenshots + 2 video covers) | `static/image/Screenshot/`, `static/image/` | **`git mv`** — preserves history. No callers outside READMEs found by grep. |
| R3 (README references updated) | Update `<img src>` paths | `README.md`, `README-EN.md`, `README-ZH.md` | **Editorial** — straight string edits. |
| R4 (no residual Chinese in EN READMEs) | Verifiable scan | Both `README.md` and `README-EN.md` | **Constraint surfaces extra asset** — `QQ群.png` (line 220) is not in the explicit ticket asset list but its src path contains Chinese, which would fail R4's verification. See Gap §3. |

### Gaps tagged

- **Constraint:** `static/image/QQ群.png` is referenced by all three READMEs but is **not explicitly listed in the ticket's scope bullets**, while the ticket's own acceptance criterion ("No Chinese characters in `README.md`, `README-EN.md` body text") would still flag its src path. Either we (a) expand scope to rename it as well or (b) accept a deviation. Recommendation: expand scope — same shape of fix, trivial cost, satisfies the literal acceptance criterion.
- **Constraint:** `backend/pyproject.toml:4` carries the identical Chinese tagline string as `package.json:4`. Not in original ticket bullets but is the obvious twin and would surprise a reviewer reading the diff. Already incorporated into requirements.md R1 acceptance criterion 4.
- **Unknown / Research Needed (minor):** Confirm GitHub Pages, the live demo site, and any external link to the screenshots do not deep-link into Chinese-named asset URLs. Quick `gh` / web check during design phase will resolve.

## 3. Implementation Approach Options

This is a docs/asset-rename feature. There is no algorithm to design — the only real decision is whether the renames go through `git mv` (preserves history) or `git rm`/`git add` (loses history). And whether to expand scope to `QQ群.png`.

### Option A — Strict ticket scope (no QQ群.png rename)

- Rename only the eight assets explicitly listed: `运行截图{1..6}.png`, `武大模拟演示封面.png`, `红楼梦模拟推演封面.jpg`.
- Translate taglines in `README.md`, `README-EN.md`, `package.json`, `backend/pyproject.toml`.
- Skip `QQ群.png`.

**Trade-offs:**
- ✅ Smallest possible diff; no scope creep.
- ❌ Acceptance criterion R4 ("no Chinese characters in README body outside language switcher") fails because line 220 still contains `QQ群` in the src path.

### Option B — Expanded scope including QQ群.png (RECOMMENDED)

- Same as Option A, plus rename `static/image/QQ群.png` → `static/image/qq-group.png` (or similar) and update its three references.

**Trade-offs:**
- ✅ Satisfies the ticket's own R4 acceptance criterion literally.
- ✅ One additional `git mv` + 3 string edits — negligible cost.
- ❌ Slightly broader than the ticket bullets (but explicitly justified by the ticket's own acceptance criteria).

### Option C — Hybrid (rename listed + leave QQ群 + edit alt-only)

Not viable: there is no way to leave the file in place and still satisfy R4 without renaming.

### Decision direction

Recommend Option B. Update requirements R2/R3 to include `QQ群.png` explicitly so the spec is internally consistent with R4.

## 4. Out-of-Scope for Gap Analysis

- Choice of exact ASCII filename slugs (decided in design phase).
- Whether to re-encode any image (No — bytes-preserving rename only, per R2.4).

## 5. Implementation Complexity & Risk

- **Effort:** **S (≈ half-day).** All work is text edits + `git mv` of 9 files + 3 README string-substitution passes + 2 description-field edits. No code changes, no tests.
- **Risk:** **Low.** Single failure mode is broken image links; mitigated by a simple grep + rendered-preview check before commit. No runtime, dependency, or pipeline impact. `git mv` preserves history.

## 6. Recommendations for Design Phase

- Adopt **Option B** (expanded scope including `QQ群.png`).
- Use `git mv` for all renames so history follows.
- Pick deterministic ASCII slugs; propose:
  - `Screenshot/screenshot{1..6}.png`
  - `wuhan-university-simulation-cover.png`
  - `dream-of-the-red-chamber-simulation-cover.jpg`
  - `qq-group.png`
- Collapse the duplicated tagline lines in `README.md` / `README-EN.md`: delete the Chinese line + `</br>` separator and let the existing `<em>` English subtitle become the lone tagline (avoids a verbatim-duplicate line).
- Verification step: re-run `rg '[\x{4e00}-\x{9fff}]' README.md README-EN.md package.json backend/pyproject.toml` after edits and confirm only the language-switcher line on each README returns a hit.

## Research items to carry forward

- (Light) confirm no off-repo deep-link into the renamed assets (live demo site, social cards). If a deep link is found, decide whether to leave a redirect / note in the PR.
