"""Keeps the index in step with the working tree (build) and says how far the
tree is from the index (status).

`status` never raises: every situation maps to one of five state words, in the
order T3-5 of the detail design fixes.
"""
import datetime
import json
import os
import sys
from typing import NamedTuple, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import codemap_inventory as inventory  # noqa: E402
import codemap_repomap as repomap  # noqa: E402
import codemap_store as store  # noqa: E402
import codemap_symbols as symbols  # noqa: E402
import preflight  # noqa: E402

# Over this a file is hashed but not parsed: one generated giant must not slow
# every dispatch (T3-4).
MAX_PARSE_BYTES = 1048576


class Result(NamedTuple):
    word: str                # state word after the write
    reparsed: int
    total: int
    shards: int
    partial: list            # [(path, reason)]


class Status(NamedTuple):
    word: str                # "fresh" | "stale" | "partial" | "absent" | "unsupported"
    detail: str              # text inside the parentheses, "" for absent
    paths: list              # every path behind the word, for the lines after line 1


def _head(top):
    done = preflight.git(top, "rev-parse", "HEAD")
    if done is None or done.returncode != 0:
        return None
    return done.stdout.strip() or None


def _jsonl(records):
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                   for r in records).encode("utf-8")


def _facts_record(facts, reason):
    return {"path": facts.path, "language": facts.language, "bytes": facts.bytes,
            "sha256": facts.sha256, "parse": "facts-only", "reason": reason,
            "backend": None, "confidence": None, "imports": []}


def _retryable(reason):
    """A file that exists but could not be opened: the next update reads it again."""
    return reason is not None and reason.startswith(inventory.CANNOT_OPEN)


def _parse(top_real, facts):
    """(file record, symbol records, crash reason or None) for one file."""
    if facts.reason is not None:
        retry = facts.reason if _retryable(facts.reason) else None
        return _facts_record(facts, facts.reason), [], retry
    if facts.bytes > MAX_PARSE_BYTES:
        return _facts_record(facts, "too-large"), [], None
    got = inventory.read_tracked(top_real, facts.path, MAX_PARSE_BYTES)
    if _retryable(got.reason):
        # Inventory's hash and size stay, so status sees partial and not stale.
        return _facts_record(facts, got.reason), [], got.reason
    if got.reason is not None:
        # Gone, replaced or moved out since inventory looked: what inventory
        # would record for it now, so the next status finds the same thing.
        return _facts_record(facts._replace(bytes=None, sha256=None), got.reason), [], None
    if len(got.data) > MAX_PARSE_BYTES:
        return _facts_record(facts, "too-large"), [], None
    # The record describes the bytes parsed, not the ones inventory hashed.
    facts = facts._replace(bytes=got.size, sha256=got.sha256)
    try:
        ex = symbols.extract(facts.path, facts.language, got.data)
    except Exception as exc:  # noqa: BLE001 -- an adapter crash costs one file, not the build
        reason = "adapter-crash: %s" % type(exc).__name__
        return _facts_record(facts, reason), [], reason
    if ex.reason is not None:
        return _facts_record(facts, ex.reason), [], None
    record = _facts_record(facts, None)
    record.update(parse="symbols", backend=ex.backend, confidence=ex.confidence,
                  imports=ex.imports)
    return record, ex.symbols, None


def _write(top, facts, previous):
    """Writes the whole index for `facts`, reusing `previous` records for files
    whose hash is unchanged and which were not partial. Returns the Result."""
    reuse_files, reuse_symbols = {}, {}
    if previous is not None:
        retry = {entry["path"] for entry in previous.state.get("partial", [])}
        by_path = {}
        for sym in previous.symbols:
            by_path.setdefault(sym["path"], []).append(sym)
        for path, rec in previous.files.items():
            if path not in retry:
                reuse_files[path] = rec
                reuse_symbols[path] = by_path.get(path, [])
    top_real = os.path.realpath(top)
    records, all_symbols, partial, reparsed = [], [], [], 0
    for f in facts:
        old = reuse_files.get(f.path)
        if old is not None and old.get("sha256") == f.sha256 and (
                f.sha256 is not None or old.get("reason") == f.reason):
            record, syms, crash = old, reuse_symbols[f.path], None
        else:
            record, syms, crash = _parse(top_real, f)
            reparsed += 1
        if crash is not None:
            partial.append((f.path, crash))
        records.append(record)
        all_symbols.extend(syms)
    all_symbols.sort(key=lambda s: (s["path"], s["start_line"], s["qualified_name"]))
    texts = repomap.render(records, all_symbols, repomap.BUDGET_TOKENS, repomap.TOLERANCE_TOKENS)

    store.ensure_dir(top)
    blobs = {store.FILES_NAME: _jsonl(records), store.SYMBOLS_NAME: _jsonl(all_symbols)}
    blobs.update((name, text.encode("utf-8")) for name, text in texts.items())
    artifacts = {name: store.write_atomic(top, name, data) for name, data in blobs.items()}
    state = {"schema_version": store.SCHEMA_VERSION,
             "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "head": _head(top), "file_count": len(records), "artifacts": artifacts,
             "partial": [{"path": p, "reason": r} for p, r in partial],
             **store.extractor_stamp()}
    store.commit_state(top, state)
    store.sweep(top, set(artifacts))
    return Result("partial" if partial else "fresh", reparsed, len(records),
                  len(texts) - 1, partial)


def build(top: str) -> Result:
    # The inventory runs first so a directory that is not a repository is
    # refused before a single byte is written under it.
    return _write(top, inventory.inventory(top), None)


def update(top: str) -> Optional[Result]:
    """None, with nothing written, when there is no index: only a person's
    `build` creates one. A damaged index is rebuilt in full."""
    facts = inventory.inventory(top)
    # Before load, not only in ensure_dir: a state.json that is itself tracked
    # came with the repository, and nothing in it may be parsed.
    if store.tracked_inside(top):
        raise store.IndexUnreadable(".cai/codemap holds tracked files")
    try:
        previous = store.load(top)
    except store.IndexUnreadable:
        previous = None
    else:
        if previous is None:
            return None
    return _write(top, facts, previous)


def _unsupported(reason):
    return Status("unsupported", reason, [])


def _named(paths, verb):
    """`_named_paths` caps the list at ten and counts the rest; it only knows a
    plural, so a single file gets the singular noun here."""
    noun = "file" if len(paths) == 1 else "files"
    return preflight._named_paths(paths, "%s %s" % (noun, verb))


def status(top: str) -> Status:
    try:
        facts = inventory.inventory(top)
    except inventory.NotARepository:
        return _unsupported("not a git repository")
    except inventory.GitFailed:
        return _unsupported("git did not answer")
    except OSError as exc:
        return _unsupported("%s while reading the tree" % type(exc).__name__)
    try:
        if store.tracked_inside(top):
            return _unsupported(".cai/codemap holds tracked files")
        index = store.load(top)
    except store.IndexUnreadable as exc:
        return _unsupported("index unreadable: %s; run build" % exc.args[0])
    except OSError:
        return _unsupported("git did not answer")
    if index is None:
        return Status("absent", "", [])
    # Hash only: a record's `reason` is why it was not parsed, which the file
    # itself does not say, so it cannot be compared with a fresh inventory.
    known = {p: r.get("sha256") for p, r in index.files.items()}
    now = {f.path: f.sha256 for f in facts}
    changed = sorted(p for p in set(known) | set(now)
                     if p not in known or p not in now or known[p] != now[p])
    if changed:
        return Status("stale", _named(changed, "changed since the index was built"), changed)
    partial = [entry["path"] for entry in index.state.get("partial", [])]
    if partial:
        return Status("partial", _named(partial, "not parsed"), partial)
    head = index.state.get("head")
    # Says whether the map has anything in it: a repo of a language with no
    # adapter is "fresh" and empty, which the file count alone hides.
    with_symbols = len({s["path"] for s in index.symbols})
    return Status("fresh", "%d files, %d with symbols, %s" % (
        len(index.files), with_symbols, "head %s" % head[:7] if head else "no commit yet"), [])


def state_line(status: Status) -> str:
    if status.detail:
        return "codemap: %s (%s)" % (status.word, status.detail)
    return "codemap: %s" % status.word


def result_line(result: Result) -> str:
    """The first line `build`/`update` print: the same `codemap: <word> (...)`
    shape as `status`, from what the write itself knows."""
    if result.partial:
        detail = _named([p for p, _ in result.partial], "not parsed")
    elif result.reparsed == result.total:
        detail = "%d files" % result.total
    else:
        detail = "reparsed %d of %d files" % (result.reparsed, result.total)
    return "codemap: %s (%s)" % (result.word, detail)
