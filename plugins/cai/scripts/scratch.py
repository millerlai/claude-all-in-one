#!/usr/bin/env python3
"""A scratch directory for the files a skill hands to a command. Zero deps.

A skill that needs a file outside the repository -- a commit message for
`git commit -F`, a report for a script -- used to be told "the temp directory",
with a name the agent made up and a deletion nothing checked. A run that was
killed, or an agent that forgot, left its files in the temp directory for good,
and nothing ever came back for them.

    scratch.py dir <label>     print a new, empty directory
    scratch.py clean <path>    delete a directory `dir` printed

Every directory lives under one root, `<temp>/cai-scratch/`, which is the only
place this script deletes from. `dir` also removes what an earlier run left
there: a direct child of that root not touched for STALE_AFTER_S. So a person
who stops using the plugin keeps at most what was in flight, and a folder of
their own that happens to start with `cai-` is never at risk.

Exit: 0 done, 2 refused (a bad label, or a path that is not under the root);
the reason is the one line printed.
"""
import argparse
import os
import re
import shutil
import stat
import sys
import tempfile
import time

ROOT_NAME = "cai-scratch"

# No run of a skill lasts hours between two uses of its own directory. Six
# hours is therefore past any live run, and short enough that one day's
# leftovers are gone before the next day's.
STALE_AFTER_S = 6 * 60 * 60

# A label becomes part of a directory name, so it may not carry a separator.
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")


def root():
    return os.path.join(tempfile.gettempdir(), ROOT_NAME)


# `onexc` replaced `onerror`, which 3.12 deprecated. A constant, not a check at
# the call, so a test can reach the older branch from the interpreter it runs on.
_HAS_ONEXC = sys.version_info >= (3, 12)


def _make_writable_then(func, target, _):
    os.chmod(target, stat.S_IWRITE)
    func(target)


def _rmtree(path):
    """A read-only file (git object files, pytest's own) stops `rmtree` on
    Windows, so one that raises is made writable and tried again."""
    if _HAS_ONEXC:
        shutil.rmtree(path, onexc=_make_writable_then)
    else:
        shutil.rmtree(path, onerror=_make_writable_then)


def _remove(path):
    """A link is unlinked, never followed into what it points at."""
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path)
    else:
        _rmtree(path)


def sweep(base, now):
    """Removes every direct child of `base` older than STALE_AFTER_S. Never
    raises: a child another run removed first, or one still open, stays for the
    next call."""
    try:
        entries = list(os.scandir(base))
    except OSError:
        return
    for entry in entries:
        try:
            if now - entry.stat(follow_symlinks=False).st_mtime >= STALE_AFTER_S:
                _remove(entry.path)
        except OSError:
            pass


def new_dir(label):
    base = root()
    os.makedirs(base, exist_ok=True)
    sweep(base, time.time())
    return tempfile.mkdtemp(prefix=label + "-", dir=base)


def is_scratch_child(path):
    """True when `path` is a direct child of the root. Both sides go through
    realpath because the temp directory is often a short 8.3 name on Windows
    and a link on macOS."""
    parent = os.path.dirname(os.path.abspath(path))
    return (os.path.normcase(os.path.realpath(parent))
            == os.path.normcase(os.path.realpath(root())))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("dir", help="print a new directory").add_argument("label")
    sub.add_parser("clean", help="delete a directory `dir` printed").add_argument("path")
    args = ap.parse_args(argv)

    if args.command == "dir":
        if not LABEL.match(args.label):
            print("refused: label %r is not 1-32 letters, digits, - or _" % args.label)
            return 2
        print(new_dir(args.label))
        return 0

    if not is_scratch_child(args.path):
        print("refused: %s is not a directory under %s" % (args.path, root()))
        return 2
    if os.path.lexists(args.path):
        _remove(args.path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
