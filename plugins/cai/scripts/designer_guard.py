#!/usr/bin/env python3
"""Enforce the designer's probe/renderer shell boundary before execution.

Agent tools lists select tools; Bash(...) is not a command sandbox (#181).
This hook refuses shell composition and arbitrary interpreter programs.
"""
import json
from pathlib import Path
import re
import shlex
import sys


def allowed(command, cwd):
    # Conservative even inside quotes: designers can pass literal resolved
    # paths instead of expansions. No second command can hide in an argument.
    command = command.replace("${CLAUDE_PLUGIN_ROOT}", "__CAI_PLUGIN_ROOT__")
    if re.search(r"[;&|<>`$(){}\n\r]", command):
        return False
    try:
        args = shlex.split(command)
    except ValueError:
        return False
    if not args:
        return False
    args = [arg.replace("__CAI_PLUGIN_ROOT__", str(Path(__file__).resolve().parent.parent))
            for arg in args]
    if args[0] == "mmdc":
        return True
    if args[0] not in ("python", "python3", "py"):
        return False
    if args[0] == "py" and len(args) > 1 and args[1] == "-3":
        args = [args[0]] + args[2:]
    if len(args) < 2 or args[1].startswith("-"):
        return False
    script = (Path(cwd) / args[1]).resolve()
    return script in {Path(__file__).with_name(name).resolve()
                      for name in ("design_probe.py", "options_lint.py")}


def main():
    try:
        payload = json.load(sys.stdin)
        command = payload["tool_input"]["command"]
        if not isinstance(command, str):
            raise ValueError("command must be text")
        ok = allowed(command, payload.get("cwd", str(Path.cwd())))
    except (ValueError, KeyError, TypeError, OSError):
        ok = False
    if not ok:
        print("Blocked: designer may run only design_probe.py, options_lint.py, or mmdc as a single "
              "command. Ask the main session to run other commands.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
