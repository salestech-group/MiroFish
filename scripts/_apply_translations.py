#!/usr/bin/env python3
"""Overwrite English values in ``locales/en.json`` from a translation map.

Usage::

    python scripts/_apply_translations.py path/to/translations.json

The translation file is a flat JSON object ``{"a.b.c": "English text", ...}``.
Each key path must already exist in ``en.json``; missing keys raise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _set_path(tree, path: str, value: str) -> None:
    parts = path.split(".")
    cursor = tree
    for part in parts[:-1]:
        if part not in cursor or not isinstance(cursor[part], dict):
            raise KeyError(f"missing parent path: {path}")
        cursor = cursor[part]
    if parts[-1] not in cursor:
        raise KeyError(f"missing leaf key: {path}")
    cursor[parts[-1]] = value


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: _apply_translations.py <translations.json>", file=sys.stderr)
        return 2
    blob_path = Path(sys.argv[1])
    translations = json.loads(blob_path.read_text(encoding="utf-8"))
    en_path = REPO_ROOT / "locales" / "en.json"
    en = json.loads(en_path.read_text(encoding="utf-8"))
    for key, value in translations.items():
        _set_path(en, key, value)
    en_path.write_text(json.dumps(en, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"applied {len(translations)} translations to {en_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
