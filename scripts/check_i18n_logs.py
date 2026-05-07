#!/usr/bin/env python3
"""Verify backend i18n externalization for ticket #6.

Two checks (both run by default):

* ``--logs``: scan the in-scope backend modules and report any Chinese
  character (U+4E00-U+9FFF) that still appears inside the string-literal
  arguments of ``logger.{info,warning,error,debug,exception}(...)`` calls or
  inside the ``error`` / ``message`` field values of ``jsonify({...})`` calls.

* ``--parity``: load every ``*.json`` in ``locales/`` (excluding
  ``languages.json``) and verify that the recursive set of key paths is
  identical across every file.

Exit code is 0 when both checks pass and 1 otherwise. Each finding is printed
on its own line as ``<file>:<line>: <reason>: <snippet>``. Final line is
``OK`` or ``N issues``.

The script depends only on the Python standard library so it can be invoked
from a clean checkout: ``python scripts/check_i18n_logs.py``.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

# In-scope backend modules per .kiro/specs/i18n-externalize-backend-logs/design.md.
# ``backend/app/__init__.py`` is also covered to satisfy the ticket's
# repo-wide grep guard, even though it lives outside the listed module set.
SOURCE_FILES = [
    "backend/app/__init__.py",
    "backend/app/services/report_agent.py",
    "backend/app/services/zep_tools.py",
    "backend/app/services/simulation_runner.py",
    "backend/app/services/oasis_profile_generator.py",
    "backend/app/services/simulation_config_generator.py",
    "backend/app/services/zep_graph_memory_updater.py",
    "backend/app/services/ontology_generator.py",
    "backend/app/services/simulation_manager.py",
    "backend/app/services/zep_entity_reader.py",
    "backend/app/services/simulation_ipc.py",
    "backend/app/services/graph_builder.py",
    "backend/app/api/simulation.py",
    "backend/app/api/report.py",
    "backend/app/api/graph.py",
]

LOCALES_DIR = REPO_ROOT / "locales"

LOGGER_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
JSONIFY_TRANSLATED_FIELDS = {"error", "message"}

CHINESE_RE = re.compile(r"[一-鿿]")


def _has_chinese(text: str) -> bool:
    return bool(CHINESE_RE.search(text))


def _string_literal_value(node: ast.AST) -> str | None:
    """Return the string value of a literal ``Constant``/``JoinedStr``, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                # Conservatively render dynamic interpolation segments as a
                # placeholder so that surrounding Chinese text in the static
                # parts is still detected.
                parts.append("�")
        return "".join(parts)
    return None


def _is_logger_call(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in LOGGER_METHODS
        and isinstance(func.value, ast.Name)
        and func.value.id == "logger"
    )


def _is_jsonify_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name) and func.id == "jsonify":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "jsonify":
        return True
    return False


def _scan_call_for_chinese(node: ast.Call, source_lines: list[str]) -> Iterable[tuple[int, str, str]]:
    """Yield (line, reason, snippet) for any Chinese in this call's arguments."""
    if _is_logger_call(node):
        for arg in node.args:
            text = _string_literal_value(arg)
            if text and _has_chinese(text):
                yield (
                    arg.lineno,
                    "chinese inside logger call argument",
                    _snippet(source_lines, arg.lineno),
                )
        for kw in node.keywords:
            text = _string_literal_value(kw.value) if kw.value is not None else None
            if text and _has_chinese(text):
                yield (
                    kw.value.lineno,
                    "chinese inside logger call keyword argument",
                    _snippet(source_lines, kw.value.lineno),
                )
        return

    if _is_jsonify_call(node):
        for arg in node.args:
            yield from _scan_jsonify_arg(arg, source_lines)


def _scan_jsonify_arg(arg: ast.AST, source_lines: list[str]) -> Iterable[tuple[int, str, str]]:
    """Yield findings for Chinese inside ``error`` or ``message`` dict values."""
    if isinstance(arg, ast.Dict):
        for key, value in zip(arg.keys, arg.values):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            if key.value not in JSONIFY_TRANSLATED_FIELDS:
                continue
            text = _string_literal_value(value)
            if text and _has_chinese(text):
                yield (
                    value.lineno,
                    f"chinese inside jsonify {key.value} field",
                    _snippet(source_lines, value.lineno),
                )


def _snippet(source_lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(source_lines):
        return source_lines[lineno - 1].rstrip()
    return ""


def check_logs() -> list[str]:
    """Return a list of findings (empty when clean)."""
    findings: list[str] = []
    for rel_path in SOURCE_FILES:
        abs_path = REPO_ROOT / rel_path
        if not abs_path.exists():
            findings.append(f"{rel_path}:0: missing in-scope file: not found")
            continue
        source = abs_path.read_text(encoding="utf-8")
        source_lines = source.splitlines()
        try:
            tree = ast.parse(source, filename=str(abs_path))
        except SyntaxError as exc:
            findings.append(f"{rel_path}:{exc.lineno or 0}: syntax error: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for line, reason, snippet in _scan_call_for_chinese(node, source_lines):
                findings.append(f"{rel_path}:{line}: {reason}: {snippet.strip()}")
    return findings


def _collect_key_paths(obj, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            child_prefix = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                paths.update(_collect_key_paths(v, child_prefix))
            else:
                paths.add(child_prefix)
    return paths


def check_parity() -> list[str]:
    findings: list[str] = []
    locale_files = sorted(p for p in LOCALES_DIR.glob("*.json") if p.name != "languages.json")
    if len(locale_files) < 2:
        return findings
    key_sets: dict[str, set[str]] = {}
    for path in locale_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(f"{path.relative_to(REPO_ROOT)}:0: invalid JSON: {exc.msg}")
            continue
        key_sets[path.name] = _collect_key_paths(data)
    if len(key_sets) < 2:
        return findings
    union = set().union(*key_sets.values())
    for path_name, keys in key_sets.items():
        missing = sorted(union - keys)
        for key_path in missing:
            findings.append(f"locales/{path_name}:0: missing key path: {key_path}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", action="store_true", help="run the source-scan check only")
    parser.add_argument("--parity", action="store_true", help="run the locale-parity check only")
    args = parser.parse_args(argv)

    run_logs = args.logs or not args.parity
    run_parity = args.parity or not args.logs
    # If neither flag is set, both default to True (handled above).

    findings: list[str] = []
    if run_logs:
        findings.extend(check_logs())
    if run_parity:
        findings.extend(check_parity())

    for finding in findings:
        print(finding)

    if findings:
        print(f"{len(findings)} issues")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
