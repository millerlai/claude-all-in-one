"""Turns `git ls-files -z --stage` into a sorted list of facts about each
tracked file: path, language, size, sha256, and why a file was not read.

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
ERROR_INVALID_NAME = 123    # Windows: the name's syntax is not one the filesystem accepts


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


CANNOT_OPEN = "cannot-open"     # prefix of "cannot-open: <exception type>"; _parse tests it


class TrackedRead(NamedTuple):
    reason: Optional[str]   # None, "missing", "not-regular", "outside-repository",
                            # or CANNOT_OPEN + ": " + type(exc).__name__
    size: Optional[int]     # bytes read; None when reason is not None
    sha256: Optional[str]   # hex sha256 of the bytes read; None when reason is not None
    data: Optional[bytes]   # the bytes read when limit is given, else None


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
    done = preflight.git(top, "ls-files", "-z", "--stage", raw=True)
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


def facts(top_real: str, mode: str, path: str, utf8: bool = True) -> FileFacts:
    language = language_of(path)
    if not utf8:
        return FileFacts(path, language, None, None, "path-not-utf8")
    if mode == "120000":
        return FileFacts(path, language, None, None, "symlink")
    if mode == "160000":
        return FileFacts(path, language, None, None, "submodule")
    got = read_tracked(top_real, path)
    return FileFacts(path, language, got.size, got.sha256, got.reason)


def inventory(top: str) -> list:
    top_real = os.path.realpath(top)   # once per call, not once per file
    return [facts(top_real, mode, path, utf8) for mode, path, utf8 in list_tracked(top)]


def _refused(reason: str) -> "TrackedRead":
    return TrackedRead(reason, None, None, None)


def _cannot_open(exc: OSError) -> "TrackedRead":
    return _refused("%s: %s" % (CANNOT_OPEN, type(exc).__name__))


def read_tracked(top_real: str, path: str, limit: Optional[int] = None) -> TrackedRead:
    """top_real must be os.path.realpath(top), computed once by the caller.
    limit None: read to end of file, keep only the hash (inventory).
    limit N: read at most N + 1 bytes and return them (_parse, tracked_texts);
    a caller that gets more than N bytes treats the file as over the cap.

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
            return TrackedRead(None, size, digest.hexdigest(), None)
        buf = bytearray()
        while len(buf) <= limit:
            chunk = os.read(fd, min(CHUNK, limit + 1 - len(buf)))
            if not chunk:
                break
            buf += chunk
        return TrackedRead(None, len(buf), hashlib.sha256(buf).hexdigest(), bytes(buf))
    except OSError as exc:
        return _cannot_open(exc)
    finally:
        os.close(fd)
