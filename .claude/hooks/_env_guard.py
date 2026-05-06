"""Helper for pre_tool_env_guard.sh — reads tool-call JSON from stdin and
prints a "match" line if the call would touch .env or secrets/. Empty
output means no match (allow)."""
import json
import re
import sys


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    ti = data.get("tool_input", {}) or {}
    fp = (
        ti.get("file_path", "")
        or ti.get("path", "")
        or ti.get("notebook_path", "")
    )
    cmd = ti.get("command", "") or ""

    path_pattern = re.compile(r"(^|/)(\.env(\.|$)|secrets/)")
    cmd_pattern = re.compile(
        r"(^|[ \t;|&])\s*(cat|less|more|head|tail|cp|mv|rm)\s+"
        r"[^|;&]*(?:\.env|secrets/)"
    )

    if fp and path_pattern.search(fp):
        print(f"path:{fp}")
        return
    if cmd and cmd_pattern.search(cmd):
        print(f"command:{cmd[:120]}")
        return


if __name__ == "__main__":
    main()
