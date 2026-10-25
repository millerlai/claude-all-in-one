#!/usr/bin/env python3
"""Where cai keeps what it writes into a project: `.cai/` beside `.git`, a
directory that ignores itself, so none of it reaches git unless the person
adds it themselves (`git add -f`).

Earlier versions kept the same things under `.claude/`, where they went into
git with the project's own files -- and a glossary every branch appended to
conflicted with every other branch. `migrate` moves them across once.

    cai_paths.py ensure  --project-dir DIR   # make .cai/ and its .gitignore
    cai_paths.py migrate --project-dir DIR   # one line per item moved

Exit 0 done, 2 the directory could not be made (the last line says why)."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

CAI_DIR = ".cai"
SELF_IGNORE = ".gitignore"
SELF_IGNORE_BODY = "*\n"
TRACK = os.path.join(CAI_DIR, "track")
CONFIG = os.path.join(CAI_DIR, "cai.json")
GLOSSARY = os.path.join(CAI_DIR, "cai-context.md")
REVIEW = os.path.join(CAI_DIR, "cai-review.md")

# Where earlier versions kept the same things, relative to the project root.
LEGACY = ((os.path.join(".claude", "track"), TRACK),
          (os.path.join(".claude", "cai.json"), CONFIG),
          (os.path.join(".claude", "cai-context.md"), GLOSSARY),
          (os.path.join(".claude", "cai-review.md"), REVIEW))


def ensure_dir(top):
    """Creates `<top>/.cai/` and, when it has none, its `.gitignore` of `*`.
    An existing `.gitignore` is left as it is: the person may have narrowed it
    to keep something of theirs in git."""
    path = os.path.join(top, CAI_DIR)
    os.makedirs(path, exist_ok=True)
    try:
        fd = os.open(os.path.join(path, SELF_IGNORE),
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    except FileExistsError:
        return path
    with os.fdopen(fd, "w", encoding="ascii", newline="\n") as fh:
        fh.write(SELF_IGNORE_BODY)
    return path


def _tracked(top, rel):
    """"no" when nothing at `rel` is tracked -- outside a repository too, where
    nothing can be -- "yes" when something is, and "unknown" when git could
    not be asked. Only "no" lets the caller move rather than copy."""
    # English messages: the "not a git repository" match must not depend on
    # the person's locale.
    env = dict(os.environ, LC_ALL="C", LANGUAGE="C")
    try:
        done = subprocess.run(["git", "ls-files", "-z", "--", rel.replace(os.sep, "/")],
                              cwd=top, capture_output=True, timeout=30, env=env)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if done.returncode != 0:
        return "no" if b"not a git repository" in done.stderr else "unknown"
    return "yes" if done.stdout.strip(b"\0") else "no"


def migrate(top):
    """Moves what an earlier cai left under `.claude/` into `.cai/`, and
    returns one line per item it moved, copied or could not move.

    Only an item whose old place exists and whose new place does not is
    touched, so running it again does nothing. One that git tracks is copied
    and the original left where it is: removing a tracked file would leave the
    working tree dirty, and whether to is the person's call."""
    lines = []
    for old_rel, new_rel in LEGACY:
        old = os.path.join(top, old_rel)
        new = os.path.join(top, new_rel)
        if not os.path.lexists(old) or os.path.lexists(new):
            continue
        shown = "%s to %s" % (old_rel.replace(os.sep, "/"), new_rel.replace(os.sep, "/"))
        try:
            ensure_dir(top)
            tracked = _tracked(top, old_rel)
            if tracked == "no":
                os.replace(old, new)
                lines.append("moved " + shown)
                continue
            if os.path.isdir(old):
                shutil.copytree(old, new, symlinks=True)
            else:
                shutil.copy2(old, new)
        except OSError as exc:
            lines.append("could not move %s (%s: %s)" % (shown, type(exc).__name__, exc))
            continue
        why = ("git tracks the original" if tracked == "yes"
               else "git could not say whether it tracks the original")
        lines.append("copied %s; %s, so it is left for you to remove" % (shown, why))
    return lines


def _git(cwd, *args):
    """Completed git process, or None when git cannot run. English messages
    and bytes decoded by the caller, as _tracked does."""
    env = dict(os.environ, LC_ALL="C", LANGUAGE="C")
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                              timeout=10, env=env)
    except (OSError, subprocess.SubprocessError):
        return None


def main_checkout(project_dir):
    """The main checkout's top when project_dir is a linked worktree, else
    (None, the reason it stays put). Returns (top, None) on success."""
    found = []
    for flag in ("--git-dir", "--git-common-dir"):
        done = _git(project_dir, "rev-parse", flag)
        if done is None or done.returncode != 0:
            return None, "not a git work tree -- nothing to copy"
        out = done.stdout.decode("utf-8", "replace").strip()
        found.append(os.path.realpath(os.path.join(project_dir, out)))
    git_dir, common = found
    if os.path.normcase(git_dir) == os.path.normcase(common):
        return None, "not a linked worktree -- the archive stays where it is"
    if os.path.basename(common) != ".git":
        return None, "the main repository is bare -- no checkout to copy into"
    return os.path.dirname(common), None


def _read_object(path):
    """The JSON object in `path`, {} when there is no file, None when it
    cannot be read or holds anything but an object."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def config_path(project_dir):
    """(the cai.json to read and write, note lines this call produced).

    A linked worktree starts with no cai.json because `.cai/` ignores itself,
    so what an earlier worktree recorded was invisible. There the answer is
    the main checkout's file, and every top-level key the worktree's own file
    has and the main one lacks is merged into it first (main wins on a
    conflict). Anywhere else, or when either file cannot be trusted as a JSON
    object, nothing is merged and a missing file is still just a path."""
    own = os.path.join(project_dir, CONFIG)
    top, _ = main_checkout(project_dir)
    if top is None:
        return own, []
    shared = os.path.join(top, CONFIG)
    mine = _read_object(own)
    if not mine:
        return shared, []
    # Read just before writing: a second worktree merging at once is seen,
    # and only what is still missing is added.
    theirs = _read_object(shared)
    if theirs is None:
        return shared, []
    lacking = sorted(k for k in mine if k not in theirs)
    if not lacking:
        return shared, []
    theirs.update({k: mine[k] for k in lacking})
    try:
        ensure_dir(top)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(shared), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(theirs, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp, shared)
        except OSError:
            os.remove(tmp)
            raise
    except OSError:
        return shared, []
    return shared, ["cai_paths: merged %s from %s into %s" % (", ".join(lacking), own, shared)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("ensure", "migrate"))
    ap.add_argument("--project-dir", default=".")
    args = ap.parse_args(argv)
    top = os.path.abspath(args.project_dir)
    if args.command == "migrate":
        for line in migrate(top):
            print(line)
        return 0
    try:
        print(ensure_dir(top))
    except OSError as exc:
        print("cai_paths: could not make %s (%s: %s)"
              % (os.path.join(top, CAI_DIR), type(exc).__name__, exc))
        return 2
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
