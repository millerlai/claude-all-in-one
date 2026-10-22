#!/usr/bin/env python3
"""Copies a finished track out of a linked worktree into the main checkout,
before the worktree, and the ignored `.cai/` inside it, is removed (#468).

`.cai/` ignores itself (cai_paths.py), and removing a worktree deletes its
ignored files, so a track that `/cai:track done` or `cancel` archived under
the worktree's `.cai/track/done/` would go with it -- and so would the
glossary terms build wrote into the worktree's `.cai/cai-context.md`. Run
right after the move into `done/`, this copies the archived track directory
to the main checkout's `.cai/track/done/` (`-1`, `-2` ... when that name is
taken) and adds the worktree's glossary entries the main checkout lacks,
each under the same `## ` heading. A term both define differently keeps the
main checkout's definition and is named, for a person to settle.

Outside a linked worktree it does nothing: the archive is already where it
stays. Every write is a file write from this script, which Claude Code's
worktree isolation does not refuse; its Edit and Write tools would be.

Usage:  track_archive.py --track-dir DIR [--project-dir DIR]
Exit:   0 done or nothing to do, 2 the copy failed (the last line says why),
        1 usage error.
"""
import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cai_paths  # noqa: E402
import glossary_check  # noqa: E402
import preflight  # noqa: E402

HEADING = re.compile(r"^## ")


def main_checkout(project_dir):
    """The main checkout's top when project_dir is a linked worktree, else
    None with the reason it stays put."""
    found = []
    for flag in ("--git-dir", "--git-common-dir"):
        done = preflight.git(project_dir, "rev-parse", flag)
        if done is None or done.returncode != 0:
            return None, "not a git work tree -- nothing to copy"
        found.append(os.path.realpath(os.path.join(project_dir, done.stdout.strip())))
    git_dir, common = found
    if os.path.normcase(git_dir) == os.path.normcase(common):
        return None, "not a linked worktree -- the archive stays where it is"
    if os.path.basename(common) != ".git":
        return None, "the main repository is bare -- no checkout to copy into"
    return os.path.dirname(common), None


def free_name(directory, name):
    target, n = os.path.join(directory, name), 0
    while os.path.exists(target):
        n += 1
        target = os.path.join(directory, "%s-%d" % (name, n))
    return target


def entries(text):
    """(heading, term key, line) for every glossary entry, in file order."""
    heading, out = None, []
    for line in text.splitlines():
        if HEADING.match(line):
            heading = line.rstrip()
            continue
        match = glossary_check.ENTRY.match(line)
        if match:
            out.append((heading, glossary_check.name_key(match.group("term")), line.rstrip()))
    return out


def merge_glossary(source_text, target_text):
    """(new target text, added terms, conflicting terms)."""
    have = {key: line for _, key, line in entries(target_text)}
    lines = target_text.splitlines()
    added, conflicts = [], []
    for heading, key, line in entries(source_text):
        heading = heading or "## Domain"
        if key in have:
            if have[key] != line:
                conflicts.append(line.split("**")[1])
            continue
        have[key] = line
        added.append(line.split("**")[1])
        if heading in lines:
            # After the last line of that heading's section.
            at = lines.index(heading) + 1
            while at < len(lines) and not HEADING.match(lines[at]):
                at += 1
            while at > lines.index(heading) + 1 and not lines[at - 1].strip():
                at -= 1
            lines.insert(at, line)
        else:
            lines += ["", heading, line]
    return "\n".join(lines) + "\n", added, conflicts


def write_atomic(path, text):
    # A plain open, not mkstemp: mkstemp's 0600 would replace the file's mode.
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def archive(track_dir, project_dir):
    """(exit code, lines to print)."""
    top, why = main_checkout(project_dir)
    if top is None:
        return 0, [why]
    out = []
    try:
        cai = cai_paths.ensure_dir(top)
        done = os.path.join(cai, "track", "done")
        os.makedirs(done, exist_ok=True)
        dest = free_name(done, os.path.basename(os.path.normpath(track_dir)))
        shutil.copytree(track_dir, dest)
        out.append("copied %s to %s" % (os.path.abspath(track_dir), dest))

        source = os.path.join(project_dir, cai_paths.GLOSSARY)
        if os.path.isfile(source):
            target = os.path.join(top, cai_paths.GLOSSARY)
            with open(source, encoding="utf-8") as fh:
                source_text = fh.read()
            if not os.path.isfile(target):
                write_atomic(target, source_text)
                out.append("glossary: copied to %s" % target)
            else:
                with open(target, encoding="utf-8") as fh:
                    text, added, conflicts = merge_glossary(source_text, fh.read())
                if added:
                    write_atomic(target, text)
                out.append("glossary: %d added to %s, %d conflicting"
                           % (len(added), target, len(conflicts)))
                out += ["conflict %s: kept the main checkout's definition" % term
                        for term in conflicts]
    except (OSError, UnicodeDecodeError) as exc:
        return 2, out + ["could not copy into the main checkout: %s" % exc]
    return 0, out


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--track-dir", required=True)
    ap.add_argument("--project-dir", default=".")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.track_dir):
        print("no such track directory: %s" % args.track_dir)
        return 2
    code, lines = archive(args.track_dir, os.path.abspath(args.project_dir))
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
