#!/usr/bin/env python3
"""Resolve which test command(s) this project's root uses, read-only.

Zero deps beyond the standard library, and it deliberately imports no sibling
(`ticket` would drag `preflight` into the hook's hot path). It only parses
files, never runs anything found in them, and prints one JSON object. Exit
0 resolved, 3 several candidates, 4 unknown, 5 invalid declaration; 1 and 2
are left to uncaught exceptions and argparse.
"""
import argparse
import codecs
import json
import os
import re
import subprocess
import sys

CONFIG_REL = os.path.join(".claude", "cai.json")
NPM_PLACEHOLDER = 'echo "Error: no test specified" && exit 1'
EXIT_RESOLVED, EXIT_SEVERAL, EXIT_UNKNOWN, EXIT_INVALID = 0, 3, 4, 5
READ_LIMIT = 1048576

# (command, whole, narrow). A declared string equal to `command` or to
# `command whole` borrows the row's narrow; anything else is unnarrowable.
KNOWN = [
    ("python -m pytest", "", "paths"),
    ("python3 -m pytest", "", "paths"),
    ("py -3 -m pytest", "", "paths"),
    ("go test", "./...", "packages"),
    ("make test", "", "none"),
    ("just test", "", "none"),
    ("task test", "", "none"),
    ("npm test", "", "none"),
    ("pnpm test", "", "none"),
    ("yarn test", "", "none"),
    ("tox", "", "none"),
    ("nox", "", "none"),
    ("cargo test", "", "none"),
    ("mvn test", "", "none"),
    ("./gradlew test", "", "none"),
    ("dotnet test", "", "none"),
]

# (name on PATH, launcher), first found wins. Many Linux and macOS systems have
# python3 and no python, and a Windows install may have only the py launcher (#274).
PYTHON_LAUNCHERS = (("python", "python"), ("python3", "python3"), ("py", "py -3"))

# `test ::= x` and `test :::= x` are GNU make's simple and immediate variable
# assignments, so the lookahead skips every `:=` spelling; `test::` still matches.
# `[ \t]*`, not `\s*`: a rule is `targets : prerequisites` on one line (#280).
MAKE_TEST = re.compile(r"^test[ \t]*::?(?!:{0,2}=)", re.M)
# GNU make's manual: "it tries the following names, in order" (#280).
MAKEFILES = ("GNUmakefile", "makefile", "Makefile")
# `test` followed by optional parameters, then the colon: `test-x:` is another
# recipe and `test := x` a variable, neither of which `just test` runs.
JUST_TEST = re.compile(r"^test(?:[ \t][^:=\n]*)?:(?!=)", re.M)
# just matches these case-insensitively and refuses several (its search.rs, #280).
JUSTFILES = ("justfile", ".justfile")
# Task's `DefaultTaskfiles`, in the priority order its docs give.
TASKFILES = ("Taskfile.yml", "taskfile.yml", "Taskfile.yaml", "taskfile.yaml",
             "Taskfile.dist.yml", "taskfile.dist.yml", "Taskfile.dist.yaml", "taskfile.dist.yaml")
TASKS_HEAD = re.compile(r"^tasks:[ \t]*(?:#.*)?$")
TASK_TEST = re.compile(r"^[ \t]+test[ \t]*:")


def _tool_path(name, cwd=None):
    """Copy of the plugin's tool_path.resolve() (this file imports no sibling):
    the full path of `name` in an absolute PATH entry that neither is nor
    holds the current directory or `cwd`, so a same-named program there never
    runs (#294). FileNotFoundError if there is none."""
    here = [os.path.join(os.path.normcase(os.path.realpath(d)), "")
            for d in (os.getcwd(), cwd) if d]
    if os.name == "nt" and not os.path.splitext(name)[1]:
        names = [name + ext for ext in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if ext]
    else:
        names = [name]
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        entry = entry.strip('"')
        if not os.path.isabs(entry):
            continue
        real = os.path.join(os.path.normcase(os.path.realpath(entry)), "")
        if any(h.startswith(real) for h in here):
            continue
        for candidate in names:
            path = os.path.join(entry, candidate)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    raise FileNotFoundError(2, "not found in a trusted PATH entry", name)


def find_root(cwd):
    """The git toplevel of `cwd`, or `cwd` itself when git cannot say."""
    try:
        proc = subprocess.run([_tool_path("git", cwd), "rev-parse", "--show-toplevel"], cwd=cwd,
                              capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return cwd
    # Decode ourselves: text=True would use the console locale (see memory).
    top = proc.stdout.decode("utf-8", "replace").strip()
    return top if proc.returncode == 0 and top else cwd


def _read(root, name, notes):
    """The first READ_LIMIT bytes of `name` as text, or None (noted)."""
    try:
        with open(os.path.join(root, name), "rb") as fh:
            data = fh.read(READ_LIMIT)
        # utf-8-sig: a BOM is not whitespace and would hide a line-1 entry. A cut
        # at READ_LIMIT can split a character; final=False drops that tail only.
        decoder = codecs.getincrementaldecoder("utf-8-sig")()
        return decoder.decode(data, final=len(data) < READ_LIMIT)
    except (OSError, UnicodeDecodeError):
        notes.append("%s: could not be read" % name)
        return None


def _command(command, whole, narrow, origin):
    return {"command": command, "whole": whole, "narrow": narrow, "origin": origin}


def _result(root, status, source=None, commands=(), candidates=(), problem=None, notes=()):
    return {"status": status, "source": source, "root": root,
            "commands": list(commands), "candidates": list(candidates),
            "problem": problem, "notes": list(notes)}


def _invalid(root, problem):
    return _result(root, "invalid", problem=problem)


def _declared(root):
    """None when nothing is declared, else a finished result (resolved or invalid)."""
    path = os.path.join(root, CONFIG_REL)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as fh:
            # Decode first: json.loads on bytes also takes UTF-16/32, which the
            # recorder and ticket.py reject; all three read UTF-8 only (#280).
            data = json.loads(fh.read(READ_LIMIT).decode("utf-8-sig"))
    except (OSError, ValueError):
        return _invalid(root, "%s could not be read as JSON" % CONFIG_REL)
    if not isinstance(data, dict):
        return _invalid(root, "%s must hold a JSON object" % CONFIG_REL)
    if "test" not in data:
        return None
    test = data["test"]
    commands = test.get("commands") if isinstance(test, dict) else None
    if (not isinstance(commands, list) or not commands
            or not all(isinstance(c, str) and c.strip() and "\r" not in c and "\n" not in c
                       for c in commands)):
        return _invalid(root, "%s: test.commands must be a non-empty list of "
                              "single-line, non-empty strings" % CONFIG_REL)
    out = []
    for raw in commands:
        text = raw.strip()
        for command, whole, narrow in KNOWN:
            if text in (command, (command + " " + whole).strip()):
                out.append(_command(command, whole, narrow, CONFIG_REL.replace(os.sep, "/")))
                break
        else:
            out.append(_command(text, "", "none", CONFIG_REL.replace(os.sep, "/")))
    return _result(root, "resolved", "declared", commands=out)


def _task_has_test(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not TASKS_HEAD.match(line):
            continue
        indent = None
        for sub in lines[i + 1:]:
            if not sub.strip() or sub.lstrip().startswith("#"):
                continue
            if not sub[0].isspace():
                return False
            width = len(sub) - len(sub.lstrip())
            if indent is None:
                indent = width
            if width == indent and TASK_TEST.match(sub):
                return True
    return False


def _entry_candidates(root, notes):
    """Files that wrap the tests in one name (Makefile, justfile, ...)."""
    out = []
    has = lambda n: os.path.isfile(os.path.join(root, n))  # noqa: E731
    try:
        listed = set(os.listdir(root))
    except OSError:
        listed = set()
    makefile = next((n for n in MAKEFILES if n in listed and has(n)), None)
    if makefile:
        text = _read(root, makefile, notes)
        if text is not None and MAKE_TEST.search(text):
            out.append(_command("make test", "", "none", makefile))
    justfiles = sorted(n for n in listed if n.lower() in JUSTFILES and has(n))
    if len(justfiles) > 1:
        notes.append("%s: just refuses more than one justfile" % ", ".join(justfiles))
    elif justfiles:
        text = _read(root, justfiles[0], notes)
        if text is not None and JUST_TEST.search(text):
            out.append(_command("just test", "", "none", justfiles[0]))
    # Exact names only, so Windows and Linux agree. The first name present is the
    # only one read (the maintainer's decision, 2026-10-04); Task's docs say the
    # names are looked up "in order of priority".
    taskfile = next((n for n in TASKFILES if n in listed and has(n)), None)
    if taskfile:
        text = _read(root, taskfile, notes)
        if text is not None and _task_has_test(text):
            out.append(_command("task test", "", "none", taskfile))
    if has("package.json"):
        text = _read(root, "package.json", notes)
        if text is not None:
            try:
                data = json.loads(text)
            except ValueError:
                notes.append("package.json: not valid JSON")
                data = None
            scripts = data.get("scripts") if isinstance(data, dict) else None
            test = scripts.get("test") if isinstance(scripts, dict) else None
            if isinstance(test, str) and test != NPM_PLACEHOLDER:
                locks = [(n, c) for n, c in (("package-lock.json", "npm test"),
                                             ("pnpm-lock.yaml", "pnpm test"),
                                             ("yarn.lock", "yarn test")) if has(n)]
                for _, command in locks or [(None, "npm test")]:
                    out.append(_command(command, "", "none", "package.json"))
    if has("tox.ini"):
        out.append(_command("tox", "", "none", "tox.ini"))
    if has("noxfile.py"):
        out.append(_command("nox", "", "none", "noxfile.py"))
    return out


def _pytest_origin(root, notes):
    """The first file that configures pytest, in the design's order."""
    checks = [("pyproject.toml", re.compile(r"^\s*\[tool\.pytest\.ini_options\]", re.M)),
              ("pytest.ini", None),
              ("tox.ini", re.compile(r"^\s*\[pytest\]", re.M)),
              ("setup.cfg", re.compile(r"^\s*\[tool:pytest\]", re.M))]
    for name, pattern in checks:
        if not os.path.isfile(os.path.join(root, name)):
            continue
        if pattern is None:
            return name
        text = _read(root, name, notes)
        if text is not None and pattern.search(text):
            return name
    return None


def _on_path(name):
    try:
        _tool_path(name)
        return True
    except FileNotFoundError:
        return False


def _python_launcher():
    """The first launcher in PYTHON_LAUNCHERS on a trusted PATH entry, else
    `python`, whose own "not found" is the clearest message when nothing is
    installed. shutil.which would also count one in the current directory."""
    return next((launcher for name, launcher in PYTHON_LAUNCHERS if _on_path(name)),
                "python")


def _marker_candidates(root, notes):
    """Files that only name a language or build tool."""
    out = []
    has = lambda n: os.path.isfile(os.path.join(root, n))  # noqa: E731
    origin = _pytest_origin(root, notes)
    if origin:
        out.append(_command(_python_launcher() + " -m pytest", "", "paths", origin))
    if has("go.mod"):
        out.append(_command("go test", "./...", "packages", "go.mod"))
    if has("Cargo.toml"):
        out.append(_command("cargo test", "", "none", "Cargo.toml"))
    if has("pom.xml"):
        out.append(_command("mvn test", "", "none", "pom.xml"))
    gradle = next((n for n in ("build.gradle", "build.gradle.kts") if has(n)), None)
    if gradle and has("gradlew"):
        out.append(_command("./gradlew test", "", "none", gradle))
    try:
        names = sorted(os.listdir(root))
    except OSError:
        names = []
    dotnet = next((n for n in names if n.endswith((".sln", ".csproj"))
                   and os.path.isfile(os.path.join(root, n))), None)
    if dotnet:
        out.append(_command("dotnet test", "", "none", dotnet))
    return out


def resolve(project_dir):
    """What `project_dir` (already a root) uses to run tests, as a dict."""
    root = project_dir
    declared = _declared(root)
    if declared is not None:
        return declared
    notes = []
    found = _entry_candidates(root, notes) + _marker_candidates(root, notes)
    if len(found) == 1:
        return _result(root, "resolved", "detected", commands=found, notes=notes)
    if found:
        return _result(root, "several", candidates=found, notes=notes)
    return _result(root, "unknown", notes=notes)


EXIT_BY_STATUS = {"resolved": EXIT_RESOLVED, "several": EXIT_SEVERAL,
                  "unknown": EXIT_UNKNOWN, "invalid": EXIT_INVALID}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project-dir", default=".",
                    help="directory to resolve from (default: current directory)")
    args = ap.parse_args(argv)
    result = resolve(find_root(os.path.abspath(args.project_dir)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_BY_STATUS[result["status"]]


if __name__ == "__main__":
    # Paths and notes may be non-ASCII; a piped Windows stdout is not UTF-8.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
