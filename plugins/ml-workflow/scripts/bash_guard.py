#!/usr/bin/env python3
"""PreToolUse guard: block destructive git/shell commands unless the user
explicitly confirmed them. Cross-platform (pure stdlib, works on Windows).

Exit codes: 0 = allow, 2 = block (stderr is fed back to Claude).
"""
import json
import re
import sys

BLOCKED = [
    # (pattern, reason)
    (r"git\s+push\b[^\n]*?(\s--force(?!-with-lease)|\s-f\b)", "force push (use --force-with-lease if truly needed)"),
    (r"git\s+reset\s+[^\n]*--hard", "hard reset discards work"),
    (r"git\s+clean\s+-[a-z]*f", "git clean -f deletes untracked files"),
    (r"git\s+[^\n]*--no-verify", "skipping hooks"),
    (r"rm\s+-[a-z]*r[a-z]*f|rm\s+-[a-z]*f[a-z]*r", "recursive force delete"),
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # malformed input: fail open, don't break the session

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        return 0

    for pattern, reason in BLOCKED:
        if re.search(pattern, command):
            sys.stderr.write(
                f"bash_guard blocked this command: {reason}.\n"
                f"Command: {command}\n"
                "If the user explicitly requested this, tell them the guard "
                "blocked it and ask them to run it manually or temporarily "
                "disable the ml-workflow plugin hook.\n"
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
