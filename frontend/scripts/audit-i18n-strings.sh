#!/usr/bin/env bash
# audit-i18n-strings.sh — verifier for issue #23 / spec i18n-frontend-ui-strings.
#
# Greps the five files in scope for hard-coded user-visible CJK literals and
# checks that locales/en.json and locales/zh.json have parity at every path.
#
# Annotation rules respected by this script:
#   - lines that are pure // line comments are skipped
#   - lines that contain `// i18n-allow:<reason>` are skipped (deliberate token)
#   - lines that contain `console.log/info/warn/error/debug(` are skipped
#     (developer logs, not user-visible UI; out of scope)
#   - lines between `// i18n-allow-block:<reason>` and `// i18n-allow-block-end`
#     are skipped (used for the REPORT_MARKERS and STAGE_PHASE_MAP blocks
#     that intentionally embed Chinese tokens for backend compatibility)
#
# Exits 0 on success; non-zero with a human-readable list of issues otherwise.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

FILES=(
    "frontend/src/views/Process.vue"
    "frontend/src/components/Step2EnvSetup.vue"
    "frontend/src/components/Step3Simulation.vue"
    "frontend/src/components/Step4Report.vue"
    "frontend/src/components/Step5Interaction.vue"
)

CJK_RE='[\x{4e00}-\x{9fff}\x{3000}-\x{303f}\x{ff00}-\x{ffef}]'

cd "$REPO_ROOT"

fail=0

for f in "${FILES[@]}"; do
    if [[ ! -f "$f" ]]; then
        echo "audit: missing file $f" >&2
        fail=1
        continue
    fi
    # awk filters out comments and dev-only constructs, then strips inline
    # trailing comments before passing the surviving line to ripgrep. The
    # remaining hits are user-visible CJK literals.
    hits="$(awk '
        BEGIN { in_allow = 0; in_html = 0; in_css = 0 }

        # Spec-controlled allowlist regions (REPORT_MARKERS, STAGE_PHASE_MAP).
        /\/\/ i18n-allow-block:/  { in_allow = 1; next }
        /\/\/ i18n-allow-block-end/ { in_allow = 0; next }
        in_allow { next }

        # Per-line allow annotation.
        /\/\/ i18n-allow:/ { next }

        # Vue template HTML comments (<!-- ... -->), single- or multi-line.
        {
            line = $0
            # Strip pairs of <!-- ... --> on the same line.
            while (match(line, /<!--.*-->/)) {
                line = substr(line, 1, RSTART - 1) substr(line, RSTART + RLENGTH)
            }
            # Detect entering/leaving an HTML comment block.
            if (in_html) {
                if (match(line, /-->/)) {
                    line = substr(line, RSTART + RLENGTH)
                    in_html = 0
                } else {
                    next
                }
            }
            if (match(line, /<!--/)) {
                line = substr(line, 1, RSTART - 1)
                in_html = 1
            }
        }

        # CSS / block JS comments (/* ... */).
        {
            while (match(line, /\/\*.*\*\//)) {
                line = substr(line, 1, RSTART - 1) substr(line, RSTART + RLENGTH)
            }
            if (in_css) {
                if (match(line, /\*\//)) {
                    line = substr(line, RSTART + RLENGTH)
                    in_css = 0
                } else {
                    next
                }
            }
            if (match(line, /\/\*/)) {
                line = substr(line, 1, RSTART - 1)
                in_css = 1
            }
        }

        # Strip inline trailing JS line comments (// ...).
        # Naive: if " //" appears, drop everything from there onwards.
        # Vue template attributes do not legitimately contain "//" outside URLs;
        # URLs in string literals stay intact because the regex requires a
        # leading whitespace before the //.
        {
            sub(/[[:space:]]\/\/.*$/, "", line)
        }

        # Whole-line single-line comments and block-comment continuations.
        line ~ /^[[:space:]]*\/\// { next }
        line ~ /^[[:space:]]*\*/  { next }

        # Developer-only console emissions: not user-visible.
        line ~ /console\.(log|info|warn|error|debug)\(/ { next }

        line { print NR ":" line }
    ' "$f" | grep -P "$CJK_RE" || true)"
    if [[ -n "$hits" ]]; then
        echo "$f:" >&2
        echo "$hits" | sed "s|^|  $f:|" >&2
        fail=1
    fi
done

# Locale parity check: every path that resolves to a scalar in en.json must also
# exist in zh.json, and vice versa.
parity_diff="$(python3 - <<'PY'
import json, sys

def paths(d, prefix=""):
    out = []
    if isinstance(d, dict):
        for k, v in d.items():
            out.extend(paths(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.extend(paths(v, f"{prefix}[{i}]"))
    else:
        out.append(prefix)
    return out

with open("locales/en.json", encoding="utf-8") as f:
    en = json.load(f)
with open("locales/zh.json", encoding="utf-8") as f:
    zh = json.load(f)

en_paths = set(paths(en))
zh_paths = set(paths(zh))

only_en = sorted(en_paths - zh_paths)
only_zh = sorted(zh_paths - en_paths)

if only_en:
    print("missing in zh.json:")
    for p in only_en:
        print(f"  {p}")
if only_zh:
    print("missing in en.json:")
    for p in only_zh:
        print(f"  {p}")

sys.exit(1 if (only_en or only_zh) else 0)
PY
)" || parity_status=$?

if [[ -n "${parity_diff:-}" ]]; then
    echo "$parity_diff" >&2
    fail=1
fi

# Sentinel: en.json must contain no CJK characters in its scalar values
# (issue #20 / spec i18n-backfill-zh-json regression guard).
en_cjk="$(grep -nP "$CJK_RE" locales/en.json || true)"
if [[ -n "$en_cjk" ]]; then
    echo "locales/en.json contains CJK characters (regression vs #20):" >&2
    echo "$en_cjk" >&2
    fail=1
fi

exit "$fail"
