"""Turns `git ls-files -z --stage` into a sorted list of facts about each
tracked file: path, language, size, sha256, and why a file was not read.

Read-only and repeatable. A file edited while it is read is recorded as it was
at that instant; the next status sees the mismatch and reports stale.
"""
import hashlib
import os
import sys
from typing import NamedTuple, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preflight  # noqa: E402

LANGUAGES = {".py": "python", ".go": "go", ".ts": "typescript", ".tsx": "typescript",
             ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
             ".cjs": "javascript"}
CHUNK = 1 << 16


class NotARepository(Exception): ...
class GitFailed(Exception): ...


class FileFacts(NamedTuple):
    path: str               # POSIX, as git prints it
    language: str           # "python" | "go" | "typescript" | "javascript" | "other"
    bytes: Optional[int]
    sha256: Optional[str]
    reason: Optional[str]   # None, or "symlink" | "submodule" | "missing" | "path-not-utf8"


def language_of(path: str) -> str:
    return LANGUAGES.get(os.path.splitext(path)[1].lower(), "other")


def list_tracked(top: str) -> list:
    """[(mode, path)] sorted by path. -z so a name with a newline or a quote
    reaches us as it is, not as git's C-quoting of it."""
    state = preflight.is_git_repo(top)
    if state is preflight.GIT_DID_NOT_ANSWER:
        raise GitFailed("git did not answer")
    if not state:
        raise NotARepository(top)
    done = preflight.git(top, "ls-files", "-z", "--stage")
    if done is None or done.returncode != 0:
        raise GitFailed("git ls-files failed")
    seen = {}
    for entry in done.stdout.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        seen.setdefault(path, meta.split(" ")[0])   # an unmerged path appears 3 times
    return sorted(((mode, path) for path, mode in seen.items()), key=lambda m: m[1])


def facts(top: str, mode: str, path: str) -> FileFacts:
    language = language_of(path)
    if "�" in path:
        return FileFacts(path, language, None, None, "path-not-utf8")
    if mode == "120000":
        return FileFacts(path, language, None, None, "symlink")
    if mode == "160000":
        return FileFacts(path, language, None, None, "submodule")
    full = os.path.join(top, *path.split("/"))
    digest = hashlib.sha256()
    size = 0
    try:
        with open(full, "rb") as fh:
            while True:
                chunk = fh.read(CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
    except OSError:
        return FileFacts(path, language, None, None, "missing")
    return FileFacts(path, language, size, digest.hexdigest(), None)


def inventory(top: str) -> list:
    return [facts(top, mode, path) for mode, path in list_tracked(top)]
