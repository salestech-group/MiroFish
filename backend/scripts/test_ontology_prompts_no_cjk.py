"""Static guard: assert ontology prompt strings contain no CJK characters.

This script enforces the i18n contract for `ontology_generator.py` (issue #2):
the module-level system prompt constant and every string literal contributed
by `_build_user_message` (excluding the method's docstring) must contain
zero CJK characters.

Logger calls, docstrings, and inline comments in the same module are
explicitly out of scope (issues #6 and #7) and are not inspected here.

The check is purely AST-based to avoid coupling to the heavy Flask /
LLM client import chain. Exit 0 on success, non-zero on regression.
"""

import ast
import os
import re
import sys


CJK_PATTERN = re.compile(r"[一-鿿]")


def _string_literals_in_function(node: ast.FunctionDef) -> list[str]:
    """Return all string-literal payloads inside a function body, except the
    function's own docstring.

    Both plain strings (`ast.Constant` of type `str`) and f-strings
    (`ast.JoinedStr`) are included. For f-strings, only the static text
    portions (`ast.Constant` children) are returned — interpolation
    placeholders cannot contain CJK literals, so they are irrelevant.
    """
    docstring = ast.get_docstring(node, clean=False)
    pieces: list[str] = []

    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            pieces.append(child.value)
        elif isinstance(child, ast.JoinedStr):
            for part in child.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    pieces.append(part.value)

    if docstring is not None:
        try:
            pieces.remove(docstring)
        except ValueError:
            pass

    return pieces


def _module_constant_value(tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    if isinstance(node.value, ast.Constant) and isinstance(
                        node.value.value, str
                    ):
                        return node.value.value
    raise SystemExit(f"Could not locate string constant '{name}' in source.")


def _find_method(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    raise SystemExit(f"Could not locate method '{class_name}.{method_name}'.")


def _assert_no_cjk(label: str, text: str) -> int:
    matches = CJK_PATTERN.findall(text)
    if matches:
        sample = "".join(matches[:30])
        print(
            f"FAIL: {label} contains {len(matches)} CJK character(s). "
            f"First few: {sample!r}",
            file=sys.stderr,
        )
        return 1
    print(f"OK: {label} is CJK-free ({len(text)} chars inspected).")
    return 0


def main() -> int:
    target = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app",
        "services",
        "ontology_generator.py",
    )
    with open(target, "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)

    failures = 0

    system_prompt_value = _module_constant_value(tree, "ONTOLOGY_SYSTEM_PROMPT")
    failures += _assert_no_cjk("ONTOLOGY_SYSTEM_PROMPT", system_prompt_value)

    method = _find_method(tree, "OntologyGenerator", "_build_user_message")
    literals = _string_literals_in_function(method)
    aggregated = "\n".join(literals)
    failures += _assert_no_cjk(
        "_build_user_message string literals (excl. docstring)", aggregated
    )

    if failures:
        print(f"\n{failures} CJK-regression check(s) failed.", file=sys.stderr)
        return 1

    print("\nAll CJK-regression checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
