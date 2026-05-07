# Implementation Plan

- [x] 1. Translate Chinese taglines to English in the project's English-facing metadata
  - In `README.md`, delete the Chinese tagline line and the immediately following `</br>` line so the existing italic English subtitle on the next line stands as the lone tagline; verify the result still renders with one tagline visible above the Shanda badge
  - Apply the identical edit to `README-EN.md`
  - In `package.json`, set the `description` value to `MiroFish - A Simple and Universal Swarm Intelligence Engine, Predicting Anything`
  - In `backend/pyproject.toml`, set the `description` value to the same English string used in `package.json`
  - Leave `README-ZH.md` line 7 (the Chinese tagline) untouched
  - Observable completion: a ripgrep scan for `[\x{4e00}-\x{9fff}]` over `README.md`, `README-EN.md`, `package.json`, and `backend/pyproject.toml` returns hits **only** on the language-switcher line of the two READMEs
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. (P) Rename Chinese-named static image assets to ASCII filenames using git mv
  - Move the six screenshot files `static/image/Screenshot/运行截图{1..6}.png` to `static/image/Screenshot/screenshot{1..6}.png`
  - Move `static/image/武大模拟演示封面.png` to `static/image/wuhan-university-simulation-cover.png`
  - Move `static/image/红楼梦模拟推演封面.jpg` to `static/image/dream-of-the-red-chamber-simulation-cover.jpg`
  - Move `static/image/QQ群.png` to `static/image/qq-group.png`
  - Quote source paths in shell invocations because they contain non-ASCII characters
  - Use `git mv` (not shell `mv` + `git add`) so rename detection is recorded directly in the index
  - Observable completion: `git status` reports nine `renamed:` entries with no other file modifications; `git diff --stat -M` shows zero content-line delta for each asset
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_
  - _Boundary: static/image/_

- [x] 3. Update README image references to point at the renamed ASCII asset paths
  - In `README.md`, rewrite the nine `<img src="...">` paths on lines 52–61, 71, 79, and 220 so each points at the corresponding ASCII filename from task 2
  - Apply the identical nine edits to `README-EN.md`
  - Apply the identical nine edits to `README-ZH.md` (asset path updates only — Chinese body text and Chinese alt attributes preserved)
  - Observable completion: a ripgrep search for `运行截图|武大模拟演示封面|红楼梦模拟推演封面|QQ群` in `README.md`, `README-EN.md`, and `README-ZH.md` returns zero matches
  - _Requirements: 3.1, 3.2, 3.3_
  - _Depends: 2_

- [x] 4. Verify acceptance gates before commit
- [x] 4.1 Run the Chinese-character verification scan and confirm zero residual hits in the EN READMEs body
  - Execute `rg --pcre2 '[\x{4e00}-\x{9fff}]' README.md README-EN.md | rg -v 'README-ZH\.md'` from the repo root
  - Observable completion: the pipeline produces zero output lines, confirming the only Chinese characters left in the EN READMEs are inside the language-switcher link to `README-ZH.md`
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 4.2 Confirm asset renames are byte-preserving and unambiguous
  - Run `git diff --stat -M` and verify each of the nine asset files appears as a pure rename (no `+` or `-` line counts)
  - Run `git status` and confirm there are no untracked Chinese-named files left behind in `static/image/` or `static/image/Screenshot/`
  - Observable completion: nine `renamed:` entries in `git status`; zero untracked Chinese-named asset files; zero content delta on the asset rows of `git diff --stat`
  - _Requirements: 2.5, 2.6, 3.4_

- [x] 4.3 Confirm rendered images by spot-checking the README in a Markdown previewer
  - Open `README.md`, `README-EN.md`, and `README-ZH.md` in a Markdown preview (GitHub preview on the feature branch or local previewer) and inspect the screenshot grid, the two video-cover thumbnails, and the QQ group image on each file
  - Observable completion: every `<img>` element renders an actual image (no broken-image placeholder) on all three READMEs
  - _Requirements: 3.4_
  - **Note**: This task ran in an autonomous environment where no Markdown previewer was available; instead, every `<img src>` path in all three READMEs was cross-checked against the working tree and all 33 references resolved to existing files (zero broken paths). A reviewer should still spot-check on the GitHub-rendered PR preview.
