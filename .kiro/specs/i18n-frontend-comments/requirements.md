# Requirements Document

## Introduction

This spec covers a pure-documentation cleanup pass: translate Chinese developer comments in `frontend/src/` to English so English-speaking maintainers can read the code. The change is documentation-only — no runtime behavior changes, no UI string changes (those live in `/locales/*.json`), and no architectural refactor. Tracked as GitHub issue #9, the lowest user-impact ticket in the i18n epic (#11).

The work targets developer-facing comments in 20 known files: 7 views, 7 components, 4 `api/*.js` modules, `App.vue`, and `store/pendingUpload.js`. The discovery method is `grep -rln '[一-鿿]' frontend/src/` (or the ripgrep equivalent), which must return zero matches at completion (or only files explicitly listed as deliberately bilingual in the PR description).

## Boundary Context

- **In scope**: Translating Chinese developer comments (line comments, block comments, JSDoc, and Vue `<!-- ... -->` template comments) to English in `frontend/src/`. Dropping comments that merely restate the code, per `dev-guidelines.md`. Appending ticket references to TODO/FIXME markers that lack one.
- **Out of scope**: Any user-facing string, label, placeholder, toast, or template-rendered text — these live in `/locales/en.json` and `/locales/zh.json` and are tracked separately (see #8). Restructuring comments into JSDoc unless they are already JSDoc-shaped. Reformatting code, renaming identifiers, or any non-comment change. Backend Python comments (covered by ticket #7).
- **Adjacent expectations**: The Vite build (`npm run build`) and the Vue dev server (`npm run dev`) must continue to compile and run. The `vue-i18n` translation surface in `/locales/*.json` is unaffected. The frontend `api/` services keep their existing behavior — the 5-min Axios timeout and exponential retry described in steering remain unchanged.

## Requirements

### Requirement 1: Comment Translation Coverage

**Objective:** As a frontend maintainer who does not read Chinese, I want every developer comment in `frontend/src/` to be in English, so that I can understand intent without translation tooling.

#### Acceptance Criteria

1. The Frontend Source Tree shall contain no Chinese characters (Unicode range U+4E00–U+9FFF) in any `.vue`, `.js`, or `.css` file under `frontend/src/`, as verified by ripgrep `[\x{4e00}-\x{9fff}]` returning zero matching files.
2. When a Chinese comment is translated, the Translation Pass shall preserve the original semantic intent (the *why* the comment was written) without paraphrasing into a different meaning.
3. Where a comment exists in `<script>`, `<template>`, or `<style>` blocks of a Single-File Component, the Translation Pass shall translate it in-place using the syntax appropriate to that block (`//` / `/* */` for script and style, `<!-- -->` for template).
4. If a Chinese comment is part of a JSDoc block (`/** ... */`), the Translation Pass shall keep the JSDoc structure intact and translate only the natural-language content.
5. Where a deliberately-bilingual comment must be retained (e.g. a quotation, a domain term needing the original), the Translation Pass shall list the file in the PR description and shall keep an English explanation alongside the Chinese.

### Requirement 2: Drop Redundant Comments

**Objective:** As a code reviewer, I want comments that merely restate the code to be removed during the translation pass, so that the codebase aligns with `dev-guidelines.md` ("comment the *why*, not the *what*").

#### Acceptance Criteria

1. When a Chinese comment only paraphrases the immediately following statement in different words (e.g. `// 获取数据` above `fetchData()`), the Translation Pass shall delete the comment rather than translate it.
2. When a Chinese comment encodes non-obvious intent (a constraint, an invariant, a workaround, a reason behind a magic number), the Translation Pass shall translate it rather than delete it.
3. If a comment's value cannot be judged from local context alone, the Translation Pass shall translate it conservatively (preserve rather than delete) and shall not delete a comment merely because the maintainer is unsure of its purpose.
4. The Translation Pass shall not introduce new comments beyond those required to translate or to add a TODO ticket reference; gratuitous explanatory comments are not added.

### Requirement 3: Preserve TODO/FIXME Markers and Add Ticket References

**Objective:** As a project maintainer tracking work-in-progress markers, I want every TODO and FIXME comment to carry a ticket reference, so that future cleanup can be triaged systematically.

#### Acceptance Criteria

1. When a Chinese TODO or FIXME comment is encountered, the Translation Pass shall keep the `TODO` / `FIXME` marker (uppercase, English) and translate the trailing description.
2. Where a TODO or FIXME marker lacks a ticket reference, the Translation Pass shall append a reference in the form `TODO(#<n>): …` or `FIXME(#<n>): …`, using `#9` if no more specific ticket exists for the underlying work.
3. If a TODO or FIXME marker already references a ticket (e.g. `TODO(#42)`), the Translation Pass shall preserve that reference unchanged.

### Requirement 4: No Runtime Behavior Change

**Objective:** As a release engineer, I want the translated branch to produce a behaviorally identical bundle, so that I can ship the change without retesting feature surfaces.

#### Acceptance Criteria

1. When `npm run build` runs against the translated branch, the Vite Build shall complete successfully with the same exit code (0) as the pre-translation baseline.
2. The Translation Pass shall not change any executable code: no identifier renames, no expression edits, no import or export changes, no Vue template structure changes outside `<!-- -->` comment text.
3. While the application is running in `npm run dev`, the User Interface shall render identically to the pre-translation baseline for the Home, Process, and each Step component flow on a manual smoke check.
4. If a translation pass risks ambiguity between a comment and a string literal (Chinese characters in a quoted string), the Translation Pass shall leave the string literal unchanged — string content is out of scope and belongs to `/locales/*.json`.

### Requirement 5: Verifiability and PR Hand-off

**Objective:** As a reviewer of this PR, I want a single command and a short checklist to confirm acceptance, so that review effort is bounded and reproducible.

#### Acceptance Criteria

1. The PR Description shall include the verification command and its expected output: `rg '[\x{4e00}-\x{9fff}]' frontend/src/` returns no matches (or only the deliberately-bilingual files listed in the PR).
2. The PR Description shall list any deliberately-retained bilingual comments with the file path and a one-line rationale.
3. The Branch Name shall be `docs/i18n-9-translate-frontend-comments` and the Commit Message shall start with `docs(i18n): translate chinese comments in frontend src to english` per the ticket's stated convention and the project's Conventional Commits rule.
4. The Translation Pass shall not modify files outside `frontend/src/` (notably no edits under `/locales/`, `/backend/`, or repo-root configuration).
