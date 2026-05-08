#!/usr/bin/env bash
# Iterate <sha-dir>/PENDING-followups/*.md and file each non-empty body
# as a GitHub issue. The first markdown heading line (`# title`) becomes
# the issue title; any `<!-- labels: a,b,c -->` line at the bottom of the
# body becomes the --label argument.
#
# On per-category failure the body is left in place and the script exits
# non-zero at the end (after attempting all categories).
set -uo pipefail

if [ "$#" -ne 1 ]; then
    printf 'usage: %s <sha-dir>\n' "$0" >&2
    exit 64
fi

sha_dir="$1"
pending_dir="${sha_dir}/PENDING-followups"
urls_path="${sha_dir}/followup-urls.txt"

if [ ! -d "${pending_dir}" ]; then
    printf 'missing PENDING-followups dir: %s\n' "${pending_dir}" >&2
    exit 1
fi

# Append-only URL log so retries on the same sha-dir preserve previous filings.
touch "${urls_path}"

if ! command -v gh >/dev/null 2>&1; then
    printf '  gh not available; leaving all bodies in PENDING-followups/\n'
    exit 2
fi

if ! gh auth status >/dev/null 2>&1; then
    printf '  gh not authenticated; leaving all bodies in PENDING-followups/\n'
    exit 2
fi

partial=0

for body in "${pending_dir}"/[0-9]*-*.md; do
    [ -f "${body}" ] || continue
    if [ ! -s "${body}" ]; then
        # Empty placeholder - the corresponding category had zero gaps in this run.
        continue
    fi

    title="$(awk 'NR==1 && /^# /{sub(/^# /, ""); print; exit}' "${body}")"
    if [ -z "${title}" ]; then
        title="i18n: follow-up from issue #10 verification ($(basename "${body}" .md))"
    fi

    label_line="$(grep -oE '<!-- labels: [^>]+-->' "${body}" | head -1 || true)"
    labels="$(printf '%s' "${label_line}" | sed -E 's/<!-- labels: //; s/ *-->//' || true)"
    label_args=()
    if [ -n "${labels}" ]; then
        IFS=',' read -ra parts <<< "${labels}"
        for label in "${parts[@]}"; do
            label_args+=( --label "$(echo "${label}" | tr -d ' ')" )
        done
    fi

    printf '  filing: %s\n' "${title}"
    if url="$(gh issue create --repo salestech-group/MiroFish \
        --title "${title}" \
        --body-file "${body}" \
        "${label_args[@]}" 2>&1)"; then
        printf '%s\n' "${url}" >> "${urls_path}"
        printf '    -> %s\n' "${url}"
        rm -f "${body}"
    else
        printf '    !! gh issue create failed: %s\n' "${url}" >&2
        partial=1
    fi
done

if [ "${partial}" -eq 1 ]; then
    exit 2
fi
exit 0
