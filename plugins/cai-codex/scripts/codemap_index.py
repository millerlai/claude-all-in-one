"""Keeps the index in step with the working tree (build) and says how far the
tree is from the index (status).

`status` never raises: every situation maps to one of five state words, and
the first that holds wins: `unsupported` when git cannot answer or the index
directory cannot be trusted, `absent` with no index, `stale` when a tracked
file differs from its record, `partial` when a file failed to parse, `fresh`
otherwise.
"""
import datetime
import json
import os
import sys
import time
from typing import NamedTuple, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import codemap_inventory as inventory  # noqa: E402
import codemap_repomap as repomap  # noqa: E402
import codemap_store as store  # noqa: E402
import codemap_symbols as symbols  # noqa: E402
import preflight  # noqa: E402

MAX_PARSE_BYTES = inventory.MAX_PARSE_BYTES
# The state words under which there is no index to read.
NO_INDEX_WORDS = ("absent", "unsupported")


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
            "sha256": facts.sha256, "mtime_ns": facts.mtime_ns,
            "parse": "facts-only", "reason": reason,
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
        return _facts_record(facts._replace(bytes=None, sha256=None, mtime_ns=None),
                             got.reason), [], None
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


def _write(top, facts, previous, scanned_at_ns):
    """Writes the whole index for `facts`, reusing `previous` records for files
    whose hash is unchanged and which were not partial. `scanned_at_ns` is when
    the inventory behind `facts` started; every record describes its file as of
    then, which is what lets the next inventory trust one unread (#448).
    Returns the Result."""
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
    records, all_symbols, partial, reparsed, touched = [], [], [], 0, 0
    for f in facts:
        old = reuse_files.get(f.path)
        if old is not None and old.get("sha256") == f.sha256 and (
                f.sha256 is not None or old.get("reason") == f.reason):
            record, syms, crash = old, reuse_symbols[f.path], None
            if old.get("mtime_ns") != f.mtime_ns:
                # Same bytes, new mtime: keep the new one, or the record can
                # never vouch for the file again and every run rereads it.
                record = dict(old, mtime_ns=f.mtime_ns)
                touched += 1
        else:
            record, syms, crash = _parse(top_real, f)
            reparsed += 1
        if crash is not None:
            partial.append((f.path, crash))
        records.append(record)
        all_symbols.extend(syms)
    all_symbols.sort(key=lambda s: (s["path"], s["start_line"], s["qualified_name"]))
    head = _head(top)
    if not touched and _unchanged(previous, records, reparsed, partial, head):
        # The usual case for a dispatch after the last one: rewriting every
        # file would only move built_at, at a cost that grows with the repo.
        shards = sum(1 for name in previous.state["artifacts"] if name.startswith("packages/"))
        return Result("fresh", 0, len(records), shards, [])
    texts = repomap.render(records, all_symbols, repomap.BUDGET_TOKENS, repomap.TOLERANCE_TOKENS)

    store.ensure_dir(top)
    blobs = {store.FILES_NAME: _jsonl(records), store.SYMBOLS_NAME: _jsonl(all_symbols)}
    blobs.update((name, text.encode("utf-8")) for name, text in texts.items())
    lock = store.acquire_write_lock(top)
    try:
        store.check_entries(top)
        store.check_targets(top, list(blobs) + [store.STATE_NAME])
        # Every temp file is written before the first rename, so an error up to
        # there leaves the previous index exactly as it was.
        staged = []
        try:
            for name, data in blobs.items():
                staged.append(store.write_atomic(top, name, data))
            artifacts = {item.name: item.sha256 for item in staged}
            state = {"schema_version": store.SCHEMA_VERSION,
                     "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     "head": head, "file_count": len(records), "artifacts": artifacts,
                     "partial": [{"path": p, "reason": r} for p, r in partial],
                     "scanned_at_ns": scanned_at_ns, **store.extractor_stamp()}
            staged.append(store.commit_state(top, state))
            store.publish(staged)
        except BaseException:
            store.discard(staged)
            raise
        store.sweep(top, set(artifacts))
    finally:
        store.release_write_lock(lock)
    # render always returns repo-map.md and, beside it, one text per shard.
    return Result("partial" if partial else "fresh", reparsed, len(records),
                  len(texts) - 1, partial)


def _unchanged(previous, records, reparsed, partial, head):
    """Whether writing would reproduce `previous` byte for byte but for its
    time stamp: every record reused, the same files, no file left partial
    then or now, and the same HEAD for the state line to name."""
    return (previous is not None and reparsed == 0 and not partial
            and not previous.state.get("partial")
            and previous.state.get("head") == head
            and [r["path"] for r in records] == sorted(previous.files))


def _trusted(index):
    """inventory's records and scanned_at_ns arguments from a loaded index."""
    if index is None:
        return None, None
    return index.files, index.state.get("scanned_at_ns")


def build(top: str) -> Result:
    # The inventory runs first so a directory that is not a repository is
    # refused before a single byte is written under it.
    scanned_at_ns = time.time_ns()
    return _write(top, inventory.inventory(top), None, scanned_at_ns)


def update(top: str) -> Optional[Result]:
    """None, with nothing written, when there is no index: only a person's
    `build` creates one. A damaged index is rebuilt in full."""
    scanned_at_ns = time.time_ns()
    # Listed first, so a directory that is not a repository is refused before
    # anything under it is read.
    listed = inventory.list_tracked(top)
    # Before load, not only in ensure_dir: a state.json that is itself tracked
    # came with the repository, and nothing in it may be parsed.
    if store.tracked_inside(top):
        raise store.IndexUnreadable(store.TRACKED_REASON)
    try:
        previous = store.load(top)
    except store.IndexUnreadable:
        previous = None
    else:
        if previous is None:
            return None
    facts = inventory.inventory(top, *_trusted(previous), listed=listed)
    return _write(top, facts, previous, scanned_at_ns)


def _unsupported(reason):
    # A reason can quote a name read from state.json, which anyone who can
    # write the index directory controls; escaped, it stays on this one line.
    return Status("unsupported", preflight.escape_control_chars(reason), [])


def _named(paths, verb):
    """`named_paths` caps the list at ten and counts the rest; it only knows a
    plural, so a single file gets the singular noun here."""
    noun = "file" if len(paths) == 1 else "files"
    return preflight.named_paths(paths, "%s %s" % (noun, verb))


def status(top: str) -> Status:
    try:
        # Listed before the index is read, which says whether this is a
        # repository; files are read only once there is an index to compare
        # them with, and then only those it no longer vouches for (#403, #448).
        listed = inventory.list_tracked(top)
    except inventory.NotARepository:
        return _unsupported("not a git repository")
    except inventory.GitFailed:
        return _unsupported("git did not answer")
    except OSError as exc:
        return _unsupported("%s while reading the tree" % type(exc).__name__)
    try:
        if store.tracked_inside(top):
            return _unsupported(store.TRACKED_REASON)
        # run build would not help: build refuses the same directory.
        store._check_inside_repository(top)
    except store.IndexUnreadable as exc:
        return _unsupported(exc.args[0])
    except OSError:
        return _unsupported("git did not answer")
    try:
        index = store.load(top)
    except store.IndexUnreadable as exc:
        return _unsupported("index unreadable: %s; run build" % exc.args[0])
    except OSError:
        return _unsupported("git did not answer")
    if index is None:
        return Status("absent", "", [])
    try:
        facts = inventory.inventory(top, *_trusted(index), listed=listed)
    except OSError as exc:
        return _unsupported("%s while reading the tree" % type(exc).__name__)
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
    # The absolute index directory: a read-only agent has no shell to find the
    # repository's top itself, and a guess from a subdirectory or another
    # worktree would read some other index (#401).
    return Status("fresh", "%d files, %d with symbols, %s, index %s" % (
        len(index.files), with_symbols, "head %s" % head[:7] if head else "no commit yet",
        preflight.escape_control_chars(store.index_dir(top))), [])


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
