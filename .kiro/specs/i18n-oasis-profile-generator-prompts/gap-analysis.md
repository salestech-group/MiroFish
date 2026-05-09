# Gap Analysis — i18n-oasis-profile-generator-prompts

This document analyzes the gap between the requirements and the existing
codebase, lists implementation options, and recommends an approach for the
design phase.

## 1. Current State Investigation

### Target file

`backend/app/services/oasis_profile_generator.py` — 1195 lines. Defines:

- `OasisAgentProfile` dataclass with Reddit / Twitter serializers.
- `OasisProfileGenerator` class with the following public-API surface:
  `__init__`, `generate_profile_from_entity`, `generate_profiles_from_entities`,
  `set_graph_id`, plus private helpers `_call_llm_with_retry`,
  `_generate_profile_rule_based`, `_get_system_prompt`,
  `_build_individual_persona_prompt`, `_build_group_persona_prompt`,
  `_print_generated_profile`, `_fix_truncated_json`, `_try_fix_json`,
  `_save_twitter_csv`, `_save_reddit_json`, `_generate_username`.

### Chinese surfaces in the file (by category)

| Category | Lines | In scope this issue? |
| --- | --- | --- |
| Module / class / method docstrings | scattered | **No** — covered by #7 |
| Inline `#` comments | scattered | **No** — covered by #7 |
| `logger.{info,warning,error}` calls (translated via `t("log.profile_generator.*")`) | scattered | **No** — already done by #6 |
| `print(...)` banners (e.g. line 945) | a few | **No** — companion to #6 in spirit; not a prompt literal |
| **System prompt `base_prompt`** (line 664) | 1 line | **Yes** |
| **Individual-persona prompt body** (lines 680–714) | block | **Yes** |
| **Group-persona prompt body** (lines 729–762) | block | **Yes** |
| `attrs_str` / `context_str` defaults `"无"` / `"无额外上下文"` (lines 677, 678, 726, 727) | 4 lines | **Yes** — they substitute *into* the prompt body |
| Rule-based fallback (`_generate_profile_rule_based`, lines 764–835) including `"country": "中国"` and `"国家"` placeholders | block | **No** — runtime data, not a prompt |
| Resilience-helper Chinese fragments (`f"{entity_name}是一个{entity_type}。"` at lines 547, 644, 659) | a few | **No** — runtime data, not a prompt |

The file already imports `get_locale`, `set_locale`, `t`, and
`get_language_instruction` from `app.utils.locale`. The locale-capture /
restore plumbing inside `generate_profiles_for_entities` (lines ~910–916)
already propagates the request locale to background-thread workers — no
changes required.

### Locale infrastructure (already in place)

`backend/app/utils/locale.py`:

- `get_language_instruction()` returns the per-locale postfix from
  `/locales/languages.json` (e.g. `Please respond in English.` for `en`,
  `请使用中文回答。` for `zh`).
- `t(key, **kwargs)` resolves `log.*` keys for backend logger messages;
  not used by this issue.
- `set_locale` / `get_locale` are thread-local, with restoration plumbed
  into `generate_profiles_for_entities`.

### Sibling specs already shipped

- `i18n-ontology-generator-prompts` (#2 — merged)
- `i18n-simulation-config-generator-prompts` (#4 — merged)
- `i18n-report-agent-prompts` (#5 — merged)
- `i18n-externalize-backend-logs` (#6 — merged; logger keys for
  `log.profile_generator.*` are already in `locales/{en,zh}.json`)

The translation pattern they established:

1. Translate the base prompt body (English narrative + headings).
2. Preserve every `get_language_instruction()` call site verbatim so
   `Accept-Language: zh` still produces Chinese output.
3. Preserve all `{variable}` interpolations in f-strings.
4. Preserve all locale-independent "lock" rules (e.g. `gender` enum) in
   English text within the prompt.
5. No new dependencies, no new files, single-file diff.

This is a direct sibling — same pattern applies.

### Test contract

`backend/scripts/test_profile_format.py`:

- Pytest-collectable function `test_profile_formats`.
- Constructs `OasisAgentProfile` instances directly (no LLM call) and
  serializes them via `_save_twitter_csv` / `_save_reddit_json`.
- Verifies CSV header includes `user_id, user_name, name, bio,
  friend_count, follower_count, statuses_count, created_at` and JSON
  output includes `realname, username, bio, persona`.
- **Does not exercise the prompts.** A pure prompt translation cannot
  break it; a refactor of dataclass field names or serializers would.

### Callers

- `backend/app/services/simulation_manager.py:316` —
  `OasisProfileGenerator(graph_id=state.graph_id)`.
- `backend/app/api/simulation.py:1413` — `OasisProfileGenerator()`.

Neither caller looks at prompt language; both consume the persona dict
output. No call-site changes are needed.

## 2. Requirement-to-Asset Map

| Req. | Asset / file | Gap |
| --- | --- | --- |
| 1. System prompt → English | `_get_system_prompt` line 664 | **Missing** — Chinese literal needs to become English literal |
| 2. Individual-persona template → English | `_build_individual_persona_prompt` lines 680–714 | **Missing** — Chinese block needs translation; preserve `{...}` interpolations and inline `{get_language_instruction()}` |
| 3. Group-persona template → English | `_build_group_persona_prompt` lines 729–762 | **Missing** — Chinese block needs translation; preserve `{...}` interpolations and inline `{get_language_instruction()}` |
| 4. Locale switching unchanged | `app.utils.locale` + the three `get_language_instruction()` call sites | **Constraint** — code path must stay byte-identical at those call sites |
| 5. Public API stability | `OasisAgentProfile` dataclass + `OasisProfileGenerator` method signatures | **Constraint** — no signatures change |
| 6. Reasoning-model parsing unchanged | `_fix_truncated_json`, `_try_fix_json` | **Constraint** — no edits |
| 7. OASIS schema parity | `_save_twitter_csv`, `_save_reddit_json`, `to_*_format` serializers | **Constraint** — no edits; pytest must continue passing |
| 8. Out-of-scope guard | logger calls, docstrings, comments, rule-based fallback | **Constraint** — explicitly do not edit |

No requirement is blocked or unknown. Every requirement maps to a known
location with a clear, narrow change.

## 3. Implementation Approach Options

### Option A — In-place edit of the three prompt builders (extend existing)

Translate `base_prompt` (1 line), the individual-persona f-string body
(~35 lines), and the group-persona f-string body (~34 lines) directly,
plus the four `"无"` / `"无额外上下文"` fallback literals. Keep all method
bodies otherwise byte-identical.

- **Files touched**: `backend/app/services/oasis_profile_generator.py`
  only.
- **Compatibility**: zero API change. All call sites unaffected. Locale
  switching preserved by leaving the inline `{get_language_instruction()}`
  placeholders untouched.
- **Complexity**: low. Pattern is identical to merged siblings #2, #4,
  #5.

**Trade-offs**:

- ✅ Minimal diff, exactly the pattern reviewers expect.
- ✅ No risk to the unrelated rule-based fallback or serialization paths.
- ✅ Out-of-scope items (logger, docstrings, rule-based fallback) are not
  touched, so #6/#7 remain clean.
- ❌ Leaves the file mixed-language in non-prompt parts (docstrings, rule
  fallback) until #7 lands. Acceptable per scope split.

### Option B — Move prompt strings into module-level constants

Introduce `INDIVIDUAL_PERSONA_PROMPT_TEMPLATE` and
`GROUP_PERSONA_PROMPT_TEMPLATE` constants at module scope (mirroring
`ONTOLOGY_SYSTEM_PROMPT` style in `ontology_generator.py`), and have the
builders `.format(**kwargs)` against them.

- **Files touched**: same single file, but with structural refactor.
- **Compatibility**: still zero public API change, but the diff is
  larger and reviewers must verify equivalent behaviour around
  `{get_language_instruction()}` (which would need to become a runtime
  substitution not an f-string interpolation, since constants don't
  re-evaluate per call).

**Trade-offs**:

- ✅ Constants are easier to spot in `git grep`.
- ❌ Larger diff, more review surface.
- ❌ The inline `get_language_instruction()` call is currently captured at
  f-string render time; moving to a `.format(...)` template requires
  passing the resolved instruction in as a kwarg — a behavioural change
  that exceeds "translate prompts only".
- ❌ Diverges from the sibling pattern just shipped (#4, #5 used in-place
  edits, not module constants). #2 used module constants but only for the
  system prompt — the user-message template was still built inside the
  method.

### Option C — Externalize prompt text into `/locales/*.json`

Move every prompt sentence into `locales/en.json` and `locales/zh.json`,
keyed under `prompt.profile_generator.*`, and use `t(key, **vars)` to
resolve.

- **Compatibility**: would address `Accept-Language` purely via the
  existing translation mechanism without depending on the
  `get_language_instruction()` postfix.

**Trade-offs**:

- ✅ Most i18n-pure approach.
- ❌ Significantly larger diff (touches three repos: source file,
  `en.json`, `zh.json`).
- ❌ Diverges from the established project pattern. The sibling specs
  (#2, #4, #5) deliberately did **not** externalize prompts — the
  project rationale (per `tech.md`) is that backend logger messages are
  the i18n surface, while LLM prompts use the `get_language_instruction()`
  postfix mechanism.
- ❌ Higher review and merge cost for no operational gain.

## 4. Recommended Approach

**Option A** — single-file in-place edit of the three prompt builders
plus the four `"无"` / `"无额外上下文"` fallback literals.

Rationale:

- Matches the merged sibling specs verbatim (#2, #4, #5) so reviewers
  can apply the same mental checklist.
- Smallest possible diff that satisfies every acceptance criterion in
  requirements.md.
- Leaves out-of-scope surfaces (logger, docstrings, rule-based
  fallback) untouched — clean handoff to #7 and clean separation from
  already-merged #6.
- Zero new dependencies, zero new files, zero API change, zero risk to
  `test_profile_format.py`.

### Translation choices to lock in during design

1. The system prompt `base_prompt` becomes a single English sentence in
   the spirit of the original (expert in social-media persona generation;
   detailed and realistic personas for opinion simulation; faithful
   reflection of real-world conditions; valid JSON, no unescaped
   newlines).
2. The two persona prompt bodies adopt English section headings and
   prose. The previously-Chinese hint
   `country: 国家（使用中文，如"中国"）` is dropped — the
   `get_language_instruction()` postfix already steers locale, and the
   rule-based fallback (out of scope) handles its own country values.
3. The trailing rules block keeps the locale-independent "lock"
   constraints inline (`gender` enum, `age` integer requirement,
   `persona` newline rule) and continues to embed
   `{get_language_instruction()}` verbatim.

## 5. Effort & Risk

- **Effort**: **S** (1–3 days; realistically <½ day). One-file diff,
  established sibling pattern, no new test infrastructure.
- **Risk**: **Low**. The translated prompts touch only the LLM
  `messages` payload. The locale-switching pathway, public API,
  serializers, retry logic, fallback, and tests are all untouched. The
  only failure mode is a mistranslated constraint (e.g. accidentally
  dropping `gender ∈ {male, female, other}`), which the design checklist
  enumerates and reviewers can verify by diff.

### Research items carried into design phase

- None blocking. The design phase will:
  - Enumerate the exact final English text for each of the three blocks.
  - Verify each translated block preserves every JSON-output key,
    every `{variable}` interpolation, and the inline
    `{get_language_instruction()}` call.
  - Spot-check that the diff stays within
    `backend/app/services/oasis_profile_generator.py`.
