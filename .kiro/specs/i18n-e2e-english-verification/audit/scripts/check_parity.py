#!/usr/bin/env python3
"""Diff locales/en.json against locales/zh.json and emit parity.txt.

Three labelled blocks are written:

* `[missing-keys]`  - keys present on one side but not the other.
* `[cjk-in-en]`     - EN catalogue values that contain CJK characters.
* `[identical-values]` - keys whose EN and ZH value are identical AND the
                        value is non-empty AND has more than two ASCII words.
                        These are review-needed signals, not gaps.

Run from the repository root.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterator, Tuple

CJK_RANGE = re.compile(r"[一-鿿]")


def flatten(d: Dict[str, object], prefix: str = "") -> Iterator[Tuple[str, object]]:
    """Recursively yield (dotted-key, value) pairs from a nested dict."""
    for key, value in d.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from flatten(value, path)
        else:
            yield path, value


def is_non_trivial_english_prose(value: object) -> bool:
    """Heuristic for the identical-value 'review-needed' signal.

    True when:
    * value is a string,
    * value is non-empty after strip,
    * value contains more than two whitespace-separated tokens,
    * value contains no CJK characters (otherwise it's just an untranslated
      ZH original which is not a review-needed signal here).
    """
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    if CJK_RANGE.search(text):
        return False
    return len(text.split()) > 2


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <sha-dir>", file=sys.stderr)
        return 64

    sha_dir = Path(argv[1])
    sha_dir.mkdir(parents=True, exist_ok=True)
    out_path = sha_dir / "parity.txt"

    en_path = Path("locales/en.json")
    zh_path = Path("locales/zh.json")
    if not en_path.exists() or not zh_path.exists():
        print(f"missing locale files: {en_path}, {zh_path}", file=sys.stderr)
        return 1

    en = json.loads(en_path.read_text(encoding="utf-8"))
    zh = json.loads(zh_path.read_text(encoding="utf-8"))

    en_flat = dict(flatten(en))
    zh_flat = dict(flatten(zh))

    en_only = sorted(set(en_flat) - set(zh_flat))
    zh_only = sorted(set(zh_flat) - set(en_flat))

    cjk_in_en = []
    for key, value in sorted(en_flat.items()):
        if isinstance(value, str) and CJK_RANGE.search(value):
            cjk_in_en.append((key, value))

    identical = []
    for key in sorted(set(en_flat) & set(zh_flat)):
        en_val = en_flat[key]
        zh_val = zh_flat[key]
        if en_val == zh_val and is_non_trivial_english_prose(en_val):
            identical.append((key, en_val))

    lines: list[str] = []
    lines.append(f"# Locale parity for HEAD")
    lines.append(f"# en keys: {len(en_flat)}")
    lines.append(f"# zh keys: {len(zh_flat)}")
    lines.append("")
    lines.append("[missing-keys]")
    if not en_only and not zh_only:
        lines.append("# (none)")
    for key in en_only:
        lines.append(f"en-only: {key}")
    for key in zh_only:
        lines.append(f"zh-only: {key}")
    lines.append("")
    lines.append("[cjk-in-en]")
    if not cjk_in_en:
        lines.append("# (none)")
    for key, value in cjk_in_en:
        snippet = value if len(value) <= 80 else value[:77] + "..."
        lines.append(f"{key}: {snippet}")
    lines.append("")
    lines.append("[identical-values]")
    if not identical:
        lines.append("# (none)")
    for key, value in identical:
        snippet = value if len(value) <= 80 else value[:77] + "..."
        lines.append(f"{key}: {snippet}")
    lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"  parity.txt written: missing={len(en_only) + len(zh_only)}, "
        f"cjk-in-en={len(cjk_in_en)}, identical-values={len(identical)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
