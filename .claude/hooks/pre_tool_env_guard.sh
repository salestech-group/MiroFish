#!/usr/bin/env bash
# PreToolUse hook — extra explicit refusal for any attempt to touch
# .env / secrets paths, on top of the permissions.deny rules in
# .claude/settings.json. Provides a clearer, friendlier message and a
# log line.
#
# Receives the tool-call payload as JSON on stdin:
#   { "tool_name": "Read|Write|Edit|Bash|...",
#     "tool_input": { "file_path": "...", "command": "..." } }
#
# Exit codes:
#   0 → allow (silent)
#   2 → block; stderr is shown to Claude so it knows why

set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"

matches="$(python3 "$HOOK_DIR/_env_guard.py" 2>/dev/null || true)"

if [ -n "$matches" ]; then
    echo "🚫 Blocked: attempt to access protected path (env / secrets)." >&2
    echo "   Detail: $matches" >&2
    echo "   Reason: .env files and secrets/ are off-limits to Claude in this project." >&2
    echo "   To grant a one-off exception, ask the developer to read the file and paste the relevant value." >&2
    exit 2
fi

exit 0
