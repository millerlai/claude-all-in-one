"""Explicit track ownership and append-only normalized timing events. Zero deps."""
import hashlib
import json
import os
import sys
import threading
import uuid

import ledger
import timing_sources

TIMING_NAME = "timing.jsonl"
MAX_RECORD = 4096
COMMON = {"format", "event_id", "run_id", "stage", "platform", "kind"}
_APPEND_LOCK = threading.Lock()
FIELDS = {
    "run_begin": set(),
    "actor_bind": {"actor_id", "session_id", "source_id", "source_run_id", "parent_actor_id"},
    "work_begin": {"actor_id", "source_id", "activity_id", "at_ms"},
    "work_end": {"actor_id", "source_id", "activity_id", "at_ms"},
    "gap": {"actor_id", "reason"},
    "run_end": set(),
    "source_coverage": {"source_id", "capture_id", "start_token", "end_token",
                        "actor_ids", "coverage_scope"},
}
COVERAGE_SCOPE = {"model", "tool", "child", "human-boundaries", "idle-boundaries"}


def _path(track_dir):
    return os.path.join(track_dir, TIMING_NAME)


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def _validate(event, stages=None):
    if not isinstance(event, dict):
        raise ValueError("journal-malformed")
    if type(event.get("format")) is not int or event["format"] != 1:
        raise ValueError("unsupported-format")
    kind = event.get("kind")
    if not isinstance(kind, str) or kind not in FIELDS:
        raise ValueError("journal-malformed")
    if set(event) != COMMON | FIELDS[kind]:
        raise ValueError("journal-malformed")
    if not all(_string(event[key]) for key in COMMON - {"format"}):
        raise ValueError("journal-malformed")
    if stages is None:
        stages = ledger.stage_ids()
    if event["stage"] not in stages or event["platform"] not in ("claude", "codex"):
        raise ValueError("journal-malformed")
    for key in FIELDS[kind] - {"at_ms", "parent_actor_id", "actor_ids", "coverage_scope"}:
        if not _string(event[key]):
            raise ValueError("journal-malformed")
    if "parent_actor_id" in event and event["parent_actor_id"] is not None and not _string(event["parent_actor_id"]):
        raise ValueError("journal-malformed")
    if "at_ms" in event and (type(event["at_ms"]) is not int or event["at_ms"] < 0):
        raise ValueError("invalid-boundary")
    if kind == "source_coverage":
        for key in ("actor_ids", "coverage_scope"):
            values = event[key]
            if not isinstance(values, list) or not all(_string(value) for value in values):
                raise ValueError("journal-malformed")
            if len(values) != len(set(values)):
                raise ValueError("journal-malformed")
        if not set(event["coverage_scope"]) <= COVERAGE_SCOPE:
            raise ValueError("journal-malformed")
    if kind in ("work_begin", "work_end", "source_coverage"):
        if not timing_sources.source_admitted(event["source_id"], event["platform"]):
            raise ValueError("source-unverified")


def _same_run(left, right):
    return all(left[key] == right[key] for key in ("run_id", "stage", "platform"))


def _binding_key(event, actor_id):
    return (event["run_id"], event["stage"], event["platform"], actor_id, event["source_id"])


def _binding_index(events):
    """How many actor_bind rows each (run, actor, source) has. Built once per
    parse: scanning every event for each work event made a parse O(events^2),
    and a long track's settle neared the hook timeout (#322)."""
    counts = {}
    for row in events:
        if row["kind"] == "actor_bind":
            key = _binding_key(row, row["actor_id"])
            counts[key] = counts.get(key, 0) + 1
    return counts


def _check_indexed(index, event):
    if event["kind"] in ("work_begin", "work_end"):
        actor_ids = [event["actor_id"]]
    elif event["kind"] == "source_coverage":
        actor_ids = event["actor_ids"]
    else:
        return
    for actor_id in actor_ids:
        count = index.get(_binding_key(event, actor_id), 0)
        if not count:
            raise ValueError("binding-missing")
        if count != 1:
            raise ValueError("binding-ambiguous")


def _check_binding(events, event):
    _check_indexed(_binding_index(events), event)


def _read_bytes(path):
    if os.name != "nt":
        with open(path, "rb") as fh:
            return fh.read()
    # Reading byte 0 while ledger's Windows append lock is held can fail.
    # Share that lock so validation never mistakes an active writer for lost ownership.
    import msvcrt
    fd = os.open(path, os.O_RDONLY | os.O_BINARY)
    try:
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        try:
            chunks = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(fd)


def _events_from_bytes(raw):
    records = {}
    seen = {}
    conflicts = set()
    problems = set()
    stages = ledger.stage_ids()  # once per parse, not once per event (#322)
    # LF is the writer's only separator; Unicode separators may occur in JSON strings.
    for line in raw.split(b"\n"):
        if not line.strip():
            continue
        try:
            if len(line) + 1 > MAX_RECORD:
                raise ValueError("journal-malformed")
            event = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeError):
            problems.add("journal-malformed")
            continue
        event_id = event.get("event_id") if isinstance(event, dict) else None
        if _string(event_id):
            if event_id in seen and seen[event_id] != event:
                conflicts.add(event_id)
                problems.add("event-conflict")
            seen[event_id] = event
        try:
            _validate(event, stages)
        except ValueError as exc:
            problems.add(str(exc))
            continue
        event_id = event["event_id"]
        if event_id in records and records[event_id] != event:
            conflicts.add(event_id)
            problems.add("event-conflict")
        else:
            records[event_id] = event
    events = [row for event_id, row in records.items() if event_id not in conflicts]
    index = _binding_index(events)
    valid = []
    for event in events:
        try:
            _check_indexed(index, event)
        except ValueError as exc:
            problems.add(str(exc))
            continue
        valid.append(event)
    return valid, sorted(problems)


def read_events(track_dir):
    """Return safe records and short gap codes without repairing the journal."""
    try:
        with _APPEND_LOCK:
            raw = _read_bytes(_path(track_dir))
        return _events_from_bytes(raw)
    except FileNotFoundError:
        return [], []
    except OSError:
        return [], ["journal-unreadable"]


def _lock_journal(fd):
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        return msvcrt
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fcntl


def _unlock_journal(fd, lock_module):
    if os.name == "nt":
        os.lseek(fd, 0, os.SEEK_SET)
        lock_module.locking(fd, lock_module.LK_UNLCK, 1)
    else:
        lock_module.flock(fd, lock_module.LOCK_UN)


def _read_fd(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def append_event(track_dir, event):
    _validate(event)
    line = ledger._encode(event)
    if len(line) > MAX_RECORD:
        raise ValueError("record-too-large")
    os.makedirs(track_dir, exist_ok=True)
    path = _path(track_dir)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
    with _APPEND_LOCK:
        fd = os.open(path, flags, 0o644)
        lock_module = None
        try:
            lock_module = _lock_journal(fd)
            events, _ = _events_from_bytes(_read_fd(fd))
            if event in events:
                return
            _check_binding(events, event)
            if event["kind"] != "run_begin":
                if not any(row["kind"] == "run_begin" and _same_run(row, event) for row in events):
                    raise ValueError("binding-missing")
            closed = any(row["kind"] == "run_end" and _same_run(row, event) for row in events)
            if closed and event["kind"] == "actor_bind":
                raise ValueError("run-closed")
            if closed and event["kind"] == "work_begin":
                # A late start may complete a previously delivered end, but cannot open new work.
                if not any(row["kind"] in ("work_begin", "work_end") and _same_run(row, event)
                           and all(row[key] == event[key] for key in ("actor_id", "source_id", "activity_id"))
                           for row in events):
                    raise ValueError("run-closed")
            if os.name == "nt":
                os.lseek(fd, 0, os.SEEK_END)
            offset = 0
            while offset < len(line):
                offset += os.write(fd, line[offset:])
        finally:
            if lock_module is not None:
                _unlock_journal(fd, lock_module)
            os.close(fd)


def _id(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()


def begin_run(track_dir, stage, run_id, platform):
    event = {"format": 1, "event_id": _id("run_begin", run_id), "run_id": run_id,
             "stage": stage, "platform": platform, "kind": "run_begin"}
    append_event(track_dir, event)
    return event


def bind_actor(track_dir, run_id, actor_id, session_id, source_id, source_run_id,
               parent_actor_id=None):
    events, _ = read_events(track_dir)
    runs = [row for row in events if row["kind"] == "run_begin" and row["run_id"] == run_id]
    if len(runs) != 1:
        raise ValueError("binding-ambiguous" if runs else "binding-missing")
    run = runs[0]
    append_event(track_dir, {"format": 1, "event_id": _id("actor_bind", run_id, actor_id,
        source_id, source_run_id),
        "run_id": run_id, "stage": run["stage"], "platform": run["platform"], "kind": "actor_bind",
        "actor_id": actor_id, "session_id": session_id, "source_id": source_id,
        "source_run_id": source_run_id, "parent_actor_id": parent_actor_id})


def _run_events(track_dir, run_id):
    events, _ = read_events(track_dir)
    return events, [row for row in events if row["kind"] == "run_begin" and row["run_id"] == run_id]


def end_run(track_dir, run_id):
    events, runs = _run_events(track_dir, run_id)
    if len(runs) != 1:
        raise ValueError("binding-ambiguous" if runs else "binding-missing")
    run = runs[0]
    append_event(track_dir, {"format": 1, "event_id": _id("run_end", run_id), "run_id": run_id,
                             "stage": run["stage"], "platform": run["platform"], "kind": "run_end"})


def find_run(project_dir, run_id):
    root = os.path.join(project_dir, ".claude", "track")
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return None
    found = []
    for name in entries:
        track_dir = os.path.join(root, name)
        if not os.path.isfile(_path(track_dir)):
            continue
        events, runs = _run_events(track_dir, run_id)
        if runs:
            closed = any(row["kind"] == "run_end" and _same_run(row, runs[0]) for row in events)
            found.append({"track_dir": track_dir, "stage": runs[0]["stage"],
                          "platform": runs[0]["platform"], "closed": closed})
    return found[0] if len(found) == 1 else None


def _marker(track_dir, run_id):
    # In .claude/track/ as a file: preflight counts only directories there.
    return os.path.join(os.path.dirname(os.path.abspath(track_dir)), "timing-open." + run_id)


def _sweep_markers(track_dir):
    """Drop the open markers of runs that already have a run_end."""
    root = os.path.dirname(os.path.abspath(track_dir))
    try:
        names = os.listdir(root)
    except OSError:
        return
    for name in names:
        if name.startswith("timing-open."):
            found = find_run(os.path.dirname(os.path.dirname(root)), name[len("timing-open."):])
            if found and found["closed"]:
                _remove(os.path.join(root, name))


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _options(argv, names):
    if len(argv) != 2 * len(names) or argv[0::2] != ["--" + n for n in names]:
        return None
    return dict(zip(names, argv[1::2]))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    command, rest = (argv[0], argv[1:]) if argv else (None, [])
    try:
        if command == "begin":
            opts = _options(rest, ["track-dir", "stage", "platform"])
            if opts is None or opts["platform"] not in timing_sources.SOURCES:
                raise ValueError("usage: begin --track-dir D --stage S --platform claude|codex")
            run_id = str(uuid.uuid4())
            begin_run(opts["track-dir"], opts["stage"], run_id, opts["platform"])
            open(_marker(opts["track-dir"], run_id), "w").close()
            _sweep_markers(opts["track-dir"])
            print("cai-timing-run: " + run_id)
        elif command == "end":
            opts = _options(rest, ["track-dir", "run"])
            if opts is None:
                raise ValueError("usage: end --track-dir D --run RUN_ID")
            events, runs = _run_events(opts["track-dir"], opts["run"])
            if len(runs) != 1:
                raise ValueError("run not found")
            if not any(row["kind"] == "run_end" and _same_run(row, runs[0]) for row in events):
                end_run(opts["track-dir"], opts["run"])
            _remove(_marker(opts["track-dir"], opts["run"]))
            _sweep_markers(opts["track-dir"])
        else:
            raise ValueError("usage: timing.py begin|end ...")
    except (ValueError, OSError) as exc:
        print("timing: " + (str(exc).splitlines() or ["failed"])[0][:100], file=sys.stderr)
        return 2
    return 0


def _binding_candidates(project_dir, platform, session_id, actor_id, source_run_id):
    root = os.path.join(project_dir, ".claude", "track")
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return []
    candidates = []
    for name in entries:
        track_dir = os.path.join(root, name)
        if not os.path.isdir(track_dir):
            continue
        events, _ = read_events(track_dir)
        for event in events:
            if (event["kind"] == "actor_bind" and event["platform"] == platform
                    and event["session_id"] == session_id
                    and event["source_run_id"] == source_run_id
                    and (actor_id is None or event["actor_id"] == actor_id)
                    and any(row["kind"] == "run_begin" and _same_run(row, event) for row in events)):
                candidates.append(dict(event, track_dir=track_dir))
    return candidates


def resolve_binding(project_dir, platform, session_id, actor_id, source_run_id):
    candidates = _binding_candidates(project_dir, platform, session_id, actor_id, source_run_id)
    return candidates[0] if len(candidates) == 1 else None


def collect_event(project_dir, platform, session_id, actor_id, source_run_id, payload):
    candidates = _binding_candidates(project_dir, platform, session_id, actor_id, source_run_id)
    if len(candidates) != 1:
        return ["binding-ambiguous" if candidates else "binding-missing"]
    binding = candidates[0]
    reasons = set()
    try:
        events = timing_sources.normalize_event(platform, payload, binding)
        # A settle re-sends every confirmed segment; append_event would re-parse the
        # whole journal to discover each one is already there, which is quadratic.
        written, _ = read_events(binding["track_dir"])
        for event in events:
            if not _same_run(event, binding) or event.get("actor_id", binding["actor_id"]) != binding["actor_id"]:
                raise ValueError("binding-ambiguous")
            if event not in written:
                append_event(binding["track_dir"], event)
            if event["kind"] == "gap":
                reasons.add(event["reason"])
    except ValueError as exc:
        reasons.add(str(exc))
    except OSError:
        reasons.add("journal-unreadable")
    return sorted(reasons)


if __name__ == "__main__":
    sys.exit(main())
