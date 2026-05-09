# Requirements Document

## Project Description (Input)
Backfill 10 keys in `locales/zh.json` that still hold English values, so Chinese UI users see Chinese strings everywhere. The `locales/en.json` and `locales/zh.json` files are structurally aligned (629 keys each) and `en.json` contains zero Chinese — this is the inverse problem (zh.json with English values), bundled into the i18n epic for symmetry.

## Introduction

This spec covers the work to translate ten remaining English-only natural-language values in `locales/zh.json` into natural Chinese, so that Chinese UI users see Chinese labels across the affected workflow steps and the graph panel. The change is data-only (locale JSON edits) and must keep `locales/en.json` and `locales/zh.json` structurally aligned (same key set, same key order). Tracks GitHub issue #8.

## Boundary Context

- **In scope**:
  - Translation of nine user-facing English values in `locales/zh.json` (the keys listed in the project description, excluding the brand string).
  - A documented decision for `log.prepareTaskId` — translate or keep English, recorded in the PR description with rationale.
  - Preservation of all interpolation placeholders (`{count}`, `{taskId}`, etc.) verbatim.
  - Preservation of the existing key set and key order in `locales/zh.json` so it remains structurally aligned with `locales/en.json`.
- **Out of scope**:
  - Any English-side translation work in `locales/en.json` (covered by other tickets in the i18n epic).
  - Restructuring locale files, moving keys between sections, or changing the i18n loader.
  - Adding new keys for currently-untranslated UI elements (file a separate issue if any are discovered).
  - Frontend code changes (`*.vue`, `*.js`, `*.ts`).
- **Adjacent expectations**:
  - The frontend i18n loader (`vue-i18n` + `frontend/src/i18n/`) reads `locales/en.json` and `locales/zh.json` directly; it expects identical key trees in both files.
  - The acceptance check `diff <(jq -r 'paths(scalars) | join(".")' locales/en.json | sort) <(jq -r 'paths(scalars) | join(".")' locales/zh.json | sort)` must remain empty after the change.

## Requirements

### Requirement 1: Backfill English-only values in `locales/zh.json` with natural Chinese
**Objective:** As a Chinese-locale UI user, I want all user-facing labels on Step 3, Step 4, Step 5, and the graph panel to be displayed in Chinese, so that I do not see English text mixed into a Chinese UI.

#### Acceptance Criteria
1. When the Chinese locale is active and a user views the Step 3 simulation screen, the MiroFish frontend shall render `step3.waitingForActions` as a natural Chinese translation of "Waiting for agent actions..." (preserving the trailing ellipsis).
2. When the Chinese locale is active and a user views the Step 4 report screen, the MiroFish frontend shall render `step4.waitingForReportAgent` as a natural Chinese translation of "Waiting for Report Agent...".
3. When the Chinese locale is active and a user views the Step 5 interaction screen, the MiroFish frontend shall render `step5.interactiveTools`, `step5.agentsAvailable`, and `step5.reportAgentChat` as natural Chinese strings.
4. When the Chinese locale is active and a user opens the graph panel, the MiroFish frontend shall render `graph.panelTitle`, `graph.nodeDetails`, and `graph.relationship` as natural Chinese strings.
5. The translated value for `step5.agentsAvailable` shall contain the placeholder `{count}` exactly once and at a position that produces grammatically natural Chinese when interpolated.
6. The MiroFish locale data shall keep `home.heroDescBrand` set to the literal string `"MiroFish"` because it is a proper noun.

### Requirement 2: Documented decision for `log.prepareTaskId`
**Objective:** As a maintainer, I want a recorded, justified decision about whether `log.prepareTaskId` should be translated, so that future contributors understand why this value differs from the surrounding policy.

#### Acceptance Criteria
1. Where `log.prepareTaskId` is intentionally retained as a locale-neutral English log scaffold, the MiroFish PR description shall document that decision and the reason (log scaffold convention).
2. Where `log.prepareTaskId` is treated as a user-facing string, the MiroFish locale data shall translate it to natural Chinese while preserving the leading whitespace, the `└─` glyph, and the `{taskId}` placeholder verbatim.
3. The MiroFish PR description shall list any keys that remain English on purpose (brand strings and any retained log scaffolds) so reviewers can see they were not overlooked.

### Requirement 3: Preserve structural alignment and placeholders
**Objective:** As a frontend developer relying on `vue-i18n`, I want `locales/en.json` and `locales/zh.json` to keep the same key set and the same key order, so that fallbacks and tooling continue to work and diffs stay reviewable.

#### Acceptance Criteria
1. The MiroFish locale data shall keep the set of scalar key paths in `locales/zh.json` identical to the set in `locales/en.json` (the diff command in the boundary context shall produce no output).
2. The MiroFish locale data shall preserve the existing order of keys in `locales/zh.json` for every object that is not modified by this change.
3. For every translated value, the MiroFish locale data shall preserve interpolation placeholders (`{count}`, `{taskId}`, …) byte-for-byte.
4. If a translation requires inserting or removing a placeholder, then the MiroFish change shall be rejected and the translation revised, because placeholder drift breaks runtime interpolation.
5. The MiroFish locale data shall remain valid JSON (parseable by `JSON.parse` / `jq`) after the change.

### Requirement 4: No frontend code changes
**Objective:** As a reviewer, I want the diff to be limited to `locales/zh.json`, so that the change is easy to verify and unrelated risk is excluded.

#### Acceptance Criteria
1. The MiroFish change shall modify only `locales/zh.json`; no `*.vue`, `*.js`, `*.ts`, `*.py`, or other source files shall be edited.
2. The MiroFish change shall not add, rename, or delete keys in `locales/zh.json`; only the values of the listed keys may change.
3. If a listed value in `locales/zh.json` already contains natural Chinese (an upstream change landed first), then the MiroFish change shall leave that value untouched and note the skip in the PR description.
