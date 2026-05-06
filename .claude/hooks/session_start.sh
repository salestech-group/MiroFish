#!/usr/bin/env bash
# SessionStart hook — print branch + working-tree status + open Kiro
# specs / cached tickets so context is visible immediately at the start
# of a session.
set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# --- Git branch + state -----------------------------------------------------
if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    branch="$(git -C "$PROJECT_DIR" symbolic-ref --short HEAD 2>/dev/null || echo 'detached')"
    upstream="$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo '')"

    ahead_behind=""
    if [ -n "$upstream" ]; then
        counts="$(git -C "$PROJECT_DIR" rev-list --left-right --count "${upstream}...HEAD" 2>/dev/null || echo '0	0')"
        behind="$(echo "$counts" | awk '{print $1}')"
        ahead="$(echo "$counts" | awk '{print $2}')"
        if [ "$ahead" != "0" ] || [ "$behind" != "0" ]; then
            ahead_behind=" (ahead $ahead, behind $behind vs $upstream)"
        fi
    fi

    dirty_count="$(git -C "$PROJECT_DIR" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$dirty_count" = "0" ]; then
        state="clean"
    else
        state="$dirty_count uncommitted change(s)"
    fi

    echo "📍 Branch: ${branch}${ahead_behind} — ${state}"
fi

# --- Active tickets ---------------------------------------------------------
shopt -s nullglob 2>/dev/null || true
tickets=("$PROJECT_DIR"/.ticket/*.md)
ticket_list=()
for f in "${tickets[@]}"; do
    base="$(basename "$f")"
    case "$base" in
        repo.md|.gitkeep) continue ;;
        *) ticket_list+=("${base%.md}") ;;
    esac
done
if [ "${#ticket_list[@]}" -gt 0 ]; then
    echo "🎫 Active tickets: ${ticket_list[*]}  (use /ticket <n> to add more)"
fi

# --- Active Kiro specs ------------------------------------------------------
if [ -d "$PROJECT_DIR/.kiro/specs" ]; then
    spec_dirs=("$PROJECT_DIR"/.kiro/specs/*/)
    spec_list=()
    for d in "${spec_dirs[@]}"; do
        [ -d "$d" ] || continue
        name="$(basename "$d")"
        # Try to read phase from spec.json if jq/python is available
        phase=""
        if [ -f "$d/spec.json" ] && command -v python3 >/dev/null 2>&1; then
            phase="$(python3 -c "
import json, sys
try:
    with open(sys.argv[1]) as f: d = json.load(f)
    print(d.get('phase') or d.get('status') or '', end='')
except Exception:
    pass
" "$d/spec.json" 2>/dev/null || true)"
        fi
        if [ -n "$phase" ]; then
            spec_list+=("$name [$phase]")
        else
            spec_list+=("$name")
        fi
    done
    if [ "${#spec_list[@]}" -gt 0 ]; then
        echo "📘 Open specs: $(printf '%s, ' "${spec_list[@]}" | sed 's/, $//')  (use /plan or /kiro:spec-status)"
    fi
fi

exit 0
