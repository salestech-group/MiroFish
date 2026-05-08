#!/usr/bin/env bash
# Orchestrate the i18n end-to-end verification audit.
#
# Reads working-tree state via git (no production-source modifications),
# captures classified output under audit/<commit-sha>/, and posts the
# verification report comment + follow-up issues via gh when available.
#
# Exit codes:
#   0 - audit succeeded and all GitHub side effects applied
#   1 - audit step failed (read-only producer aborted)
#   2 - audit succeeded but at least one GitHub side effect was deferred to PENDING
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

spec_root=".kiro/specs/i18n-e2e-english-verification"
scripts_dir="${spec_root}/audit/scripts"

sha="$(git rev-parse HEAD)"
sha_dir="${spec_root}/audit/${sha}"
mkdir -p "${sha_dir}"

printf 'Verification audit\n  repo: %s\n  sha:  %s\n  out:  %s\n\n' \
    "${repo_root}" "${sha}" "${sha_dir}"

ghs_exit=0

step() {
    local label="$1"
    shift
    printf '== %s ==\n' "${label}"
    "$@"
}

step "audit_cjk.sh"      bash       "${scripts_dir}/audit_cjk.sh"      "${sha_dir}"
step "check_parity.py"   python3    "${scripts_dir}/check_parity.py"   "${sha_dir}"
step "classify.py"       python3    "${scripts_dir}/classify.py"       "${sha_dir}"
step "render_report.py"  python3    "${scripts_dir}/render_report.py"  "${sha_dir}" "${sha}"

# GitHub side effects: failures here downgrade the run to exit 2 but
# do not abort the rest of the side effects.
set +e
step "post_comment.sh" bash "${scripts_dir}/post_comment.sh" "${sha_dir}"
[ $? -ne 0 ] && ghs_exit=2

step "file_followups.sh" bash "${scripts_dir}/file_followups.sh" "${sha_dir}"
[ $? -ne 0 ] && ghs_exit=2
set -e

printf '\n== summary ==\n'
printf 'sha-dir: %s\n' "${sha_dir}"
if [ -f "${sha_dir}/comment-url.txt" ]; then
    printf 'comment: %s\n' "$(cat "${sha_dir}/comment-url.txt")"
else
    printf 'comment: PENDING (see %s/PENDING-issue-10-comment.md)\n' "${sha_dir}"
fi
if [ -f "${sha_dir}/followup-urls.txt" ]; then
    printf 'follow-ups posted:\n'
    sed 's/^/  /' "${sha_dir}/followup-urls.txt"
fi
if compgen -G "${sha_dir}/PENDING-followups/[0-9]*-*.md" > /dev/null; then
    printf 'follow-ups PENDING:\n'
    for body in "${sha_dir}"/PENDING-followups/[0-9]*-*.md; do
        if [ -s "${body}" ]; then
            printf '  %s\n' "${body}"
        fi
    done
fi

exit "${ghs_exit}"
