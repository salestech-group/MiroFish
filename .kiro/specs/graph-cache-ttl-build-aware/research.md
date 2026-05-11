# Research & Design Decisions

## Summary

- **Feature**: `graph-cache-ttl-build-aware`
- **Discovery Scope**: Extension (light discovery)
- **Key Findings**:
  - The graph data cache lives entirely inside `backend/app/api/graph.py` (module-level dicts + one helper + one route). Scope is genuinely small.
  - `ProjectManager.list_projects()` is the canonical lookup pattern; `_refresh_graph_cache` at `graph.py:562-567` already uses it to map `graph_id → project`. Reusing it keeps the implementation single-pattern.
  - All existing protections (stale-while-revalidate, per-`graph_id` refresh lock, empty-result short TTL) are orthogonal to the TTL-selection change and need no modification.

## Research Log

### Existing cache structure in `backend/app/api/graph.py`

- **Context**: Confirm what state and helpers already exist before designing the TTL change.
- **Sources Consulted**: `backend/app/api/graph.py:24-32, 556-615`.
- **Findings**:
  - Two module-level dicts: `_graph_data_cache` (`graph_id → {data, ts}`) and `_graph_refresh_locks` (`graph_id → threading.Lock`).
  - Two TTL constants: `_GRAPH_CACHE_TTL = 300`, `_GRAPH_EMPTY_CACHE_TTL = 5`.
  - `_refresh_graph_cache(graph_id)` is the single background-refresh entry point; it already iterates `ProjectManager.list_projects()` to pull `ontology` for the owning project.
  - `get_graph_data` computes `effective_ttl` inline at `:595-598`: `empty → empty TTL, else → fixed 300s`. This is the exact branch the feature replaces.
- **Implications**:
  - The TTL-selection change is a pure swap of the inline branch for a helper call. No new module, no signature changes elsewhere.
  - The `_refresh_graph_cache` lookup pattern is reused verbatim — keeps the surface area of the change small and consistent.

### Project status enum and ownership

- **Context**: Verify what status values exist and how a `Project` exposes its `graph_id`.
- **Sources Consulted**: `backend/app/models/project.py:18-24, 27-46, 196-197`.
- **Findings**:
  - `ProjectStatus` values: `CREATED`, `ONTOLOGY_GENERATED`, `GRAPH_BUILDING`, `GRAPH_COMPLETED`, `FAILED`.
  - `Project.graph_id: Optional[str]` is set after step 2 (graph build) starts; it identifies the cache key.
  - `ProjectManager.list_projects(limit: int = 50)` returns newest first with a **default cap of 50**.
- **Implications**:
  - Only `GRAPH_BUILDING` triggers the short TTL; all other statuses (`CREATED`, `ONTOLOGY_GENERATED`, `GRAPH_COMPLETED`, `FAILED`) map to the stable TTL by simple `!= GRAPH_BUILDING` test.
  - The default 50-project cap means a `graph_id` owned by the 51st-newest project will not be found and falls back to the stable TTL. This matches the pre-existing behavior of `_refresh_graph_cache` and is consistent with Requirement 3.2's safe-fallback rule. Out of scope to fix here; called out as a known limitation.

### Frontend polling cadence

- **Context**: Confirm the 15s-during-build value is a fit, not a guess.
- **Sources Consulted**: `frontend/src/views/Process.vue:701` and ticket #44 analysis.
- **Findings**: The frontend polls `/api/graph/data/<graph_id>` roughly every 10 seconds during a build; UI rerender is gated by `node_count` change (`Process.vue:738`).
- **Implications**: A 15s building TTL gives one fresh-cache hit per poll, with the next poll triggering a background refresh via the existing stale-while-revalidate path. New entities surface within ~one poll cycle, no UI jitter from re-rendering identical node counts.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Module-level helper inside `graph.py` (chosen) | Add `_resolve_ttl(graph_id, is_empty)` next to the cache state | Co-located with the only caller, matches existing `_refresh_graph_cache` style, zero cross-layer churn | Project lookup is O(projects) on each call; mitigated by 50-project cap and trivial per-call cost | Aligns with steering: "API handlers stay thin, but cache state and TTL policy are API-layer concerns" |
| Move TTL policy into `GraphBuilderService` | Push the helper into `services/` | Keeps API handler purely declarative | Drags service into a concern that's currently API-only state; new cross-layer dependency; harder to reason about | Rejected — no behavioral benefit; violates "logic where the state lives" |
| Cache `graph_id → project_id` index | Memoize the project lookup | O(1) lookup; relevant only if hot | Adds eviction concerns we already have on the cache; premature for this scale | Ticket explicitly defers this as a follow-up if it ever becomes hot |

## Design Decisions

### Decision: Build-state-aware TTL computed by a private helper in `graph.py`

- **Context**: Replace the single `_GRAPH_CACHE_TTL = 300` with a function of `(graph_id, is_empty)` while keeping the change blast-radius limited to one file.
- **Alternatives Considered**:
  1. Module-level helper inside `graph.py` — co-located with cache state.
  2. Service-layer helper in `services/graph_builder.py` — moves TTL policy out of API.
- **Selected Approach**: Module-level helper `_resolve_ttl(graph_id: str, is_empty: bool) -> int` in `backend/app/api/graph.py`, alongside the existing `_refresh_graph_cache`.
- **Rationale**: TTL selection is API-layer cache policy, not graph business logic. The helper sits beside the state it operates on, mirrors the existing `_refresh_graph_cache` pattern (same `ProjectManager.list_projects()` lookup), and keeps the file dependency graph unchanged.
- **Trade-offs**: O(projects) lookup on every GET that hits the cache decision; acceptable given the 50-project default cap and the cheap iteration cost.
- **Follow-up**: If profiling ever shows the lookup is hot, file a separate spec to add a `graph_id → project` index (called out as out-of-scope in the requirements).

### Decision: Safe-fallback path treats resolution failure identically to "not found"

- **Context**: Requirement 3.4 forbids exposing project-resolution exceptions to the request thread.
- **Alternatives Considered**:
  1. Let resolution exceptions propagate (current `_refresh_graph_cache` behavior partially does this in its broad `try/except`).
  2. Wrap the resolution in a narrow `try/except Exception` and fall back to the stable TTL.
- **Selected Approach**: Option 2 — broad `try/except Exception` around the `ProjectManager.list_projects()` iteration; on any error, return `_GRAPH_CACHE_TTL_STABLE`. A `logger.warning` records the failure for observability but the request thread is unaffected.
- **Rationale**: Matches the project's error-handling steering ("graceful degradation, partial functionality over complete failure"); a poll request must never 500 because TTL policy could not resolve.
- **Trade-offs**: Silently picks the long TTL on resolution failure; an operator chasing "why isn't my graph refreshing" might miss the cause. Mitigated by the `WARNING` log line per `error-handling.md` standards.

### Decision: Empty-result TTL takes precedence over build state

- **Context**: Requirements 2.1–2.3 require empty results to use the existing 5s TTL regardless of build state.
- **Alternatives Considered**:
  1. Check `is_empty` first inside the helper.
  2. Check build state first; treat empty as an override afterward.
- **Selected Approach**: Option 1 — the helper short-circuits on `is_empty=True` before consulting `ProjectManager`.
- **Rationale**: Empty-state handling is orthogonal to project status (ticket explicitly says so); checking it first avoids a project lookup when it doesn't matter.
- **Trade-offs**: None material — the cheap check happens first.

## Risks & Mitigations

- **Risk**: `ProjectManager.list_projects(limit=50)` truncates older projects, so the owner of an older `graph_id` falls back to the stable TTL during a real build → user sees the slow 5-minute refresh on legacy projects. **Mitigation**: documented limitation; addressed by future `graph_id → project` index spec only if it ever bites. The fallback is the safe (longer) TTL, not a broken state.
- **Risk**: Race between the build-completion transition (`GRAPH_BUILDING → GRAPH_COMPLETED`) and an in-flight cache check could pick a stale TTL for one poll cycle. **Mitigation**: at most one poll cycle of "wrong" TTL; benign on either side (15s during a stable graph adds one extra refresh; 300s right after completion is what we want anyway).
- **Risk**: Log spam if the helper logs on every resolution failure. **Mitigation**: log at `WARNING` only when an actual exception is caught, not on "not found".

## References

- Ticket: [salestech-group/MiroFish#44](https://github.com/salestech-group/staat-suite/MiroFish/issues/44)
- Existing pattern: `backend/app/api/graph.py:556-576` (`_refresh_graph_cache`)
- Existing inline TTL branch being replaced: `backend/app/api/graph.py:593-598`
- Project model: `backend/app/models/project.py:18-24` (status enum), `:196-197` (list_projects)
- Steering: `.kiro/steering/error-handling.md` (graceful degradation, WARNING log convention)
