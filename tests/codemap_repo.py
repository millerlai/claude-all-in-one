"""Shared fixture helpers for the test_codemap_*.py files.

A real `git init` in `tmp_path`, never a fake git: the engine's whole job is
reading what git says. conftest.py already puts GIT_CEILING_DIRECTORIES above
`tmp_path`, so a repo made here is the one git finds.
"""
import os
import subprocess

GIT_IDENTITY = ["-c", "user.name=t", "-c", "user.email=t@example.invalid",
                "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]


def git(top, *args):
    done = subprocess.run(["git", *GIT_IDENTITY, *args], cwd=str(top),
                          capture_output=True, encoding="utf-8", errors="replace")
    assert done.returncode == 0, (args, done.stderr)
    return done.stdout


def write(top, rel, text, binary=False):
    path = os.path.join(str(top), *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if binary:
        with open(path, "wb") as fh:
            fh.write(text)
    else:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return path


def make_repo(top, files, commit=True):
    """`git init` at `top`, write `files` (rel posix path -> text) and, with
    `commit`, add and commit all of them."""
    git(top, "init", "-q")
    for rel, text in files.items():
        write(top, rel, text)
    git(top, "add", "-A")
    if commit:
        git(top, "commit", "-q", "-m", "init")
    return str(top)


def same_mtimes(src, dst):
    """Gives every file under `dst` that also exists under `src` src's mtime.
    File records carry mtime_ns (#448), so two trees compare byte for byte
    only when their files were last written at the same instant too."""
    for dirpath, dirnames, names in os.walk(str(dst)):
        dirnames[:] = [d for d in dirnames if d not in (".git", ".cai")]
        for name in names:
            rel = os.path.relpath(os.path.join(dirpath, name), str(dst))
            other = os.path.join(str(src), rel)
            if os.path.isfile(other):
                ns = os.stat(other).st_mtime_ns
                os.utime(os.path.join(dirpath, name), ns=(ns, ns))
