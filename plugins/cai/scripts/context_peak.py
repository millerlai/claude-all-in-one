#!/usr/bin/env python3
"""Peak per-request context occupancy for one orchestrator session.

Imports only the standard library plus two sibling modules in this same
directory (usage_collector for the transcript, ledger for the track's own
ledger.jsonl). No third-party dependency.

Usage:  context_peak.py --track-dir DIR  [--project-dir DIR] [--window N]
        context_peak.py --session-id ID  [--project-dir DIR] [--window N]
Exit:   0 at least one peak was printed, 2 nothing measurable, 1 usage error.
"""
import argparse
import os
import sys

import ledger
import usage_collector

DEFAULT_WINDOW = 1000000


def occupancy(usage):
    """int: what one request had to have resident -- input_tokens plus
    cache_read_input_tokens plus usage_collector.cache_creation_total().
    Not output_tokens: those are produced, not resident, and come back as
    part of the next request's input_tokens.

    The first two keys are guaranteed present and non-negative by
    _valid_usage(), which usage_records() already applied; the third is
    not a validated key and cache_creation_total() answers 0 for it
    rather than raising.

    Reads the top-level fields only. message.usage also carries an
    `iterations` list repeating the same fields; summing it would count
    one request several times."""
    return (usage["input_tokens"] + usage["cache_read_input_tokens"]
            + usage_collector.cache_creation_total(usage))


def peak(records):
    """(tokens, record) for the largest occupancy() among `records`, or
    (0, None) when there are none. `records` is what
    usage_collector.usage_records() yields, so `record` is the
    (number, request_id, model, usage, timestamp) five-tuple and carries
    everything format_line() needs. Ties go to the first, so the position
    reported is where the ceiling was first reached."""
    best_tokens, best_record = 0, None
    for record in records:
        tokens = occupancy(record[3])
        if best_record is None or tokens > best_tokens:
            best_tokens, best_record = tokens, record
    return best_tokens, best_record


def session_ids(track_dir):
    """[str]: distinct non-null `session_id` values in a track's
    ledger.jsonl, in first-appearance order.

    Delegates the reading to ledger.records(track_dir) rather than opening
    the file: that function already treats a missing file as zero records
    and a bad line as a malformed placeholder instead of raising, and
    writing a second reader for the same file is the defect this track
    exists to remove. Malformed placeholders carry no session_id and drop
    out naturally.

    A track recorded before usage tracking landed has only nulls and
    yields [] -- reported by main(), never raised on."""
    seen = []
    for record in ledger.records(track_dir):
        sid = record.get("session_id")
        if sid and sid not in seen:
            seen.append(sid)
    return seen


def measure(session_id, project_dir, projects_root=None):
    """(tokens, record, problems) for one session's own transcript.
    Orchestrator only: subagent transcripts live in a sibling
    `subagents/` directory and are a different window.

    `record` is None, and `problems` carries a named reason, in both of
    the two ways this can come up empty: no transcript file for that
    session on this machine, and a transcript that exists but holds no
    usable record (empty file, no assistant lines, or every line rejected).
    Neither may be reported as a peak of 0 -- zero would claim the session
    used nothing, which is not a fact this can assert."""
    problems = []
    root = projects_root or usage_collector._projects_root()
    path = usage_collector.session_transcript(root, project_dir, session_id)
    if path is None:
        return 0, None, ["no session transcript for session %s under %s"
                          % (session_id, root)]
    lines = usage_collector.read_window(path, None, None, problems)
    records = usage_collector.usage_records(lines, path, problems)
    tokens, record = peak(records)
    if record is None:
        problems.append("no usable assistant record in %s" % path)
        return 0, None, problems
    return tokens, record, problems


def format_line(session_id, tokens, record, window):
    """One line: the session id, the peak, its percentage of `window`, and
    the position -- the record's timestamp, its requestId, and its
    assistant-record ordinal. Never called with record=None; main() routes
    that case to stderr."""
    number, request_id, _model, _usage, timestamp = record
    pct = 100.0 * tokens / window if window else 0.0
    return ("%s peak %d tokens (%.1f%% of %d) at %s %s (assistant record %d)"
            % (session_id, tokens, pct, window, timestamp, request_id, number))


def main(argv=None):
    """Exactly one of --track-dir / --session-id, else exit 1.
    --project-dir defaults to os.getcwd(); it is required because the
    per-track ledger.jsonl does not carry the project path.

    Prints one line per session that yielded a peak; every `problems`
    entry goes to stderr. Exit 0 if at least one session printed a peak,
    2 if none did -- a track with one measurable and one unmeasurable
    session is a 0 with a stderr note, not a failure."""
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--track-dir")
    group.add_argument("--session-id")
    parser.add_argument("--project-dir", default=os.getcwd())
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    args = parser.parse_args(argv)

    if args.track_dir:
        ids = session_ids(args.track_dir)
        if not ids:
            print("no session_id recorded in %s" % args.track_dir, file=sys.stderr)
            return 2
    else:
        ids = [args.session_id]

    printed = False
    for sid in ids:
        tokens, record, problems = measure(sid, args.project_dir)
        for problem in problems:
            print(problem, file=sys.stderr)
        if record is not None:
            print(format_line(sid, tokens, record, args.window))
            printed = True
    return 0 if printed else 2


if __name__ == "__main__":
    sys.exit(main())
