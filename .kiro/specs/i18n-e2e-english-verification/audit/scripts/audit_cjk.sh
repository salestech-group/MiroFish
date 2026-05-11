#!/usr/bin/env bash
# Run the canonical CJK grep with PCRE, then write the raw output and a
# bucketed summary partitioned by top-level path. Excludes binary file
# matches (e.g. .jpeg) since ripgrep / git grep can otherwise score them.
set -euo pipefail

if [ "$#" -ne 1 ]; then
    printf 'usage: %s <sha-dir>\n' "$0" >&2
    exit 64
fi

sha_dir="$1"
mkdir -p "${sha_dir}"

raw="${sha_dir}/cjk-grep.txt"
bucketed="${sha_dir}/cjk-grep-bucketed.txt"

# Canonical PCRE grep against the three top-level paths owned by this audit.
# git grep -P uses PCRE2 - ranges like \x{4e00}-\x{9fff} are valid here.
# `-I` (--no-binary) excludes binary-file matches outright so the audit
# reports only text content.
git grep -nIP '[\x{4e00}-\x{9fff}]' \
    -- backend/app frontend/src locales/en.json \
    > "${raw}" \
    || true

awk_script='
function bucket(path) {
    if (path ~ /^backend\/app\//)    return "backend/app"
    if (path ~ /^frontend\/src\//)   return "frontend/src"
    if (path ~ /^locales\/en\.json/) return "locales/en.json"
    return "other"
}
{
    split($0, parts, ":")
    path = parts[1]
    b = bucket(path)
    counts[b]++
    lines[b] = (b in lines ? lines[b] "\n" : "") $0
}
END {
    order[1] = "backend/app"
    order[2] = "frontend/src"
    order[3] = "locales/en.json"
    order[4] = "other"
    for (i = 1; i <= 4; i++) {
        b = order[i]
        c = (b in counts ? counts[b] : 0)
        printf("[%s] (%d lines)\n", b, c)
        if (c > 0) {
            print lines[b]
        }
        print ""
    }
}
'

awk "${awk_script}" "${raw}" > "${bucketed}"

raw_lines=$(wc -l < "${raw}" | tr -d ' ')
printf '  cjk-grep.txt:          %s lines\n' "${raw_lines}"
printf '  cjk-grep-bucketed.txt: written\n'
