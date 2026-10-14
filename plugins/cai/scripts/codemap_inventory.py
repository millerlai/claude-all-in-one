"""Turns `git ls-files -z --stage` into a sorted list of facts about each
tracked file: path, language, size, sha256, mtime, and why a file was not
read. A file the last index still vouches for keeps its recorded sha256
without being read (read_tracked's `known`).

Read-only and repeatable. A file edited while it is read is recorded as it was
at that instant; the next status sees the mismatch and reports stale.
"""
import errno
import hashlib
import os
import stat
import sys
from typing import NamedTuple, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preflight  # noqa: E402

LANGUAGES = {".py": "python", ".go": "go", ".ts": "typescript", ".tsx": "typescript",
             ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
             ".cjs": "javascript"}
CHUNK = 1 << 16
# Listing every tracked file of a large repository can take longer than the
# five seconds other git calls get, and a timeout here makes the whole index
# unsupported for that repository.
LIST_TIMEOUT = 60
# Over this a file is hashed but not parsed or scanned: one generated giant
# must not slow every dispatch. The one cap both reads share.
MAX_PARSE_BYTES = 1048576
ERROR_INVALID_NAME = 123    # Windows: the name's syntax is not one the filesystem accepts
# A record is trusted without reading the file only when the file's mtime is at
# least this much older than the scan that recorded it. A second write inside
# the same timestamp tick keeps the mtime, so a file modified that close to the
# scan is "racy" and always hashed again; 2 s is FAT's tick, the coarsest a
# local file system uses (#448).
RACY_NS = 2 * 10**9


class NotARepository(Exception): ...
class GitFailed(Exception): ...


class FileFacts(NamedTuple):
    path: str               # POSIX, as git prints it
    language: str           # "python" | "go" | "typescript" | "javascript" | "other"
    bytes: Optional[int]
    sha256: Optional[str]
    reason: Optional[str]   # None, or "symlink" | "submodule" | "path-not-utf8" |
                            # "missing" | "not-regular" | "outside-repository" |
                            # "cannot-open: <exception type>"
    mtime_ns: Optional[int] = None   # lstat's, taken before the file is read


CANNOT_OPEN = "cannot-open"     # prefix of "cannot-open: <exception type>"; _parse tests it


class TrackedRead(NamedTuple):
    reason: Optional[str]   # None, "missing", "not-regular", "outside-repository",
                            # or CANNOT_OPEN + ": " + type(exc).__name__
    size: Optional[int]     # bytes read; None when reason is not None
    sha256: Optional[str]   # hex sha256 of the bytes read; None when reason is not None
    data: Optional[bytes]   # the bytes read when limit is given, else None
    mtime_ns: Optional[int] = None   # lstat's, taken before the file is read


def language_of(path: str) -> str:
    return LANGUAGES.get(os.path.splitext(path)[1].lower(), "other")


def list_tracked(top: str) -> list:
    """[(mode, path, utf8)] sorted by path. -z so a name with a newline or a
    quote reaches us as it is, not as git's C-quoting of it; read as bytes, so
    two names that differ only in bytes that are not UTF-8 stay two entries
    and a carriage return in a name is not turned into a newline. A name that
    is not UTF-8 has `utf8` False and its bad bytes written as `\\xNN`."""
    state = preflight.is_git_repo(top)
    if state is preflight.GIT_DID_NOT_ANSWER:
        raise GitFailed("git did not answer")
    if not state:
        raise NotARepository(top)
    done = preflight.git(top, "ls-files", "-z", "--stage", raw=True, timeout=LIST_TIMEOUT)
    if done is None or done.returncode != 0:
        raise GitFailed("git ls-files failed")
    seen = {}
    for entry in done.stdout.split(b"\0"):
        if not entry:
            continue
        meta, _, raw = entry.partition(b"\t")
        seen.setdefault(raw, meta.split(b" ")[0].decode("ascii"))   # an unmerged path appears 3 times
    out = []
    for raw, mode in seen.items():
        try:
            out.append((mode, raw.decode("utf-8"), True))
        except UnicodeDecodeError:
            out.append((mode, raw.decode("utf-8", "backslashreplace"), False))
    return sorted(out, key=lambda m: m[1])


def skip_reason(mode: str, utf8: bool) -> Optional[str]:
    """Why a listed path is never opened, or None. One rule for the inventory
    and for the query's text scan, so a new reason reaches both."""
    if not utf8:
        return "path-not-utf8"
    if mode == "120000":
        return "symlink"
    if mode == "160000":
        return "submodule"
    return None


def facts(top_real: str, mode: str, path: str, utf8: bool = True, known=None) -> FileFacts:
    language = language_of(path)
    skip = skip_reason(mode, utf8)
    if skip is not None:
        return FileFacts(path, language, None, None, skip)
    got = read_tracked(top_real, path, known=known)
    return FileFacts(path, language, got.size, got.sha256, got.reason, got.mtime_ns)


def _known(record, scanned_at_ns):
    """(size, mtime_ns, sha256, scanned_at_ns) a record can vouch with, or None
    when it lacks any of them."""
    if not isinstance(record, dict) or not isinstance(scanned_at_ns, int):
        return None
    size, mtime, sha = record.get("bytes"), record.get("mtime_ns"), record.get("sha256")
    if isinstance(size, int) and isinstance(mtime, int) and isinstance(sha, str):
        return size, mtime, sha, scanned_at_ns
    return None


def inventory(top: str, records=None, scanned_at_ns=None, listed=None) -> list:
    """Facts for every tracked file. `records` (path -> file record) and
    `scanned_at_ns` come from the last index written: a file they still
    describe is not read again (read_tracked's `known`). `listed` is
    list_tracked's answer when the caller already has it."""
    top_real = os.path.realpath(top)   # once per call, not once per file
    records = records or {}
    return [facts(top_real, mode, path, utf8, _known(records.get(path), scanned_at_ns))
            for mode, path, utf8 in (list_tracked(top) if listed is None else listed)]


def _refused(reason: str) -> "TrackedRead":
    return TrackedRead(reason, None, None, None)


def _cannot_open(exc: OSError) -> "TrackedRead":
    return _refused("%s: %s" % (CANNOT_OPEN, type(exc).__name__))


def read_tracked(top_real: str, path: str, limit: Optional[int] = None,
                 known=None) -> TrackedRead:
    """top_real must be os.path.realpath(top), computed once by the caller.
    limit None: read to end of file, keep only the hash (inventory).
    limit N: read at most N + 1 bytes and return them (_parse, tracked_texts);
    a caller that gets more than N bytes treats the file as over the cap.
    known (inventory only): (size, mtime_ns, sha256, scanned_at_ns) from the
    last index. When lstat still shows that size and mtime and the mtime is
    RACY_NS older than that scan, the recorded sha256 is returned unread: any
    write after the scan would have moved the mtime past it (#448).

    The path is looked at before it is opened: a FIFO would block the open, and a
    link would carry the read outside the repository. Every OSError becomes a
    reason; nothing but a program error travels out."""
    full = os.path.join(top_real, *path.split("/"))
    try:
        info = os.lstat(full)
    except (FileNotFoundError, NotADirectoryError):
        return _refused("missing")
    except OSError as exc:
        # A name the filesystem refuses outright (Windows `?` or `"`, an over-long
        # component) cannot have been checked out: the file is absent, not unopenable.
        if getattr(exc, "winerror", None) == ERROR_INVALID_NAME or exc.errno == errno.ENAMETOOLONG:
            return _refused("missing")
        return _cannot_open(exc)
    if not stat.S_ISREG(info.st_mode):
        return _refused("not-regular")
    # A parent directory may be a link; both sides are real paths so a repo that
    # itself sits under a link (macOS /tmp) is not taken for being outside.
    root = os.path.normcase(top_real)
    try:
        if os.path.commonpath([root, os.path.normcase(os.path.realpath(full))]) != root:
            return _refused("outside-repository")
    except ValueError:   # different drives on Windows
        return _refused("outside-repository")
    mtime = info.st_mtime_ns
    if known is not None and limit is None:
        size, recorded, sha, scanned_at = known
        if info.st_size == size and mtime == recorded and mtime + RACY_NS <= scanned_at:
            return TrackedRead(None, size, sha, None, mtime)
    try:
        fd = os.open(full, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_BINARY", 0))
    except (FileNotFoundError, NotADirectoryError):
        return _refused("missing")
    except OSError as exc:
        return _cannot_open(exc)
    try:
        if limit is None:
            digest, size = hashlib.sha256(), 0
            while True:
                chunk = os.read(fd, CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
            return TrackedRead(None, size, digest.hexdigest(), None, mtime)
        buf = bytearray()
        while len(buf) <= limit:
            chunk = os.read(fd, min(CHUNK, limit + 1 - len(buf)))
            if not chunk:
                break
            buf += chunk
        return TrackedRead(None, len(buf), hashlib.sha256(buf).hexdigest(), bytes(buf), mtime)
    except OSError as exc:
        return _cannot_open(exc)
    finally:
        os.close(fd)
