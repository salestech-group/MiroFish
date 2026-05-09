#!/usr/bin/env python3
"""AST-aware classifier of Chinese characters in a Python source file.

Usage::

    python3 .kiro/specs/i18n-translate-backend-comments/scan_chinese.py <path>

Classifies every line containing CJK Unified Ideographs (U+4E00..U+9FFF)
into one of three buckets:

* ``DOCSTRING`` — line lies within a module/class/function docstring (in
  scope for ticket #7).
* ``COMMENT``   — line contains a ``#`` and is not inside a docstring or
  a string literal span (in scope for ticket #7).
* ``STRING``    — line is part of a string literal value (out of scope —
  owned by sibling tickets #2/#3/#4/#5/#6).

Exit code is the count of in-scope hits (DOCSTRING + COMMENT). Stdout
lists each in-scope hit as ``<line> <bucket>: <content>`` so callers can
inspect them.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

CJK_RE = re.compile(r"[一-鿿]")


def classify(path: pathlib.Path) -> int:
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    tree = ast.parse(text)

    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            ds = ast.get_docstring(node, clean=False)
            if ds is None:
                continue
            body = node.body
            if not body or not isinstance(body[0], ast.Expr):
                continue
            const = body[0].value
            if isinstance(const, ast.Constant) and isinstance(const.value, str):
                start = const.lineno
                end = getattr(const, "end_lineno", start)
                for ln in range(start, end + 1):
                    docstring_lines.add(ln)

    string_value_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            for ln in range(start, end + 1):
                string_value_lines.add(ln)

    in_scope_count = 0
    for i, line in enumerate(lines, start=1):
        if not CJK_RE.search(line):
            continue
        if i in docstring_lines:
            print(f"{i:5d} DOCSTRING: {line.rstrip()[:120]}")
            in_scope_count += 1
        elif i in string_value_lines:
            # Out of scope: owned by sibling tickets.
            pass
        elif "#" in line:
            print(f"{i:5d} COMMENT  : {line.rstrip()[:120]}")
            in_scope_count += 1
        # else: unclassified — treat as out of scope (STRING value spanning).

    return in_scope_count


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: scan_chinese.py <path>", file=sys.stderr)
        return 2
    path = pathlib.Path(argv[1])
    in_scope = classify(path)
    print(f"---", file=sys.stderr)
    print(f"in-scope CJK hits in {path}: {in_scope}", file=sys.stderr)
    return 0 if in_scope == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
