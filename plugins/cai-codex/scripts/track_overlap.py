#!/usr/bin/env python3
"""Names the files this worktree's work and another worktree's track both
change, before a merge finds out (#470).

Tracks started on main run side by side in their own worktrees (#467), and
nothing compared them: two that edit the same file met only at merge time.
For each other worktree with an active track (`.cai/track/current`), the
files it changed -- committed since it left the base branch, plus what is
still uncommitted or untracked -- are compared with this worktree's, and
every file both touch prints one line:

    overlap <file>: <feature> (<worktree>), <feature> (<worktree>)

It reads only, and always exits 0 when it could look: an overlap is for a
person to know about, not a reason to stop. preflight.py runs it before build
and ship and passes the lines on as a warning. A worktree it cannot read
prints `skipped <worktree>: <why>`.

Usage:  track_overlap.py [--project-dir DIR]
Exit:   0 compared (whatever it found), 2 could not list worktrees, 1 usage.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preflight  # noqa: E402
import track_state  # noqa: E402


def changed_files(path, base):
    """The set of paths changed in this worktree against `base`, or a string
    saying why git could not tell."""
    out = set()
    if base:
        done = preflight.git(path, "merge-base", "HEAD", base)
        if done is None or done.returncode != 0:
            return "no merge base with %s" % base
        committed = preflight.git(path, "diff", "--name-only", "-z",
                                  done.stdout.strip(), "HEAD")
        if committed is None or committed.returncode != 0:
            return "git diff did not answer"
        out.update(p for p in committed.stdout.split("\0") if p)
    for args in (("diff", "--name-only", "-z", "HEAD"),
                 ("ls-files", "--others", "--exclude-standard", "-z")):
        done = preflight.git(path, *args)
        if done is None or done.returncode != 0:
            return "git %s did not answer" % args[0]
        out.update(p for p in done.stdout.split("\0") if p)
    return out


def overlaps(project_dir):
    """(lines to print, exit code)."""
    found = track_state.worktrees(project_dir)
    if not found:
        return ["not a git work tree with worktrees -- nothing to compare"], 2
    here = os.path.normcase(os.path.realpath(project_dir))
    base = preflight.find_base_ref(project_dir)
    if base is preflight.GIT_DID_NOT_ANSWER:
        return ["git did not answer -- nothing compared"], 2
    main_top = found[0][0]

    def label(path):
        feature = track_state.current_feature(
            os.path.join(path, track_state.DEFAULT_TRACK_ROOT)) or "no track"
        rel = os.path.relpath(path, main_top).replace(os.sep, "/")
        return "%s (%s)" % (feature, path if rel.startswith("..") else rel)

    mine = changed_files(project_dir, base)
    if isinstance(mine, str):
        return ["skipped %s: %s" % (project_dir, mine)], 0
    lines = []
    for path, _branch, prunable in found:
        if os.path.normcase(os.path.realpath(path)) == here or prunable \
                or not os.path.isdir(path):
            continue
        if not track_state.current_feature(os.path.join(path, track_state.DEFAULT_TRACK_ROOT)):
            continue
        theirs = changed_files(path, base)
        if isinstance(theirs, str):
            lines.append("skipped %s: %s" % (path, theirs))
            continue
        for file in sorted(mine & theirs):
            lines.append("overlap %s: %s, %s" % (file, label(project_dir), label(path)))
    return lines, 0


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project-dir", default=".")
    args = ap.parse_args(argv)
    lines, code = overlaps(os.path.abspath(args.project_dir))
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
