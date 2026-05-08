#!/usr/bin/env python3
"""Classify each CJK match into a 4-class label and a category tag.

Inputs (read from <sha-dir>):
  cjk-grep.txt   - raw `git grep -nP` output, one match per line.
  parity.txt     - output of check_parity.py (used to harvest cjk-in-en gaps).

Output (written to <sha-dir>/classified.csv):
  CSV columns: file, line, match, class, category, pipeline_step

Classes are a closed set: deliberate / gap / non-applicable / review-needed.
Categories and pipeline-step tags are likewise closed sets - see classify_match.

Run from the repository root.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import Iterable, Tuple

CJK_RANGE = re.compile(r"[一-鿿]")
PROMPT_FILES = (
    "backend/app/services/ontology_generator.py",
    "backend/app/services/oasis_profile_generator.py",
    "backend/app/services/simulation_config_generator.py",
    "backend/app/services/report_agent.py",
    "backend/app/services/zep_graph_memory_updater.py",
)
LOG_HINTS = ("logger.", "log.", "print(", "build_logger.", "logging.")
BINARY_EXTS = (
    ".jpg", ".jpeg", ".png", ".gif", ".pdf",
    ".woff", ".woff2", ".ttf", ".eot", ".ico",
)


def classify_match(file: str, raw_line: str) -> Tuple[str, str, str]:
    """Return (class, category, pipeline_step) for one grep match line."""
    if any(file.lower().endswith(ext) for ext in BINARY_EXTS):
        return ("non-applicable", "binary-false-positive", "n/a")

    if file == "locales/en.json":
        return ("gap", "catalogue-parity", "UI")

    stripped = raw_line.lstrip()
    pipeline_step = pipeline_step_for(file)

    if file.endswith(".vue"):
        if re.search(r"\.match\s*\(\s*/", raw_line):
            return ("gap", "frontend-regex-parser", pipeline_step)
        if re.search(r"['\"`].*[一-鿿].*['\"`]", raw_line):
            return ("gap", "frontend-ui-string", pipeline_step)
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            return ("deliberate", "frontend-comment", pipeline_step)
        return ("review-needed", "frontend-other", pipeline_step)

    if file.endswith(".py"):
        if stripped.startswith("#"):
            return ("deliberate", "backend-comment", pipeline_step)
        if stripped.startswith('"""') or stripped.startswith("'''"):
            return ("deliberate", "backend-docstring", pipeline_step)
        if not re.search(r"['\"]", raw_line):
            # bare CJK on a non-string line: most likely an unterminated docstring
            # body. Treat as a docstring continuation.
            return ("deliberate", "backend-docstring", pipeline_step)
        if any(hint in raw_line for hint in LOG_HINTS):
            return ("gap", "backend-log", "Logs")
        if file in PROMPT_FILES:
            return ("gap", "backend-prompt-label", pipeline_step)
        return ("review-needed", "backend-string", pipeline_step)

    if file.endswith(".js") or file.endswith(".ts"):
        if stripped.startswith("//") or stripped.startswith("*"):
            return ("deliberate", "frontend-comment", pipeline_step)
        return ("review-needed", "frontend-other", pipeline_step)

    return ("review-needed", "uncategorised", pipeline_step)


def pipeline_step_for(file: str) -> str:
    """Map a path to one of the closed-set pipeline-step tags."""
    if "ontology_generator" in file or "graph_builder" in file or "graph.py" in file:
        return "Graph Build"
    if "oasis_profile_generator" in file or "Step2" in file:
        return "Env Setup"
    if "simulation_config_generator" in file or "simulation" in file or "Step3" in file:
        return "Simulation"
    if "report_agent" in file or "Step4" in file:
        return "Report"
    if "Step5" in file or "interaction" in file.lower() or "interview" in file.lower():
        return "Interaction"
    if "logger" in file or "retry" in file:
        return "Logs"
    if file.startswith("frontend/src/views/") or file.startswith("frontend/src/components/"):
        return "UI"
    return "n/a"


def parse_grep_line(line: str) -> Tuple[str, str, str]:
    """Split a `git grep -n` line into (file, line-number, match-text)."""
    parts = line.split(":", 2)
    if len(parts) < 3:
        return ("", "", line)
    return (parts[0], parts[1], parts[2])


def parity_to_rows(parity_path: Path) -> Iterable[Tuple[str, str, str, str, str, str]]:
    """Promote `[cjk-in-en]` block entries from parity.txt into classified rows."""
    if not parity_path.exists():
        return
    in_block = False
    for raw in parity_path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("["):
            in_block = raw.strip() == "[cjk-in-en]"
            continue
        if not in_block:
            continue
        if not raw or raw.startswith("#"):
            continue
        yield (
            "locales/en.json",
            "0",
            raw,
            "gap",
            "catalogue-parity",
            "UI",
        )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <sha-dir>", file=sys.stderr)
        return 64

    sha_dir = Path(argv[1])
    grep_path = sha_dir / "cjk-grep.txt"
    parity_path = sha_dir / "parity.txt"
    out_path = sha_dir / "classified.csv"

    if not grep_path.exists():
        print(f"missing input: {grep_path}", file=sys.stderr)
        return 1

    rows: list[Tuple[str, str, str, str, str, str]] = []
    grep_lines = grep_path.read_text(encoding="utf-8").splitlines()
    for raw_line in grep_lines:
        if not raw_line:
            continue
        file, lineno, match = parse_grep_line(raw_line)
        if not file:
            continue
        cls, category, step = classify_match(file, match)
        rows.append((file, lineno, match.strip(), cls, category, step))

    rows.extend(parity_to_rows(parity_path))

    raw_count = sum(1 for line in grep_lines if line.strip())
    grep_rows = [r for r in rows if r[0] != "locales/en.json" or r[1] != "0"]
    if len(grep_rows) != raw_count:
        print(
            f"row-count drift: input={raw_count}, classified={len(grep_rows)}",
            file=sys.stderr,
        )
        return 1

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["file", "line", "match", "class", "category", "pipeline_step"])
        writer.writerows(rows)

    summary: dict[str, int] = {}
    for row in rows:
        summary[row[3]] = summary.get(row[3], 0) + 1
    summary_str = ", ".join(f"{cls}={n}" for cls, n in sorted(summary.items()))
    print(f"  classified.csv: {len(rows)} rows ({summary_str})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
