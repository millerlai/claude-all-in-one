#!/usr/bin/env python3
"""Hold test-runner's Bash to the resolver and what it resolved.

Agent tools lists select tools; Bash(...) is not a command sandbox (#181).
bash_guard.py hands every Bash call of this agent here, by `agent_type`,
before its own general rules. Each call re-resolves the project's test command
from the files as they are now, so nothing the agent was told earlier counts.
"""
import os
from pathlib import Path
import re
import shlex
import sys

import resolve_test_command

AGENTS = frozenset({"cai:test-runner"})
UNSAFE = re.compile(r"[;&|<>`$(){}\n\r]")
ROOT_VAR = "<cai-root>"
ROOT_MARK = "__CAI_PLUGIN_ROOT__"


def _squeeze(command):
    return re.sub(r"[ \t]+", " ", command.strip())


def _runs_script(command, cwd, name):
    """`python <script> [plain args]` where <script> is `name` next to this file.

    The interpreter is python/python3/py, the
    script path is resolved against cwd, and no argument can hide a second
    command because UNSAFE characters are refused anywhere in the text."""
    command = command.replace(ROOT_VAR, ROOT_MARK)
    if UNSAFE.search(command):
        return False
    try:
        args = shlex.split(command)
    except ValueError:
        return False
    if not args or args[0] not in ("python", "python3", "py"):
        return False
    if args[0] == "py" and len(args) > 1 and args[1] == "-3":
        args = [args[0]] + args[2:]
    if len(args) < 2 or args[1].startswith("-"):
        return False
    plugin_root = str(Path(__file__).resolve().parent.parent)
    script = (Path(cwd) / args[1].replace(ROOT_MARK, plugin_root)).resolve()
    return script == Path(__file__).with_name(name).resolve()


def _extends(command, base):
    """`command` is `base`, or `base` followed by arguments with no shell symbol."""
    return command == base or (command.startswith(base + " ")
                               and not UNSAFE.search(command[len(base):]))


def _resolved_commands(cwd):
    result = resolve_test_command.resolve(resolve_test_command.find_root(cwd))
    if result["status"] != "resolved":
        return []
    return [_squeeze(c["command"]) for c in result["commands"]]


def allowed(command, cwd):
    if "\n" in command or "\r" in command:
        return False
    if _runs_script(command, cwd, "resolve_test_command.py"):
        return True
    squeezed = _squeeze(command)
    try:
        # A declared string is the person's own text and may carry `&&`: it is
        # compared whole first, and only what follows it is held to UNSAFE.
        return any(_extends(squeezed, base) for base in _resolved_commands(cwd))
    except Exception:  # a guard on a scoped agent fails closed
        return False


def check(payload):
    """0 to let the call through, 2 to block it with the reason on stderr."""
    agent = payload.get("agent_type")
    try:
        command = payload["tool_input"]["command"]
        if not isinstance(command, str):
            raise ValueError("command must be text")
        ok = allowed(command, payload.get("cwd") or os.getcwd())
    except (ValueError, KeyError, TypeError, OSError):
        ok = False
    if ok:
        return 0
    print("Blocked: %s may run only the resolver and the test commands it "
          "resolved (see test-command.md), each optionally followed by plain "
          "arguments. Do not cd, do not redirect (stderr is already returned), "
          "and do not chain." % agent, file=sys.stderr)
    return 2
