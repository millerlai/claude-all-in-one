#!/usr/bin/env python3
"""Install this plugin's status line into ~/.claude/, deterministically.

    python install_statusline.py --check     # report, change nothing
    python install_statusline.py             # install, refuse to clobber
    python install_statusline.py --force     # install over a foreign statusLine

`/cai:setup` runs this instead of editing settings.json itself. That file is
the user's whole global configuration -- permissions, enabled plugins, the
autoMode environment block -- and a model asked to rewrite it byte for byte
around one new key has a bad day eventually. Here the edit is: parse, set one
key, write back.

The copy lands at ~/.claude/cai-statusline.py rather than the conventional
~/.claude/statusline.py, because that name belongs to whatever the built-in
`/statusline` command last generated. Overwriting it would eat work this
plugin never created.

Exit codes: 0 done or reported, 1 error, 2 refused (a statusLine that is not
ours is already configured; re-run with --force).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_NAME = "cai-statusline.py"
SOURCE = Path(__file__).resolve().parent / "statusline.py"

# Bare interpreter names, in the order the plugin's other launchers try them.
# A bare name and not sys.executable's absolute path: on Windows without Git
# Bash, Claude Code runs the status line through PowerShell, where a command
# line starting with a quoted path is a string literal rather than a command,
# so `"C:/Program Files/.../python.exe" script.py` prints the path and exits 0
# -- a status line that fails by silently showing nothing.
CANDIDATES = [("py", "-3"), ("python",)] if os.name == "nt" else [("python3",), ("python",)]

PROBE = '{"model":{"display_name":"probe"}}'


def find_interpreter():
    """The first candidate resolvable on PATH, or None."""
    for candidate in CANDIDATES:
        if shutil.which(candidate[0]):
            return candidate
    return None


def command_string(interpreter, dest):
    """The `statusLine.command` value.

    Forward slashes because Claude Code runs the status line through Git Bash
    on Windows, and Git Bash eats an unquoted backslash as an escape. The path
    is quoted (a home directory may contain spaces) but the interpreter is
    not -- see CANDIDATES for why that asymmetry is deliberate."""
    return f'{" ".join(interpreter)} "{str(dest).replace(os.sep, "/")}"'


def read_settings(path):
    """The parsed settings file, or {} when absent. Raises on malformed JSON:
    overwriting a file we could not read is how configuration disappears."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_settings(path, settings):
    """Replace `path` atomically, keeping a .bak of what was there.

    A partially written settings.json is unparseable, and Claude Code then
    starts with no permissions, no plugins and no marketplaces -- worse than
    any failure this script is trying to prevent."""
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    body = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def verify(interpreter, dest):
    """Run the installed copy the way Claude Code will. Reported rather than
    fatal: a status line that prints nothing fails invisibly, so the one thing
    worth knowing is whether it produced output at all."""
    try:
        result = subprocess.run([*interpreter, str(dest)], input=PROBE,
                                capture_output=True, text=True, timeout=10)
        return result.returncode == 0 and result.stdout.strip() != ""
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="report the current state, change nothing")
    ap.add_argument("--force", action="store_true",
                    help="replace a statusLine this script did not install")
    ap.add_argument("--claude-dir", default=str(Path.home() / ".claude"),
                    help="the directory holding settings.json (default: ~/.claude)")
    args = ap.parse_args()

    # Absolute, because the resolved path is written into settings.json and
    # Claude Code runs the status line from whatever directory it likes.
    claude_dir = Path(args.claude_dir).expanduser().resolve()
    settings_path = claude_dir / "settings.json"
    dest = claude_dir / SCRIPT_NAME

    try:
        settings = read_settings(settings_path)
    except (OSError, ValueError) as exc:
        print(f"cannot read {settings_path}: {exc}")
        return 1

    existing = settings.get("statusLine")
    current = existing.get("command", "") if isinstance(existing, dict) else ""
    ours = SCRIPT_NAME in current

    if args.check:
        print(f"settings: {settings_path} ({'present' if settings_path.exists() else 'absent'})")
        print(f"script:   {dest} ({'present' if dest.exists() else 'absent'})")
        if not existing:
            print("statusLine: none configured")
        elif ours:
            print(f"statusLine: installed by cai -> {current}")
        else:
            print(f"statusLine: configured by someone else -> {current}")
        interpreter = find_interpreter()
        print(f"interpreter: {' '.join(interpreter) if interpreter else 'NOT FOUND'}")
        return 0

    if existing and not ours and not args.force:
        print(f"refused: a statusLine is already configured -> {current}")
        print("Ask the user before replacing it, then re-run with --force.")
        return 2

    interpreter = find_interpreter()
    if interpreter is None:
        print("no Python interpreter on PATH: "
              + ", ".join(c[0] for c in CANDIDATES))
        return 1

    if not SOURCE.exists():
        print(f"source script missing: {SOURCE}")
        return 1

    desired = {"type": "command", "command": command_string(interpreter, dest)}
    backup = settings_path.with_suffix(settings_path.suffix + ".bak")
    wrote = False
    try:
        claude_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE, dest)
        # Only when it would actually differ. Re-running after every
        # `/plugin update` is the documented routine, and a write on a run
        # that changes nothing would replace the .bak holding whatever
        # statusLine the user had before this script first ran.
        if settings.get("statusLine") != desired:
            wrote = settings_path.exists()
            settings["statusLine"] = desired
            write_settings(settings_path, settings)
    except OSError as exc:
        print(f"install failed: {exc}")
        return 1

    print(f"installed: {dest}")
    print(f"statusLine: {desired['command']}")
    if wrote and backup.exists():
        print(f"backup:    {backup}")
    print("verified: " + ("the installed script prints a status line"
                          if verify(interpreter, dest)
                          else "FAILED -- it produced no output"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
