# Requirements Document

## Project Description (Input)
Translate the Chinese tagline in README.md, README-EN.md, and package.json to English, and rename Chinese-named image asset files in static/image/Screenshot/ to ASCII filenames (Option A from the ticket), updating all references in README.md and README-ZH.md. Acceptance: no Chinese characters in README.md or README-EN.md body text (except the language switcher link to README-ZH.md); package.json description in English; all image links work. Source: GitHub issue #12 (.ticket/12.md).

## Introduction

This feature removes the remaining Chinese surface text from the English documentation entry points (`README.md`, `README-EN.md`) and from the npm package metadata (`package.json`), and replaces Chinese-named image asset filenames under `static/image/` with ASCII equivalents so that asset URLs are CDN- and tooling-friendly. References to those assets are updated in all three READMEs (`README.md`, `README-EN.md`, `README-ZH.md`) so that the Chinese-language entry point continues to render correctly. The Chinese-language README (`README-ZH.md`) keeps its Chinese body text by design.

## Boundary Context

- **In scope**:
  - English tagline replacing Chinese tagline in `README.md`, `README-EN.md`, and `package.json` `description`.
  - Renaming `static/image/Screenshot/运行截图{1..6}.png` to ASCII filenames.
  - Renaming `static/image/武大模拟演示封面.png` and `static/image/红楼梦模拟推演封面.jpg` to ASCII filenames.
  - Renaming `static/image/QQ群.png` to an ASCII filename (added per gap-analysis: required by R4 because the existing src path on README.md:220 / README-EN.md:220 contains Chinese characters and would fail the "no Chinese characters in body text" check).
  - Updating all `<img src="...">` references to those renamed files in `README.md`, `README-EN.md`, and `README-ZH.md`.
  - Updating `backend/pyproject.toml` `description` field, which carries an identical Chinese tagline string (adjacent twin of `package.json`).
- **Out of scope**:
  - Translating the body of `README-ZH.md` (Chinese variant by design).
  - Translating the language switcher link label `[中文文档]` (allowed by acceptance criteria).
  - Touching `locales/zh.json` Chinese tagline value (legitimate Chinese locale content).
- **Adjacent expectations**:
  - The ticket recommends Option A (rename to ASCII). This spec adopts Option A.
  - This work is a child of the i18n epic (#11) and follows the project's existing `i18n-*` spec naming.

## Requirements

### Requirement 1: English tagline in English-facing documentation
**Objective:** As a non-Chinese-reading visitor landing on the GitHub repo or installing the npm package, I want the tagline in the English README files and the npm package metadata to be in English, so that I am not surprised by untranslated Chinese strings on the entry surface.

#### Acceptance Criteria
1. The README.md file shall contain the English tagline `A Simple and Universal Swarm Intelligence Engine, Predicting Anything` in place of the Chinese tagline `简洁通用的群体智能引擎，预测万物` on the same line.
2. The README-EN.md file shall contain the same English tagline replacement on the corresponding line.
3. The package.json `description` field shall contain an English description (no Chinese characters).
4. The backend/pyproject.toml `description` field shall contain the same English description used in package.json.
5. The README-ZH.md file shall keep its Chinese tagline unchanged.

### Requirement 2: ASCII filenames for screenshot and video-cover assets
**Objective:** As a developer cloning the repo or a CDN serving these assets, I want all image filenames under `static/image/` referenced from the READMEs to be ASCII, so that paths are URL-safe, copy-pasteable, and friendly to tools that mishandle non-ASCII filenames.

#### Acceptance Criteria
1. The `static/image/Screenshot/运行截图{N}.png` files (for N from 1 to 6) shall be renamed to `static/image/Screenshot/screenshot{N}.png`.
2. The `static/image/武大模拟演示封面.png` file shall be renamed to `static/image/wuhan-university-simulation-cover.png`.
3. The `static/image/红楼梦模拟推演封面.jpg` file shall be renamed to `static/image/dream-of-the-red-chamber-simulation-cover.jpg`.
4. The `static/image/QQ群.png` file shall be renamed to `static/image/qq-group.png`.
5. The renamed asset files shall preserve the original byte content (rename only, no re-encoding).
6. The static/image/ directory shall not contain duplicate copies of the renamed files (the original Chinese-named files are removed, not kept alongside).

### Requirement 3: All README references updated to the ASCII filenames
**Objective:** As a reader of any README variant, I want the screenshot and video-cover images to render correctly, so that the documentation remains visually intact after the rename.

#### Acceptance Criteria
1. The README.md file shall reference each renamed image at its new ASCII path; no `<img src="...">` in the file shall point to a Chinese-named file under `static/image/`.
2. The README-EN.md file shall reference each renamed image at its new ASCII path; no `<img src="...">` in the file shall point to a Chinese-named file under `static/image/`.
3. The README-ZH.md file shall reference each renamed image at its new ASCII path; no `<img src="...">` in the file shall point to a Chinese-named file under `static/image/`.
4. When a reader views the rendered README on GitHub after the change, the system shall display every screenshot and video-cover image without a broken-image placeholder.

### Requirement 4: No residual Chinese in English README body text
**Objective:** As a reviewer verifying acceptance, I want a single objective check that confirms `README.md` and `README-EN.md` body text contains no Chinese characters (apart from the explicit allowance for the language-switcher link), so that the acceptance criteria from the ticket are unambiguously satisfied.

#### Acceptance Criteria
1. The README.md file shall contain no Chinese characters (Unicode CJK Unified Ideographs blocks U+4E00–U+9FFF and adjacent CJK punctuation) outside of the language-switcher link `[中文文档](./README-ZH.md)`.
2. The README-EN.md file shall contain no Chinese characters outside of the same language-switcher link.
3. If a reviewer runs a Chinese-character scan over `README.md` and `README-EN.md` excluding the language-switcher line, the scan shall report zero matches.
