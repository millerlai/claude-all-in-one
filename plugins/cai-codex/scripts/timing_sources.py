"""Source rules: which platform sources may write work, and how one subagent's
ordered hook observations become confirmed model segments. Pure; no file access."""
import hashlib
import json

SOURCE_ID = "claude-hooks-1"
CODEX_SOURCE_ID = "codex-hooks-1"
SOURCES = {"claude": SOURCE_ID, "codex": CODEX_SOURCE_ID}
# Codex has no PostToolBatch hook: each tool closes with its own PostToolUse
# ("post"), recorded in tests/fixtures/timing/codex-hooks/ (#333).
_EVENTS = {"claude": ("start", "pre", "batch", "stop"), "codex": ("start", "pre", "post", "stop")}


def source_admitted(source_id, platform):
    # Admitted only on the strength of each platform's hook documentation plus
    # its recorded real session under tests/fixtures/timing/ (unit 4a, #333).
    # `in` first: .get() would answer None for an unknown platform, matching a missing source_id.
    return platform in SOURCES and SOURCES[platform] == source_id


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


def _valid(row, platform):
    if not isinstance(row, dict) or not _int(row.get("seq")) or not _int(row.get("at_ms")):
        return False
    event = row.get("event")
    if event not in _EVENTS[platform]:
        return False
    if event in ("pre", "post"):
        return isinstance(row.get("tool_use_id"), str) and bool(row["tool_use_id"])
    if event == "batch":
        ids = row.get("tool_use_ids")
        return isinstance(ids, list) and bool(ids) and all(isinstance(i, str) and i for i in ids)
    return True


def _batches(rows):
    """Codex posts as the batches they amount to: the tools started since the last
    batch close together when the last of them closes. A post for a tool that
    was never started is passed on as a batch of its own, which _segments
    rejects as missing."""
    out, outstanding, closed = [], set(), []
    for row in sorted(rows, key=lambda r: (r["at_ms"], r["seq"])):
        if row["event"] != "post":
            if row["event"] == "pre":
                outstanding.add(row["tool_use_id"])
            out.append(row)
            continue
        tool = row["tool_use_id"]
        if tool not in outstanding:
            out.append({"seq": row["seq"], "event": "batch", "at_ms": row["at_ms"], "tool_use_ids": [tool]})
            continue
        outstanding.discard(tool)
        closed.append(tool)
        if not outstanding:
            out.append({"seq": row["seq"], "event": "batch", "at_ms": row["at_ms"], "tool_use_ids": closed})
            closed = []
    return out


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
    if not source_admitted(binding["source_id"], platform):
        # An unverified source cannot establish either work or source coverage.
        return [_gap(platform, binding, "source-unverified", "")]
    rows = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not all(_valid(r, platform) for r in rows):
        return [_gap(platform, binding, "event-missing", "payload")]
    confirmed, missing_at = _segments(_batches(rows) if platform == "codex" else rows)
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
