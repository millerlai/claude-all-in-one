#!/usr/bin/env python3
"""PostToolUse hook: re-run validate.py when a shipped component is edited.

CLAUDE.md asks for `python scripts/validate.py` before pushing — a rule that
holds only as long as someone remembers it. CI catches the miss, but not until
after the push. This closes the gap to the edit that caused it.

PostToolUse cannot block; the write already happened. A non-zero exit only puts
validate.py's failures in front of Claude while the context is still fresh.
"""
import json
import os
import subprocess
import sys

# Everything outside these two trees is either docs or this script's own
# scaffolding — not worth a full validate run on every keystroke.
WATCHED = ("plugins/cai/", ".claude-plugin/")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    path = (payload.get("tool_input") or {}).get("file_path", "")
    if not path:
        return 0

    try:
        edited = os.path.relpath(path, ROOT).replace(os.sep, "/")
    except ValueError:
        return 0  # another drive on Windows, so not a file in this repo
    if not edited.startswith(WATCHED):
        return 0

    # validate.py tests this hook, and testing it re-runs validate.py. The flag
    # tells that run to skip the hook block, so neither the test nor a real
    # edit pays for an unbounded chain of nested runs.
    done = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "validate.py")],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "CAI_VALIDATE_NESTED": "1"},
    )
    if done.returncode == 0:
        return 0

    failures = [line for line in done.stdout.splitlines() if line.startswith("FAIL")]
    sys.stderr.write(
        f"scripts/validate.py now fails after editing {edited}:\n"
        + "\n".join(failures or [done.stdout[-2000:]])
        # Plain ASCII: this lands on a Windows console whose codepage mangles
        # anything else before Claude ever sees it.
        + "\nFix this before moving on; CI runs the same script.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
