# Implementation Plan

> All work in this spec lives inside `backend/app/api/graph.py`. Tasks share the same file boundary, so they run sequentially and no `(P)` markers apply.

- [x] 1. Replace fixed cache TTL constants and rewrite the module rationale comment
  - Remove the single non-empty TTL constant currently defined near the cache state at the top of the graph API module.
  - Introduce two replacement constants for the non-empty path: a short freshness window of 15 seconds for the build state, and a long freshness window of 300 seconds for the stable state.
  - Leave the existing empty-result freshness window (5 seconds) untouched in both name and value.
  - Rewrite the comment block above the cache constants to describe the cache as a smoothing layer for concurrent local-Neo4j polls (the Zep rate-limit rationale is no longer accurate), and to summarize the build-state-aware policy: short TTL while the owning project is building, long TTL when stable, separate short TTL for empty payloads.
  - Observable completion: grepping the module for the old single TTL symbol returns no matches; both new constants are defined at module level alongside the unchanged empty TTL; the comment block above them no longer mentions rate-limiting or Zep as the cache's primary justification.
  - _Requirements: 1.1, 1.4, 2.2, 4.1, 4.2, 4.3_

- [x] 2. Implement the build-state-aware TTL resolver helper
  - Add a private module-level helper alongside the existing background-refresh helper that, given a graph identifier and a flag indicating whether the cached payload is empty, returns the appropriate freshness window in seconds.
  - Make the empty-payload case short-circuit and return the empty TTL before any project lookup.
  - For the non-empty case, locate the owning project by iterating the list returned by the project manager (matching the existing lookup pattern used by the background refresh helper) and comparing each project's graph identifier to the requested one.
  - Return the short building freshness window when the owning project's status indicates the graph build is in progress; return the long stable freshness window for any other status, when no owning project is found, or when the lookup raises.
  - Wrap the project iteration in a broad exception handler that emits a single warning log line (using the existing API-layer logger, truncating the exception message to match the style of the existing background-refresh warning) and falls through to the stable freshness window. The helper must never propagate an exception to its caller.
  - Observable completion: a direct call with an empty-flag of true returns the empty TTL value; with a graph identifier owned by a building project returns the building TTL value; with an unknown identifier, a non-building owning status, or when the project manager raises returns the stable TTL value; in the raising case exactly one warning line is emitted for that call.
  - _Requirements: 1.2, 1.3, 2.1, 2.3, 3.1, 3.2, 3.3, 3.4_

- [x] 3. Wire the resolver into the graph data cache-hit branch
  - Replace the inline conditional in the cache-hit path of the graph data route that currently chooses between the empty and the non-empty TTL with a single call to the new resolver helper, passing the cached graph identifier and the existing empty-payload flag.
  - Leave the cache-miss 202 path, the stale-while-revalidate branch, the response envelope shape, the per-graph-identifier refresh lock, and the background refresh helper itself unchanged.
  - Observable completion: reading the cache-hit branch of the route shows a single call to the resolver as the only source of the freshness window; the cache-miss and stale-while-revalidate code paths read byte-identical to before this spec (verified by diff review); polling the endpoint against a populated cache still returns the existing success envelope with the `cached: true` flag and, when stale, the `stale: true` flag.
  - _Requirements: 1.2, 1.3, 2.1, 2.3, 3.1, 3.2, 3.3_

- [ ] 4. Manual end-to-end verification on a live graph build
  - Run the dev stack against a local Neo4j, start a new project, upload seed material, and trigger a graph build. While the project status is the build-in-progress state, confirm that newly extracted entities appear in the graph panel within roughly one frontend poll cycle (≈15 seconds plus the natural refresh latency).
  - After the project transitions out of the build-in-progress state, leave the workflow page open for more than five minutes and confirm the backend log shows at most one "Graph cache refreshed" line per 300-second window for that graph identifier.
  - On the very first poll of a fresh build (when the cached payload still reports zero nodes and zero edges), confirm the empty snapshot is replaced within roughly the existing empty freshness window (≈5 seconds), not the longer building window.
  - Confirm the stale-while-revalidate behavior is preserved: a stale cache hit serves immediately and spawns at most one background refresh per graph identifier at a time, governed by the existing per-graph-identifier lock.
  - Observable completion: the four bullets above are reproduced in a live run; no new exceptions or stack traces appear in the backend log; the only new log line introduced is the truncated warning the resolver emits when project lookup raises, and it appears at most once per resolution failure.
  - _Requirements: 5.1, 5.2, 5.3_
