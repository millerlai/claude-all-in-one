"""Owns every byte under `<top>/.cai/codemap/`: the directory, the self-ignore
file written before anything else, atomic data files, and the state file written
last and checked on read.

Nothing here prints; a failure travels as an exception to codemap_cli.py, which
turns it into one state line.
"""
import hashlib
import json
import os
import sys
from typing import NamedTuple, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preflight  # noqa: E402

INDEX_PARTS = (".cai", "codemap")
SCHEMA_VERSION = 1
STATE_NAME = "state.json"
FILES_NAME = "files.jsonl"
SYMBOLS_NAME = "symbols.jsonl"
SELF_IGNORE_NAME = ".gitignore"
SELF_IGNORE_BODY = b"*\n"


class IndexUnreadable(Exception):
    """args[0] is a one-line reason."""


class Index(NamedTuple):
    state: dict
    files: dict      # path -> file record (dict)
    symbols: list    # symbol records, file order


def index_dir(top: str) -> str:
    return os.path.join(top, *INDEX_PARTS)


def _git(top, *args):
    done = preflight.git(top, *args)
    if done is None or done.returncode != 0:
        raise OSError("git did not answer")
    return done.stdout


def tracked_inside(top: str) -> bool:
    out = _git(top, "ls-files", "-z", "--", "/".join(INDEX_PARTS))
    return bool(out.strip("\0"))


def _write_self_ignore(top: str, target: str) -> None:
    """The temp file lives in the git directory, never in the working tree:
    killed half-way, `git status` has nothing to show (T3-1)."""
    git_dir = os.path.join(top, _git(top, "rev-parse", "--git-dir").strip())
    tmp = os.path.join(git_dir, "cai-codemap-gitignore.%d.tmp" % os.getpid())
    with open(tmp, "wb") as fh:
        fh.write(SELF_IGNORE_BODY)
    try:
        os.replace(tmp, target)
    except OSError:
        # A different filesystem: the one place a direct write is the only way.
        with open(target, "wb") as fh:
            fh.write(SELF_IGNORE_BODY)


def ensure_dir(top: str) -> str:
    """Returns the index directory with its `.gitignore` guaranteed `*\\n`."""
    if tracked_inside(top):
        raise IndexUnreadable(".cai/codemap holds tracked files")
    path = index_dir(top)
    # A tracked `.cai` symlink passes the check above (git lists the link, not
    # a path under it) and would carry every write and every sweep outside the
    # repository, past what typing `build` authorises.
    inside = os.path.join(os.path.realpath(top), *INDEX_PARTS)
    if os.path.normcase(os.path.realpath(path)) != os.path.normcase(inside):
        raise IndexUnreadable(".cai/codemap is not inside the repository")
    os.makedirs(path, exist_ok=True)
    target = os.path.join(path, SELF_IGNORE_NAME)
    try:
        with open(target, "rb") as fh:
            if fh.read() == SELF_IGNORE_BODY:
                return path
    except OSError:
        pass
    _write_self_ignore(top, target)
    return path


def write_atomic(top: str, name: str, data: bytes) -> str:
    """Writes `name` (a POSIX path inside the index directory) through a
    temp file and `os.replace`; returns the sha256 hex of `data`."""
    target = os.path.join(index_dir(top), *name.split("/"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = "%s.%d.tmp" % (target, os.getpid())
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, target)
    return hashlib.sha256(data).hexdigest()


def commit_state(top: str, state: dict) -> None:
    """Last step of every write: the state file vouches for the data files."""
    text = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    write_atomic(top, STATE_NAME, text.encode("utf-8"))


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def load(top: str) -> Optional[Index]:
    """None when there is no state file; raises IndexUnreadable when the state
    file or any file it vouches for cannot be trusted."""
    root = index_dir(top)
    try:
        raw = _read(os.path.join(root, STATE_NAME))
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise IndexUnreadable("state.json cannot be read (%s)" % type(exc).__name__)
    try:
        state = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise IndexUnreadable("state.json is not valid JSON")
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION \
            or not isinstance(state.get("artifacts"), dict):
        raise IndexUnreadable("state.json has the wrong shape or schema_version")
    blobs = {}
    for name, digest in state["artifacts"].items():
        try:
            data = _read(os.path.join(root, *name.split("/")))
        except OSError:
            raise IndexUnreadable("%s is missing" % name)
        if hashlib.sha256(data).hexdigest() != digest:
            raise IndexUnreadable("%s does not match state.json (index files disagree)" % name)
        blobs[name] = data
    try:
        files = {}
        for line in blobs.get(FILES_NAME, b"").decode("utf-8").splitlines():
            record = json.loads(line)
            files[record["path"]] = record
        symbols = [json.loads(line)
                   for line in blobs.get(SYMBOLS_NAME, b"").decode("utf-8").splitlines()]
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        raise IndexUnreadable("a data file holds a line that is not a record")
    return Index(state, files, symbols)


def sweep(top: str, keep: set) -> None:
    """Removes `*.tmp` leftovers and data files the state no longer names.
    `keep` holds POSIX names relative to the index directory."""
    root = index_dir(top)
    always = {STATE_NAME, SELF_IGNORE_NAME}
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        for filename in filenames:
            rel = filename if rel_dir == "." else rel_dir + "/" + filename
            if rel in always or rel in keep:
                continue
            try:
                os.remove(os.path.join(dirpath, filename))
            except OSError:
                pass
        if rel_dir != ".":
            try:
                os.rmdir(dirpath)
            except OSError:
                pass
