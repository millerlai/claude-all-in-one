"""Source rules: which platform sources may write work, and how one subagent's
ordered hook observations become confirmed model segments. Pure; no file access."""
import hashlib
import json

SOURCE_ID = "claude-hooks-1"
_EVENTS = ("start", "pre", "batch", "stop")


def source_admitted(source_id, platform):
    # Admitted only on the strength of the official hook documentation plus the
    # recorded real session in tests/fixtures/timing/claude-hooks/ (unit 4a).
    return (source_id, platform) == (SOURCE_ID, "claude")


def _id(*parts):
    # Same hashing as timing._id; copied so this module never imports timing.
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()


def _gap(platform, binding, reason, key):
    return {"format": 1, "event_id": _id("gap", binding["run_id"], binding["actor_id"],
                                         binding["source_id"], reason, key),
            "run_id": binding["run_id"], "stage": binding["stage"], "platform": platform,
            "kind": "gap", "actor_id": binding["actor_id"], "reason": reason}


def _int(value):
    return type(value) is int and value >= 0


def _valid(row):
    if not isinstance(row, dict) or not _int(row.get("seq")) or not _int(row.get("at_ms")):
        return False
    event = row.get("event")
    if event not in _EVENTS:
        return False
    if event == "pre":
        return isinstance(row.get("tool_use_id"), str) and bool(row["tool_use_id"])
    if event == "batch":
        ids = row.get("tool_use_ids")
        return isinstance(ids, list) and bool(ids) and all(isinstance(i, str) and i for i in ids)
    return True


def _segments(rows):
    """Return (confirmed, missing_at). confirmed: (start, end, start_key, end_key)."""
    confirmed, pending = [], []
    open_seg = None  # (at_ms, key)
    outstanding = set()
    stopped = False  # stop seen while tools were outstanding: a late batch may still certify them
    for row in sorted(rows, key=lambda r: (r["at_ms"], r["seq"])):
        event, at = row["event"], row["at_ms"]
        if event == "start":
            if outstanding or open_seg is not None:
                return confirmed, at
            open_seg, stopped = (at, "start@%d" % at), False
        elif event == "pre":
            if open_seg is not None:
                pending.append((open_seg[0], at, open_seg[1], row["tool_use_id"]))
                open_seg = None
            outstanding.add(row["tool_use_id"])
        elif event == "batch":
            ids = set(row["tool_use_ids"])
            if not ids <= outstanding or outstanding - ids:
                return confirmed, at
            outstanding = set()
            confirmed += pending
            pending = []
            if not stopped:
                key = hashlib.sha256("\0".join(sorted(ids)).encode("utf-8")).hexdigest()
                open_seg = (at, key)
        else:  # stop
            if open_seg is not None:
                confirmed.append((open_seg[0], at, open_seg[1], "stop@%d" % at))
                open_seg = None
            if not outstanding:
                confirmed += pending
                pending = []
            else:
                stopped = True
    return confirmed, None


def normalize_event(platform, payload, binding):
    if platform != "claude" or binding["source_id"] != SOURCE_ID:
        # An unverified source cannot establish either work or source coverage.
        return [_gap(platform, binding, "source-unverified", "")]
    rows = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not all(_valid(r) for r in rows):
        return [_gap(platform, binding, "event-missing", "payload")]
    confirmed, missing_at = _segments(rows)
    events = []
    for begin, end, start_key, end_key in confirmed:
        if end < begin:
            events.append(_gap(platform, binding, "invalid-boundary", "%d:%d" % (begin, end)))
            continue
        activity = _id(binding["actor_id"], start_key, end_key)[:32]
        for kind, at in (("work_begin", begin), ("work_end", end)):
            events.append({"format": 1,
                           "event_id": _id(kind, binding["run_id"], binding["actor_id"], activity),
                           "run_id": binding["run_id"], "stage": binding["stage"],
                           "platform": platform, "kind": kind, "actor_id": binding["actor_id"],
                           "source_id": binding["source_id"], "activity_id": activity, "at_ms": at})
    if missing_at is not None:
        events.append(_gap(platform, binding, "event-missing", str(missing_at)))
    return events
