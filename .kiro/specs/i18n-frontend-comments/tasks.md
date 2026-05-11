# Implementation Plan

## Foundation

- [x] 1. Sweep TODO/FIXME markers and capture pre-translation baseline
  - Run `rg 'TODO|FIXME' frontend/src/` and record all matches with file/line; for each, note whether the description is in Chinese (in scope for translation) or already English (out of scope per Boundary Commitments).
  - Capture the pre-translation ripgrep baseline so the verification command output can be compared after the translation pass.
  - Observable completion: a working note (not committed) listing every TODO/FIXME in `frontend/src/`, classified as "translate-and-tag", "already-tagged", or "English-out-of-scope", and a recorded count of files matching `[\x{4e00}-\x{9fff}]` in `frontend/src/` (expected: 20 files, ~902 occurrences).
  - _Requirements: 3.1, 3.2, 3.3, 5.1_

## Core Translation Pass

- [x] 2. Translate light-touch files (≤10 hits)
  - Translate Chinese comments to English in `App.vue`, `store/pendingUpload.js`, `views/MainView.vue`, `views/InteractionView.vue`, `views/ReportView.vue`, `components/Step1GraphBuild.vue`, `api/index.js`, `api/graph.js`, `api/report.js`. Apply the region-eligibility matrix from design.md: translate line/block/JSDoc/template comments; preserve JSDoc tag syntax; delete comments that merely restate the next statement; keep comments that encode intent.
  - Translate Chinese content inside `console.error|warn|log` string literals in `components/Step1GraphBuild.vue` (3 known hits at lines 216, 237, 241). Leave all other string literals unchanged.
  - For any TODO/FIXME marker that was Chinese and lacked a ticket reference, append `(#9)`; preserve existing references.
  - Observable completion: `rg '[\x{4e00}-\x{9fff}]' frontend/src/{App.vue,store,views/MainView.vue,views/InteractionView.vue,views/ReportView.vue,components/Step1GraphBuild.vue,api}` returns no matches (no retained-bilingual cases expected in this group).
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.2, 4.4, 5.4_

- [x] 3. Translate mid-touch files (10–60 hits)
  - Translate `api/simulation.js` (29 hits, JSDoc-heavy: keep `@param`, `@returns`, etc., translate only natural-language content), `views/SimulationRunView.vue` (18 hits), `views/SimulationView.vue` (22 hits), `views/Home.vue` (43 hits), `components/Step5Interaction.vue` (34 hits), `components/Step3Simulation.vue` (52 hits).
  - In `components/Step5Interaction.vue`, retain Chinese inside the LLM prompt template strings (around lines 725–727) per Requirement 1.5; record file/line in a working note for the PR description. Translate all comments and any non-LLM-prompt Chinese content in this file as normal.
  - For any other Chinese-content string literal encountered in this group, leave the literal unchanged and record file/line for the PR description.
  - Observable completion: `rg '[\x{4e00}-\x{9fff}]' <files-in-group>` returns matches only for `components/Step5Interaction.vue` (LLM prompt strings) and any other documented retained-bilingual literals; no comment-region match remains in any of these files.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.2, 4.4, 5.4_

- [x] 4. Translate high-touch files (>60 hits)
  - Translate `components/Step2EnvSetup.vue` (76 hits), `components/GraphPanel.vue` (84 hits, mixed D3 logic comments and `<template>` comments), `components/HistoryDatabase.vue` (124 hits), `components/Step4Report.vue` (176 hits), `views/Process.vue` (191 hits, the 2067-line workflow orchestrator).
  - These files concentrate ~80% of total occurrences; budget time accordingly. Apply the same region-eligibility matrix as task 2: translate comments, preserve JSDoc tag syntax, delete redundant comments, keep intent-bearing ones.
  - Translate `console.*` Chinese strings if encountered; leave LLM prompts and other string literals unchanged and record for the PR description.
  - Observable completion: `rg '[\x{4e00}-\x{9fff}]' frontend/src/components/{Step2EnvSetup,GraphPanel,HistoryDatabase,Step4Report}.vue frontend/src/views/Process.vue` returns no comment-region matches; any residuals are documented retained-bilingual string literals.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.2, 4.4, 5.4_

## Integration & Validation

- [x] 5. Run final acceptance verification
  - Run `rg '[\x{4e00}-\x{9fff}]' frontend/src/` on the full directory and confirm output is empty or contains only the pre-recorded retained-bilingual files (LLM prompt strings in `components/Step5Interaction.vue` and any others documented during tasks 2–4).
  - Run `npm run build` and confirm exit code 0 and successful Vite build output.
  - Run `git diff --stat main..HEAD` (or against the branch base) and confirm only `frontend/src/**` paths are modified — no edits under `/locales/`, `/backend/`, or repo root.
  - Observable completion: all three checks pass; if any check fails, return to the relevant translation task before proceeding to PR.
  - _Requirements: 1.1, 4.1, 4.2, 5.4_

- [x] 6. Manual UI smoke check
  - Run `npm run dev`; in a browser, navigate Home → Process → each Step component (1–5) → Interaction → Report; confirm rendering matches the pre-translation baseline (no missing text, no broken bindings, no console errors that did not exist before).
  - Per `tech.md` steering, the manual smoke is the only practical proof that no executable change crept in; type-check or build pass alone is not sufficient.
  - Observable completion: every page renders identically to baseline; no new console errors; the implementer can confirm "UI unchanged" in the PR description.
  - _Requirements: 4.3_

- [x] 7. Compose PR description with verification artifacts
  - Draft the PR body listing: (a) the verification command `rg '[\x{4e00}-\x{9fff}]' frontend/src/` and its post-translation output, (b) the file count and any retained-bilingual files with one-line rationale per Requirement 5.2, (c) confirmation that the manual UI smoke passed, (d) confirmation that no files outside `frontend/src/` were modified.
  - Use branch name `docs/i18n-9-translate-frontend-comments` and commit message `docs(i18n): translate chinese comments in frontend src to english` per Requirement 5.3 and the project's Conventional Commits rule.
  - Observable completion: the PR description, branch name, and commit subject are ready to use by `/done`; all five Requirement 5 acceptance criteria are visibly satisfied in the PR body.
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
