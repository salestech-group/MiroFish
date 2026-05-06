#!/usr/bin/env bash
# SessionStart hook — print branch + working-tree status to give Claude
# (and the developer) immediate context at the start of a session.
set -euo pipefail

# Run only inside a git repo
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    exit 0
fi

branch="$(git symbolic-ref --short HEAD 2>/dev/null || echo 'detached')"
upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo '')"

# Ahead / behind vs upstream
ahead_behind=""
if [ -n "$upstream" ]; then
    counts="$(git rev-list --left-right --count "${upstream}...HEAD" 2>/dev/null || echo '0	0')"
    behind="$(echo "$counts" | awk '{print $1}')"
    ahead="$(echo "$counts" | awk '{print $2}')"
    if [ "$ahead" != "0" ] || [ "$behind" != "0" ]; then
        ahead_behind=" (ahead $ahead, behind $behind vs $upstream)"
    fi
fi

# Working-tree status
dirty_count="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
if [ "$dirty_count" = "0" ]; then
    state="clean"
else
    state="$dirty_count uncommitted change(s)"
fi

echo "📍 Branch: ${branch}${ahead_behind} — ${state}"
