# Design Document — i18n-simulation-config-generator-prompts

## Overview

**Purpose**: Translate the three LLM prompt blocks and two prompt-feeding helpers in `backend/app/services/simulation_config_generator.py` from Chinese to English so that, under `Accept-Language: en`, the model emits English-flavoured output for `content`, `narrative_direction`, `hot_topics`, and `reasoning` fields. Today, these fields skew Chinese because the base prompt language biases the model — the `get_language_instruction()` postfix alone is insufficient.

**Users**: MiroFish operators running the 5-step pipeline under English locale; reviewers tracking the i18n epic (#11); developers maintaining sibling i18n issues (#5, #6, #7) downstream.

**Impact**: Behavioural — generated simulation-config string content will switch from Chinese-flavoured to English-flavoured under `Accept-Language: en`. No public-API change. No JSON-shape change. No infrastructure or dependency change.

### Goals

- Replace Chinese text inside three prompt blocks (`_generate_time_config`, `_generate_event_config`, `_generate_agent_configs_batch`) and two prompt-feeding helpers (`_build_context`, `_summarize_entities`) with English equivalents.
- Preserve every variable interpolation, every JSON-output key, every constraint phrase (`PascalCase`, enum strings), and every `get_language_instruction()` call site.
- Keep the public API of `SimulationConfigGenerator` and the `SimulationParameters` payload byte-for-byte equivalent in shape.

### Non-Goals

- Logger calls (`logger.info`, `logger.warning`, `logger.error`) inside the same file — owned by issue #6.
- Module docstring, class docstrings, dataclass docstrings, inline `#` comments — owned by issue #7.
- Refactoring prompt structure, JSON output schema, or retry/repair logic.
- Externalizing prompts into `/locales/*.json`.
- Default-simulation-parameter changes (rounds, action lists) — owned by `app/config.py`.
- Live end-to-end OASIS subprocess validation (deferred to fixture-based static checks; reviewer trust on Step 3 parity).

## Boundary Commitments

### This Spec Owns

- The string-literal **content** of the six prompt-string regions in `simulation_config_generator.py`:
    - `_generate_time_config` user prompt (~543–586) and system prompt (588).
    - `_generate_event_config` user prompt (~676–703) and system prompt (705).
    - `_generate_agent_configs_batch` user prompt (~833–867) and system prompt (869).
- The Chinese section headings and overflow markers inside `_build_context` (~393–406) and `_summarize_entities` (~422–430) that flow into prompts via `{context_truncated}`.
- The two static-literal `reasoning` values in the default paths: `_get_default_time_config` (line 608) and the `_generate_event_config` exception fallback (line 716).

### Out of Boundary

- All `logger.*` calls in this file (issue #6).
- All docstrings (`"""..."""`) and `#` comments in this file (issue #7).
- `backend/app/utils/locale.py`, `/locales/*.json`, `languages.json`.
- `services/simulation_ipc.py`, `services/simulation_runner.py`, OASIS subprocess source.
- `backend/app/config.py` constants.
- `backend/pyproject.toml`, `backend/uv.lock`.
- All other files in the repository.

### Allowed Dependencies

- Read access to `get_language_instruction()` from `backend/app/utils/locale.py` — call sites preserved verbatim.
- Read access to `t(...)` from `backend/app/utils/locale.py` — call sites preserved verbatim (these already exist for progress messages around lines 296–334).
- No new external dependencies.

### Revalidation Triggers

- A change to the `SimulationParameters.to_dict()` payload shape would force the OASIS subprocess to re-validate. **This spec does not change the shape.**
- A change to any JSON-output key emitted by the three prompts (e.g. renaming `agent_configs` to `agents`) would force the parsing logic in `_parse_time_config` / `_parse_event_config` / `_generate_agent_configs_batch`'s response-merge to re-validate. **This spec does not rename keys.**
- A change to the `get_language_instruction()` call sites or the trailing English `IMPORTANT:` directives' constraint semantics would force locale switching and OASIS-side enum validation to re-validate. **This spec preserves both verbatim.**

## Architecture

### Existing Architecture Analysis

`SimulationConfigGenerator` is a single Python class in a single module. The three target methods follow a uniform pattern:

```
prompt = f"""<chinese user prompt with {interpolations}>"""
system_prompt = "<chinese system prompt>"
system_prompt = f"{system_prompt}\n\n{get_language_instruction()}<optional english IMPORTANT directive>"
return self._call_llm_with_retry(prompt, system_prompt)
```

`_build_context` and `_summarize_entities` are private helpers that produce the `context` string passed (truncated) into all three prompt methods via `{context_truncated}`. They emit Chinese section headings.

There is no abstraction layer between prompt construction and LLM invocation — the prompt text and the call site are colocated. This matches sister modules (`ontology_generator.py`, `oasis_profile_generator.py`).

### Architecture Pattern & Boundary Map

**Selected pattern**: In-place string-literal translation. No new components, no new modules, no new abstractions.

```mermaid
flowchart TB
    subgraph Caller["Caller — services/simulation_runner.py"]
        callsite[generate_config(...)]
    end
    subgraph SimConfig["simulation_config_generator.py — IN SCOPE"]
        gen[generate_config]
        time[_generate_time_config<br/>**translate prompt + system_prompt**]
        event[_generate_event_config<br/>**translate prompt + system_prompt**]
        agent[_generate_agent_configs_batch<br/>**translate prompt + system_prompt**]
        ctx[_build_context<br/>**translate section headings**]
        sum[_summarize_entities<br/>**translate type headings**]
        defT[_get_default_time_config<br/>**translate reasoning literal**]
        retry[_call_llm_with_retry<br/>UNCHANGED]
    end
    subgraph Locale["backend/app/utils/locale.py — UNCHANGED"]
        gli[get_language_instruction]
        tr[t]
    end
    subgraph IPC["simulation_ipc.py + OASIS subprocess — UNCHANGED"]
        oasis[OASIS rounds]
    end

    callsite --> gen
    gen --> ctx
    gen --> sum
    gen --> time
    gen --> event
    gen --> agent
    time -.exception.-> defT
    event -.exception.-> event
    time --> retry
    event --> retry
    agent --> retry
    time --> gli
    event --> gli
    agent --> gli
    gen --> tr
    gen --> oasis
```

**Architecture Integration**:
- **Selected pattern**: In-place translation. Matches sister-spec implementations (`0806832`, `9d1d29b`).
- **Domain/feature boundaries**: All edits are inside `simulation_config_generator.py`. No file-boundary crossings except the read-only call to `get_language_instruction()` and `t()`.
- **Existing patterns preserved**: f-string template assembly; `system_prompt = f"{system_prompt}\n\n{get_language_instruction()}..."` postfix injection; `_call_llm_with_retry` envelope; `_parse_*` extraction with default fallbacks; per-entity-type heuristic ranges.
- **New components rationale**: None. The work is text-only.
- **Steering compliance**:
    - `.kiro/steering/tech.md` "Internationalization" — base prompts are part of the i18n surface; this work brings their language in line with the locale postfix.
    - `.kiro/steering/tech.md` "Code Quality" — match surrounding style; preserve mixed Chinese/English in comments and docstrings (we do — those are #7's scope).
    - `.kiro/steering/structure.md` — single-file edit; respects per-project graph isolation, since no graph code is touched.

### Technology Stack

| Layer | Choice / Version | Role in Feature | Notes |
|-------|------------------|-----------------|-------|
| Frontend / CLI | (n/a) | (n/a) | No frontend change. |
| Backend / Services | Python 3.11+, in-place file edit | Translate prompt-string content | One file modified. |
| Data / Storage | (n/a) | (n/a) | No DB schema change. |
| Messaging / Events | (n/a) | (n/a) | No IPC payload-shape change. |
| Infrastructure / Runtime | (n/a) | (n/a) | No deps, env-var, or runtime change. |

## File Structure Plan

### Directory Structure

```
backend/app/services/
└── simulation_config_generator.py   # All edits live here
```

### Modified Files

- `backend/app/services/simulation_config_generator.py`
    - **Lines ~393–406** (`_build_context`): translate the four Chinese section heading strings. Preserve `{simulation_requirement}`, `{len(entities)}`, `{entity_summary}`, `{doc_text}` interpolations.
    - **Lines ~422–430** (`_summarize_entities`): translate the per-entity-type heading and overflow marker. Preserve `{entity_type}`, `{len(type_entities)}`, `{e.name}`, `{summary_preview}`, `{display_count}` interpolations.
    - **Lines ~543–586** (`_generate_time_config` user prompt): translate the f-string body. Preserve `{context_truncated}`, `{max_agents_allowed}`. Preserve every JSON-output key. Keep the UTC+8 reference example as illustrative guidance.
    - **Line 588** (`_generate_time_config` system prompt): translate the literal.
    - **Line 589** (`_generate_time_config` postfix): unchanged — `system_prompt = f"{system_prompt}\n\n{get_language_instruction()}"`.
    - **Line 608** (`_get_default_time_config` `reasoning`): translate the literal to English.
    - **Lines ~676–703** (`_generate_event_config` user prompt): translate the f-string body. Preserve `{simulation_requirement}`, `{context_truncated}`, `{type_info}`. Preserve every JSON-output key.
    - **Line 705** (`_generate_event_config` system prompt): translate the literal.
    - **Line 706** (`_generate_event_config` postfix + IMPORTANT directive): unchanged.
    - **Line 716** (`_generate_event_config` exception-path `reasoning`): translate the literal to English.
    - **Lines ~833–867** (`_generate_agent_configs_batch` user prompt): translate the f-string body. Preserve `{simulation_requirement}` and `{json.dumps(entity_list, ensure_ascii=False, indent=2)}`. Preserve every JSON-output key. Preserve the per-entity-type heuristic ranges.
    - **Line 869** (`_generate_agent_configs_batch` system prompt): translate the literal.
    - **Line 870** (`_generate_agent_configs_batch` postfix + IMPORTANT directive): unchanged.

> Note: Line numbers are approximate; the implementation will locate edits by string content, not by line number.

## System Flows

Skipped — no behavioural flow change. The only flow visible is "caller → `generate_config` → three internal `_generate_*` LLM calls → `SimulationParameters`," which is unchanged.

## Requirements Traceability

| Requirement | Summary | Components | Interfaces | Flows |
|-------------|---------|------------|------------|-------|
| 1.1 | Block 1 user prompt zero-Chinese | `_generate_time_config` lines 543–586 | f-string body | (n/a) |
| 1.2 | Block 1 system prompt zero-Chinese | `_generate_time_config` line 588 | string literal | (n/a) |
| 1.3 | Block 1 JSON keys preserved | `_generate_time_config` user prompt | `total_simulation_hours`, `minutes_per_round`, `agents_per_hour_min`/`max`, `peak_hours`, `off_peak_hours`, `morning_hours`, `work_hours`, `reasoning` | (n/a) |
| 1.4 | Field-level numeric constraints preserved | `_generate_time_config` user prompt | constraint ranges in prose | (n/a) |
| 1.5 | Block 1 interpolations preserved | `_generate_time_config` user prompt | `{context_truncated}`, `{max_agents_allowed}` | (n/a) |
| 1.6 | UTC+8 reference example retained | `_generate_time_config` user prompt | illustrative bullet block | (n/a) |
| 1.7 | `get_language_instruction()` call site preserved | `_generate_time_config` line 589 | call expression | (n/a) |
| 2.1 | Block 2 user prompt zero-Chinese | `_generate_event_config` lines 676–703 | f-string body | (n/a) |
| 2.2 | Block 2 system prompt zero-Chinese | `_generate_event_config` line 705 | string literal | (n/a) |
| 2.3 | Block 2 JSON keys preserved | `_generate_event_config` user prompt | `hot_topics`, `narrative_direction`, `initial_posts[].content`, `initial_posts[].poster_type`, `reasoning` | (n/a) |
| 2.4 | Block 2 interpolations preserved | `_generate_event_config` user prompt | `{simulation_requirement}`, `{context_truncated}`, `{type_info}` | (n/a) |
| 2.5 | `get_language_instruction()` call site preserved | `_generate_event_config` line 706 | call expression | (n/a) |
| 2.6 | `poster_type` PascalCase directive preserved | `_generate_event_config` line 706 | trailing `IMPORTANT:` clause | (n/a) |
| 2.7 | Type-to-author examples translated, pairings intact | `_generate_event_config` user prompt | example-list bullet block | (n/a) |
| 2.8 | `zh` locale produces Chinese output | `_generate_event_config` + `get_language_instruction()` | postfix call | (n/a) |
| 3.1 | Block 3 user prompt zero-Chinese | `_generate_agent_configs_batch` lines 833–867 | f-string body | (n/a) |
| 3.2 | Block 3 system prompt zero-Chinese | `_generate_agent_configs_batch` line 869 | string literal | (n/a) |
| 3.3 | Block 3 JSON keys preserved | `_generate_agent_configs_batch` user prompt | `agent_configs[].agent_id` and 9 sub-keys | (n/a) |
| 3.4 | Block 3 interpolations preserved | `_generate_agent_configs_batch` user prompt | `{simulation_requirement}`, `json.dumps(entity_list,...)` | (n/a) |
| 3.5 | Per-entity-type heuristic ranges preserved | `_generate_agent_configs_batch` user prompt | bullet block describing officials/media/individuals/experts ranges | (n/a) |
| 3.6 | `get_language_instruction()` call site preserved | `_generate_agent_configs_batch` line 870 | call expression | (n/a) |
| 3.7 | `stance` enum + JSON-shape directive preserved | `_generate_agent_configs_batch` line 870 | trailing `IMPORTANT:` clause | (n/a) |
| 4.1 | Three call sites preserved at same positions | lines 589, 706, 870 | postfix injections | (n/a) |
| 4.2 | `zh` locale produces Chinese output (verification) | end-to-end | (n/a) | runtime |
| 4.3 | `en` locale produces English output (verification) | end-to-end | (n/a) | runtime |
| 4.4 | Locale source files unchanged | (n/a — guard) | (n/a) | (n/a) |
| 4.5 | Reasoning-model JSON repair preserved | `_fix_truncated_json`, `_try_fix_config_json` | (unchanged) | (n/a) |
| 5.1–5.6 | Public API and constants stable | class surface | (unchanged) | (n/a) |
| 6.1 | Default-path `reasoning` non-empty | `_get_default_time_config`, exception path | string literal | (n/a) |
| 6.2 | Default-path literals translated to locale-agnostic English | lines 608, 716 | string literals | (n/a) |
| 6.3 | `generation_reasoning` join semantics preserved | `generate_config` reasoning_parts assembly | `" | ".join(...)` | (n/a) |
| 7.1 | `_build_context` headings English | `_build_context` lines 393–406 | f-string body | (n/a) |
| 7.2 | `_summarize_entities` headings English | `_summarize_entities` lines 422–430 | f-string body | (n/a) |
| 7.3 | User-provided `entity.name`/`entity.summary` preserved verbatim | `_summarize_entities` | (data passthrough) | (n/a) |
| 7.4 | `_build_context`/`_summarize_entities` signatures unchanged | helpers | (unchanged) | (n/a) |
| 8.1–8.4 | Step 3 parity (verification) | end-to-end OASIS run | (n/a) | runtime |
| 9.1 | logger calls untouched | (guard) | (n/a) | (n/a) |
| 9.2 | docstrings/comments untouched | (guard) | (n/a) | (n/a) |
| 9.3 | No production-code edits outside target file | (guard) | (n/a) | (n/a) |
| 9.4 | No dependency change | (guard) | (n/a) | (n/a) |
| 9.5 | No edits to listed adjacent files | (guard) | (n/a) | (n/a) |

## Components and Interfaces

| Component | Domain/Layer | Intent | Req Coverage | Key Dependencies (P0/P1) | Contracts |
|-----------|--------------|--------|--------------|--------------------------|-----------|
| `_generate_time_config` (modified) | services | Render English time-config prompts; preserve LLM contract | 1.1–1.7, 4.1 | `_call_llm_with_retry` (P0), `get_language_instruction` (P0), `_get_default_time_config` (P1) | Service |
| `_generate_event_config` (modified) | services | Render English event-config prompts; preserve LLM contract and `poster_type` constraint | 2.1–2.8, 4.1, 6.1, 6.2 | `_call_llm_with_retry` (P0), `get_language_instruction` (P0) | Service |
| `_generate_agent_configs_batch` (modified) | services | Render English agent-config prompts; preserve LLM contract and `stance` constraint | 3.1–3.7, 4.1 | `_call_llm_with_retry` (P0), `get_language_instruction` (P0), `_generate_agent_config_by_rule` (P1) | Service |
| `_build_context` (modified) | services | Emit English section headings into context string | 7.1, 7.3, 7.4 | `_summarize_entities` (P0) | State |
| `_summarize_entities` (modified) | services | Emit English type headings/overflow markers | 7.2, 7.3, 7.4 | (none) | State |
| `_get_default_time_config` (modified) | services | Emit locale-agnostic English `reasoning` on default path | 6.1, 6.2 | (none) | State |
| `_call_llm_with_retry` (unchanged) | services | LLM invocation, retry, JSON repair | 4.5, 5.6 | `OpenAI` client (P0) | Service |
| `SimulationParameters.to_dict()` (unchanged) | services | Payload to OASIS subprocess | 5.4, 8.4 | `dataclasses.asdict` (P0) | State |

Detailed component blocks below for the three prompt-rendering methods. The two helper methods and the default-path method need only the summary-table entry above.

### Domain: Simulation Config Generation

#### `_generate_time_config` (modified)

| Field | Detail |
|-------|--------|
| Intent | Translate the time-config prompt and system prompt to English; preserve LLM contract, locale postfix, and JSON-key shape |
| Requirements | 1.1–1.7, 4.1 |

**Responsibilities & Constraints**
- Render an English f-string `prompt` containing `{context_truncated}` and `{max_agents_allowed}`, preserving the JSON-output schema and per-field numeric constraints.
- Render an English `system_prompt` literal; postfix `get_language_instruction()` exactly as today.
- Continue to fall back to `_get_default_time_config(num_entities)` on LLM exception.

**Dependencies**
- Inbound: `generate_config` — calls this method as Step 1 of the pipeline (P0).
- Outbound: `_call_llm_with_retry` (P0), `get_language_instruction` (P0), `_get_default_time_config` (P1).

**Contracts**: Service [x]

##### Service Interface

```python
def _generate_time_config(self, context: str, num_entities: int) -> Dict[str, Any]:
    """Returns a dict with keys: total_simulation_hours, minutes_per_round,
    agents_per_hour_min, agents_per_hour_max, peak_hours, off_peak_hours,
    morning_hours, work_hours, reasoning."""
```

- Preconditions: `context` is a non-empty string; `num_entities` ≥ 1.
- Postconditions: returned dict contains all eight numeric/array keys plus `reasoning`. On LLM failure, defaults are returned via `_get_default_time_config`.
- Invariants: signature unchanged; exception-fallback path unchanged.

**Implementation Notes**
- Integration: invoked by `generate_config` at line 298. No call-site change.
- Validation: zero `[一-鿿]` matches across the f-string body and `system_prompt` literal (excluding the `get_language_instruction()` postfix expression itself).
- Risks: missing an interpolation during translation produces a `KeyError` on f-string formatting — caught by fixture render check.

#### `_generate_event_config` (modified)

| Field | Detail |
|-------|--------|
| Intent | Translate the event-config prompt and system prompt to English; preserve LLM contract, `poster_type` PascalCase constraint, and JSON-key shape |
| Requirements | 2.1–2.8, 4.1, 6.1, 6.2 |

**Responsibilities & Constraints**
- Render an English f-string `prompt` containing `{simulation_requirement}`, `{context_truncated}`, and `{type_info}`.
- Preserve verbatim the trailing English `IMPORTANT: The 'poster_type' field value MUST be in English PascalCase ...` directive (constraint semantics unchanged).
- Translate the static `reasoning` literal in the exception-path fallback to English (Decision: translate default-path strings).

**Dependencies**
- Inbound: `generate_config` — calls this method as Step 2 (P0).
- Outbound: `_call_llm_with_retry` (P0), `get_language_instruction` (P0).

**Contracts**: Service [x]

##### Service Interface

```python
def _generate_event_config(
    self,
    context: str,
    simulation_requirement: str,
    entities: List[EntityNode],
) -> Dict[str, Any]:
    """Returns a dict with keys: hot_topics, narrative_direction,
    initial_posts (list of {content, poster_type}), reasoning."""
```

- Preconditions: `entities` non-empty (else `type_info` will be empty — acceptable, prompt still renders).
- Postconditions: returned dict contains the four keys; on exception, fallback dict carries the (now-English) `"Used default config"` reasoning.
- Invariants: signature unchanged; the trailing `IMPORTANT: ... PascalCase ...` directive remains verbatim.

**Implementation Notes**
- Integration: invoked at line 304.
- Validation: zero Chinese chars in the `prompt` and `system_prompt` literals; `IMPORTANT:` clause byte-equal.
- Risks: accidentally dropping or paraphrasing the `IMPORTANT:` directive could allow the LLM to emit lowercase or localized `poster_type` values, which `_assign_initial_post_agents`'s alias map (line 750) might or might not handle gracefully — keep verbatim.

#### `_generate_agent_configs_batch` (modified)

| Field | Detail |
|-------|--------|
| Intent | Translate the agent-config batch prompt and system prompt to English; preserve LLM contract, `stance` enum constraint, JSON-key shape, and per-entity-type heuristic ranges |
| Requirements | 3.1–3.7, 4.1 |

**Responsibilities & Constraints**
- Render an English f-string `prompt` containing `{simulation_requirement}` and `{json.dumps(entity_list, ensure_ascii=False, indent=2)}`.
- Preserve the per-entity-type heuristic ranges currently embedded as bullet points (officials/media/individuals/experts).
- Preserve verbatim the trailing English `IMPORTANT: The 'stance' field value MUST be one of ...` directive (constraint semantics unchanged).

**Dependencies**
- Inbound: `generate_config` — calls this method N times (one per batch) at line 320 (P0).
- Outbound: `_call_llm_with_retry` (P0), `get_language_instruction` (P0), `_generate_agent_config_by_rule` (P1, fallback per entity).

**Contracts**: Service [x]

##### Service Interface

```python
def _generate_agent_configs_batch(
    self,
    context: str,
    entities: List[EntityNode],
    start_idx: int,
    simulation_requirement: str,
) -> List[AgentActivityConfig]:
    """Returns one AgentActivityConfig per input entity, populated from
    LLM output where possible, else from rule-based fallback."""
```

- Preconditions: `entities` non-empty; `start_idx` ≥ 0.
- Postconditions: returned list length equals `len(entities)`; each item has a populated `stance` ∈ {`supportive`, `opposing`, `neutral`, `observer`}.
- Invariants: signature unchanged; rule-based fallback (`_generate_agent_config_by_rule`) wiring unchanged.

**Implementation Notes**
- Integration: invoked at line 320 inside the batch loop.
- Validation: zero Chinese chars; `IMPORTANT: stance ...` clause byte-equal; the four-range heuristic block is translated but the numeric ranges are preserved.
- Risks: paraphrasing the `stance` enum constraint could allow Chinese stance values into the OASIS subprocess — keep verbatim.

## Data Models

No new or changed data models. `AgentActivityConfig`, `TimeSimulationConfig`, `EventConfig`, `PlatformConfig`, `SimulationParameters` and `to_dict()` outputs are unchanged.

## Error Handling

### Error Strategy

No new error strategy. The existing two-tier fallback (LLM retry inside `_call_llm_with_retry`; per-method default-config fallback when retry exhausts) is preserved unchanged.

### Error Categories and Responses

- **LLM call failure (retry exhausted)** → `_get_default_time_config` (block 1) or static fallback dict (block 2). The fallback `reasoning` is now English (Decision: R6).
- **JSON parse failure** → repaired by `_fix_truncated_json` and `_try_fix_config_json`. Unchanged.
- **`stance` not in enum** → consumed by OASIS subprocess; behaviour unchanged. The translated `IMPORTANT:` directive guards against this at the LLM-output level.
- **`poster_type` not matching available entity types** → consumed by `_assign_initial_post_agents` (line 793); falls back to highest-influence agent. Unchanged.

### Monitoring

No new logging. `logger.warning("时间配置LLM生成失败...")` and similar lines remain in their current Chinese form (issue #6's scope).

## Testing Strategy

### Unit / fixture-based static checks (in scope for this implementation)

1. **Compile pass** — `python -m py_compile backend/app/services/simulation_config_generator.py` runs clean.
2. **Zero-Chinese assertion on prompt regions** — read the file, locate the six prompt literals + the two helper bodies via AST or by anchored substring match, assert `re.findall(r'[一-鿿]', region) == []`.
3. **Render check** — instantiate `SimulationConfigGenerator` with stub credentials, monkeypatch `_call_llm_with_retry` to a no-op stub, and call `_build_context`, `_summarize_entities`, plus the three prompt-rendering paths via the f-string `.format` route (or via `_generate_time_config`/`_generate_event_config`/`_generate_agent_configs_batch` directly with a mocked client). Assert: every documented interpolation appears in the rendered prompt; no `KeyError`; no `IndexError`.
4. **Constraint-clause byte-equal check** — assert the exact string `IMPORTANT: The 'poster_type' field value MUST be in English PascalCase exactly matching the available entity types.` substring is present in line 706 region; assert `IMPORTANT: The 'stance' field value MUST be one of the English strings: 'supportive', 'opposing', 'neutral', 'observer'.` substring is present in line 870 region.

### Integration tests (deferred)

5. **OASIS Step 3 smoke run** — deferred. Sister specs (#2, #3) shipped without a live e2e run; the same posture applies here. The reviewer is trusted on Step 3 parity by virtue of unchanged JSON shape (Requirement 5).

### E2E / UI

(n/a — backend-only change.)

## Optional Sections

### Migration Strategy

No data migration. The change takes effect on the next call to `SimulationConfigGenerator.generate_config(...)` after deploy. Locale-resolved Chinese postfix continues to bias the LLM toward Chinese output for `Accept-Language: zh`, so `zh` users see no perceptible change. `en` users (and any non-`zh` locale) see English-flavoured output starting immediately.

Rollback: revert the single commit. No database, no cache, no schema concerns.

## Supporting References

- `research.md` — full discovery log, alternative-architecture evaluation, decision records.
- Sister-spec implementations: commits `0806832` (#2), `9d1d29b` (#3).
- Sister-spec planning artefacts: `.kiro/specs/i18n-ontology-generator-prompts/`, `.kiro/specs/i18n-oasis-profile-generator-prompts/`.
