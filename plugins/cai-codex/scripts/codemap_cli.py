#!/usr/bin/env python3
"""The one entry point to the codemap index.

    codemap_cli.py status --project-dir DIR
    codemap_cli.py build  --project-dir DIR
    codemap_cli.py update --project-dir DIR
    codemap_cli.py query  --project-dir DIR TEXT

The first line printed is always the state line. Exit 0: a state line was
printed (any state word). Exit 2: `build` could not finish writing, or something
unexpected happened; the line is `codemap: unsupported (<reason>)`, never a
traceback. Exit 1: the command line was wrong.
"""
import argparse
import os
import sys
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import codemap_index  # noqa: E402
import codemap_inventory  # noqa: E402
import codemap_query  # noqa: E402
import codemap_store  # noqa: E402
import preflight  # noqa: E402

ABSENT_HINT = "run $codemap build to create one"


def _top(project_dir):
    start = os.path.abspath(project_dir)
    done = preflight.git(start, "rev-parse", "--show-toplevel")
    if done is None or done.returncode != 0 or not done.stdout.strip():
        return start
    return os.path.normpath(done.stdout.strip())


def _shown(text):
    """Paths, matched lines and messages come from the repository or the index
    directory; escaped, one of them can never add a line of its own -- a forged
    `codemap: fresh` among them."""
    return preflight.escape_control_chars(str(text))


def _reason(exc):
    if isinstance(exc, codemap_inventory.NotARepository):
        return "not a git repository"
    if isinstance(exc, codemap_inventory.GitFailed):
        return "git did not answer"
    if isinstance(exc, codemap_store.IndexUnreadable):
        return _shown(exc.args[0])
    if isinstance(exc, OSError) and (exc.filename is not None or exc.filename2 is not None):
        # str() of it carries local absolute paths, and this line ends up in an
        # agent's output; strerror is the OS's message without them.
        return "%s: %s" % (type(exc).__name__, _shown(exc.strerror)) if exc.strerror \
            else type(exc).__name__
    first = (str(exc).splitlines() or [""])[0]
    return "%s: %s" % (type(exc).__name__, _shown(first)) if first else type(exc).__name__


def _print_status(status):
    print(codemap_index.state_line(status))
    if status.word == "absent":
        print(ABSENT_HINT)
    shown = status.paths[:preflight.MAX_CONFLICTS_SHOWN]
    for path in shown:
        print("  %s: %s" % (status.word, _shown(path)))
    if len(status.paths) > len(shown):
        # After a branch switch the list can run to thousands, and all of it
        # would land in the context of whoever ran this (#403).
        print("  … and %d more" % (len(status.paths) - len(shown)))


def _print_result(result):
    print(codemap_index.result_line(result))
    print("%d files, %d shards" % (result.total, result.shards))
    shown = result.partial[:preflight.MAX_CONFLICTS_SHOWN]
    for path, reason in shown:
        print("  partial: %s (%s)" % (_shown(path), _shown(reason)))
    if len(result.partial) > len(shown):
        print("  … and %d more" % (len(result.partial) - len(shown)))


QUERY_LIMIT = 10   # Recall@10 is the largest N the benchmark asks about


def _query(top, text):
    status = codemap_index.status(top)
    print(codemap_index.state_line(status))
    if status.word in codemap_index.NO_INDEX_WORDS:
        if status.word == "absent":
            print(ABSENT_HINT)
        return 0
    hits = codemap_query.query(top, codemap_store.load(top), text, QUERY_LIMIT)
    for hit in hits:
        print("%d %s:%d %s %s" % (hit.score, _shown(hit.path), hit.line, hit.kind,
                                  _shown(hit.name)))
    if not hits:
        print("no hit")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="codemap_cli.py", add_help=True)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "build", "update", "query"):
        one = sub.add_parser(name)
        one.add_argument("--project-dir", default=".")
        if name == "query":
            one.add_argument("text", nargs="+")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 1 if exc.code else 0
    top = _top(args.project_dir)
    try:
        if args.command == "status":
            _print_status(codemap_index.status(top))
            return 0
        if args.command == "query":
            return _query(top, " ".join(args.text))
        if args.command == "update":
            result = codemap_index.update(top)
            if result is None:      # no index: only `build` makes one
                _print_status(codemap_index.status(top))
                return 0
        else:
            result = codemap_index.build(top)
        _print_result(result)
        return 0
    except Exception as exc:  # noqa: BLE001 -- the contract is one line, never a traceback
        print("codemap: unsupported (%s)" % _reason(exc))
        return 2


if __name__ == "__main__":
    # A piped Windows stdout is the ANSI codepage; a path or a matched line that
    # it cannot encode would turn a good answer into `unsupported`.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
