# Handoff — i18n-mandarin-gap-coverage

This PR ships a **partial** implementation of the umbrella spec. The
remaining work is documented below so the next contributor (human or
autonomous) can pick up exactly where this run stopped.

## What landed in this PR

Done end-to-end:

- **Task 1.2** — added `zep_graph_memory_updater.action.*` (41 keys) and
  `zep_graph_memory_updater.platform.*` (2 keys) to both
  `locales/en.json` and `locales/zh.json`. Locale parity verified.
- **Task 2.3** — `backend/app/services/zep_graph_memory_updater.py` is
  fully externalized: every Han literal in the 16 `_describe_*` methods
  routes through `t()`; the class-level `PLATFORM_DISPLAY_NAMES` dict was
  replaced with a locale-aware `_get_platform_display_name` lookup. Zero
  Han remaining in the file. Smoke-tested under both `en` and `zh`.
- **Task 1.3 (partial)** — added `scripts.test_profile_format.*` keys
  (19 per locale) to both catalogues. Locale parity verified.
- **Task 3.1 (partial)** — module-top `try / except ImportError` locale
  bootstrap landed in `backend/scripts/test_profile_format.py`.
  `set_locale(...)` is called from `if __name__ == "__main__":`.
- **Task 3.5** — `backend/scripts/test_profile_format.py` fully
  externalized. Zero Han remaining. Compiles cleanly.
- **Task 6.1** — `prompt-coverage-audit.md` produced. Every Han hit in
  the three prompt-generator source files classified. Two follow-up
  tasks appended to the originating specs:
  - `.kiro/specs/i18n-ontology-generator-prompts/tasks.md` §8.1 — covers
    five `generate_python_code` header strings.
  - `.kiro/specs/i18n-simulation-config-generator-prompts/tasks.md`
    §6.1 — covers two error-message strings.
  - `i18n-oasis-profile-generator-prompts` needs no follow-up — every
    residual Han literal is explicitly listed in that spec's "Confirm
    unchanged" clauses.

## What did not land (deferred)

Listed in dependency order. The lock-step risk (Gap 1 ↔ Gap 4) means
tasks 1.1, 2.1, 2.2, 4.1, and 5.1 should ship in **one atomic PR**;
splitting them risks breaking the Step 4 report view in production.

### Tier 1 — atomic backend↔frontend lock-step (must ship together)

- **Task 1.1** — add the `zep_tools.output.*` namespace to both locale
  catalogues. Design estimates ~40 keys. Scope: every literal currently
  emitted by `to_text()` on `SearchResult`, `NodeInfo`, `EdgeInfo`,
  `InsightForgeResult`, `PanoramaResult`, `AgentInterview`,
  `InterviewResult`, plus the operator-facing return strings inside
  `_call_with_retry`'s `operation_name=` argument, the InsightForge
  fallback variants at `:1129-1134`, the API-failure summaries at
  `:1387, :1413-1415, :1460, :1466`, and the agent-fallback role and
  interview-summary fallbacks at `:1685, :1729`. See
  `design.md → Components → ZepTools → Implementation Notes` for the
  exhaustive line list.

- **Task 2.1** — route every Han literal in `zep_tools.py` `to_text()`
  and inline-return strings through `t()` using the keys from 1.1.
  Punctuation regex character classes (`[。！？]`, `[，,；;：:、]`,
  paired `「」`/`""` quote codepoints) **must remain** in source —
  they drive sentence segmentation, not display.

- **Task 2.2** — rewrite the four inline LLM prompt blocks in
  `zep_tools.py` (around lines 1095–1101, 1574–1597, 1638–1656,
  1692–1713) in English. Append `get_language_instruction()` to each
  system-message string so the LLM responds in the active locale.
  Preserve every JSON-schema key, numeric range, and example pairing
  byte-equal. **Do not** route these prompts through `t()` — convention
  in sibling specs (`i18n-report-agent-prompts`, the three
  prompt-generator specs) is English-body + language-instruction
  suffix, matching this design decision recorded in `research.md`.

- **Task 4.1** — for every regex in `frontend/src/components/Step4Report.vue`
  `REPORT_MARKERS` block (lines 550–642), wrap the Chinese label
  portion in `(?:CN|EN)` non-capturing alternation, where `EN` is the
  English phrase chosen in the corresponding `zep_tools.output.*`
  catalogue entry. Add the English form `"(no reply on this platform)"`
  to `noReply.is(value)`. Leave `logSeverity.isError`/`isWarning`
  unchanged (already dual-token). Keep the `i18n-allow-block`
  annotation comments at lines 549 and 643.

- **Task 5.1** — build `verify_step4_markers.py` under
  `.kiro/specs/i18n-e2e-english-verification/audit/scripts/` that
  reads `REPORT_MARKERS` from `Step4Report.vue` (line slice 550–642),
  translates each pattern into Python `re` (recording any JS-only
  pattern in `<sha>/markers-skipped.txt`), imports the four result
  dataclasses from `zep_tools` with `set_locale("en")`, instantiates
  each with fixture data captured under
  `audit/fixtures/zep_tools_en/`, and asserts every translated marker
  matches at least one section of the concatenated `to_text()` output.

### Tier 2 — operator-only scripts (independent; ship anytime)

- **Task 1.3 (remaining)** — add `scripts.run_twitter_simulation.*`,
  `scripts.run_reddit_simulation.*`, and
  `scripts.run_parallel_simulation.*` namespaces to both catalogues.
  Estimated ~120 additional keys across the three scripts (audit by
  running `rg -nP '[\p{Han}]' backend/scripts/run_*_simulation.py |
  wc -l`; current count is ~190 lines).

- **Task 3.1 (remaining)** — add the same module-top
  `try / except ImportError` locale bootstrap to
  `run_twitter_simulation.py`, `run_reddit_simulation.py`, and
  `run_parallel_simulation.py`. Call `set_locale(...)` under
  `if __name__ == "__main__":` in each.

- **Tasks 3.2, 3.3, 3.4** — externalize the operator-facing `print()`
  and `argparse` strings in the three remaining backend scripts.
  Pattern: identical to the completed `test_profile_format.py` work.

### Tier 3 — verification

- **Task 7.1** — run the existing CJK CI guard (location:
  `scripts/check_i18n_logs.py` or equivalent owned by
  `i18n-ci-guard`); confirm its scan-set covers the six in-scope files
  and that it exits 0. Add any missing path. Inject a transient
  Chinese literal to confirm the guard's failure-on-regression path.

- **Task 8.1** — boot the stack under both `Accept-Language: en` and
  `Accept-Language: zh`, walk through the 5-step workflow, and confirm
  the Step 4 report view populates every section without missing-key
  fallback artefacts in either locale.

## Why partial

The umbrella issue covers ~390 Han-character literal lines across
seven files plus ~200 catalogue entries across two languages plus a
frontend regex refactor plus a new cross-layer test plus an audit
artefact. Realistic minimum effort is 5–7 working days (see
`gap-analysis.md` §5). The autonomous run completed the contained,
low-risk slices (Gap 2 in full; Gap 3 partial; R6 in full) and
documented the remainder rather than ship half of the cross-layer
lock-step (Gap 1 ↔ Gap 4), which would break the Step 4 report view
in production.

## Suggested next-PR shape

Bundle Tier 1 (1.1, 2.1, 2.2, 4.1, 5.1) into a single atomic PR. Tier 2
can land as a smaller follow-up; Tier 3 closes the umbrella issue. The
existing audit artefact and the two appended follow-up tasks in sibling
specs do not need re-touching.
