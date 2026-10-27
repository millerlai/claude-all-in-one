#!/usr/bin/env python3
"""Decide the platform-review call for verify, or why to fall back to a reviewer.

    resolve_review_command.py --platform {claude,codex} --base <ref> [--project-dir <dir>]

Prints one JSON object and no model is called. `decide` is a pure function of
explicit inputs (same input, same output); `gather` is the only part that reads
git, `claude --version`, settings files and the environment. Exit 0 = run,
3 = fall back (the `reason` says why), 5 = the inputs cannot be used (empty
diff, unknown platform, git failure); argparse errors exit 2.

The diff is measured against the working tree, not `<ref>...HEAD`, because both
platforms review uncommitted tracked changes too: measure what is reviewed.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import tool_path

MIN_CLAUDE_VERSION = (2, 1, 288)
LINE_LIMIT = 400
DOC_SUFFIXES = (".md", ".txt", ".rst")
# The only place size -> (level, --max-findings) is written.
LEVELS = {"docs": ("low", 5), "small": ("high", 10), "large": ("max", 15)}
EXIT_RUN, EXIT_FALLBACK, EXIT_INVALID = 0, 3, 5

_EXIT_BY_STATUS = {"run": EXIT_RUN, "fallback": EXIT_FALLBACK, "invalid": EXIT_INVALID}
# A skill set to one of these cannot be invoked by the model.
_UNCALLABLE = ("user-invocable-only", "off")
_VERSION = re.compile(r"\d+\.\d+\.\d+")
# The base ref goes into codex's argv, and on Windows a `codex.cmd` shim is run
# by cmd.exe, which reads & | ^ % " ( ) < > as its own. A ref outside this set
# (git allows far more) is refused rather than quoted; it never starts with `-`.
_SAFE_REF = re.compile(r"[A-Za-z0-9._/@~+][A-Za-z0-9._/@~+-]*\Z")
_GIT_TIMEOUT = 60
_VERSION_TIMEOUT = 15


class GatherError(Exception):
    """The environment could not be read; the message is a fixed phrase."""


def _is_docs(path):
    return path.lower().endswith(DOC_SUFFIXES)


def _inside(directory, top):
    root = os.path.join(os.path.normcase(os.path.realpath(top)), "")
    return os.path.join(os.path.normcase(os.path.realpath(directory)), "").startswith(root)


def _lines(numstat):
    # Binary rows carry None, None: no lines, but the path still counts elsewhere.
    return sum((a or 0) + (d or 0) for a, d, _ in numstat)


def size_class(numstat):
    """`docs` when every touched path is a document (however large), else
    `small` up to LINE_LIMIT lines and `large` above it."""
    if all(_is_docs(p) for _, _, p in numstat):
        return "docs"
    return "small" if _lines(numstat) <= LINE_LIMIT else "large"


def _result(platform, base, status, reason, lines=0, docs_only=False, notes=()):
    return {"format": 1, "platform": platform, "status": status, "reason": reason,
            "base": base, "lines": lines, "docs_only": docs_only,
            "notes": list(notes), "call": None}


def _fallback_reasons(platform, claude_version, settings_layers, skill_dirs, codex_path):
    if platform == "codex":
        return [] if codex_path else ["codex not found in a trusted PATH entry"]
    reasons = []
    if not claude_version:
        reasons.append("claude --version unreadable")
    elif tuple(int(n) for n in claude_version.split(".")) < MIN_CLAUDE_VERSION:
        reasons.append("claude --version reported %s, below %s"
                       % (claude_version, ".".join(map(str, MIN_CLAUDE_VERSION))))
    for number, layer in enumerate(settings_layers, 1):
        overrides = layer.get("skillOverrides") if isinstance(layer, dict) else None
        value = overrides.get("code-review") if isinstance(overrides, dict) else None
        if value in _UNCALLABLE:
            reasons.append("skillOverrides sets code-review to %s in settings layer %d"
                           % (value, number))
    for path in skill_dirs:
        reasons.append("%s replaces the built-in code-review" % path)
    return reasons


def decide(platform, base_ref, numstat, claude_version=None, settings_layers=(),
           skill_dirs=(), codex_path=None, codex_home=None, notes=()):
    if platform not in ("claude", "codex"):
        return _result(str(platform), base_ref, "invalid", "unknown platform %s" % platform,
                       notes=notes)
    if not _SAFE_REF.match(base_ref):
        # A fixed phrase: the ref is the text that is not safe to print or run.
        return _result(platform, base_ref, "invalid",
                       "base ref has characters outside A-Z a-z 0-9 . _ / @ ~ + -", notes=notes)
    if not numstat:
        return _result(platform, base_ref, "invalid", "empty diff against %s" % base_ref,
                       notes=notes)
    lines = _lines(numstat)
    kind = size_class(numstat)
    out = _result(platform, base_ref, "run", None, lines, kind == "docs", notes)
    reasons = _fallback_reasons(platform, claude_version, settings_layers, skill_dirs, codex_path)
    if reasons:
        out["status"], out["reason"] = "fallback", "; ".join(reasons)
        return out
    if platform == "claude":
        level, limit = LEVELS[kind]
        out["level"], out["max_findings"] = level, limit
        out["args"] = "%s --max-findings %d %s...HEAD" % (level, limit, base_ref)
        out["call"] = "/code-review " + out["args"]
    else:
        out["argv"] = [codex_path, "exec", "review", "--base", base_ref,
                       "-c", "sandbox_mode=read-only"]
        out["env"] = {"CODEX_HOME": codex_home}
        out["call"] = "codex exec review --base %s -c sandbox_mode=read-only" % base_ref
    return out


def _run(argv, cwd):
    """Raw stdout bytes, or None when the command cannot run or exits non-zero.
    Bytes: git paths and tool output are not in the console's locale."""
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=_GIT_TIMEOUT,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def _git(top, *args):
    try:
        git = tool_path.resolve("git", cwd=top)
    except FileNotFoundError:
        raise GatherError("git not found in a trusted PATH entry")
    out = _run([git, *args], top)
    if out is None:
        raise GatherError("git %s failed" % args[0])
    return out


def _parse_numstat(raw):
    rows = []
    for record in raw.decode("utf-8", errors="replace").split("\0"):
        if not record:
            continue
        added, deleted, path = record.split("\t", 2)
        binary = added == "-" or deleted == "-"
        rows.append((None if binary else int(added), None if binary else int(deleted), path))
    return rows


def _claude_version(top):
    try:
        exe = tool_path.resolve("claude", cwd=top)
        p = subprocess.run([exe, "--version"], cwd=top, capture_output=True,
                           timeout=_VERSION_TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    found = _VERSION.search(p.stdout.decode("utf-8", errors="replace"))
    return found.group(0) if found else None


def _load_layer(path, notes):
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError):
        notes.append("%s could not be read; treated as empty" % path.name)
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        notes.append("%s is not a JSON object; treated as empty" % path.name)
        return {}
    return data


def gather(platform, base_ref, project_dir, environ=None):
    """Keyword arguments for `decide` (plus `notes`). Raises GatherError."""
    environ = os.environ if environ is None else environ
    top_raw = _git(os.path.abspath(project_dir), "rev-parse", "--show-toplevel") \
        if os.path.isdir(project_dir) else None
    if top_raw is None:
        raise GatherError("project dir is not a directory")
    top = top_raw.decode("utf-8", errors="replace").strip()
    merge_base = _git(top, "merge-base", "HEAD", base_ref).decode("ascii", "replace").strip()
    numstat = _parse_numstat(_git(top, "diff", "--numstat", "--no-renames", "-z", merge_base))
    kwargs = {"platform": platform, "base_ref": base_ref, "numstat": numstat, "notes": []}
    home = Path.home()
    if platform == "claude":
        config = Path(environ.get("CLAUDE_CONFIG_DIR") or home / ".claude")
        project = Path(top) / ".claude"
        kwargs["claude_version"] = _claude_version(top)
        kwargs["settings_layers"] = [
            _load_layer(config / "settings.json", kwargs["notes"]),
            _load_layer(project / "settings.json", kwargs["notes"]),
            _load_layer(project / "settings.local.json", kwargs["notes"])]
        candidates = [project / "skills" / "code-review", config / "skills" / "code-review",
                      project / "commands" / "code-review.md", config / "commands" / "code-review.md"]
        kwargs["skill_dirs"] = [str(c) for c in candidates if c.exists()]
    elif platform == "codex":
        try:
            found = tool_path.resolve("codex", cwd=top)
        except FileNotFoundError:
            found = None
        if found and _inside(os.path.dirname(found), top):
            # The reviewed checkout controls what is in it; tool_path only skips
            # PATH entries that are above the working directory, not below it.
            kwargs["notes"].append("a codex inside the reviewed repository was ignored")
            found = None
        kwargs["codex_path"] = found
        kwargs["codex_home"] = environ.get("CODEX_HOME") or str(home / ".codex")
    return kwargs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--platform", required=True, choices=("claude", "codex"))
    ap.add_argument("--base", required=True, help="base ref to review against")
    ap.add_argument("--project-dir", default=".",
                    help="directory inside the repository (default: current directory)")
    args = ap.parse_args(argv)
    try:
        result = decide(**gather(args.platform, args.base, args.project_dir))
    except GatherError as e:
        result = _result(args.platform, args.base, "invalid", str(e))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return _EXIT_BY_STATUS[result["status"]]


if __name__ == "__main__":
    # Paths in the output may be non-ASCII; a piped Windows stdout is not UTF-8.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
