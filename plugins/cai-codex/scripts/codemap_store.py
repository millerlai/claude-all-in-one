"""Owns every byte under `<top>/.cai/codemap/`: the directory, the self-ignore
file written before anything else, data files staged and renamed under a write
lock, and the state file renamed last and checked on read.

Nothing here prints; a failure travels as an exception to codemap_cli.py, which
turns it into one state line.
"""
import errno
import hashlib
import json
import os
import stat
import sys
import tempfile
import time
from typing import NamedTuple, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preflight  # noqa: E402

INDEX_PARTS = (".cai", "codemap")
TRACKED_REASON = ".cai/codemap holds tracked files"
# 3: file records carry mtime_ns and state.json scanned_at_ns (#448).
# 4: state.json carries files_with_symbols, so status need not parse symbols.jsonl (#449).
SCHEMA_VERSION = 4
# Covers every piece of code that turns a file's path and bytes into records:
# codemap_inventory.LANGUAGES, MAX_PARSE_BYTES and the reasons read_tracked
# returns, codemap_index._facts_record and _parse, and all of
# codemap_symbols (MAX_SIGNATURE included). Bump it when any of them changes
# what a record says; an index written before the bump is then rebuilt.
EXTRACTOR_VERSION = 3
# A data file this large is not one this tool wrote; refusing it keeps a
# planted device, pipe or huge file from being read into memory.
MAX_ARTIFACT_BYTES = 1 << 28
STATE_NAME = "state.json"
FILES_NAME = "files.jsonl"
SYMBOLS_NAME = "symbols.jsonl"
REPO_MAP_NAME = "repo-map.md"
SELF_IGNORE_NAME = ".gitignore"
SELF_IGNORE_BODY = b"*\n"
LOCK_NAME = "write.lock"
BUSY_REASON = "another build or update is running"
FILE_MODE = 0o600   # mode for files os.open creates (.gitignore, lock file);
                    # mkstemp already gives 0o600
TEMP_SUFFIX = ".tmp"
# The bit a Windows reparse tag sets when the name stands for another named
# entity: a symlink or a junction, but not a cloud-sync placeholder.
NAME_SURROGATE_BIT = 0x20000000
# On Windows a target another process holds open refuses the rename; 5 tries
# 50 ms apart wait out at most 0.2 s of that.
REPLACE_ATTEMPTS = 5
REPLACE_DELAY_SECONDS = 0.05


class IndexUnreadable(Exception):
    """args[0] is a one-line reason."""


class Staged(NamedTuple):
    """A data file written to a temp file and not yet renamed."""
    name: str       # POSIX name inside the index directory, the artifacts key
    tmp: str        # absolute path of the temp file
    target: str     # absolute path it is renamed to
    sha256: str     # hex sha256 of the bytes written


class Index(NamedTuple):
    state: dict
    files: dict      # path -> file record (dict)
    symbols: Optional[list]   # symbol records, file order; None from load(symbols=False)


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


def _entry_kind(info) -> str:
    """'link', 'directory', 'file' or 'other', from an lstat result. A Windows
    junction lstats as a directory; its reparse tag is what says it leads elsewhere."""
    if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            and getattr(info, "st_reparse_tag", 0) & NAME_SURROGATE_BIT):
        return "link"
    if stat.S_ISDIR(info.st_mode):
        return "directory"
    if stat.S_ISREG(info.st_mode):
        return "file"
    return "other"


def _lstat_or_none(path: str):
    try:
        return os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None


def _check_inside_repository(top: str) -> str:
    """A tracked `.cai` symlink passes `tracked_inside` (git lists the link, not
    a path under it) and would carry every read, write and sweep outside the
    repository, past what typing `build` authorises. `packages` is the one
    directory below it that the writer creates files in, so it gets the same
    check."""
    path = index_dir(top)
    inside = os.path.join(os.path.realpath(top), *INDEX_PARTS)
    if os.path.normcase(os.path.realpath(path)) != os.path.normcase(inside):
        raise IndexUnreadable(".cai/codemap is not inside the repository")
    packages = os.path.join(path, "packages")      # same literal as _is_index_name
    info = _lstat_or_none(packages)
    if info is not None and (
            _entry_kind(info) != "directory"
            or os.path.normcase(os.path.realpath(packages))
            != os.path.normcase(os.path.join(inside, "packages"))):
        raise IndexUnreadable(".cai/codemap/packages is not a directory inside the repository")
    return path


def _ensure_self_ignore(path: str) -> None:
    """Makes `.gitignore` in the index directory `*\\n` without ever writing
    anywhere else: created exclusively, or compared and replaced through a temp
    file beside it. When the rename cannot be done the error travels; a direct
    write would follow a link planted at the name."""
    target = os.path.join(path, SELF_IGNORE_NAME)
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                     FILE_MODE)
    except FileExistsError:
        pass            # there already, or another writer just made it: compare it
    else:
        with os.fdopen(fd, "wb") as fh:
            fh.write(SELF_IGNORE_BODY)
        return
    fd = os.open(target, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as fh:
        if fh.read(len(SELF_IGNORE_BODY) + 1) == SELF_IGNORE_BODY:
            return
    fd, tmp = _new_temp(path, SELF_IGNORE_NAME)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(SELF_IGNORE_BODY)
        _replace_retrying(tmp, target)
    except BaseException:
        _unlink_quietly(tmp)
        raise


def ensure_dir(top: str) -> str:
    """Returns the index directory with its `.gitignore` guaranteed `*\\n`."""
    if tracked_inside(top):
        raise IndexUnreadable(TRACKED_REASON)
    path = _check_inside_repository(top)
    os.makedirs(path, exist_ok=True)
    # lstat before anything opens the name: a FIFO would block an open, and a
    # link would carry the write elsewhere. Both names are our own constants,
    # so the reason may echo them.
    for name in (SELF_IGNORE_NAME, LOCK_NAME):
        info = _lstat_or_none(os.path.join(path, name))
        if info is not None and _entry_kind(info) != "file":
            raise IndexUnreadable(".cai/codemap/%s is not a regular file" % name)
    _ensure_self_ignore(path)
    return path


def _new_temp(directory: str, base: str) -> tuple:
    """(fd, path) of a file just created exclusively beside `base`, under a name
    nobody could have planted a link at."""
    return tempfile.mkstemp(dir=directory, prefix=base + ".", suffix=TEMP_SUFFIX)


def _unlink_quietly(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _replace_retrying(src: str, dst: str) -> None:
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_DELAY_SECONDS)


def write_atomic(top: str, name: str, data: bytes) -> Staged:
    """First half of an atomic write: `data` goes into a new temp file beside
    `name` and `publish` renames it. Still called write_atomic because tests
    replace it to stop a build before its first data file."""
    target = os.path.join(index_dir(top), *name.split("/"))
    directory = os.path.dirname(target)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = _new_temp(directory, os.path.basename(target))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except BaseException:
        _unlink_quietly(tmp)
        raise
    return Staged(name, tmp, target, hashlib.sha256(data).hexdigest())


def commit_state(top: str, state: dict) -> Staged:
    """The state file, staged like the rest; `publish` renames it last so it
    vouches only for data files that are already in place."""
    text = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    return write_atomic(top, STATE_NAME, text.encode("utf-8"))


def publish(staged: list) -> None:
    for item in staged:
        _replace_retrying(item.tmp, item.target)


def discard(staged: list) -> None:
    """Removes the temp files that are still there; never raises, because it
    runs while another exception is on its way to the caller."""
    for item in staged:
        _unlink_quietly(item.tmp)


def check_entries(top: str) -> None:
    """Refuses the whole write when anything in the index directory, walked
    through real directories only, is not a regular file or a directory. Called
    with the lock held, so no other writer is renaming names under it. The
    reason does not echo the name: it comes from the file system, and on POSIX
    it may hold a newline."""
    pending = [index_dir(top)]
    while pending:
        directory = pending.pop()
        for name in os.listdir(directory):
            full = os.path.join(directory, name)
            info = _lstat_or_none(full)
            if info is None:
                continue
            kind = _entry_kind(info)
            if kind == "directory":
                pending.append(full)
            elif kind != "file":
                raise IndexUnreadable(
                    ".cai/codemap holds an entry that is not a regular file or directory")


def check_targets(top: str, names) -> None:
    """Refuses the write when one of the names it is about to rename onto is
    something other than a regular file. `check_entries` lets every real
    directory through, since `packages/` must be one; a directory sitting on a
    data file's name would fail its rename halfway through `publish`, after
    earlier data files were already replaced, and every later `build` would
    fail the same way. Called before anything is staged, so the previous
    index stays exactly as it was."""
    for name in names:
        info = _lstat_or_none(os.path.join(index_dir(top), *name.split("/")))
        if info is not None and _entry_kind(info) != "file":
            raise IndexUnreadable(".cai/codemap holds a directory where a data file goes")


def acquire_write_lock(top: str) -> int:
    """Takes the index directory's write lock without waiting; returns the fd
    that `release_write_lock` gives back. The lock file is never deleted: on
    POSIX a new file would be a new inode, and two writers would both hold it."""
    path = os.path.join(index_dir(top), LOCK_NAME)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
                 | getattr(os, "O_NOFOLLOW", 0), FILE_MODE)
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        # Only "someone holds it" is the busy answer; a filesystem that cannot
        # lock at all must not read as another writer.
        if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
            raise IndexUnreadable(BUSY_REASON) from None
        raise
    return fd


def release_write_lock(fd: int) -> None:
    """Never raises: it runs in a `finally`, and a new exception there would
    replace the one the caller is about to see."""
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass        # closing the fd below releases it anyway
    try:
        os.close(fd)
    except OSError:
        pass


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
    count = state.get("files_with_symbols")
    return _str_or_none(state.get("head")) and _is_int(state.get("scanned_at_ns")) \
        and _is_int(count) and count >= 0 \
        and isinstance(partial, list) and all(
        isinstance(entry, dict) and isinstance(entry.get("path"), str) for entry in partial)


def _is_file_record(record) -> bool:
    """A key read with `.get` may be absent; one read with `[]` may not. A field
    the tool itself writes as null (`sha256`, `reason`, `confidence`) stays null."""
    return (isinstance(record, dict) and isinstance(record.get("path"), str)
            and isinstance(record.get("language"), str)
            and all(_str_or_none(record.get(k)) for k in ("sha256", "reason", "confidence"))
            and all(record.get(k) is None or _is_int(record.get(k))
                    for k in ("bytes", "mtime_ns")))


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


def load(top: str, symbols: bool = True) -> Optional[Index]:
    """None when there is no state file; raises IndexUnreadable when the state
    file or any file it vouches for cannot be trusted. symbols=False (status)
    still checks symbols.jsonl against its sha256 but does not parse it or
    check its records' shape -- the bulk of a large index's load, for a count
    state.json already holds -- and leaves Index.symbols None (#449)."""
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
        records = None
        if symbols:
            records = []
            for line in _records(blobs[SYMBOLS_NAME]):
                record = json.loads(line)
                if not _is_symbol_record(record):
                    raise ValueError("not a symbol record")
                records.append(record)
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        raise IndexUnreadable("a data file holds a line that is not a record")
    return Index(state, files, records)


def sweep(top: str, keep: set) -> None:
    """Removes `*.tmp` leftovers and data files the state no longer names.
    `keep` holds POSIX names relative to the index directory. Only regular
    files are deleted and only real directories are entered: a link or a
    special file is left where it is, since `os.walk` would walk into a Windows
    junction and `os.rmdir` would then remove the junction itself."""
    _sweep(index_dir(top), "", set(keep) | {STATE_NAME, SELF_IGNORE_NAME, LOCK_NAME})


def _sweep(directory: str, rel_dir: str, keep: set) -> None:
    for name in os.listdir(directory):
        full = os.path.join(directory, name)
        rel = rel_dir + "/" + name if rel_dir else name
        info = _lstat_or_none(full)
        kind = _entry_kind(info) if info is not None else None
        if kind == "directory":
            _sweep(full, rel, keep)
            try:
                os.rmdir(full)
            except OSError:
                pass        # still holds a kept file
        elif kind == "file" and rel not in keep:
            _unlink_quietly(full)
