#!/usr/bin/env python3
"""One-shot codemod for ticket #6.

For a single in-scope backend Python file, walk every Chinese-bearing
``logger.{info,warning,error,debug,exception}(...)`` call and every
``jsonify({"error|message": "..."})`` call, replace the literal with a
``t("<sub_namespace>.<key>", **kwargs)`` lookup, and emit the matching
zh-side locale entries (en-side stubs use the same Chinese text and are
translated manually afterwards).

Usage::

    python scripts/_codemod_i18n.py <file> --log-namespace log.<module> [--api-error-namespace api.error.<scope>] [--api-message-namespace api.message.<scope>]

The script:
  * Modifies the source file in place.
  * Writes a JSON blob of new locale entries to stdout::

        {"keys": {"log.<module>.<key>": "原文", ...}}

This blob is merged into both ``locales/en.json`` and ``locales/zh.json`` by a
separate pass (English values are translated by hand afterward).
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from pathlib import Path
from typing import Iterable

CHINESE_RE = re.compile(r"[一-鿿]")
PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")
SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_]")

DEFAULT_PLACEHOLDER_NAMES = [
    "value", "value2", "value3", "value4", "value5", "value6", "value7",
]


def _has_chinese(s: str) -> bool:
    return bool(CHINESE_RE.search(s))


def _expr_to_kw(expr: ast.AST, source: str) -> str:
    """Pretty-print an expression node back into source text."""
    return ast.unparse(expr)


def _primary_name(expr_text: str) -> str | None:
    """Extract the leading identifier from a Python expression text, if any."""
    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)", expr_text.strip())
    return match.group(1) if match else None


def _slugify_expr(expr_text: str, used: set[str]) -> str:
    primary = _primary_name(expr_text)
    if primary:
        base = primary.lower()
    else:
        base = SAFE_NAME_RE.sub("_", expr_text).strip("_") or "value"
        base = re.sub(r"_+", "_", base).lower()
    if not base or base[0].isdigit():
        base = f"v_{base}"
    return _next_unique(base, used)


def _next_unique(name: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name
    i = 2
    while f"{name}_{i}" in used:
        i += 1
    final = f"{name}_{i}"
    used.add(final)
    return final


def _flatten_string_arg(node: ast.AST, source: str) -> tuple[str, dict[str, str]] | None:
    """Return (template, kwargs) for a string-like argument or None.

    ``template`` uses ``{name}`` placeholders; ``kwargs`` maps each placeholder
    name to the source text of its expression.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, {}
    if isinstance(node, ast.JoinedStr):
        used: set[str] = set()
        parts: list[str] = []
        kwargs: dict[str, str] = {}
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                expr_text = _expr_to_kw(value.value, source)
                placeholder = _slugify_expr(expr_text, used)
                kwargs[placeholder] = expr_text
                parts.append("{" + placeholder + "}")
            else:
                return None
        template = "".join(parts)
        # Normalise braces inside literal text so {} not coming from a placeholder
        # doesn't get misread by t().replace(); literals containing literal { or }
        # are rare in this codebase but we'll guard anyway.
        for ph_name in kwargs:
            if template.count("{" + ph_name + "}") < 1:
                return None
        return template, kwargs
    return None


def _slug_from_template(template: str, used: set[str], fallback_index: int) -> str:
    """Build a key suffix.

    The naming scheme is ``m<NNN>`` based on a per-file counter. This keeps
    the JSON keys ASCII-only, easy to grep, and stable enough for review.
    Semantic renaming can be done in a post-pass for the keys that justify it.
    """
    candidate = f"m{fallback_index:03d}"
    return _next_unique(candidate, used)


def _format_t_call(namespace: str, key: str, kwargs: dict[str, str]) -> str:
    full_key = f"{namespace}.{key}"
    if not kwargs:
        return f't("{full_key}")'
    formatted_kwargs = ", ".join(f"{name}={expr}" for name, expr in kwargs.items())
    return f't("{full_key}", {formatted_kwargs})'


class Rewriter(ast.NodeVisitor):
    def __init__(
        self,
        source: str,
        log_namespace: str,
        api_error_namespace: str | None,
        api_message_namespace: str | None,
    ):
        self.source = source
        self.log_namespace = log_namespace
        self.api_error_namespace = api_error_namespace
        self.api_message_namespace = api_message_namespace
        # Each replacement is (lineno, original_segment_text, new_text).
        # ``lineno`` is the 1-based line on which the original segment starts;
        # used as an anchor so multiple identical segments in the file can be
        # disambiguated.
        self.replacements: list[tuple[int, str, str]] = []
        self.entries: dict[str, str] = {}  # full_key -> original chinese template
        self.used_keys: set[str] = set()
        self.counter = 0

    def visit_Call(self, node: ast.Call):
        if self._is_logger_call(node):
            for i, arg in enumerate(node.args):
                self._maybe_rewrite_arg(arg, self.log_namespace)
            for kw in node.keywords:
                if kw.value is not None:
                    self._maybe_rewrite_arg(kw.value, self.log_namespace)
        elif self._is_jsonify_call(node):
            for arg in node.args:
                if isinstance(arg, ast.Dict):
                    for key, value in zip(arg.keys, arg.values):
                        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                            continue
                        if key.value == "error" and self.api_error_namespace:
                            self._maybe_rewrite_arg(value, self.api_error_namespace)
                        elif key.value == "message" and self.api_message_namespace:
                            self._maybe_rewrite_arg(value, self.api_message_namespace)
        self.generic_visit(node)

    @staticmethod
    def _is_logger_call(node: ast.Call) -> bool:
        func = node.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr in {"debug", "info", "warning", "error", "exception", "critical"}
            and isinstance(func.value, ast.Name)
            and func.value.id == "logger"
        )

    @staticmethod
    def _is_jsonify_call(node: ast.Call) -> bool:
        func = node.func
        if isinstance(func, ast.Name) and func.id == "jsonify":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "jsonify":
            return True
        return False

    def _maybe_rewrite_arg(self, node: ast.AST, namespace: str) -> None:
        flat = _flatten_string_arg(node, self.source)
        if flat is None:
            return
        template, kwargs = flat
        if not _has_chinese(template):
            return
        original_segment = ast.get_source_segment(self.source, node)
        if original_segment is None:
            return
        self.counter += 1
        key = _slug_from_template(template, self.used_keys, self.counter)
        full_key = f"{namespace}.{key}"
        new_text = _format_t_call(namespace, key, kwargs)
        self.replacements.append((node.lineno, original_segment, new_text))
        self.entries[full_key] = template


def _apply_replacements(source: str, replacements):
    """Apply each (lineno, original_segment, new_text) replacement in order.

    Each replacement is anchored to the line on which its original segment
    starts so that identical literals elsewhere in the file are not touched
    by accident.
    """
    lines = source.splitlines(keepends=True)
    line_offsets = [0]
    for line in lines:
        line_offsets.append(line_offsets[-1] + len(line))

    # Apply in source order so the search anchor stays correct as offsets shift.
    sorted_reps = sorted(replacements, key=lambda r: r[0])
    delta = 0
    for lineno, original, new_text in sorted_reps:
        anchor = line_offsets[lineno - 1] + delta
        idx = source.find(original, anchor)
        if idx == -1:
            raise RuntimeError(
                f"could not locate original segment on line {lineno}: {original!r}"
            )
        source = source[:idx] + new_text + source[idx + len(original):]
        delta += len(new_text) - len(original)
    return source


_API_LOCALE_IMPORT = "from ..utils.locale import t\n"
_SERVICE_LOCALE_IMPORT = "from ..utils.locale import t\n"


def _ensure_t_import(source: str, target_path: Path) -> str:
    """Add ``from ..utils.locale import t`` when no ``t`` is imported yet."""
    tree = ast.parse(source, filename=str(target_path))
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("utils.locale"):
            for alias in node.names:
                if alias.name == "t":
                    return source  # already imports t
            # Append ``t`` to the existing import line.
            new_names = [alias.name for alias in node.names] + ["t"]
            new_line = f"from {'.' * node.level}{node.module} import {', '.join(new_names)}\n"
            lines = source.splitlines(keepends=True)
            # Preserve original line range; ImportFrom may span multiple lines but
            # in this codebase they are always single-line.
            start = node.lineno - 1
            end = (node.end_lineno or node.lineno) - 1
            return "".join(lines[:start]) + new_line + "".join(lines[end + 1:])
    # No locale import at all — insert one after the last top-level import.
    lines = source.splitlines(keepends=True)
    insert_at = 0
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            insert_at = max(insert_at, (node.end_lineno or node.lineno))
    return "".join(lines[:insert_at]) + _SERVICE_LOCALE_IMPORT + "".join(lines[insert_at:])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--log-namespace", required=True)
    parser.add_argument("--api-error-namespace", default=None)
    parser.add_argument("--api-message-namespace", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    source = args.path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(args.path))
    rewriter = Rewriter(
        source=source,
        log_namespace=args.log_namespace,
        api_error_namespace=args.api_error_namespace,
        api_message_namespace=args.api_message_namespace,
    )
    rewriter.visit(tree)

    if not rewriter.replacements:
        print(json.dumps({"keys": {}, "modified": False}))
        return 0

    new_source = _apply_replacements(source, rewriter.replacements)
    new_source = _ensure_t_import(new_source, args.path)
    if not args.dry_run:
        args.path.write_text(new_source, encoding="utf-8")
    print(json.dumps({"keys": rewriter.entries, "modified": not args.dry_run}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
