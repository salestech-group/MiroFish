# Research & Design Decisions — i18n-readme-tagline-and-assets

## Summary
- **Feature**: `i18n-readme-tagline-and-assets`
- **Discovery Scope**: Simple Addition (docs cleanup + asset rename, no runtime code paths)
- **Key Findings**:
  - The duplicate Chinese-tagline / English-`<em>` structure on lines 7–9 of `README.md` and `README-EN.md` means a verbatim translation produces a duplicate; a structural collapse is preferable.
  - `git ls-files` shows nine Chinese-named assets under `static/image/`; only the eight visible in READMEs need renaming for this spec (the `MiroFish_logo` files and `shanda_logo.png` already use ASCII names).
  - `backend/pyproject.toml:4` is a twin of `package.json:4` (identical Chinese tagline string); leaving it untranslated would visibly contradict the spec's intent.

## Research Log

### Topic — Inventory of Chinese-named assets and references

- **Context**: Confirm the full set of files and references the spec must touch so no broken-image regression slips in.
- **Sources Consulted**: `git ls-files static/image/`, `rg '[\x{4e00}-\x{9fff}]'` over `README.md`, `README-EN.md`, `README-ZH.md`, `package.json`, `backend/pyproject.toml`.
- **Findings**:
  - Tracked Chinese-named files (9): `QQ群.png`, six `Screenshot/运行截图{N}.png`, `武大模拟演示封面.png`, `红楼梦模拟推演封面.jpg`.
  - Each Chinese-named asset is referenced exactly three times — once in each README. No code path or test references them.
  - `locales/zh.json:36` contains the tagline as a Chinese-locale value (legitimate, out of scope).
- **Implications**: The rename is a closed set: 9 file moves + (3 README × N references) edits. No runtime impact.

### Topic — Tagline structure on lines 7–9

- **Context**: Decide the cleanest replacement for the Chinese tagline on the English-facing READMEs.
- **Sources Consulted**: `README.md:7-9`, `README-EN.md:7-9`.
- **Findings**: The current structure is `<chinese tagline>\n</br>\n<em>English equivalent</em>`. The English subtitle already exists. Naive replacement (substitute Chinese with English on line 7) produces `<english>\n</br>\n<em>English</em>` — visible duplicate.
- **Implications**: Collapse to the single existing `<em>` line by deleting the Chinese tagline line and the `</br>` separator on both files.

### Topic — `git mv` vs. `rm`/`add` for renames

- **Context**: Choose a rename mechanism that preserves blame/history on the assets.
- **Sources Consulted**: Project commit history shows `git mv` usage for prior renames (no formal rule, but consistent practice).
- **Findings**: `git mv "old" "new"` records a rename in the index. Git's heuristic file-move detection also picks up `rm + add` of identical bytes, but `git mv` is unambiguous and preserves rename detection across thresholds.
- **Implications**: Use `git mv` for all nine renames. Quote source paths (rule from `.claude/rules/file-paths.md`) since they contain non-ASCII characters.

### Topic — Off-repo deep links to renamed assets (light check)

- **Context**: The ticket's gap analysis flagged a research item: confirm no external pages deep-link the Chinese-named files.
- **Sources Consulted**: `git grep` of repo (no off-repo references). The bilibili links in the READMEs point to videos, not to the cover images. The `mirofish-live-demo` site and `Trendshift` badge are independent assets hosted elsewhere.
- **Findings**: No in-repo references outside the READMEs. Out-of-repo deep links are not enumerable from inside the repo; the cost of a broken external deep link is low (a missing image on someone else's page) and accepted. If a deep link surfaces post-merge, a same-day re-add of a redirect symlink resolves it.
- **Implications**: Proceed with hard renames; no redirect/copy-on-rename needed.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Strict ticket scope | Rename only the 8 explicitly listed assets; leave `QQ群.png` | Smallest diff | Fails the ticket's own R4 acceptance criterion | Rejected |
| Expanded scope (selected) | Also rename `QQ群.png` and update `backend/pyproject.toml` | Internally consistent with R4; trivial cost | Slightly broader than ticket bullets | Selected |
| Hybrid (allow exception in R4) | Rename the 8 listed, exempt `QQ群` in the verification scan | Preserves the ticket bullets exactly | Adds an explicit ad-hoc exception that future readers must decode | Rejected |

## Design Decisions

### Decision: Rename `static/image/QQ群.png` to ASCII despite not being in the ticket's bullet list

- **Context**: Acceptance criterion R4 ("no Chinese characters in `README.md` / `README-EN.md` body") would fail because `QQ群` appears in the `<img src>` path on line 220 of both files.
- **Alternatives Considered**:
  1. Strict scope — leave `QQ群.png` and accept R4 fail.
  2. Expand scope — rename and update.
  3. Exempt `QQ群.png` in R4's verification scope with explicit allow-list.
- **Selected Approach**: Expand scope. Rename `static/image/QQ群.png` → `static/image/qq-group.png`, update three references.
- **Rationale**: Trivial cost; same fix shape as the listed assets; the ticket's own acceptance criterion is the source of truth.
- **Trade-offs**: One extra file move. None material.
- **Follow-up**: None.

### Decision: Translate `backend/pyproject.toml:4` description in the same PR

- **Context**: `backend/pyproject.toml` carries the identical Chinese tagline as `package.json`. Leaving it untranslated produces a half-finished diff.
- **Alternatives Considered**:
  1. Leave it for a follow-up ticket.
  2. Translate it now alongside `package.json`.
- **Selected Approach**: Translate now.
- **Rationale**: Identical string, identical fix, same review surface. Splitting would create needless coordination.
- **Trade-offs**: One additional one-line diff. None material.
- **Follow-up**: None.

### Decision: Collapse duplicate tagline structure rather than substitute in place

- **Context**: Lines 7–9 of `README.md` and `README-EN.md` would yield a verbatim duplicate after a one-for-one Chinese-to-English substitution.
- **Alternatives Considered**:
  1. Substitute Chinese line in place (produces duplicate).
  2. Delete Chinese line + `</br>` separator; let the existing `<em>` line stand alone.
  3. Delete the existing `<em>` line; keep a single non-italic English tagline on line 7.
- **Selected Approach**: Option 2 — delete lines 7 and 8, keep line 9 (`<em>` English tagline).
- **Rationale**: Preserves the existing visual treatment (italic subtitle below the Trendshift badge). Avoids style drift on a docs-only PR.
- **Trade-offs**: Slightly different visual weight (italic only) vs. the prior bilingual stack (plain Chinese + italic English). Acceptable for an English-facing doc.
- **Follow-up**: None.

### Decision: Use `git mv` for all renames

- **Context**: Need to preserve rename detection.
- **Alternatives Considered**: `git mv` vs. shell `mv` + `git rm` / `git add`.
- **Selected Approach**: `git mv "old" "new"` with quoted paths.
- **Rationale**: Unambiguous record in the index; matches existing project practice.
- **Trade-offs**: None.
- **Follow-up**: None.

## Risks & Mitigations

- **Risk:** Broken images on rendered GitHub README after merge. **Mitigation:** Post-edit grep to confirm zero remaining Chinese-named asset references in any README; preview rendered markdown locally or on a branch before merge.
- **Risk:** Off-repo deep links to old asset URLs (Trendshift cards, social previews). **Mitigation:** Accepted; cost is a single missing image on an external page.
- **Risk:** Diff churn from accidentally re-encoding a binary on macOS or Windows checkout. **Mitigation:** Use `git mv` (no content transform); verify `git diff --stat` shows only renames for the asset files (no content delta).

## References
- Ticket source: `.ticket/12.md` / GitHub issue #12.
- Project rule on quoting paths: `.claude/rules/file-paths.md`.
- Project commit conventions: `.claude/rules/commits.md` and `.kiro/steering/structure.md`.
