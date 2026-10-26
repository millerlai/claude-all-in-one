#!/usr/bin/env python3
"""A per-project record of the answers a person gave to questions the evidence
could not settle, so the next track does not ask the same thing again.

The file is `<main checkout>/.cai/answers.md`, one table row per answer:
`| date | track | question's first line | answer |`. It sits in the main
checkout, not the worktree a track runs in, because `.cai/` ignores itself and
a worktree's copy would go when the worktree does. pending.py appends to it
for a question that was handed up as `Why asked: evidence-split`, and never
for a consent (gate, irreversible, outward).

    answers.py path --project-dir DIR    # print the file's path

Exit 0 done, 1 usage error."""
import argparse
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cai_paths  # noqa: E402
import ledger  # noqa: E402

FILE_NAME = "answers.md"
CUT = 1000


def path(project_dir):
    """The file for `project_dir`: the main checkout's when it is a linked
    worktree, else the project's own."""
    top, _ = cai_paths.main_checkout(project_dir)
    return os.path.join(top or project_dir, cai_paths.CAI_DIR, FILE_NAME)


def _cell(text, first_line=False):
    if first_line:
        text = text.strip().split("\n", 1)[0]
    text = ledger._cut(text, CUT)
    return re.sub(r"\r\n|\r|\n", " ", text.replace("|", "\\|")).strip()


def append(project_dir, track, question, answer):
    """Adds one row and returns the path written. Raises OSError when the
    write fails; the caller's own work does not depend on it."""
    target = path(project_dir)
    cai_paths.ensure_dir(os.path.dirname(os.path.dirname(target)))
    row = "| %s | %s | %s | %s |\n" % (datetime.date.today().isoformat(), _cell(track),
                                       _cell(question, True), _cell(answer))
    # ledger._write_line, not a plain O_APPEND: on Windows that lost rows
    # when processes appended at once (see its docstring).
    ledger._write_line(target, row.encode("utf-8"))
    return target


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("path",))
    ap.add_argument("--project-dir", default=".")
    args = ap.parse_args(argv)
    print(path(os.path.abspath(args.project_dir)))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
