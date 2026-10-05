#!/usr/bin/env python3
"""Plugin hook receiver for stage timing. Reads one hook JSON on stdin, spools
content-free observations per subagent, binds subagents to a tracked run, and
settles confirmed model segments into the track's timing journal.

It never writes to stdout (a PreToolUse hook's stdout is parsed as a decision)
and always exits 0, so it can never change what a tool call does."""
import hashlib
import json
import os
import re
import sys
import time

import timing

SOURCE_ID = "claude-hooks-1"
SPOOL = "timing-spool"
MAX_CHAIN = 8
EXPIRY_SECONDS = 7 * 24 * 3600
_MARKER = re.compile(r"(?m)^cai-timing-run: (\S+)[ \t]*\r?$")
_AGENT_TOOLS = ("Agent", "Task")


def _h(identity):
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def _dir(data_dir, kind):
    return os.path.join(data_dir, SPOOL, kind)


def _file(data_dir, kind, identity):
    return os.path.join(_dir(data_dir, kind), _h(identity) + ".jsonl")


class _Lock:
    """The spool-wide lock, taken with the journal's own locking primitive."""

    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, SPOOL, "lock")

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        self.module = timing._lock_journal(self.fd)
        return self

    def __exit__(self, *exc):
        try:
            timing._unlock_journal(self.fd, self.module)
        finally:
            os.close(self.fd)


def _append(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n"
    if len(line) > timing.MAX_RECORD:
        return
    with open(path, "a", encoding="ascii", newline="\n") as fh:
        fh.write(line)


def _read_rows(path):
    try:
        with open(path, encoding="ascii") as fh:
            lines = fh.read().split("\n")
    except OSError:
        return None
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _text(value):
    return value if isinstance(value, str) and value else None


def _observe_row(payload, event, agent):
    if event == "PostToolBatch":
        calls = payload.get("tool_calls")
        ids = [c.get("tool_use_id") for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []
        if not ids or not all(_text(i) for i in ids):
            return None
        return {"event": "batch", "tool_use_ids": ids}
    if event == "PreToolUse":
        return {"event": "pre", "tool_use_id": _text(payload.get("tool_use_id"))} if _text(payload.get("tool_use_id")) else None
    return {"event": "start" if event == "SubagentStart" else "stop"}


def _bind_row(payload, project_dir):
    """The binding record a main-session Agent result implies, or gaps to write."""
    agent_id = payload["tool_response"]["agentId"]
    prompt = (payload.get("tool_input") or {}).get("prompt")
    run_ids = sorted(set(_MARKER.findall(prompt))) if isinstance(prompt, str) else []
    if len(run_ids) > 1:
        for run_id in run_ids:
            _gap(project_dir, run_id, agent_id, "binding-ambiguous")
        return {"agent": agent_id, "unbound": True}
    if not run_ids:
        return {"agent": agent_id, "unbound": True}
    found = timing.find_run(project_dir, run_ids[0])
    if found is None:
        return {"agent": agent_id, "unbound": True}
    if found["closed"]:
        _gap(project_dir, run_ids[0], agent_id, "run-closed")
        return {"agent": agent_id, "unbound": True}
    session_id = _text(payload.get("session_id"))
    if session_id is None:
        return {"agent": agent_id, "unbound": True}
    return {"agent": agent_id, "run_id": run_ids[0], "track_dir": found["track_dir"],
            "project_dir": project_dir, "session_id": session_id}


def _gap(project_dir, run_id, actor_id, reason):
    found = timing.find_run(project_dir, run_id)
    if found is None:
        return
    _write_gap(found["track_dir"], run_id, found["stage"], found["platform"], actor_id, reason)


def _write_gap(track_dir, run_id, stage, platform, actor_id, reason):
    timing.append_event(track_dir, {
        "format": 1, "event_id": timing._id("gap", run_id, actor_id, reason), "run_id": run_id,
        "stage": stage, "platform": platform, "kind": "gap", "actor_id": actor_id, "reason": reason})


def observe(payload, data_dir, project_dir, now_ms):
    if not isinstance(payload, dict):
        return
    event = payload.get("hook_event_name")
    agent = _text(payload.get("agent_id"))
    if event in ("SubagentStart", "PreToolUse", "PostToolBatch", "SubagentStop") and agent:
        row = _observe_row(payload, event, agent)
        if row is None:
            return
        with _Lock(data_dir):
            path = _file(data_dir, "obs", agent)
            existing = _read_rows(path) or []
            _append(path, dict(row, format=1, seq=len(existing), at_ms=now_ms, agent_id=agent))
            if event in ("PostToolBatch", "SubagentStop"):
                _settle(data_dir, now_ms)
    elif event == "PostToolUse" and payload.get("tool_name") in _AGENT_TOOLS:
        response = payload.get("tool_response")
        agent_id = _text(response.get("agentId")) if isinstance(response, dict) else None
        if agent_id is None:
            return
        with _Lock(data_dir):
            if agent:
                record = {"agent": agent_id, "parent": agent}
            else:
                record = _bind_row(payload, project_dir)
            _append(_file(data_dir, "bind", agent_id), record)
            _settle(data_dir, now_ms)


def _resolve(data_dir, agent):
    """Follow parent links to a terminal record. Returns (state, record, parent_of_agent)."""
    current, direct_parent = agent, None
    for depth in range(MAX_CHAIN + 1):
        rows = _read_rows(_file(data_dir, "bind", current))
        if rows is None or not rows:
            return "none", None, None
        distinct = {json.dumps(r, sort_keys=True) for r in rows}
        if len(distinct) != 1:
            return "unbound", None, None
        record = rows[0]
        if record.get("unbound"):
            return "unbound", None, None
        if "run_id" in record:
            return "bound", record, direct_parent
        parent = _text(record.get("parent"))
        if parent is None:
            return "unbound", None, None
        if depth == 0:
            direct_parent = parent
        current = parent
    return "unbound", None, None


def _outstanding(rows):
    pending = set()
    for row in sorted(rows, key=lambda r: (r["at_ms"], r["seq"])):
        if row["event"] == "pre":
            pending.add(row["tool_use_id"])
        elif row["event"] == "batch":
            pending -= set(row["tool_use_ids"])
    return pending


def _finished(rows):
    """A stop with nothing started after it and no tool left open."""
    order = [r["event"] for r in sorted(rows, key=lambda r: (r["at_ms"], r["seq"]))]
    if "stop" not in order:
        return False
    after_last_stop = order[len(order) - order[::-1].index("stop"):]
    return "start" not in after_last_stop and not _outstanding(rows)


def _settle_one(data_dir, path):
    rows = _read_rows(path)
    rows = [r for r in rows or [] if isinstance(r.get("agent_id"), str) and isinstance(r.get("at_ms"), int)
            and isinstance(r.get("seq"), int) and r.get("event") in ("start", "pre", "batch", "stop")]
    if not rows:
        return set(), False
    agent = rows[0]["agent_id"]
    state, record, parent = _resolve(data_dir, agent)
    if state == "none":
        return set(), False
    if state == "unbound":
        return set(), _finished(rows)
    reasons = set()
    track_dir = record["track_dir"]
    try:
        timing.bind_actor(track_dir, record["run_id"], agent, record["session_id"], SOURCE_ID, agent, parent)
    except ValueError as exc:
        reasons.add(str(exc))
    if not reasons:
        observations = [{k: r[k] for k in ("seq", "event", "at_ms", "tool_use_id", "tool_use_ids") if k in r}
                        for r in rows]
        reasons |= set(timing.collect_event(record["project_dir"], "claude", record["session_id"],
                                            agent, agent, {"observations": observations}))
    if "run-closed" in reasons:
        runs = timing._run_events(track_dir, record["run_id"])[1]
        if len(runs) == 1:
            _write_gap(track_dir, record["run_id"], runs[0]["stage"], runs[0]["platform"], agent, "run-closed")
    retry = reasons & {"journal-unreadable", "binding-missing", "binding-ambiguous"}
    return reasons, _finished(rows) and not retry


def _expire(data_dir, now_ms):
    for kind in ("obs", "bind"):
        folder = _dir(data_dir, kind)
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            path = os.path.join(folder, name)
            try:
                if now_ms / 1000 - os.path.getmtime(path) > EXPIRY_SECONDS:
                    os.remove(path)
            except OSError:
                pass
        try:
            os.rmdir(folder)  # only succeeds when empty
        except OSError:
            pass


def _settle(data_dir, now_ms):
    reasons = set()
    folder = _dir(data_dir, "obs")
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        names = []
    for name in names:
        path = os.path.join(folder, name)
        try:
            found, delete = _settle_one(data_dir, path)
        except (ValueError, OSError, KeyError):
            continue
        reasons |= found
        if delete:
            try:
                os.remove(path)
            except OSError:
                pass
    _expire(data_dir, now_ms)
    return sorted(reasons)


def settle(data_dir, now_ms):
    with _Lock(data_dir):
        return _settle(data_dir, now_ms)


def main():
    now_ms = time.time_ns() // 1_000_000  # first action: the clock reading is the event time
    try:
        data_dir, project_dir = os.environ.get("CLAUDE_PLUGIN_DATA"), os.environ.get("CLAUDE_PROJECT_DIR")
        if data_dir and project_dir:
            # Bytes, so json detects UTF-8 itself; text-mode stdin uses the locale code page.
            observe(json.loads(sys.stdin.buffer.read()), data_dir, project_dir, now_ms)
    except Exception as exc:  # never break the tool call the hook is attached to
        print("timing_hook: " + type(exc).__name__, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
