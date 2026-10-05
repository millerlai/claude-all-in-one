"""Reproducible stage work unions and source completeness. Zero deps."""
import os

import ledger
import timing


def _gap(event, reason):
    return {"stage": event.get("stage"), "run_id": event.get("run_id"),
            "reason": reason}


def _records(events):
    records = {}
    conflicts = set()
    gaps = []
    for event in events:
        if not isinstance(event, dict):
            gaps.append(_gap({}, "journal-malformed"))
            continue
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            gaps.append(_gap(event, "journal-malformed"))
            continue
        if event_id in records and records[event_id] != event:
            gaps.extend([_gap(records[event_id], "event-conflict"),
                         _gap(event, "event-conflict")])
            conflicts.add(event_id)
        else:
            records[event_id] = event
    valid = []
    for event_id, event in records.items():
        if event_id in conflicts:
            continue
        try:
            timing._validate(event)
        except ValueError as exc:
            gaps.append(_gap(event, str(exc)))
        else:
            valid.append(event)
    ownership = {}
    for event in valid:
        ownership.setdefault(event["run_id"], set()).add((event["stage"], event["platform"]))
    safe = []
    for event in valid:
        if len(ownership[event["run_id"]]) != 1:
            gaps.append(_gap(event, "binding-ambiguous"))
            continue
        try:
            timing._check_binding(valid, event)
        except ValueError as exc:
            gaps.append(_gap(event, str(exc)))
        else:
            safe.append(event)
    return safe, gaps


def _intervals(events):
    intervals = {stage: [] for stage in ledger.stage_ids()}
    gaps = []
    activities = {}
    for event in events:
        if event["kind"] in ("work_begin", "work_end"):
            key = tuple(event[name] for name in
                        ("run_id", "actor_id", "source_id", "activity_id"))
            activities.setdefault(key, []).append(event)
    for rows in activities.values():
        begin = [row for row in rows if row["kind"] == "work_begin"]
        end = [row for row in rows if row["kind"] == "work_end"]
        if len(begin) > 1 or len(end) > 1:
            reason = "activity-ambiguous"
        elif not begin:
            reason = "begin-missing"
        elif not end:
            reason = "open-activity"
        elif end[0]["at_ms"] < begin[0]["at_ms"]:
            reason = "invalid-boundary"
        else:
            runs = [row for row in events if row["kind"] == "run_begin"
                    and timing._same_run(row, begin[0])]
            if len(runs) != 1:
                reason = "binding-ambiguous" if runs else "binding-missing"
            else:
                intervals[begin[0]["stage"]].append((begin[0]["at_ms"], end[0]["at_ms"]))
                continue
        gaps.append(_gap(rows[0], reason))
    return intervals, gaps


def work_intervals(events: list[dict]) -> tuple[dict[str, list[tuple[int, int]]], list[dict]]:
    records, gaps = _records(events)
    intervals, activity_gaps = _intervals(records)
    gaps += [_gap(row, row["reason"]) for row in records if row["kind"] == "gap"]
    return intervals, gaps + activity_gaps


def union_ms(intervals: list[tuple[int, int]]) -> int:
    total = 0
    right = None
    for start, end in sorted(intervals):
        if right is None or start > right:
            total += end - start
        elif end > right:
            total += end - right
        right = end if right is None else max(right, end)
    return total


def _run_gaps(events):
    gaps = []
    runs = {}
    for event in events:
        runs.setdefault((event["run_id"], event["stage"], event["platform"]), []).append(event)
    for rows in runs.values():
        begin = [row for row in rows if row["kind"] == "run_begin"]
        if len(begin) != 1:
            gaps.append(_gap(rows[0], "binding-ambiguous" if begin else "binding-missing"))
        if not any(row["kind"] == "run_end" for row in rows):
            gaps.append(_gap(rows[0], "run-open"))
        bindings = [row for row in rows if row["kind"] == "actor_bind"]
        keys = [(row["actor_id"], row["source_id"]) for row in bindings]
        if len(keys) != len(set(keys)):
            gaps.append(_gap(rows[0], "binding-ambiguous"))
        coverage = [row for row in rows if row["kind"] == "source_coverage"
                    and set(row["coverage_scope"]) == timing.COVERAGE_SCOPE]
        # Each source must prove all bound actors, rather than borrowing a different source's proof.
        sources = {row["source_id"] for row in bindings}
        covered = bool(sources)
        for source in sources:
            actors = {row["actor_id"] for row in bindings if row["source_id"] == source}
            covered = covered and any(row["source_id"] == source
                                      and actors <= set(row["actor_ids"]) for row in coverage)
        if not covered:
            gaps.append(_gap(rows[0], "coverage-missing"))
        for row in rows:
            if row["kind"] == "gap":
                gaps.append(_gap(row, row["reason"]))
    return gaps


def track_timing(events: list[dict], problems: list[str]) -> dict[str, dict]:
    records, gaps = _records(events)
    intervals, activity_gaps = _intervals(records)
    gaps += activity_gaps + _run_gaps(records)
    reasons = {stage: set(problems) for stage in ledger.stage_ids()}
    for gap in gaps:
        stages = [gap["stage"]] if gap["stage"] in reasons else reasons
        for stage in stages:
            reasons[stage].add(gap["reason"])
    # An unsupported version prevents interpreting any part of that file as format 1.
    unsupported = "unsupported-format" in problems or any(
        gap["reason"] == "unsupported-format" for gap in gaps)
    if unsupported:
        for stage in reasons:
            reasons[stage].add("unsupported-format")
            intervals[stage] = []
    result = {}
    for stage in ledger.stage_ids():
        present = any(row.get("stage") == stage for row in events if isinstance(row, dict))
        status = "incomplete" if reasons[stage] else "complete" if present else "no-data"
        elapsed = union_ms(intervals[stage]) if intervals[stage] or status == "complete" else None
        result[stage] = {"elapsed_ms": elapsed, "timing_status": status,
                         "timing_reasons": sorted(reasons[stage])}
    return result


def timing_report(track_dir: str) -> dict[str, dict]:
    events, problems = timing.read_events(track_dir)
    if not events and not problems and os.path.exists(os.path.join(track_dir, timing.TIMING_NAME)):
        problems = ["journal-malformed"]
    return track_timing(events, problems)
