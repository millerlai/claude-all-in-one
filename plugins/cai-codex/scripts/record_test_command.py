#!/usr/bin/env python3
"""Record the test commands a person confirmed into `.claude/cai.json`.

Writes `test.commands` and leaves every other key (the `ticket` object, other
`test` subkeys) as it was. Exit 0 written, 2 bad commands, 5 the existing file
cannot be merged into or could not be written -- in both exit-5 cases nothing
is changed. Zero deps beyond the standard library and `resolve_test_command`.
"""
import argparse
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import resolve_test_command as resolver  # noqa: E402


class ConfigProblem(ValueError):
    """The existing cai.json is not something we can safely add a key to."""


def _load(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except ValueError:
        raise ConfigProblem("%s could not be read as JSON" % resolver.CONFIG_REL)
    if not isinstance(data, dict):
        raise ConfigProblem("%s must hold a JSON object" % resolver.CONFIG_REL)
    if "test" in data and not isinstance(data["test"], dict):
        raise ConfigProblem("%s has a \"test\" key that is not an object" % resolver.CONFIG_REL)
    return data


def record(project_dir, commands):
    """Write `commands` as test.commands under `project_dir`; returns the path."""
    cleaned = [c.strip() for c in commands]
    if not cleaned or any(not c or "\r" in c or "\n" in c for c in cleaned):
        raise ValueError("commands must be non-empty single-line strings")
    path = os.path.join(project_dir, resolver.CONFIG_REL)
    data = _load(path)
    data.setdefault("test", {})["commands"] = cleaned
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Same directory so os.replace is one rename and a reader never sees half a file.
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project-dir", default=".",
                    help="directory to record into (default: current directory)")
    ap.add_argument("commands", nargs="*", metavar="COMMAND",
                    help="one test command per argument, quoted")
    args = ap.parse_args(argv)
    root = resolver.find_root(os.path.abspath(args.project_dir))
    try:
        path = record(root, args.commands)
    except ConfigProblem as exc:
        print("record_test_command: %s; nothing written" % exc, file=sys.stderr)
        return 5
    except ValueError as exc:
        print("record_test_command: %s" % exc, file=sys.stderr)
        return 2
    except OSError:
        print("record_test_command: could not write %s; nothing changed" % resolver.CONFIG_REL,
              file=sys.stderr)
        return 5
    print("%s: %s" % (path, json.dumps([c.strip() for c in args.commands], ensure_ascii=False)))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
