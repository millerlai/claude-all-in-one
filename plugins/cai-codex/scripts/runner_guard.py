#!/usr/bin/env python3
"""Hold test-runner's and verifier's Bash to the resolver and what it resolved.

Agent tools lists select tools; Bash(...) is not a command sandbox (#181).
bash_guard.py hands every Bash call of these two agents here, by `agent_type`,
before its own general rules. Each call re-resolves the project's test command
from the files as they are now, so nothing the agent was told earlier counts.
"""
import os
from pathlib import Path
import re
import shlex
import sys

import resolve_test_command

RUNNER_AGENTS = frozenset({"cai:test-runner"})
VERIFIER_AGENTS = frozenset({"cai:verifier"})
AGENTS = RUNNER_AGENTS | VERIFIER_AGENTS
UNSAFE = re.compile(r"[;&|<>`$(){}\n\r]")
ROOT_VAR = "<cai-root>"
ROOT_MARK = "__CAI_PLUGIN_ROOT__"

# Verifier only. These two take no arguments: `git symbolic-ref` with a second
# argument writes a ref, and `git rev-parse` is only wanted for the toplevel.
VERIFIER_EXACT = ("git symbolic-ref --short refs/remotes/origin/HEAD",
                  "git rev-parse --show-toplevel")
# `git merge-base HEAD <rev>` needs the rev; the others may stand alone.
VERIFIER_PREFIXES = ("git merge-base HEAD ",)
VERIFIER_VERBS = ("git diff", "git log", "git show")
# The agents stage-verify.md dispatches, plugin-scoped or as it spells them (#277).
VERIFIER_LENSES = frozenset({"cai:reviewer", "cai:security-reviewer",
                             "reviewer", "security-reviewer"})


def _squeeze(command):
    return re.sub(r"[ \t]+", " ", command.strip())


def _runs_script(command, cwd, name):
    """`python <script> [plain args]` where <script> is `name` next to this file.

    Same shape as designer_guard: the interpreter is python/python3/py, the
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


def _writes_a_file(command):
    """`--output=<file>` makes git diff/log/show write it (#277). git refuses an
    abbreviation today; one down to `--out` is refused here all the same."""
    try:
        args = shlex.split(command)
    except ValueError:
        return True
    return any(len(name) >= 5 and "--output".startswith(name)
               for name in (a.split("=", 1)[0] for a in args))


def _resolved_commands(cwd):
    result = resolve_test_command.resolve(resolve_test_command.find_root(cwd))
    if result["status"] != "resolved":
        return []
    return [_squeeze(c["command"]) for c in result["commands"]]


def allowed(command, cwd, agent_type):
    if "\n" in command or "\r" in command:
        return False
    if _runs_script(command, cwd, "resolve_test_command.py"):
        return True
    squeezed = _squeeze(command)
    try:
        # A declared string is the person's own text and may carry `&&`: it is
        # compared whole first, and only what follows it is held to UNSAFE.
        if any(_extends(squeezed, base) for base in _resolved_commands(cwd)):
            return True
    except Exception:  # a guard on a scoped agent fails closed
        return False
    if agent_type not in VERIFIER_AGENTS:
        return False
    return (squeezed in VERIFIER_EXACT
            or any(squeezed.startswith(p) and not UNSAFE.search(squeezed[len(p):])
                   for p in VERIFIER_PREFIXES)
            or any(_extends(squeezed, verb) and not _writes_a_file(squeezed)
                   for verb in VERIFIER_VERBS)
            or _runs_script(command, cwd, "provenance.py"))


def check_dispatch(payload):
    """An Agent call: 0, or 2 when the verifier asks for anything but a lens.

    A dispatched agent is guarded by its own agent_type, so an unrestricted one
    would carry none of the verifier's limits, and a subagent's `tools:` cannot
    narrow Agent to named types (#277)."""
    if payload.get("agent_type") not in VERIFIER_AGENTS:
        return 0
    wanted = (payload.get("tool_input") or {}).get("subagent_type")
    if wanted in VERIFIER_LENSES:
        return 0
    print("Blocked: %s may dispatch only cai:reviewer and cai:security-reviewer "
          "(the four lenses in stage-verify.md), not %r." % (payload["agent_type"], wanted),
          file=sys.stderr)
    return 2


def check(payload):
    """0 to let the call through, 2 to block it with the reason on stderr."""
    agent = payload.get("agent_type")
    try:
        command = payload["tool_input"]["command"]
        if not isinstance(command, str):
            raise ValueError("command must be text")
        ok = allowed(command, payload.get("cwd") or os.getcwd(), agent)
    except (ValueError, KeyError, TypeError, OSError):
        ok = False
    if ok:
        return 0
    message = ("Blocked: %s may run only the resolver and the test commands it "
               "resolved (see test-command.md), each optionally followed by plain "
               "arguments. Do not cd, do not redirect (stderr is already returned), "
               "and do not chain." % agent)
    if agent in VERIFIER_AGENTS:
        message += (" The verifier may also run git symbolic-ref --short "
                    "refs/remotes/origin/HEAD, git rev-parse --show-toplevel, git "
                    "merge-base HEAD <rev>, git diff, git log, git show, and "
                    "provenance.py.")
    print(message, file=sys.stderr)
    return 2
