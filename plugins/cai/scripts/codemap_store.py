"""Owns every byte under `<top>/.cai/codemap/`: the directory, the self-ignore
file written before anything else, atomic data files, and the state file written
last and checked on read.

Nothing here prints; a failure travels as an exception to codemap_cli.py, which
turns it into one state line.
"""
import hashlib
import json
import os
import stat
import sys
from typing import NamedTuple, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preflight  # noqa: E402

INDEX_PARTS = (".cai", "codemap")
SCHEMA_VERSION = 2
# Covers every piece of code that turns a file's path and bytes into records:
# codemap_inventory.LANGUAGES and the reasons read_tracked returns,
# codemap_index.MAX_PARSE_BYTES, _facts_record and _parse, and all of
# codemap_symbols (MAX_SIGNATURE included). Bump it when any of them changes
# what a record says; an index written before the bump is then rebuilt.
EXTRACTOR_VERSION = 1
# A data file this large is not one this tool wrote; refusing it keeps a
# planted device, pipe or huge file from being read into memory.
MAX_ARTIFACT_BYTES = 1 << 28
STATE_NAME = "state.json"
FILES_NAME = "files.jsonl"
SYMBOLS_NAME = "symbols.jsonl"
REPO_MAP_NAME = "repo-map.md"
SELF_IGNORE_NAME = ".gitignore"
SELF_IGNORE_BODY = b"*\n"


class IndexUnreadable(Exception):
    """args[0] is a one-line reason."""


class Index(NamedTuple):
    state: dict
    files: dict      # path -> file record (dict)
    symbols: list    # symbol records, file order


def extractor_stamp() -> dict:
    """The state fields that say which extractor and which Python wrote an index."""
    return {"extractor_version": EXTRACTOR_VERSION,
            "python_version": "%d.%d" % sys.version_info[:2]}


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


def _check_inside_repository(top: str) -> str:
    """A tracked `.cai` symlink passes `tracked_inside` (git lists the link, not
    a path under it) and would carry every read, write and sweep outside the
    repository, past what typing `build` authorises."""
    path = index_dir(top)
    inside = os.path.join(os.path.realpath(top), *INDEX_PARTS)
    if os.path.normcase(os.path.realpath(path)) != os.path.normcase(inside):
        raise IndexUnreadable(".cai/codemap is not inside the repository")
    return path


def ensure_dir(top: str) -> str:
    """Returns the index directory with its `.gitignore` guaranteed `*\\n`."""
    if tracked_inside(top):
        raise IndexUnreadable(".cai/codemap holds tracked files")
    path = _check_inside_repository(top)
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
    # lstat, not open-then-fstat: a symlink, device or pipe is refused before it
    # is opened. FileNotFoundError still travels as itself.
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARTIFACT_BYTES:
        raise IndexUnreadable("%s is not a regular file of at most %d bytes"
                              % (os.path.basename(path), MAX_ARTIFACT_BYTES))
    with open(path, "rb") as fh:
        data = fh.read(MAX_ARTIFACT_BYTES + 1)
    if len(data) > MAX_ARTIFACT_BYTES:
        raise IndexUnreadable("%s grew past %d bytes while it was read"
                              % (os.path.basename(path), MAX_ARTIFACT_BYTES))
    return data


def _is_index_name(name) -> bool:
    """state.json names the files it vouches for, and it is a file on disk like
    any other: one name, or one name under `packages/`, never a way out."""
    if not isinstance(name, str):
        return False
    parts = name.split("/")
    if not (len(parts) == 1 or (len(parts) == 2 and parts[0] == "packages")):
        return False
    return all(p not in ("", ".", "..", STATE_NAME) and not set(p) & set("\\:\0")
               for p in parts)


def _is_int(value) -> bool:
    # bool is a subclass of int, and JSON `true` would otherwise pass for a line.
    return isinstance(value, int) and not isinstance(value, bool)


def _str_or_none(value) -> bool:
    return value is None or isinstance(value, str)


def _is_state(state: dict) -> bool:
    """The state.json fields the readers use that `load` does not already check.
    Only fields a reader takes are looked at: one nobody reads cannot hurt."""
    partial = state.get("partial", [])
    return _str_or_none(state.get("head")) and isinstance(partial, list) and all(
        isinstance(entry, dict) and isinstance(entry.get("path"), str) for entry in partial)


def _is_file_record(record) -> bool:
    """A key read with `.get` may be absent; one read with `[]` may not. A field
    the tool itself writes as null (`sha256`, `reason`, `confidence`) stays null."""
    return (isinstance(record, dict) and isinstance(record.get("path"), str)
            and isinstance(record.get("language"), str)
            and all(_str_or_none(record.get(k)) for k in ("sha256", "reason", "confidence")))


def _is_symbol_record(record) -> bool:
    return (isinstance(record, dict)
            and all(isinstance(record.get(k), str)
                    for k in ("path", "qualified_name", "name", "kind"))
            and _is_int(record.get("start_line"))
            and (record.get("end_line") is None or _is_int(record.get("end_line")))
            and _str_or_none(record.get("signature")))


def _records(blob: bytes) -> list:
    """The lines of a JSONL file. Split on `\\n` only: `json.dumps` escapes a
    newline inside a record but leaves U+2028, U+2029 and U+0085 raw, and
    `str.splitlines` would cut a record at each of them."""
    parts = blob.decode("utf-8").split("\n")
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def load(top: str) -> Optional[Index]:
    """None when there is no state file; raises IndexUnreadable when the state
    file or any file it vouches for cannot be trusted."""
    root = _check_inside_repository(top)
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
    if not isinstance(state, dict):
        raise IndexUnreadable("state.json has the wrong shape or schema_version")
    # Before schema_version: an index from before the stamp existed is both, and
    # "another codemap wrote it" is the reason that helps the person reading it.
    if any(state.get(key) != value for key, value in extractor_stamp().items()):
        raise IndexUnreadable("built by another codemap or Python version")
    if state.get("schema_version") != SCHEMA_VERSION \
            or not isinstance(state.get("artifacts"), dict) or not _is_state(state):
        raise IndexUnreadable("state.json has the wrong shape or schema_version")
    # The readers open these three by name; a table that does not list one would
    # leave it unchecked against its digest.
    for name in (FILES_NAME, SYMBOLS_NAME, REPO_MAP_NAME):
        if name not in state["artifacts"]:
            raise IndexUnreadable("%s is missing" % name)
    blobs = {}
    for name, digest in state["artifacts"].items():
        if not _is_index_name(name):
            # The name itself is not echoed: it came from a file we do not trust.
            raise IndexUnreadable("state.json names a file outside the index directory")
        try:
            data = _read(os.path.join(root, *name.split("/")))
        except OSError:
            raise IndexUnreadable("%s is missing" % name)
        if hashlib.sha256(data).hexdigest() != digest:
            raise IndexUnreadable("%s does not match state.json (index files disagree)" % name)
        blobs[name] = data
    try:
        files = {}
        for line in _records(blobs[FILES_NAME]):
            record = json.loads(line)
            if not _is_file_record(record):
                raise ValueError("not a file record")
            files[record["path"]] = record
        symbols = []
        for line in _records(blobs[SYMBOLS_NAME]):
            record = json.loads(line)
            if not _is_symbol_record(record):
                raise ValueError("not a symbol record")
            symbols.append(record)
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
