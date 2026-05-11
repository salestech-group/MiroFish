#!/usr/bin/env python3
"""i18n CJK guard for pull-request CI.

Run from the repository root::

    python scripts/ci/i18n_cjk_guard.py
    python scripts/ci/i18n_cjk_guard.py --update-baseline

Three checks always run (no short-circuit):

* ``locales/en.json`` must contain zero CJK characters
  (range ``U+4E00..U+9FFF``).
* CJK match counts under ``backend/app/`` and ``frontend/src/`` must not
  exceed the committed per-path baseline at
  ``.kiro/specs/i18n-ci-guard/baseline.txt``.
* Locale-key parity: every flattened dotted key in ``locales/en.json``
  must also appear in ``locales/zh.json`` and vice versa.

The first two checks rely on the canonical scan
``git grep -nIP '[\\x{4e00}-\\x{9fff}]' -- <scoped_path>`` so the guard
stays bytewise-aligned with the broader audit pipeline.

Stdlib only. Exit code is 0 on success and 1 on any failure or hard
error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal, NamedTuple

CJK_RE: re.Pattern[str] = re.compile(r"[一-鿿]")
CJK_PATTERN: str = r"[\x{4e00}-\x{9fff}]"
SCOPED_PATHS: tuple[str, ...] = ("backend/app", "frontend/src")
EN_JSON_REL_PATH: str = "locales/en.json"
ZH_JSON_REL_PATH: str = "locales/zh.json"
DEFAULT_BASELINE_REL_PATH: str = ".kiro/specs/i18n-ci-guard/baseline.txt"
SNIPPET_MAX_LEN: int = 80
REFRESH_COMMAND: str = "python scripts/ci/i18n_cjk_guard.py --update-baseline"
REFRESH_HINT: str = f"# refresh via: {REFRESH_COMMAND}"

LocaleFinding = tuple[str, int, str]


class BaselineError(Exception):
    """Raised when the baseline file is missing or malformed."""


def _truncate(text: str, limit: int = SNIPPET_MAX_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _flatten(prefix: str, value: object, out: list[tuple[str, object]]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            _flatten(child_prefix, child, out)
    else:
        out.append((prefix, value))


def _value_line_number(text_lines: list[str], value: str) -> int:
    """Best-effort line number for ``value`` in the original JSON text.

    Tries the raw value first (matches when the JSON file was written with
    ``ensure_ascii=False``), then the JSON-escaped form, then falls back to
    line 1 so callers always have a usable integer.
    """
    candidates: list[str] = [value]
    escaped = json.dumps(value)[1:-1]
    if escaped not in candidates:
        candidates.append(escaped)
    for candidate in candidates:
        if not candidate:
            continue
        for index, line in enumerate(text_lines, start=1):
            if candidate in line:
                return index
    return 1


def scan_locale_cjk(en_json_path: Path) -> list[LocaleFinding]:
    """Return ``(dotted_key, line_number, snippet)`` for every CJK leaf.

    Args:
        en_json_path: Path to ``locales/en.json``.

    Returns:
        A list of findings in document order. Empty when the catalogue is
        CJK-clean. Non-string leaves and empty strings are skipped.

    Raises:
        FileNotFoundError: If ``en_json_path`` does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    raw = en_json_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    flat: list[tuple[str, object]] = []
    _flatten("", data, flat)
    text_lines = raw.splitlines()
    findings: list[LocaleFinding] = []
    for key, value in flat:
        if not isinstance(value, str) or not value:
            continue
        if not CJK_RE.search(value):
            continue
        line_no = _value_line_number(text_lines, value)
        findings.append((key, line_no, _truncate(value)))
    return findings


def count_path_cjk(repo_root: Path, scoped_path: str) -> int:
    """Count CJK match lines under ``scoped_path`` via ``git grep -nIP``.

    Args:
        repo_root: Working-tree root used as ``git`` CWD.
        scoped_path: Repo-relative path to scan (e.g. ``backend/app``).

    Returns:
        The number of matching tracked-text lines. ``-I`` excludes binary
        files; untracked files are excluded by default.

    Raises:
        RuntimeError: If ``git grep`` fails for any reason other than
            "no matches" (exit code 1, which is treated as zero matches).
    """
    cmd = ["git", "grep", "-nIP", CJK_PATTERN, "--", scoped_path]
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"git grep failed (exit {proc.returncode}) for {scoped_path}: "
            f"{proc.stderr.strip()}"
        )
    if not proc.stdout:
        return 0
    return sum(1 for line in proc.stdout.splitlines() if line)


def read_baseline(baseline_path: Path) -> dict[str, int]:
    """Parse the baseline file and return ``{scoped_path: count}``.

    Args:
        baseline_path: Absolute path to the baseline file.

    Returns:
        A dict keyed by scoped path with non-negative integer counts.

    Raises:
        BaselineError: If the file is missing or contains a malformed line.
    """
    if not baseline_path.exists():
        raise BaselineError(
            f"{baseline_path}: missing or malformed; "
            f"refresh via: {REFRESH_COMMAND}"
        )
    counts: dict[str, int] = {}
    for raw_line in baseline_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("#"):
            continue
        if "\t" not in line:
            raise BaselineError(
                f"{baseline_path}: malformed line {raw_line!r}; "
                f"expected '<path>\\t<count>'"
            )
        path, _, count_str = line.partition("\t")
        if not path or not count_str.isdigit():
            raise BaselineError(
                f"{baseline_path}: malformed line {raw_line!r}; "
                f"expected '<path>\\t<count>'"
            )
        counts[path] = int(count_str)
    return counts


def write_baseline(baseline_path: Path, counts: dict[str, int]) -> None:
    """Atomically write the baseline file with sorted entries.

    Args:
        baseline_path: Target file path.
        counts: Per-path baseline counts; keys are written in lexicographic
            order with a single trailing newline.
    """
    header = (
        "# Per-path CJK baseline for the i18n CI guard.\n"
        "# Format: <path>\\t<count>. Sorted lexicographically.\n"
        f"# Refresh via: {REFRESH_COMMAND}\n"
    )
    body_lines = [f"{path}\t{counts[path]}" for path in sorted(counts)]
    body = "\n".join(body_lines) + "\n"
    contents = header + body
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = baseline_path.with_suffix(baseline_path.suffix + ".tmp")
    tmp.write_text(contents, encoding="utf-8")
    os.replace(tmp, baseline_path)


def _format_locale_finding(key: str, line_no: int, snippet: str) -> str:
    return f"{EN_JSON_REL_PATH}:{line_no}: cjk-in-en: {key} = {snippet}"


def _format_regression_line(path: str, baseline: int, current: int) -> str:
    delta = current - baseline
    sign = "+" if delta > 0 else ""
    return (
        f"{path}: cjk-regression: baseline={baseline} "
        f"current={current} delta={sign}{delta}"
    )


ParitySide = Literal["en-only", "zh-only"]


class ParityResult(NamedTuple):
    """Outcome of the locale-key parity check.

    ``failure_lines`` is non-empty only when ``passed`` is ``False`` and
    always ends with the trailing ``parity: en-only=N, zh-only=M``
    summary line in that case. ``success_summary`` is non-``None`` only
    when ``passed`` is ``True``.
    """

    passed: bool
    failure_lines: list[str]
    success_summary: str | None


def _flatten_keys(data: dict[str, object]) -> set[str]:
    """Return the set of dotted-key paths of a parsed JSON catalogue.

    Path semantics match
    ``.kiro/specs/i18n-e2e-english-verification/audit/scripts/check_parity.py:flatten``:
    descend into ``dict`` values only; treat any non-``dict`` value
    (string, number, bool, ``None``, list) as a leaf and emit its key.
    Dict-typed parents are not themselves emitted as keys.
    """
    flat: list[tuple[str, object]] = []
    _flatten("", data, flat)
    return {key for key, _ in flat}


def _locate_key_line(text_lines: list[str], dotted_key: str) -> int:
    """Best-effort 1-based line number for ``dotted_key`` in raw JSON text.

    Searches for the leaf segment of ``dotted_key`` (after the last dot)
    wrapped in JSON quotes, e.g. ``"missingKey"``. Returns the line of
    the first match, or ``1`` when no match is found. The dotted key
    itself remains the source of truth in the failure message; the line
    number is a navigation aid only.
    """
    leaf = dotted_key.rsplit(".", 1)[-1]
    needle = f'"{leaf}"'
    for index, line in enumerate(text_lines, start=1):
        if needle in line:
            return index
    return 1


def _format_parity_finding(
    file_rel_path: str,
    line_no: int,
    dotted_key: str,
    side: ParitySide,
) -> str:
    """Format one parity-failure line.

    Layout: ``<file>:<line>: parity-<side>: <dotted-key>``. Side is
    constrained to ``"en-only"`` / ``"zh-only"`` to keep the failure
    category greppable across CI logs.
    """
    return f"{file_rel_path}:{line_no}: parity-{side}: {dotted_key}"


def _safe_load_catalogue(
    path: Path,
    rel_path: str,
    failure_lines: list[str],
) -> dict[str, object] | None:
    """Load a locale catalogue or append a parity-error line and return ``None``.

    Catches missing-file and malformed-JSON errors so the guard reports
    a clean stderr line rather than crashing CI with a Python traceback.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        failure_lines.append(
            f"{rel_path}: parity-error: cannot read ({exc.__class__.__name__})"
        )
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        failure_lines.append(
            f"{rel_path}: parity-error: invalid JSON: {exc.msg}"
        )
        return None
    if not isinstance(data, dict):
        failure_lines.append(
            f"{rel_path}: parity-error: top-level value is not an object"
        )
        return None
    return data


def run_parity_check(repo_root: Path) -> ParityResult:
    """Compute locale-key parity between ``en.json`` and ``zh.json``.

    Reads both catalogues from ``repo_root``, flattens each into a
    dotted-key set, and computes the symmetric difference. On match
    the result carries an ``OK locale-parity: <count> keys per side``
    success summary. On mismatch the result carries one
    ``parity-en-only`` line per en-only key (lex-sorted), then one
    ``parity-zh-only`` line per zh-only key (lex-sorted), then a final
    ``parity: en-only=<n>, zh-only=<m>`` summary line.

    Missing or malformed catalogues are surfaced as a single
    ``parity-error`` line per offending file and yield a non-passing
    result without raising.
    """
    en_path = repo_root / EN_JSON_REL_PATH
    zh_path = repo_root / ZH_JSON_REL_PATH
    failure_lines: list[str] = []
    en_data = _safe_load_catalogue(en_path, EN_JSON_REL_PATH, failure_lines)
    zh_data = _safe_load_catalogue(zh_path, ZH_JSON_REL_PATH, failure_lines)
    if en_data is None or zh_data is None:
        return ParityResult(
            passed=False,
            failure_lines=failure_lines,
            success_summary=None,
        )

    en_keys = _flatten_keys(en_data)
    zh_keys = _flatten_keys(zh_data)
    en_only = sorted(en_keys - zh_keys)
    zh_only = sorted(zh_keys - en_keys)

    if not en_only and not zh_only:
        return ParityResult(
            passed=True,
            failure_lines=[],
            success_summary=(
                f"OK locale-parity: {len(en_keys)} keys per side"
            ),
        )

    en_text_lines = en_path.read_text(encoding="utf-8").splitlines()
    zh_text_lines = zh_path.read_text(encoding="utf-8").splitlines()
    for key in en_only:
        line_no = _locate_key_line(en_text_lines, key)
        failure_lines.append(
            _format_parity_finding(
                EN_JSON_REL_PATH, line_no, key, "en-only"
            )
        )
    for key in zh_only:
        line_no = _locate_key_line(zh_text_lines, key)
        failure_lines.append(
            _format_parity_finding(
                ZH_JSON_REL_PATH, line_no, key, "zh-only"
            )
        )
    failure_lines.append(
        f"parity: en-only={len(en_only)}, zh-only={len(zh_only)}"
    )
    return ParityResult(
        passed=False,
        failure_lines=failure_lines,
        success_summary=None,
    )


def run_check(repo_root: Path, baseline_path: Path) -> int:
    """Run both guard checks and return the script exit code.

    Args:
        repo_root: Working-tree root passed to ``git grep``.
        baseline_path: Path to the baseline file.

    Returns:
        ``0`` when both checks pass, ``1`` otherwise.
    """
    failed = False
    success_summary: list[str] = []

    en_json_path = repo_root / EN_JSON_REL_PATH
    if not en_json_path.exists():
        print(f"{EN_JSON_REL_PATH}: missing catalogue file", file=sys.stderr)
        failed = True
    else:
        try:
            findings = scan_locale_cjk(en_json_path)
        except json.JSONDecodeError as exc:
            print(
                f"{EN_JSON_REL_PATH}: invalid JSON: {exc.msg}",
                file=sys.stderr,
            )
            findings = []
            failed = True
        if findings:
            for key, line_no, snippet in findings:
                print(
                    _format_locale_finding(key, line_no, snippet),
                    file=sys.stderr,
                )
            print(f"{len(findings)} issues", file=sys.stderr)
            failed = True
        elif not failed:
            success_summary.append("OK locales/en.json is CJK-clean")

    try:
        baseline = read_baseline(baseline_path)
    except BaselineError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    current_counts: dict[str, int] = {}
    try:
        for path in SCOPED_PATHS:
            current_counts[path] = count_path_cjk(repo_root, path)
    except RuntimeError as exc:
        print(f"git grep failed: {exc}", file=sys.stderr)
        return 1

    regressions: list[str] = []
    for path in SCOPED_PATHS:
        baseline_value = baseline.get(path, 0)
        current_value = current_counts[path]
        if current_value > baseline_value:
            regressions.append(
                _format_regression_line(path, baseline_value, current_value)
            )

    if regressions:
        for line in regressions:
            print(line, file=sys.stderr)
        print(REFRESH_HINT, file=sys.stderr)
        failed = True
    else:
        per_path = ", ".join(
            f"{path}={current_counts[path]}<={baseline.get(path, 0)}"
            for path in SCOPED_PATHS
        )
        success_summary.append(
            f"OK per-path counts within baseline ({per_path})"
        )

    parity_result = run_parity_check(repo_root)
    if not parity_result.passed:
        for line in parity_result.failure_lines:
            print(line, file=sys.stderr)
        failed = True
    elif parity_result.success_summary is not None:
        success_summary.append(parity_result.success_summary)

    if not failed:
        for line in success_summary:
            print(line)

    return 1 if failed else 0


def update_baseline(repo_root: Path, baseline_path: Path) -> int:
    """Refresh ``baseline_path`` with current per-path counts.

    Args:
        repo_root: Working-tree root passed to ``git grep``.
        baseline_path: Target baseline file path; created if missing.

    Returns:
        ``0`` on success.
    """
    counts: dict[str, int] = {}
    for path in SCOPED_PATHS:
        counts[path] = count_path_cjk(repo_root, path)
    write_baseline(baseline_path, counts)
    print(f"baseline updated: {baseline_path}")
    for path in sorted(counts):
        print(f"  {path}\t{counts[path]}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="i18n_cjk_guard",
        description=(
            "PR-time guard: fail when locales/en.json contains CJK, when "
            "backend/app + frontend/src CJK match counts exceed the "
            "committed baseline, or when locales/en.json and "
            "locales/zh.json have non-equal flattened-key sets."
        ),
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "overwrite the baseline file with current counts and exit 0"
        ),
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help=(
            f"path to the baseline file (default: {DEFAULT_BASELINE_REL_PATH})"
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help=(
            "repository root (default: detected via "
            "`git rev-parse --show-toplevel`)"
        ),
    )
    return parser


def _detect_repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"unable to detect repository root: {proc.stderr.strip()}"
        )
    return Path(proc.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the script exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        repo_root = _detect_repo_root(args.repo_root)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.baseline is not None:
        baseline_path = args.baseline.resolve()
    else:
        baseline_path = (repo_root / DEFAULT_BASELINE_REL_PATH).resolve()
    if args.update_baseline:
        return update_baseline(repo_root, baseline_path)
    return run_check(repo_root, baseline_path)


if __name__ == "__main__":
    sys.exit(main())
