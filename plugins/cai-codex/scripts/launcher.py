#!/usr/bin/env python3
"""
Fixed-path entry point installed at $HOME/.codex/cai/launcher.py (D1=C). It
runs from the user's Codex shell, wherever `python` resolves there, and finds
the actual cai-codex scripts by walking the plugin cache Codex itself
maintains -- no `${CLAUDE_PLUGIN_ROOT}`-style substitution exists on Codex.

    python launcher.py <script-name> [args...]   # run <cai-root>/scripts/<script-name>.py
    python launcher.py --root                     # print the resolved cai root
    python launcher.py guard                       # adapt a Codex hook payload and run bash_guard.py

Design: docs/design/2026-09-18-codex-support-detail.md, "### launcher.py".
Standard library only: this runs on a machine that only has whatever
interpreter Codex's shell finds, on Windows and POSIX alike.

Exit codes: 3 = the installed agents' version stamp does not match the
resolved plugin's version (before a <script-name> run only -- not --root or
guard, which must stay fail-open like bash_guard.py); 4 = no cai-codex cache
found at all; otherwise the child process's own exit code.
"""
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

STAMP_RE = re.compile(r"#\s*cai-codex-version:\s*(\S+)")
ENCODED_COMMAND_FLAGS = ("-encodedcommand", "-e", "-enc")
BASH_PROGRAMS = ("bash", "sh", "zsh")


def _codex_home() -> Path:
    home = os.environ.get("CODEX_HOME")
    return Path(home) if home else Path.home() / ".codex"


def _version_key(name: str):
    """A comparable (major, minor, patch, ...) tuple, or None for a directory
    name that is not a numeric version (so a stray non-version dir under the
    cache is skipped rather than crashing resolution)."""
    parts = name.split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def resolve_cai_root():
    """The highest-version `.../plugins/cache/*/cai-codex/<version>/` under
    `$CODEX_HOME` (or `~/.codex`), or None when nothing is cached (E1)."""
    cache_dir = _codex_home() / "plugins" / "cache"
    best_root = None
    best_key = None
    if not cache_dir.is_dir():
        return None
    for marketplace_dir in sorted(cache_dir.iterdir()):
        plugin_dir = marketplace_dir / "cai-codex"
        if not plugin_dir.is_dir():
            continue
        for version_dir in plugin_dir.iterdir():
            key = _version_key(version_dir.name)
            if key is None or not version_dir.is_dir():
                continue
            if best_key is None or key > best_key:
                best_key, best_root = key, version_dir
    return best_root


def plugin_version(root: Path):
    """The resolved root's own version, from `.codex-plugin/plugin.json`, or
    None when it is missing or unreadable -- a reason to skip the stamp
    check, not to block a run neither side can explain."""
    try:
        data = json.loads((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        return data["version"]
    except (OSError, ValueError, KeyError):
        return None


def stamp_mismatch(root: Path):
    """(agents_version, plugin_version) when an installed `cai_*.toml`'s
    first-line stamp disagrees with the resolved plugin's version, else None.
    No agents directory, no stamped file, or no readable plugin version all
    mean there is nothing to compare -- not a mismatch (G3 is a check
    against the version Codex actually has installed, not a requirement that
    it exist yet)."""
    target = plugin_version(root)
    if target is None:
        return None
    agents_dir = _codex_home() / "agents"
    if not agents_dir.is_dir():
        return None
    for toml_path in sorted(agents_dir.glob("cai_*.toml")):
        try:
            first_line = toml_path.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, IndexError):
            continue
        m = STAMP_RE.match(first_line)
        if m and m.group(1) != target:
            return m.group(1), target
    return None


def _decode_encoded_command(token):
    """PowerShell's `-EncodedCommand` (and its `-e`/`-enc` abbreviations)
    carry the script as base64 of UTF-16LE text, not literal text -- left
    undecoded, bash_guard.py's regexes see an opaque token and can never
    match it, no matter what the script says. An undecodable token is
    passed through unchanged rather than raising: it still won't match
    anything, same as today, but it can't crash the guard either."""
    try:
        return base64.b64decode(token).decode("utf-16-le")
    except Exception:
        return token


def _adapt_command(command):
    """Codex's `tool_input.command`, UNVERIFIED (C9): a string passes
    through; a list whose first element is a shell executable followed by
    `-Command`/`-c` yields the element after that flag, or by
    `-EncodedCommand`/`-e`/`-enc` decodes the base64 script that follows;
    any other list is joined with spaces."""
    if isinstance(command, list):
        if len(command) >= 3 and command[1] in ("-Command", "-c"):
            return command[2]
        if len(command) >= 3 and str(command[1]).lower() in ENCODED_COMMAND_FLAGS:
            return _decode_encoded_command(command[2])
        return " ".join(str(c) for c in command)
    return command


def _tool_name(command) -> str:
    """Which of bash_guard.py's two rule sets applies. The list form names
    its own program in command[0] -- more reliable than guessing from the
    host OS, since a POSIX host can still run Codex through cross-platform
    `pwsh`, and a Windows host can run real Bash through Git Bash/WSL. A
    bare string carries no such hint, so it falls back to the host OS."""
    if isinstance(command, list) and command:
        if Path(str(command[0])).stem.lower() in BASH_PROGRAMS:
            return "Bash"
        return "PowerShell"
    return "PowerShell" if os.name == "nt" else "Bash"


def _adapt_payload(payload: dict) -> dict:
    adapted = dict(payload)
    tool_input = dict(adapted.get("tool_input") or {})
    command = tool_input.get("command")
    adapted["tool_name"] = _tool_name(command)
    if command:  # missing/empty: pass through untouched, bash_guard fails open
        tool_input["command"] = _adapt_command(command)
        adapted["tool_input"] = tool_input
    return adapted


def run_guard(root: Path) -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        return 0  # unparsable payload: fail open, matching bash_guard.py:174-175
    adapted = _adapt_payload(payload)
    guard = root / "scripts" / "bash_guard.py"
    # bash_guard.py's own current_branch()/worktree_dirty() checks run `git`
    # in the payload's own `cwd` (bash_guard.py:198), not the launcher's --
    # without the same safe.directory override _git_safe_env() gives a
    # dispatched script, Codex's elevated Windows sandbox's "dubious
    # ownership" makes those `git` calls fail, and both checks treat "can't
    # tell" as an unrelated repo, i.e. fail open: a protected-branch commit
    # or a dirty-tree discard would go through unblocked. No cwd in the
    # payload leaves the guard's environment untouched, same as before --
    # bash_guard.py already fails open when it can't read a cwd (its own
    # `payload.get("cwd")` default of None becomes `cwd=None`, and
    # subprocess.run's own `cwd=None` means "inherit").
    cwd = adapted.get("cwd")
    env = _git_safe_env(cwd) if cwd else None
    result = subprocess.run([sys.executable, str(guard)],
                             input=json.dumps(adapted), encoding="utf-8", env=env)
    return result.returncode


def _git_safe_env(directory) -> dict:
    """Environment for a subprocess's own `git` calls, with `directory`
    declared a safe directory via git's documented environment form
    (GIT_CONFIG_COUNT/GIT_CONFIG_KEY_n/GIT_CONFIG_VALUE_n, git >= 2.31).
    Codex's elevated Windows sandbox runs commands as a different user than
    the repo's owner, so a `git` call from either a dispatched script or
    bash_guard.py's own checks would otherwise fail with "dubious ownership"
    for the very folder the user opened and trusted Codex in -- scoped to
    that one directory, not `*`, and appended after whatever GIT_CONFIG_*
    pairs the environment already carries rather than clobbering them."""
    env = dict(os.environ)
    try:
        count = int(env.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        count = 0
    env[f"GIT_CONFIG_KEY_{count}"] = "safe.directory"
    env[f"GIT_CONFIG_VALUE_{count}"] = str(directory)
    env["GIT_CONFIG_COUNT"] = str(count + 1)
    return env


def run_script(root: Path, name: str, args: list) -> int:
    mismatch = stamp_mismatch(root)
    if mismatch:
        agents_version, plugin_v = mismatch
        print(f"cai-codex agents are version {agents_version}, plugin is "
              f"version {plugin_v}: run $setup", file=sys.stderr)
        return 3
    script = root / "scripts" / f"{name}.py"
    try:
        result = subprocess.run([sys.executable, str(script), *args],
                                 env=_git_safe_env(Path.cwd().as_posix()))
    except FileNotFoundError:
        print(f"no such script: {name}", file=sys.stderr)
        return 1
    return result.returncode


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: launcher.py {--root|guard|<script-name>} [args...]", file=sys.stderr)
        return 2

    root = resolve_cai_root()
    if root is None:
        print("cai-codex is not installed", file=sys.stderr)
        return 4

    if argv[0] == "--root":
        print(root)
        return 0
    if argv[0] == "guard":
        return run_guard(root)
    return run_script(root, argv[0], argv[1:])


if __name__ == "__main__":
    sys.exit(main())
