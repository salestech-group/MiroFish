# Implementation Plan

- [x] 1. Add parity primitives to the i18n CJK Guard module
  - Introduce a constant naming the Chinese catalogue path alongside the existing English-catalogue constant.
  - Add a private helper that returns the dotted-key set of a parsed catalogue, mirroring the audit pipeline's `flatten` contract (descend into dicts only; treat scalar leaves and string leaves identically; type-narrow nothing).
  - Add a private helper that resolves the 1-based line number of a dotted key in raw JSON source text by searching for the leaf segment wrapped in JSON quotes, and falls back to line 1 on any miss.
  - Add a private helper that formats a single parity-failure line in the layout `<file>:<line>: parity-en-only: <key>` or `... parity-zh-only: <key>`, with the side parameter typed as a literal of the two allowed strings (improvement carried over from the design review).
  - Add an immutable result carrier (named tuple or frozen dataclass) holding the parity outcome (passed flag, formatted failure lines including the trailing summary, optional success-summary line).
  - All additions stay stdlib-only and import nothing new beyond what the existing module already imports.
  - Observable completion: the module exports the new constant, helpers, and result carrier; importing the module from a Python REPL or test stays warning-free, and the helpers can be exercised in isolation.
  - _Requirements: 1.1, 1.5, 2.1, 2.2, 4.1, 4.3_
  - _Boundary: i18n_cjk_guard module — helper layer_

- [x] 2. Implement the parity-check orchestrator
  - Read both locale catalogues from the working tree using the existing path constants.
  - Flatten each catalogue and compute the symmetric difference of the dotted-key sets.
  - On match, build the success-summary string of the form `OK locale-parity: <count> keys per side`.
  - On mismatch, sort en-only keys lexicographically and emit one formatted failure line per key with the EN catalogue path and a best-effort line number; then sort zh-only keys lexicographically and emit one line per key with the ZH catalogue path and a best-effort line number.
  - Append a final summary line of the form `parity: en-only=<n>, zh-only=<m>` to the failure list so the orchestrator can print all lines uniformly.
  - Treat a missing or malformed catalogue file as a parity failure that returns a single descriptive failure line; if the EN catalogue is the unreadable side, attribute the error to the parity check without re-stating the en-only error already produced by the existing CJK-clean block (refinement carried over from the design review).
  - All output strings are deterministic across runs for identical inputs.
  - Observable completion: calling the orchestrator function with synthetic parity-clean and parity-divergent catalogues returns a result carrier whose passed flag, failure list, and success summary match the documented contracts; running it against the live `locales/` directory returns `passed=True`.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.3, 2.4, 2.5, 4.2, 4.3_
  - _Boundary: i18n_cjk_guard module — orchestrator-leaf layer_

- [x] 3. Compose the parity check into the existing run-check orchestrator
  - Insert a new block inside the existing `run_check` function, after the per-path-ratchet block and before the final all-success branch.
  - Invoke the parity-check orchestrator with the working-tree root.
  - When the result is not passed, set the existing `failed` accumulator to true and print every entry of the result's failure list to stderr, one per call, preserving order.
  - When the result is passed, append the result's success-summary line to the existing `success_summary` collector so it prints alongside the other success summaries on a fully-clean run.
  - Update the module docstring to list all three checks (CJK-clean, per-path ratchet, locale-parity).
  - Leave the CLI argument parser, `--update-baseline`, `--baseline`, `--repo-root`, the workflow file, and the baseline file format untouched. Confirm by visual diff that no other functions or files are modified.
  - Observable completion: invoking the guard script via its CLI produces a single exit code, and `--help` text plus the existing CLI smoke test continues to pass without modification.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - _Boundary: i18n_cjk_guard module — run_check orchestrator_
  - _Depends: 2_

- [x] 4. Add unit and integration tests for the parity check
  - Extend the existing test-fixture helper that builds synthetic git repositories so callers can supply a Chinese catalogue alongside the English one; default the Chinese catalogue to a parity-clean mirror of the English fixture so the existing test cases continue to pass without semantic change.
  - Add unit-level tests for the dotted-key flattener (empty input, flat input, mixed scalar/string/null leaves, three-level nesting), the line-number resolver (exact match, multi-occurrence first-wins, not-found line-1 fallback), and the failure-line formatter (both sides, special characters in key names).
  - Add integration tests against the parity-check orchestrator covering: identical key sets pass; an en-only divergence fails with the expected category token, summary, and line attributing the key to the EN catalogue; a zh-only divergence fails with the symmetric output; a both-sides divergence yields en-only lines first then zh-only lines, each lex-sorted within its group; same-path scalar leaves on both sides do not count as a parity failure; a missing or malformed catalogue file produces a single deterministic failure line.
  - All new tests use the standard-library testing framework already used in the existing test module; negative-path fixtures are self-contained and do not depend on the live catalogues.
  - Observable completion: running the test module from the repository root produces a passing run with at least the new test cases reported, and a manually-induced en-only or zh-only key reliably trips the relevant test.
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - _Boundary: i18n_cjk_guard test module — parity unit + integration coverage_
  - _Depends: 3_

- [x] 5. Add a no-short-circuit composition test covering all three guard checks
  - Plant CJK content in a synthetic English catalogue AND a parity-divergent key (in either direction) inside the same synthetic repository.
  - Assert that running the full composed guard returns exit code 1, that stderr contains both the existing CJK-related category token and the new parity category token, and that the order of these blocks is preserved (CJK first, then ratchet, then parity) so failure logs remain greppable.
  - Assert that on a fully-clean repository (no CJK in EN, ratchet within baseline, parity holds) the composed guard prints all three success summaries on stdout and exits 0.
  - Observable completion: the new test case fails if any future change short-circuits the orchestrator after the first failure or before invoking the parity check.
  - _Requirements: 3.1, 3.2, 3.3, 5.1_
  - _Boundary: i18n_cjk_guard test module — composition coverage_
  - _Depends: 3, 4_

- [x] 6. Verify the guard against the live locale catalogues
  - Run the guard once from the repository root against the live `locales/en.json` and `locales/zh.json` and confirm it exits 0 with three success-summary lines (CJK-clean, per-path ratchet, locale-parity).
  - If the live catalogues turn out to have non-zero symmetric difference at the time of implementation, document the divergence in this `tasks.md` as a blocking finding and remediate the divergence before completing the task; do not weaken the parity check.
  - Observable completion: the guard's CLI invocation against the live tree prints `OK locale-parity: <count> keys per side` and exits 0, demonstrating that the new check is satisfied by the merge target without any source change.
  - _Requirements: 6.1, 6.2_
  - _Boundary: live `locales/` content (read-only verification)_
  - _Depends: 5_
