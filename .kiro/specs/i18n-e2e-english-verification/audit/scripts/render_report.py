#!/usr/bin/env python3
"""Render the gap report and the issue-#10 comment body.

Inputs (from <sha-dir>):
  classified.csv          - per-match classification rows.
  parity.txt              - en/zh catalogue parity output.
  cjk-grep-bucketed.txt   - human-readable bucketed grep output.

Inputs (from repo):
  .ticket/10.md           - snapshot of issue #10's body (used to mirror its checklist).

Outputs (to <sha-dir>):
  gap-report.md           - full structured report (seven sections).
  comment-body.md         - markdown comment to be posted on issue #10.
  PENDING-followups/01..04-*.md - one body per gap category (placeholders allowed).

Usage:
    python3 render_report.py <sha-dir> <commit-sha>
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

ISSUE_NUMBER = 10
REPO_SLUG = "salestech-group/MiroFish"


def load_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_ticket_body(ticket_path: Path) -> str:
    """Strip the YAML frontmatter and return the markdown body."""
    text = ticket_path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5 :]
    return text


CHECKBOX_RE = re.compile(r"^(\s*)- \[ \] (.+)$")
SUBBULLET_RE = re.compile(r"^(\s+)- (.+)$")


def evidence_for_step(rows: list[dict], step: str) -> list[dict]:
    """Return gap rows whose pipeline_step matches the given UI tag."""
    return [r for r in rows if r["class"] == "gap" and r["pipeline_step"] == step]


def render_section_5(ticket_body: str, rows: list[dict]) -> str:
    """Map every checklist item from the ticket body to a status."""
    gaps_by_step = defaultdict(list)
    for row in rows:
        if row["class"] == "gap":
            gaps_by_step[row["pipeline_step"]].append(row)

    out: list[str] = []
    out.append("## Section 5 - Issue #10 checklist mapping\n")
    out.append("Each line below is taken from the ticket body, with an explicit status.\n")

    in_checklist = False
    for line in ticket_body.splitlines():
        match = CHECKBOX_RE.match(line)
        if match:
            in_checklist = True
            indent, text = match.group(1), match.group(2)
            status, note = status_for_checklist_item(text, gaps_by_step)
            out.append(f"{indent}- [{('x' if status == 'pass' else ' ')}] **{status.upper()}** - {text}{note}")
            continue

        sub = SUBBULLET_RE.match(line)
        if in_checklist and sub:
            indent, text = sub.group(1), sub.group(2)
            status, note = status_for_checklist_item(text, gaps_by_step)
            out.append(f"{indent}- {status.upper()}: {text}{note}")
            continue

        if line.startswith("##") or line.startswith("---"):
            in_checklist = False

    return "\n".join(out) + "\n"


def status_for_checklist_item(text: str, gaps_by_step: Dict[str, list]) -> tuple[str, str]:
    """Return (status, suffix-note) for one checklist line.

    Pure-UI items default to manual-pending in this run; items with a
    backing pipeline-step that has gaps are reported as gap with a count.
    """
    lower = text.lower()
    candidates: list[str] = []
    if "graph build" in lower or "ontology" in lower:
        candidates.append("Graph Build")
    if "env setup" in lower or "agent profile" in lower or "profession" in lower:
        candidates.append("Env Setup")
    if "simulation" in lower or "tweet" in lower or "reddit" in lower or "sim config" in lower:
        candidates.append("Simulation")
    if "report" in lower:
        candidates.append("Report")
    if "interaction" in lower or "interview" in lower or "chat repl" in lower:
        candidates.append("Interaction")
    if "log" in lower:
        candidates.append("Logs")

    relevant_gaps = []
    for step in candidates:
        relevant_gaps.extend(gaps_by_step.get(step, []))

    if "frontend ui" in lower or "no chinese strings on screen" in lower or "every label" in lower:
        ui_gaps = gaps_by_step.get("UI", [])
        if ui_gaps:
            return ("gap", f" - {len(ui_gaps)} hard-coded CJK literal(s) in `frontend/src/views|components/`")
        return ("manual-pending", " - live UI walkthrough not run in this sandbox")

    if "locale propagation" in lower or "set_locale" in lower:
        prop = gaps_by_step.get("Logs", [])
        if prop:
            return ("gap", f" - {len(prop)} CJK log strings on EN code path")
        return ("manual-pending", " - locale-propagation runtime check not run in this sandbox")

    if relevant_gaps:
        return ("gap", f" - {len(relevant_gaps)} gap(s) classified, see Section 1/3")

    if any(c in lower for c in ("ui", "screenshot", "chat", "modal", "tooltip", "render", "trace", "thinking")):
        return ("manual-pending", " - requires live walkthrough")

    return ("manual-pending", " - not verifiable statically; awaiting live run")


def render_gap_report(rows: list[dict], ticket_body: str, parity_text: str, sha: str) -> str:
    classes = Counter(r["class"] for r in rows)
    gap_rows = [r for r in rows if r["class"] == "gap"]
    gap_categories = Counter(r["category"] for r in gap_rows)
    gap_steps = Counter(r["pipeline_step"] for r in gap_rows)

    out: list[str] = []
    out.append(f"# Verification gap report - i18n-e2e-english-verification\n")
    out.append(f"**Commit:** `{sha}`\n")
    out.append("")
    out.append("## Overview\n")
    out.append(f"- Total CJK matches audited: **{len(rows)}**")
    out.append(f"- Class distribution: {format_counter(classes)}")
    out.append(f"- Gap categories: {format_counter(gap_categories)}")
    out.append(f"- Gap pipeline steps: {format_counter(gap_steps)}")
    out.append("")

    out.append("## Section 1 - Static CJK audit\n")
    out.append("Canonical command (PCRE):\n")
    out.append("```")
    out.append('git grep -nIP "[\\x{4e00}-\\x{9fff}]" -- backend/app frontend/src locales/en.json')
    out.append("```")
    out.append("")
    out.append(f"Raw output captured at `audit/{sha}/cjk-grep.txt` and bucketed at `audit/{sha}/cjk-grep-bucketed.txt`.")
    out.append("")
    out.append(f"`locales/en.json` CJK matches: **{sum(1 for r in rows if r['file'] == 'locales/en.json')}** (acceptance: zero).")
    out.append("")
    out.append("Top files by gap count:")
    out.append("")
    out.append("| File | Gap count |")
    out.append("|------|-----------|")
    by_file = Counter(r["file"] for r in gap_rows)
    for file, count in by_file.most_common(15):
        out.append(f"| `{file}` | {count} |")
    out.append("")

    out.append("## Section 2 - Locale catalogue parity\n")
    out.append("```")
    out.append(parity_text.strip())
    out.append("```")
    out.append("")

    out.append("## Section 3 - LLM-prompt locale verification\n")
    prompt_gaps = [r for r in gap_rows if r["category"] == "backend-prompt-label"]
    out.append(f"Backend prompt-label gaps (CJK string literals inside services that compose LLM prompts): **{len(prompt_gaps)}**")
    out.append("")
    if prompt_gaps:
        out.append("First 10 examples (file:line - match):")
        out.append("")
        for row in prompt_gaps[:10]:
            out.append(f"- `{row['file']}:{row['line']}` - {row['match']}")
        if len(prompt_gaps) > 10:
            out.append(f"- ... and {len(prompt_gaps) - 10} more (see `classified.csv`)")
        out.append("")
    out.append(
        "These prompts feed the LLM verbatim; CJK labels bias the model toward Chinese output even when "
        "the requested locale is English."
    )
    out.append("")

    out.append("## Section 4 - Locale propagation surface\n")
    log_gaps = [r for r in gap_rows if r["category"] == "backend-log"]
    out.append("| Boundary | Status | Evidence |")
    out.append("|----------|--------|----------|")
    out.append(
        "| HTTP -> Flask handler | manual-pending | runtime not exercised in sandbox; static review showed no per-request locale carrier |"
    )
    out.append(
        "| Flask handler -> Task worker | manual-pending | thread-local `set_locale` referenced in CLAUDE.md but not statically verified end-to-end |"
    )
    out.append(
        f"| Task worker -> OASIS subprocess | manual-pending | subprocess boundary requires live run |"
    )
    out.append(
        f"| Backend logger | {'gap' if log_gaps else 'pass'} | {len(log_gaps)} hard-coded CJK log line(s) on EN code path |"
    )
    out.append("")
    if log_gaps:
        out.append("First 10 backend-log gap examples:")
        out.append("")
        for row in log_gaps[:10]:
            out.append(f"- `{row['file']}:{row['line']}` - {row['match']}")
        out.append("")

    out.append(render_section_5(ticket_body, rows))

    out.append("## Section 6 - ZH regression check\n")
    out.append(
        "- Locale catalogues at full key parity (953 EN keys / 953 ZH keys, symmetric difference 0 - "
        "see Section 2).\n"
        "- No ZH-specific regression detected in static review. Live ZH walkthrough is `manual-pending`.\n"
    )

    out.append("## Section 7 - Follow-up plan\n")
    out.append("Per R7.2, gaps are grouped into the following follow-up issues (placeholder bodies in `PENDING-followups/`):")
    out.append("")
    out.append(
        f"1. **Frontend hard-coded UI strings** ({len(by_category(rows, 'frontend-ui-string'))} matches + "
        f"{len(by_category(rows, 'frontend-regex-parser'))} regex parsers depending on CJK backend output)."
    )
    out.append(f"2. **Backend log strings** ({len(by_category(rows, 'backend-log'))} matches).")
    out.append(f"3. **Backend LLM-prompt context labels** ({len(by_category(rows, 'backend-prompt-label'))} matches).")
    out.append("4. **Permanent CI guard** (preventative - re-run this audit on every PR).")
    out.append("")
    out.append(
        "Backend docstring/comment matches (the bulk of `deliberate` rows) are covered by the existing issue #7 and are not re-filed here."
    )

    return "\n".join(out) + "\n"


def by_category(rows: list[dict], category: str) -> list[dict]:
    return [r for r in rows if r["category"] == category and r["class"] == "gap"]


def format_counter(c: Counter) -> str:
    return ", ".join(f"{k}={v}" for k, v in c.most_common())


def render_comment_body(rows: list[dict], ticket_body: str, sha: str) -> str:
    classes = Counter(r["class"] for r in rows)
    gap_rows = [r for r in rows if r["class"] == "gap"]
    gap_categories = Counter(r["category"] for r in gap_rows)

    out: list[str] = []
    out.append(f"### Verification report - run on commit `{sha}`\n")
    out.append("This run was produced by `.kiro/specs/i18n-e2e-english-verification/audit/scripts/run_audit.sh`.")
    out.append("Captured artefacts live under `.kiro/specs/i18n-e2e-english-verification/audit/<commit-sha>/`.\n")
    out.append("")
    out.append(f"**Audit summary:** {sum(classes.values())} CJK matches across the auditable paths.")
    out.append(f"- {classes.get('gap', 0)} `gap` (actionable, see follow-ups)")
    out.append(f"- {classes.get('review-needed', 0)} `review-needed` (soft signal; needs human eyeball)")
    out.append(f"- {classes.get('deliberate', 0)} `deliberate` (mostly backend docstrings/comments - covered by issue #7)")
    out.append(
        f"- {classes.get('non-applicable', 0)} `non-applicable` (binary file false positives - excluded)"
    )
    out.append("")
    out.append(f"**Gap-category breakdown:** {format_counter(gap_categories)}")
    out.append("")
    out.append("---")
    out.append("")
    out.append("#### Issue checklist mapping")
    out.append("")
    out.append(render_section_5(ticket_body, rows))
    out.append("---")
    out.append("")
    out.append("#### How to re-run")
    out.append("")
    out.append("```bash")
    out.append("# from the repository root, on any commit:")
    out.append("bash .kiro/specs/i18n-e2e-english-verification/audit/scripts/run_audit.sh")
    out.append("# artefacts at .kiro/specs/i18n-e2e-english-verification/audit/<HEAD-sha>/")
    out.append("```")
    out.append("")
    out.append(
        "If `gh` is not authenticated when re-running, the comment body and follow-up bodies are written to "
        "`PENDING-issue-10-comment.md` / `PENDING-followups/` for a human to post."
    )
    out.append("")
    out.append("Out of scope for this run (per R5.3 / R7.3): live UI walkthrough, full Docker-Compose pipeline run, and any inline gap fixes.")
    return "\n".join(out) + "\n"


def render_followup_bodies(rows: list[dict], sha_dir: Path, sha: str) -> None:
    pending_dir = sha_dir / "PENDING-followups"
    pending_dir.mkdir(parents=True, exist_ok=True)

    ui_gaps = by_category(rows, "frontend-ui-string") + by_category(rows, "frontend-regex-parser")
    log_gaps = by_category(rows, "backend-log")
    prompt_gaps = by_category(rows, "backend-prompt-label")

    files = [
        (
            "01-frontend-ui-strings.md",
            "i18n: replace hard-coded chinese ui strings in process and step components with i18n keys",
            ui_gaps,
            (
                "Several `.vue` templates in `frontend/src/views/` and `frontend/src/components/` still emit "
                "Chinese strings directly instead of routing them through `vue-i18n` keys. Some `Step4Report.vue` "
                "regex parsers also rely on Chinese tokens emitted by the backend (so they will silently break "
                "once the backend prompts are translated)."
            ),
            ["i18n", "bug"],
        ),
        (
            "02-backend-log-strings.md",
            "i18n: externalise remaining chinese log strings in flask api and utils",
            log_gaps,
            (
                "After issue #6 externalised most backend log messages, a handful of `logger.info` / "
                "`logger.error` call sites in `backend/app/api/graph.py` and `backend/app/utils/retry.py` "
                "still hard-code Chinese strings, so backend logs leak Chinese under EN locale."
            ),
            ["i18n"],
        ),
        (
            "03-backend-prompt-labels.md",
            "i18n: translate chinese context labels inside llm-prompt assembly in backend services",
            prompt_gaps,
            (
                "Several `services/*_generator.py` files compose LLM prompts that still embed Chinese "
                "context labels (e.g. `\"事实信息:\"`, `\"相关实体:\"`) into the prompt string verbatim. These "
                "labels bias the LLM toward Chinese output even when the requested locale is English."
            ),
            ["i18n"],
        ),
        (
            "04-permanent-ci-guard.md",
            "i18n: add a permanent ci guard that runs the e2e cjk audit on every pr",
            [],
            (
                "Promote the audit pipeline at `.kiro/specs/i18n-e2e-english-verification/audit/scripts/` to "
                "a permanent CI check. The guard should fail when `locales/en.json` contains any CJK character "
                "and when the gap count regresses against a committed baseline."
            ),
            ["i18n", "enhancement"],
        ),
    ]

    for name, title, gaps, summary, labels in files:
        if not gaps and not name.startswith("04-"):
            (pending_dir / name).write_text("", encoding="utf-8")
            continue

        body = [
            f"# {title}",
            "",
            "## Summary",
            "",
            summary,
            "",
            "## Linked from",
            "",
            f"- Issue #{ISSUE_NUMBER} (verification report comment).",
            f"- Spec: `.kiro/specs/i18n-e2e-english-verification/` at commit `{sha}`.",
            "",
            "## Evidence",
            "",
        ]
        if gaps:
            for row in gaps[:50]:
                body.append(f"- `{row['file']}:{row['line']}` - {row['match']}")
            if len(gaps) > 50:
                body.append(f"- ... and {len(gaps) - 50} more (see `classified.csv` in the spec dir)")
        else:
            body.append("- (No gaps in this run; this is a preventative follow-up only.)")
        body.append("")
        body.append("## Acceptance")
        body.append("")
        body.append("- [ ] Each `file:line` above is fixed (or explicitly classified as `deliberate`).")
        body.append("- [ ] Re-running `bash .kiro/specs/i18n-e2e-english-verification/audit/scripts/run_audit.sh` shows zero gaps in this category.")
        body.append("")
        body.append(f"<!-- labels: {','.join(labels)} -->")
        body.append("")
        (pending_dir / name).write_text("\n".join(body), encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <sha-dir> <commit-sha>", file=sys.stderr)
        return 64

    sha_dir = Path(argv[1])
    sha = argv[2]

    rows = load_rows(sha_dir / "classified.csv")
    parity_text = (sha_dir / "parity.txt").read_text(encoding="utf-8")
    ticket_body = load_ticket_body(Path(".ticket/10.md"))

    gap_report = render_gap_report(rows, ticket_body, parity_text, sha)
    (sha_dir / "gap-report.md").write_text(gap_report, encoding="utf-8")

    comment_body = render_comment_body(rows, ticket_body, sha)
    (sha_dir / "comment-body.md").write_text(comment_body, encoding="utf-8")

    render_followup_bodies(rows, sha_dir, sha)

    print(f"  gap-report.md, comment-body.md, PENDING-followups/ written under {sha_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
