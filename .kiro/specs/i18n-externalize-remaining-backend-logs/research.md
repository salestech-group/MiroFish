# Research & Design Decisions

## Summary

- **Feature**: `i18n-externalize-remaining-backend-logs`
- **Discovery Scope**: Simple Addition (extending an established convention from ticket #6)
- **Key Findings**:
  - The `t()` helper, per-thread locale, and missing-key fallback are already in place in `backend/app/utils/locale.py` and require no changes.
  - The convention `t("log.<domain>.m###", **kwargs)` with `{name}` placeholders is already used by all sibling modules; this spec strictly extends it.
  - No existing test fixtures reference any of the nine Chinese strings to be replaced.

## Research Log

### Existing locale namespace structure
- **Context**: Need to add new keys without colliding with existing entries.
- **Sources Consulted**: `locales/en.json`, `locales/zh.json`, `.kiro/specs/i18n-externalize-backend-logs/requirements.md`.
- **Findings**:
  - `log.graph_api` is densely populated `m006`–`m019` plus `m026`. Free contiguous slots starting at the tail: `m027`, `m028`, `m029`.
  - `log.profile_generator` is densely populated `m001`–`m023`. Free slots: `m024`, `m025`.
  - `log.retry` does not exist; introducing it as a sibling to other `log.<domain>` namespaces matches the existing pattern.
- **Implications**: New keys append at the tail per existing namespace; `log.retry` is created fresh starting at `m001`.

### Locale resolution in async / background contexts
- **Context**: `retry.py` is shared infrastructure invoked from sync request handlers, background tasks, and async coroutines.
- **Sources Consulted**: `backend/app/utils/locale.py`, `backend/app/services/oasis_profile_generator.py` (uses `set_locale`), Flask docs (request-context behaviour).
- **Findings**:
  - `get_locale()` returns the request-context `Accept-Language` header when a Flask request is active, the per-thread locale otherwise, and `'zh'` as the default.
  - Asyncio coroutines run on the same OS thread by default, so the per-thread locale set by the parent function propagates into `await`-driven calls.
  - Missing-key fallback returns the key string and emits a deduped warning — never raises.
- **Implications**: No new locale-propagation wiring needed inside `retry.py`. Adding `from ..utils.locale import t` is sufficient.

### `print(...)` vs `logger` for the OASIS banners
- **Context**: Two `print(...)` banner statements at `oasis_profile_generator.py:945` and `:1001` decorate stdout. Should we keep them as `print` or fold them into existing `logger.info` calls?
- **Sources Consulted**: `backend/app/services/oasis_profile_generator.py:943` (existing `logger.info(t("log.profile_generator.m017", …))`), ticket #24 acceptance ("each `file:line` is fixed").
- **Findings**:
  - The existing `logger.info` and the `print(...)` are emitting the same logical event in two channels. The banner adds `'='*60` separators on the surrounding lines, which is purely a console-cosmetic; replacing the print with a logger call would lose the visual banner.
  - Ticket #24 wants externalisation, not removal.
- **Implications**: Keep both calls. Wrap the `print(f"...")` argument with `t(...)`. Introduce dedicated keys (`m024`, `m025`) so the banner copy is decoupled from the structured log copy at `m017`.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Append-at-tail (selected) | Add new `m###` keys at the next contiguous slot per namespace; create `log.retry` fresh | Mirrors #6 convention; minimal diff; no overwrite risk | Numbering gaps under `log.graph_api` remain | Aligns with steering principle of preserving established conventions |
| Fill numbering gaps | Reuse missing slots `m009`, `m010`, etc. | Tighter numbering | Risk of colliding with reserved-but-not-yet-merged keys; mixed insertion sites complicate review | Rejected |
| Consolidate banner prints into logger | Remove the `print(...)` calls; use only `logger.info(t(...))` | One fewer key | Behaviour change (loses console banner); violates Requirement 3.2 | Rejected |

## Design Decisions

### Decision: Add a new `log.retry` sub-namespace rather than reusing `log.bootstrap` or `log.graph_api`
- **Context**: `retry.py` is a generic utility used by many callers; it does not belong to a single domain.
- **Alternatives Considered**:
  1. Place keys under `log.bootstrap` — wrong domain (bootstrap is for app startup logs).
  2. Place keys under each caller's namespace — would require dynamic key resolution, adding complexity.
  3. New `log.retry` sub-namespace — clean and self-describing.
- **Selected Approach**: Introduce `log.retry.m001`–`m004` as a peer of `log.graph_api`, `log.profile_generator`, etc.
- **Rationale**: Matches the per-domain naming scheme already in use; locates retry-specific copy in one place.
- **Trade-offs**: Adds one new sub-namespace under `log`, but does not change the top-level key set.
- **Follow-up**: Verify that no other module already defines `log.retry` (verified: it does not exist).

### Decision: Wrap `print(...)` arguments rather than removing the prints
- **Context**: Ticket #24 mandates externalisation of the listed call sites; behaviour preservation is in scope.
- **Alternatives Considered**:
  1. Keep `print(t("..."))` — preserves console banner, externalises text.
  2. Remove `print(...)`; rely on `logger.info` only — drops banner.
- **Selected Approach**: Option 1. The `'='*60` separator lines stay; only the message text routes through `t(...)`.
- **Rationale**: Minimum change; respects Requirement 3.2.
- **Trade-offs**: None significant.
- **Follow-up**: Confirm during validation that the surrounding separator prints (`print(f"\n{'='*60}")`) are not on the ticket's evidence list (they are not — they contain only ASCII).

### Decision: Pass exception text as a keyword argument named `e` (not `error`)
- **Context**: Existing `log.profile_generator` keys use `e=str(e)` and `error=...` inconsistently. Need to pick one convention to remain consistent.
- **Alternatives Considered**:
  1. Use `e` — matches `log.profile_generator.m003`, `m005`, `m008`, `m012`.
  2. Use `error` — matches `log.profile_generator.m018`.
- **Selected Approach**: Use `e` for raw exception strings (the more common pattern). Where a separate label is more readable, use a domain-specific name (e.g. `error` is fine when it carries semantic weight).
- **Rationale**: Match the dominant existing convention.
- **Trade-offs**: None.
- **Follow-up**: Use `e` throughout the new keys.

## Risks & Mitigations

- **Async retry on a fresh thread without `set_locale`** — Falls back to `'zh'`. Acceptable: ticket #24 acceptance targets *source-code* CJK absence. Documented for future ticket if needed.
- **Circular imports when adding `from ..utils.locale import t` to `retry.py`** — `locale.py` imports only `json`, `logging`, `os`, `threading`, and `flask` (no project modules). No circular risk.
- **Test-suite breakage from changed log text** — No fixtures match the Chinese strings. Verified by grep of `backend/`. Low risk.

## References

- Sibling spec: `.kiro/specs/i18n-externalize-backend-logs/requirements.md` — established convention.
- Ticket #6 (closed) and ticket #24 (this work).
- `backend/app/utils/locale.py` — `t()` contract.
