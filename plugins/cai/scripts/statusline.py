#!/usr/bin/env python3
"""Claude Code status line: project, branch, model + effort, and three
remaining-capacity gauges.

`/cai:setup` copies this file to ~/.claude/cai-statusline.py and points
`statusLine.command` in ~/.claude/settings.json at the copy, so it must stay
standalone -- stdlib only, no import from anywhere else in the plugin.

Every gauge reads as "how much is left", never "how much is spent", so one
colour scale covers all three: green is safe, red means wrap up. The context
window already reports remaining; the rate-limit windows report used, and are
inverted here to match.
"""
import sys
import json
import subprocess
from pathlib import Path

try:
    # Windows picks the locale encoding (cp950 here) for a piped stdout, which
    # turns the "·" separator into mojibake. Measured, not hypothetical.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RESET = "\033[0m"
BRIGHT_CYAN = "\033[96m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"


def gauge(label, remaining):
    """A coloured `label NN%` reading, where `remaining` is a percentage of
    headroom left.

    Rounds before choosing the colour, not after: 49.6 displays as 50%, and a
    "50%" painted amber next to a green "50%" elsewhere on the line is the kind
    of inconsistency nobody can debug from a screenshot."""
    pct = round(remaining)
    color = GREEN if pct >= 50 else YELLOW if pct >= 21 else RED
    return f"{color}{label} {pct}%{RESET}"


def git_branch(current_dir):
    """The checked-out branch of `current_dir`, or "" when git says nothing
    useful. Separate from render() so a test can replace it -- it is the only
    part of the line that shells out."""
    try:
        result = subprocess.run(
            ["git", "-C", current_dir, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def render(data):
    """The status line for one payload. Every segment is independently
    optional: Claude Code omits or nulls most of these fields at some point in
    a session's life, and a status line that raises just disappears."""
    parts: list[str] = []

    # repo.name only exists with an origin remote; current_dir's basename is
    # the fallback for a repo (or non-repo dir) that has none.
    current_dir = ""
    try:
        workspace = data.get("workspace", {})
        current_dir = workspace.get("current_dir", "")
        repo_name = (workspace.get("repo") or {}).get("name", "")
        project = repo_name or (Path(current_dir).name if current_dir else "")
        if project:
            parts.append(f"{BRIGHT_CYAN}{project}{RESET}")
    except Exception:
        pass

    try:
        if current_dir:
            branch = git_branch(current_dir)
            if branch:
                parts.append(branch)
    except Exception:
        pass

    # effort is absent on models without the reasoning-effort parameter, and
    # rides along with the model rather than as its own segment -- bracketed
    # so "Sonnet 5 [high]" cannot be misread as a model variant.
    try:
        model_name = data.get("model", {}).get("display_name", "")
        if model_name:
            level = (data.get("effort") or {}).get("level", "")
            if level:
                model_name = f"{model_name} {DIM}[{level}]{RESET}"
            parts.append(model_name)
    except Exception:
        pass

    # None (not just absent) early in a session, before the first API reply
    # or right after /compact — a present-but-null field, so check is not None.
    try:
        remaining = data.get("context_window", {}).get("remaining_percentage")
        if remaining is not None:
            parts.append(gauge("ctx", remaining))
    except Exception:
        pass

    # rate_limits only exists for Claude.ai subscribers, and only after this
    # session's first API response; each window can be absent independently
    # and Claude Code drops one outright once its resets_at has passed.
    for label, window in (("5h", "five_hour"), ("7d", "seven_day")):
        try:
            used = data.get("rate_limits", {}).get(window, {}).get("used_percentage")
            if used is not None:
                parts.append(gauge(label, 100 - used))
        except Exception:
            pass

    return " · ".join(parts)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("statusline: bad input")
        return
    print(render(data))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("statusline: error")
