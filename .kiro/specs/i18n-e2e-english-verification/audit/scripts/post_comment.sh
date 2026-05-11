#!/usr/bin/env bash
# Post comment-body.md as a comment on issue #10.
#
# Falls back to writing PENDING-issue-10-comment.md when gh is unavailable
# or the post fails - exits non-zero in that case so the orchestrator can
# downgrade its overall status.
set -euo pipefail

if [ "$#" -ne 1 ]; then
    printf 'usage: %s <sha-dir>\n' "$0" >&2
    exit 64
fi

sha_dir="$1"
body="${sha_dir}/comment-body.md"
if [ ! -f "${body}" ]; then
    printf 'missing comment body: %s\n' "${body}" >&2
    exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
    printf '  gh not available; writing PENDING-issue-10-comment.md\n'
    cp "${body}" "${sha_dir}/PENDING-issue-10-comment.md"
    exit 2
fi

if ! gh auth status >/dev/null 2>&1; then
    printf '  gh not authenticated; writing PENDING-issue-10-comment.md\n'
    cp "${body}" "${sha_dir}/PENDING-issue-10-comment.md"
    exit 2
fi

if url="$(gh issue comment 10 --repo salestech-group/MiroFish --body-file "${body}" 2>&1)"; then
    printf '%s\n' "${url}" > "${sha_dir}/comment-url.txt"
    printf '  posted: %s\n' "${url}"
    rm -f "${sha_dir}/PENDING-issue-10-comment.md"
    exit 0
fi

printf '  gh post failed; writing PENDING-issue-10-comment.md\n'
cp "${body}" "${sha_dir}/PENDING-issue-10-comment.md"
exit 2
