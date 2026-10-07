#!/usr/bin/env python3
"""Resolve how this project starts its app (the `run` object), read-only.

Reads `run` from `.claude/cai.json` and checks its shape; with no declaration it
lists candidates from `package.json` and never runs anything. Prints one JSON
object. Exit 0 declared, 3 candidates, 4 unknown, 5 invalid declaration; 1 and 2
are left to uncaught exceptions and argparse. Zero deps beyond the standard
library and `resolve_test_command`.
"""
import argparse
import json
import os
import sys
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import resolve_test_command as rtc  # noqa: E402

PORT = "{port}"
LOOPBACK = ("127.0.0.1", "localhost", "::1")
EXIT_DECLARED, EXIT_CANDIDATES, EXIT_UNKNOWN, EXIT_INVALID = 0, 3, 4, 5
KEYS = ("start", "ready", "e2e")
SCRIPTS = ("dev", "start")


def _words(value, where):
    """Problem text unless `value` is a non-empty list of non-empty one-line strings."""
    if (not isinstance(value, list) or not value
            or not all(isinstance(w, str) and w and not any(c in w for c in "\r\n\0")
                       for w in value)):
        return "%s must be a non-empty list of non-empty strings without line breaks or NUL" % where
    return None


def _ready_problem(ready):
    if not isinstance(ready, str) or any(c in ready for c in "\r\n\0"):
        return "ready must be a single-line string"
    if not ready.startswith("http://"):
        return "ready must start with http://"
    try:
        # {port} stands in for a number so urlsplit can judge the rest.
        parts = urlsplit(ready.replace(PORT, "1"))
        parts.port
    except ValueError:
        return "ready is not a valid URL (host or port)"
    if "@" in parts.netloc or parts.hostname not in LOOPBACK:
        return "ready host must be one of 127.0.0.1, localhost, [::1]"
    authority = ready[len("http://"):].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if PORT in ready and not authority.endswith(":" + PORT):
        return "ready may use {port} only as the port after the host"
    return None


def validate(group):
    """(declaration, None) for a well-formed `run` object, else (None, problem)."""
    if not isinstance(group, dict):
        return None, "run must be an object"
    unknown = sorted(k for k in group if k not in KEYS)
    if unknown:
        return None, "run has unknown key %s (allowed: start, ready, e2e)" % ", ".join(unknown)
    for key in ("start", "ready"):
        if key not in group:
            return None, "run.%s is missing" % key
    problem = _words(group["start"], "run.start")
    if problem:
        return None, problem
    problem = _ready_problem(group["ready"])
    if problem:
        return None, "run.%s" % problem
    e2e = group.get("e2e", {})
    if not isinstance(e2e, dict):
        return None, "run.e2e must be an object of name to command list"
    for name, words in e2e.items():
        problem = _words(words, "run.e2e.%s" % name)
        if problem:
            return None, problem
    start_has = any(PORT in w for w in group["start"])
    if (PORT in group["ready"]) != start_has:
        return None, "run.ready and run.start must both use {port} or neither"
    if not start_has and any(PORT in w for words in e2e.values() for w in words):
        return None, "run.e2e uses {port} but run.start does not"
    return {"start": group["start"], "ready": group["ready"], "e2e": e2e}, None


def _result(root, status, declaration=None, candidates=(), problem=None):
    return {"status": status, "root": root, "declaration": declaration,
            "candidates": list(candidates), "problem": problem}


def _declared(root):
    """None when nothing is declared, else a finished result (declared or invalid)."""
    path = os.path.join(root, rtc.CONFIG_REL)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as fh:
            # UTF-8 only, as resolve_test_command and the recorders read it.
            data = json.loads(fh.read(rtc.READ_LIMIT).decode("utf-8-sig"))
    except (OSError, ValueError):
        return _result(root, "invalid", problem="%s could not be read as JSON" % rtc.CONFIG_REL)
    if not isinstance(data, dict):
        return _result(root, "invalid", problem="%s must hold a JSON object" % rtc.CONFIG_REL)
    if "run" not in data:
        return None
    declaration, problem = validate(data["run"])
    if problem:
        return _result(root, "invalid", problem="%s: %s" % (rtc.CONFIG_REL, problem))
    return _result(root, "declared", declaration=declaration)


def _candidates(root):
    """package.json's scripts.dev / scripts.start as `<pm> run <name>`."""
    notes = []
    text = rtc._read(root, "package.json", notes)
    if text is None:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return []
    pm = next((name for lock, name in (("package-lock.json", "npm"), ("pnpm-lock.yaml", "pnpm"),
                                       ("yarn.lock", "yarn"))
               if os.path.isfile(os.path.join(root, lock))), "npm")
    return [{"start": [pm, "run", name], "origin": "package.json", "script": name}
            for name in SCRIPTS if isinstance(scripts.get(name), str)]


def resolve(root):
    """How `root` (already a root) starts its app, as a dict; writes nothing."""
    declared = _declared(root)
    if declared is not None:
        return declared
    found = _candidates(root)
    return _result(root, "candidates" if found else "unknown", candidates=found)


EXIT_BY_STATUS = {"declared": EXIT_DECLARED, "candidates": EXIT_CANDIDATES,
                  "unknown": EXIT_UNKNOWN, "invalid": EXIT_INVALID}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project-dir", default=".",
                    help="directory to resolve from (default: current directory)")
    args = ap.parse_args(argv)
    result = resolve(rtc.find_root(os.path.abspath(args.project_dir)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_BY_STATUS[result["status"]]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
