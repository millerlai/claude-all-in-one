#!/usr/bin/env python3
"""
Decide, by comparing hashes rather than by a model's reading, whether setup may
overwrite a file it installed earlier, and keep a timestamped copy of anything
it is about to change (#455).

    python setup_files.py status --dest DIR [--diff]   # one line per shipped rule
    python setup_files.py install --dest DIR [--overwrite NAME ...]
    python setup_files.py backup FILE               # copy FILE aside, print where

`status` and `install` compare `<plugin-root>/rules/*.md` (`--src` overrides
it) with the installed copies in `--dest`, Claude Code's user rules directory.
Each file is in one state:

    absent            not installed yet                 -> written
    identical         same text as the shipped copy     -> left alone
    stale-unmodified  what cai last wrote, now outdated -> backed up, rewritten
    user-modified     differs from what cai last wrote  -> backed up and
                      rewritten only when named with --overwrite, else skipped

"What cai last wrote" is the sha256 kept in `<dest>/.cai-manifest.json`. A file
with no recorded hash -- every file of an install older than the manifest --
counts as user-modified, the cautious reading. The manifest's name neither
ends in `.md` nor is loaded as a rule; nor is a backup, named
`<name>.<YYYY-MM-DD-HHMMSS>.bak` beside the original, with `-1`, `-2` ... added
when that name is taken within the same second. The Codex installer keeps its
AGENTS.md block's hash in the same format, through the functions below.

Comparison ignores line endings and the language named on communication.md's
`- Respond in ...` line, which setup itself rewrites; a rewrite keeps the
language the installed copy names, so an update no longer resets it.
"""
from __future__ import annotations
import argparse
import datetime
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

MANIFEST_NAME = ".cai-manifest.json"
FORMAT = 1
LANGUAGE_RE = re.compile(
    r"^- Respond in [^;\r\n]+; keep technical terms in their original form\.(?=\r?$)",
    re.MULTILINE)
CANONICAL_LANGUAGE = "- Respond in English; keep technical terms in their original form."


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", "replace")


def normalize(text: str) -> str:
    return LANGUAGE_RE.sub(CANONICAL_LANGUAGE, text.replace("\r\n", "\n"))


def digest(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def carry_language(new: str, old: str) -> str:
    """`new` with the language line `old` names, when both have one."""
    found = LANGUAGE_RE.search(old)
    if not found:
        return new
    return LANGUAGE_RE.sub(lambda _: found.group(0), new, count=1)


def state(installed: str | None, shipped: str, recorded: str | None) -> str:
    if installed is None:
        return "absent"
    if normalize(installed) == normalize(shipped):
        return "identical"
    if recorded == digest(installed):
        return "stale-unmodified"
    return "user-modified"


def load_manifest(directory: Path) -> dict[str, str]:
    """Recorded hashes by file name; an unreadable manifest records nothing,
    so every file it would have vouched for is treated as user-modified."""
    try:
        data = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
        files = data["files"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    if data.get("format") != FORMAT or not isinstance(files, dict):
        return {}
    return {k: v for k, v in files.items() if isinstance(k, str) and isinstance(v, str)}


def save_manifest(directory: Path, files: dict[str, str]):
    body = json.dumps({"format": FORMAT, "files": dict(sorted(files.items()))}, indent=2)
    atomic_write(directory / MANIFEST_NAME, (body + "\n").encode("utf-8"))


def atomic_write(path: Path, data: bytes):
    # Through a symlinked rule to the file it names, as `cp` did, rather than
    # replacing the link with a copy.
    path = Path(os.path.realpath(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def backup(path: Path, now: datetime.datetime | None = None) -> Path:
    stamp = (now or datetime.datetime.now()).strftime("%Y-%m-%d-%H%M%S")
    target = path.with_name(f"{path.name}.{stamp}.bak")
    n = 0
    while target.exists():
        n += 1
        target = path.with_name(f"{path.name}.{stamp}-{n}.bak")
    shutil.copy2(path, target)
    return target


def shipped_rules(src: Path) -> dict[str, str]:
    return {p.name: read_text(p) for p in sorted(src.glob("*.md"))}


def states(src: Path, dest: Path) -> list[tuple[str, str, str | None, str]]:
    """(name, state, installed text, shipped text) per shipped rule."""
    recorded = load_manifest(dest)
    out = []
    for name, shipped in shipped_rules(src).items():
        target = dest / name
        installed = read_text(target) if target.is_file() else None
        out.append((name, state(installed, shipped, recorded.get(name)), installed, shipped))
    return out


def cmd_status(src: Path, dest: Path, diff: bool) -> int:
    for name, st, installed, shipped in states(src, dest):
        print(f"{st} {name}")
        if diff and st == "user-modified":
            sys.stdout.writelines(difflib.unified_diff(
                normalize(installed).splitlines(keepends=True),
                normalize(shipped).splitlines(keepends=True),
                f"installed/{name}", f"shipped/{name}"))
    return 0


def cmd_install(src: Path, dest: Path, overwrite: set[str]) -> int:
    recorded = load_manifest(dest)
    for name, st, installed, shipped in states(src, dest):
        target = dest / name
        if st == "identical":
            recorded[name] = digest(shipped)
            print(f"unchanged {name}")
            continue
        if st == "user-modified" and name not in overwrite:
            print(f"skipped {name} (user-modified)")
            continue
        if installed is not None:
            print(f"backup {backup(target)}")
            shipped = carry_language(shipped, installed)
        atomic_write(target, shipped.encode("utf-8"))
        recorded[name] = digest(shipped)
        print(f"wrote {name}")
    save_manifest(dest, recorded)
    return 0


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "install"):
        p = sub.add_parser(name)
        p.add_argument("--src", type=Path, default=root / "rules")
        p.add_argument("--dest", type=Path, required=True)
    sub.choices["status"].add_argument("--diff", action="store_true")
    sub.choices["install"].add_argument("--overwrite", action="append", default=[])
    sub.add_parser("backup").add_argument("file", type=Path)
    args = parser.parse_args(argv)

    if args.command == "backup":
        if not args.file.is_file():
            print(f"no such file: {args.file}")
            return 1
        print(f"backup {backup(args.file.resolve())}")
        return 0
    if not any(args.src.glob("*.md")):
        print(f"no rules found in {args.src}")
        return 1
    if args.command == "status":
        return cmd_status(args.src, args.dest, args.diff)
    return cmd_install(args.src, args.dest, set(args.overwrite))


if __name__ == "__main__":
    sys.exit(main())
