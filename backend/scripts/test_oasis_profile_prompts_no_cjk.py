"""Static guard: assert OASIS profile prompt strings contain no CJK characters.

This script enforces the i18n contract for `oasis_profile_generator.py`
(issue #3): every string literal contributed by the prompt-building
helpers must contain zero CJK characters.

In-scope methods (their string literals, excluding docstrings):
- `OasisProfileGenerator._get_system_prompt`
- `OasisProfileGenerator._build_individual_persona_prompt`
- `OasisProfileGenerator._build_group_persona_prompt`
- `OasisProfileGenerator._build_entity_context`
- `OasisProfileGenerator._search_zep_for_entity` (excluding logger-call
  argument literals, which are owned by issue #6)

Out-of-scope (NOT inspected, even though they live in the same file):
- All `logger.<level>(...)` argument literals (issue #6)
- `_print_generated_profile` and `generate_profiles_from_entities`
  console-progress strings (issue #6)
- Module/class/method docstrings and inline comments (issue #7)
- The Chinese fallback persona strings in the JSON-repair path
  (`_generate_profile_with_llm`, `_try_fix_json`) — out of scope for #3
- `_normalize_gender` Chinese-to-English mapping keys (must remain to
  support `zh`-locale outputs)

The check is purely AST-based to avoid coupling to the heavy Flask /
OpenAI / Graphiti import chain. Exit 0 on success, non-zero on
regression.
"""

import ast
import os
import re
import sys


CJK_PATTERN = re.compile(r"[一-鿿]")


def _is_logger_call(node: ast.AST) -> bool:
    """Return True if `node` is a `logger.<anything>(...)` call expression."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    value = func.value
    return isinstance(value, ast.Name) and value.id == "logger"


def _string_literals_in_function(node: ast.FunctionDef) -> list[str]:
    """Return all string-literal payloads inside a function body, except
    the function's own docstring AND any literal that is part of a
    `logger.<level>(...)` call AND any literal inside a nested function
    definition (which has its own scope and is owned by issues #6/#7).

    Both plain strings (`ast.Constant` of type `str`) and f-string static
    portions (`ast.Constant` children of `ast.JoinedStr`) are included.
    Subtrees rooted at a logger call are skipped wholesale, so logger
    argument literals — including Chinese ones owned by issue #6 — are
    not inspected. Nested `FunctionDef` / `AsyncFunctionDef` subtrees are
    likewise skipped: their literals do not contribute to the outer
    function's prompt content.
    """
    docstring = ast.get_docstring(node, clean=False)
    pieces: list[str] = []

    def visit(child: ast.AST) -> None:
        if _is_logger_call(child):
            return  # Skip the entire logger-call subtree.
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return  # Skip nested function definitions entirely.
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            pieces.append(child.value)
        elif isinstance(child, ast.JoinedStr):
            for part in child.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    pieces.append(part.value)
            # JoinedStr children are FormattedValue / Constant; do not
            # recurse further — formatted values cannot contain string
            # literals at the source level.
            return
        for grandchild in ast.iter_child_nodes(child):
            visit(grandchild)

    for top_child in ast.iter_child_nodes(node):
        visit(top_child)

    if docstring is not None:
        try:
            pieces.remove(docstring)
        except ValueError:
            pass

    return pieces


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
        "oasis_profile_generator.py",
    )
    with open(target, "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)

    failures = 0

    in_scope_methods = (
        "_get_system_prompt",
        "_build_individual_persona_prompt",
        "_build_group_persona_prompt",
        "_build_entity_context",
        "_search_zep_for_entity",
    )

    for method_name in in_scope_methods:
        method = _find_method(tree, "OasisProfileGenerator", method_name)
        literals = _string_literals_in_function(method)
        aggregated = "\n".join(literals)
        failures += _assert_no_cjk(
            f"OasisProfileGenerator.{method_name} string literals "
            f"(excl. docstring and logger-call args)",
            aggregated,
        )

    if failures:
        print(f"\n{failures} CJK-regression check(s) failed.", file=sys.stderr)
        return 1

    print("\nAll CJK-regression checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
