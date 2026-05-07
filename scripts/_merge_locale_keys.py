#!/usr/bin/env python3
"""Merge a flat ``{"keys": {"a.b.c": "..."}}`` blob into both locale files.

Usage::

    cat blob.json | python scripts/_merge_locale_keys.py

The blob is the JSON line emitted by ``_codemod_i18n.py``. New keys are
inserted into both ``locales/en.json`` and ``locales/zh.json``. The Chinese
text is preserved verbatim on both sides; the English translations are
applied in a separate manual pass after every codemod run completes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = REPO_ROOT / "locales"


def _set_path(tree: dict, key_path: str, value: str) -> bool:
    """Insert ``value`` at the dotted ``key_path`` inside ``tree``.

    Returns True when the key is newly added; False when it already existed.
    Raises ``ValueError`` if an intermediate segment exists but is not a dict.
    """
    parts = key_path.split(".")
    cursor = tree
    for part in parts[:-1]:
        nxt = cursor.get(part)
        if nxt is None:
            nxt = {}
            cursor[part] = nxt
        elif not isinstance(nxt, dict):
            raise ValueError(
                f"cannot insert {key_path}: existing value at '{part}' is not a dict"
            )
        cursor = nxt
    leaf = parts[-1]
    if leaf in cursor:
        return False
    cursor[leaf] = value
    return True


def _sort_dict_recursive(tree):
    if isinstance(tree, dict):
        return {k: _sort_dict_recursive(tree[k]) for k in sorted(tree.keys())}
    return tree


def main() -> int:
    blob = json.loads(sys.stdin.read())
    entries: dict[str, str] = blob.get("keys", {})
    if not entries:
        print("no entries", file=sys.stderr)
        return 0

    en_path = LOCALES_DIR / "en.json"
    zh_path = LOCALES_DIR / "zh.json"
    en = json.loads(en_path.read_text(encoding="utf-8"))
    zh = json.loads(zh_path.read_text(encoding="utf-8"))

    # Determine the nested sub-namespace to keep alphabetised
    namespaces_touched: set[str] = set()
    for full_key in entries:
        parts = full_key.split(".")
        # Re-sort up to the parent of the leaf so new keys land alphabetically.
        namespaces_touched.add(".".join(parts[:-1]))

    added = 0
    for full_key, value in entries.items():
        if _set_path(en, full_key, value):
            added += 1
        _set_path(zh, full_key, value)

    # Sort the touched sub-namespaces (and their parents) so diffs are stable.
    for ns in namespaces_touched:
        for tree in (en, zh):
            cursor = tree
            parts = ns.split(".")
            for part in parts:
                if part not in cursor or not isinstance(cursor[part], dict):
                    cursor = None
                    break
                cursor = cursor[part]
            if cursor is None:
                continue
            sorted_subtree = _sort_dict_recursive(cursor)
            cursor.clear()
            cursor.update(sorted_subtree)

    en_path.write_text(json.dumps(en, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    zh_path.write_text(json.dumps(zh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"added {added} new keys ({len(entries) - added} already present)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
