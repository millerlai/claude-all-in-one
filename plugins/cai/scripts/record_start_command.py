#!/usr/bin/env python3
"""Record the start command and ready URL a person confirmed into `.claude/cai.json`.

Writes `run.start` and `run.ready` and leaves every other key (`test`, `ticket`,
an existing `run.e2e`) as it was. Exit 0 written, 2 arguments that fail
`validate()`, 5 the existing file cannot be merged into or could not be written
-- in both exit-5 cases nothing is changed. Everything after the first `--` is
the command, so a later `--` (as in `npm run dev -- --port {port}`) is kept.
Zero deps beyond the standard library and its sibling scripts.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import record_test_command  # noqa: E402
import resolve_start_command as starter  # noqa: E402
import resolve_test_command as rtc  # noqa: E402

ConfigProblem = record_test_command.ConfigProblem


def record(project_dir, start, ready):
    """Write run.start and run.ready under `project_dir`; returns the path."""
    path = os.path.join(project_dir, rtc.CONFIG_REL)
    data = record_test_command._load(path)
    run = data.get("run", {})
    if not isinstance(run, dict):
        raise ConfigProblem("%s has a \"run\" key that is not an object" % rtc.CONFIG_REL)
    group = {"start": start, "ready": ready}
    if "e2e" in run:  # kept, but it must still agree with the new start on {port}
        group["e2e"] = run["e2e"]
    _, problem = starter.validate(group)
    if problem:
        raise ValueError(problem)
    run["start"], run["ready"] = start, ready
    data["run"] = run
    record_test_command.write_config(path, data)
    return path


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    # Split by hand: argparse's treatment of a second `--` varies by Python version.
    cut = argv.index("--") if "--" in argv else len(argv)
    words = argv[cut + 1:]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 usage="%(prog)s [--project-dir DIR] --ready URL -- WORD [WORD ...]")
    ap.add_argument("--project-dir", default=".",
                    help="directory to record into (default: current directory)")
    ap.add_argument("--ready", required=True, help="URL polled to tell the app is up")
    args = ap.parse_args(argv[:cut])
    root = rtc.find_root(os.path.abspath(args.project_dir))
    try:
        path = record(root, words, args.ready)
    except ConfigProblem as exc:
        print("record_start_command: %s; nothing written" % exc, file=sys.stderr)
        return 5
    except ValueError as exc:
        print("record_start_command: %s" % exc, file=sys.stderr)
        return 2
    except OSError:
        print("record_start_command: could not write %s; nothing changed" % rtc.CONFIG_REL,
              file=sys.stderr)
        return 5
    print("%s: run.start=%s run.ready=%s" % (path, json.dumps(words, ensure_ascii=False), args.ready))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
