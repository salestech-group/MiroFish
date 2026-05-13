# Requirements Document

## Introduction

The graph data endpoint in MiroFish caches Neo4j fetches with a single 5-minute TTL inherited from the Zep era when the upstream API was rate-limited. With Neo4j now co-located with the Flask app, that 5-minute cache mostly delays the appearance of newly extracted entities during a graph build, where the frontend polls roughly every 10 seconds.

This feature replaces the fixed cache TTL with a **build-state-aware TTL**: short during `GRAPH_BUILDING`, long once the graph is stable, while keeping the existing 5-second TTL for empty results untouched. The change targets `backend/app/api/graph.py` only; the per-project `group_id` isolation, the stale-while-revalidate path, and the per-`graph_id` refresh lock are unchanged.

Linked ticket: [salestech-group/MiroFish#44](https://github.com/salestech-group/MiroFish/issues/44).

## Boundary Context

- **In scope**:
  - TTL selection for cached graph fetches in `backend/app/api/graph.py`.
  - Resolving the owning project for a `graph_id` to decide which TTL applies.
  - Updating the module-level comment that explains the cache rationale.
- **Out of scope**:
  - Behavior of `_refresh_graph_cache` other than how it is triggered by TTL expiry.
  - Eviction / unbounded growth of `_graph_data_cache` and `_graph_refresh_locks` (separate follow-up).
  - Changes to the response envelope or the frontend polling cadence.
  - Any change to the empty-result TTL value or to the build pipeline itself.
- **Adjacent expectations**:
  - `ProjectManager.list_projects()` continues to expose `graph_id` and `status` on each project (matches the pattern already used in `_refresh_graph_cache`).
  - `ProjectStatus.GRAPH_BUILDING` continues to identify a project whose graph is currently being written; all other statuses are treated as "graph is stable enough to cache for long".

## Requirements

### Requirement 1: Build-state-aware TTL selection

**Objective:** As a frontend user watching a graph being built, I want the cache to refresh quickly while a build is in progress, so that newly extracted entities appear in the graph panel within seconds rather than minutes.

#### Acceptance Criteria

1. The Graph API shall expose two non-empty-result TTL values: a short building TTL of 15 seconds and a stable TTL of 300 seconds.
2. While the project owning a `graph_id` is in `ProjectStatus.GRAPH_BUILDING`, when a cached graph entry is served, the Graph API shall treat the building TTL (15 seconds) as the freshness window.
3. While the project owning a `graph_id` is in any status other than `GRAPH_BUILDING`, when a cached graph entry is served, the Graph API shall treat the stable TTL (300 seconds) as the freshness window.
4. The Graph API shall not expose a single combined non-empty-result TTL constant once the change is complete — the prior `_GRAPH_CACHE_TTL = 300` is replaced by the two separate values.

### Requirement 2: Empty-result handling preserved

**Objective:** As an operator, I want the existing protection against caching empty graph snapshots to remain in place, so that the first poll during a build does not lock the UI to an empty graph for minutes.

#### Acceptance Criteria

1. When the cached graph data reports both `node_count == 0` and `edge_count == 0`, the Graph API shall treat the existing empty-result TTL (5 seconds) as the freshness window, regardless of the owning project's status.
2. The Graph API shall not change the value of the empty-result TTL as part of this feature.
3. When a cached graph data entry is non-empty, the Graph API shall not apply the empty-result TTL.

### Requirement 3: Project lookup and safe fallback

**Objective:** As a backend maintainer, I want TTL selection to degrade safely when the owning project cannot be identified, so that a missing or transient project record never causes shorter polling than the historical default.

#### Acceptance Criteria

1. When selecting the TTL for a non-empty cached entry, the Graph API shall resolve the owning project by looking up the project whose `graph_id` matches the cached entry's `graph_id` via `ProjectManager.list_projects()`.
2. If no project owning the requested `graph_id` is found, the Graph API shall fall back to the stable TTL (300 seconds).
3. If the owning project is found but its status is not `GRAPH_BUILDING`, the Graph API shall use the stable TTL (300 seconds).
4. The Graph API shall not raise an exception to the request thread if project resolution fails for any reason; it shall treat resolution failure as "owning project not found" and use the stable TTL.

### Requirement 4: Documentation reflects the new policy

**Objective:** As a future contributor reading `backend/app/api/graph.py`, I want the module-level cache comment to explain the current policy, so that I do not waste time on the obsolete Zep-rate-limit rationale.

#### Acceptance Criteria

1. The Graph API shall expose a module-level comment near the cache constants that describes the cache as a smoothing layer for concurrent local-Neo4j polls, not a workaround for a rate-limited remote API.
2. The Graph API module-level comment shall describe the build-state-aware TTL policy in plain language (short TTL during `GRAPH_BUILDING`, long TTL otherwise, separate short TTL for empty results).
3. The Graph API module-level comment shall not retain the obsolete claim that the cache exists primarily because of rate-limiting on the upstream graph service.

### Requirement 5: Observable behavior during a real build

**Objective:** As a QA reviewer or operator, I want a clear, observable acceptance signal so that I can verify the change does what the ticket promised in a live run.

#### Acceptance Criteria

1. While a project is in `GRAPH_BUILDING`, when a new entity is written to Neo4j and the next graph poll occurs, the graph panel shall reflect the new entity within approximately the building TTL window (15 seconds plus the natural background-refresh latency).
2. Once a project's status transitions out of `GRAPH_BUILDING`, when subsequent polls arrive within the stable TTL window, the Graph API shall serve cached data and shall not log a background refresh more often than once per 300 seconds for that `graph_id`.
3. The Graph API shall continue to use the existing stale-while-revalidate pattern: a stale cache is served immediately and a background refresh is dispatched, deduplicated per `graph_id` by the existing refresh lock.
