"""Ranks a query against the index: symbol names, paths, and file text.

Read-only, and the order is a function of the inputs alone (ties fall to path,
then line), so the same query on the same tree always prints the same list.
Scores are the design's T3-7: name equals a query word 100; the name contains a
term 30 each; the qualified name 20 each; a path 10 each; file text 1 per
matching line, at most 5.
"""
import os
import re
import sys
from typing import NamedTuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import codemap_inventory as inventory  # noqa: E402
import codemap_store  # noqa: E402

MAX_TEXT_BYTES = 1048576   # the same cap as parsing: a bigger file is not scanned
TEXT_LINE_CAP = 5
NAME_EQUALS, NAME_HAS, QUALIFIED_HAS, PATH_HAS = 100, 30, 20, 10


class Hit(NamedTuple):
    score: int
    path: str
    line: int
    kind: str        # symbol kind, or "path", or "text"
    name: str


def terms(text: str) -> list:
    """Lower-cased words of `text`, split on anything that is not a letter or
    digit and on camelCase boundaries, each once, in order of appearance."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    seen = []
    for word in re.split(r"[\W_]+", spaced.lower()):
        if word and word not in seen:
            seen.append(word)
    return seen


def tracked_texts(top: str) -> list:
    """[(path, text)] for every tracked file git lists that can be read as
    text now: not a symlink, not a submodule, a regular file inside the
    repository, under the size cap, no NUL."""
    out = []
    top_real = os.path.realpath(top)
    for mode, path in inventory.list_tracked(top):
        if mode in ("120000", "160000") or "�" in path:
            continue
        got = inventory.read_tracked(top_real, path, MAX_TEXT_BYTES)
        if got.reason is not None or len(got.data) > MAX_TEXT_BYTES:
            continue
        if b"\0" in got.data:
            continue
        out.append((path, got.data.decode("utf-8", errors="replace")))
    return out


def _count(haystack, words):
    return sum(1 for w in words if w in haystack)


def query(top: str, index: codemap_store.Index, text: str, limit: int) -> list:
    words = terms(text)
    if not words:
        return []
    # A whole identifier typed as one word ("parse_config") is an exact-name
    # candidate even though `terms` has split it.
    exact = set(words) | {t.lower() for t in text.split()}
    hits = []
    for sym in index.symbols:
        name, qualified, path = sym["name"].lower(), sym["qualified_name"].lower(), \
            sym["path"].lower()
        score = (NAME_EQUALS if name in exact else 0) + NAME_HAS * _count(name, words) \
            + QUALIFIED_HAS * _count(qualified, words) + PATH_HAS * _count(path, words)
        if score:
            hits.append(Hit(score, sym["path"], sym["start_line"], sym["kind"],
                            sym["qualified_name"]))
    for path in index.files:
        score = PATH_HAS * _count(path.lower(), words)
        if score:
            hits.append(Hit(score, path, 1, "path", path))
    for path, body in tracked_texts(top):
        matches = [(n, line) for n, line in enumerate(body.splitlines(), start=1)
                   if any(w in line.lower() for w in words)]
        if matches:
            first_line, first = matches[0]
            hits.append(Hit(min(len(matches), TEXT_LINE_CAP), path, first_line, "text",
                            first.strip()[:80]))
    hits.sort(key=lambda h: (-h.score, h.path, h.line, h.kind, h.name))
    return hits[:limit]
