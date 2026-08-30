#!/usr/bin/env python3
"""Append-only attempt ledger for one track. Zero deps.

state.md keeps one row per stage and the track overwrites it, so a stage that
runs twice leaves no trace of the first run. This file is the record that does
not get overwritten: one JSON object per line, appended, never edited.

Why this script writes when track_state.py:6 says the scripts only read: that
rule exists because state.md's note is prose the model wrote, so the model owns
the row. Every field here except note is a reproducible computation -- a
timestamp, a closed-set enum, a SHA-256 of bytes on disk -- and handing those
to the model is exactly what this file exists to prevent (R3). The rule does
not apply, and this is the exception, not a convention being dropped.

This file used to import nothing from this repo; that changed when usage
tracking landed. track_state.py already imports preflight, and preflight
imports this file -- a third edge back to either of them would close the
cycle. usage_collector.py is safe to import because it is a leaf on that
chain: only ledger.py imports it, and it imports nothing from this repo in
turn, so no edge points back. stage_ids() and ArgParser below are still
copied from track_state.py:31-33 and :133-138 rather than imported, for the
same reason as always -- deliberate duplication, bought with a dependency
cycle removed -- do not "fix" it.

Usage:  ledger.py append --track-dir DIR --stage S --outcome O
                        [--artifact P] [--gate auto|human] [--note TEXT]
        ledger.py show   --track-dir DIR [--stage S]
Exit:   0 written (a truncated note still counts), 2 refused, 1 usage error.
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

import usage_collector

HERE = os.path.dirname(os.path.abspath(__file__))
STAGES_JSON = os.path.join(HERE, "..", "skills", "track", "stages.json")
LEDGER_NAME = "ledger.jsonl"

OUTCOMES = ("passed", "failed", "blocked", "skipped", "unavailable")
GATES = ("auto", "human")

# What the retry cap is allowed to count. `unavailable` is deliberately absent:
# a provider that refused to serve the request did not produce an attempt that
# failed, it produced no attempt at all, and five rate limits must not lock a
# stage nobody did anything wrong in.
COUNTS_AS_RETRY = ("failed", "blocked")

# A record has to land in one write, and one write is only atomic up to a size
# the platform decides. 4096 is the user's call (2026-08-29); the note gets
# whatever is left after the mechanical fields.
MAX_RECORD = 4096
MAX_NOTE = 3840
TRUNCATED = "…[truncated]"

# D7: the central record is record plus `project` and `track`, so it is the
# larger of the two things one append() writes -- it is the one _fit()
# shrinks to. The reserve is spent on `synced`/`sync_error`, added only
# after the central write, so it must be held back before _fit ever runs.
SYNC_RESERVE = 256
CENTRAL_FIT_LIMIT = MAX_RECORD - SYNC_RESERVE
SYNC_ERROR_MAX = 200

# state.md's "no artifact" cell, so `/cai:track skip` can be recorded as-is.
NO_ARTIFACT = "—"

# Enough of a broken line to recognise it, not enough to bloat the report.
RAW_KEEP = 200


def stage_ids():
    with open(STAGES_JSON, encoding="utf-8") as fh:
        return [row["id"] for row in json.load(fh)["stages"]]


def _path(track_dir):
    return os.path.join(track_dir, LEDGER_NAME)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_ms():
    """Millisecond-precision UTC ISO 8601 string, matching what
    usage_collector._parse_ms() expects (D4). `ts` above stays second
    precision -- this is the separate `window_end` field, not a replacement."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)


def _window_since(session_id):
    """The lower bound for this attempt's usage window: the latest
    `window_end` this session has anywhere in the central ledger -- across
    every track and project, not just this one -- or, when there is none,
    the import-day floor (R3, D10).

    Scoped to the session, not to (session, track) (Blocker, 2026-08-30): a
    session's own ledger.jsonl only has entries for tracks it has already
    written to, so a session that starts a second track mid-conversation
    would never find itself there and would fall back to the floor,
    re-counting everything the first track's window already covered. The
    central ledger has every track's records in one place, so it is the
    only file that can answer "since" for the session as a whole."""
    since = _data_start_floor()
    try:
        with open(usage_collector.central_ledger_path(), "rb") as fh:
            raw = fh.read()
    except OSError:
        return since
    for text in raw.decode("utf-8", "replace").splitlines():
        if not text.strip():
            continue
        try:
            record = json.loads(text)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("session_id") != session_id:
            continue
        window_end = record.get("window_end")
        # window_end is a fixed-width millisecond ISO 8601 string (D4), so
        # lexicographic comparison agrees with chronological order.
        if window_end and (since is None or window_end > since):
            since = window_end
    return since


def _data_start_floor():
    """Midnight UTC of the day the central ledger was first created, as a
    `window_end`-shaped string -- or None when no marker has been written
    yet, meaning this machine has never recorded anything to floor
    against (D10: the date is written down, not derived from the central
    ledger's earliest record, which cannot exist yet on that first call)."""
    try:
        with open(usage_collector.data_start_path(), encoding="utf-8") as fh:
            date = fh.read().strip()
    except OSError:
        return None
    if not date:
        return None
    return date + "T00:00:00.000Z"


def _collapse_usage(bucket):
    """Per-model detail -> one dict of the five token totals, summed across
    every model in `bucket`. Step 4 of _fit (D5): the source is a 30-day
    transcript, so once it is gone only the total survives."""
    totals = {key: 0 for key in usage_collector.TOKEN_KEYS}
    for model_totals in bucket.values():
        for key in usage_collector.TOKEN_KEYS:
            totals[key] += model_totals.get(key, 0)
    return totals


def _encode(record):
    return (json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            + "\n").encode("utf-8")


def _cut(text, keep_bytes):
    """`text` shortened to at most keep_bytes of UTF-8, never mid-character."""
    if keep_bytes <= 0:
        return ""
    return text.encode("utf-8")[:keep_bytes].decode("utf-8", "ignore")


def _sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class LedgerError(Exception):
    """A write this script refuses to make. Carries the message the caller sees."""


def append(track_dir, stage, outcome, artifact=None, gate="auto", note=""):
    """Add one record and return it. Raises LedgerError rather than writing
    something that would be wrong: reading is forgiving, writing is strict."""
    if outcome not in OUTCOMES:
        raise LedgerError("unknown outcome: %s (expected one of %s)"
                          % (outcome, ", ".join(OUTCOMES)))
    if gate not in GATES:
        raise LedgerError("unknown gate: %s (expected one of %s)"
                          % (gate, ", ".join(GATES)))
    ids = stage_ids()
    if stage not in ids:
        raise LedgerError("unknown stage: %s (expected one of %s)"
                          % (stage, ", ".join(ids)))

    # An empty cell and the em dash both mean "this stage produced nothing",
    # which is a fact worth recording, not a path that failed to resolve.
    named = artifact not in (None, "", NO_ARTIFACT)
    digest = None
    if named:
        try:
            digest = _sha256(artifact)
        except OSError as exc:
            raise LedgerError("cannot read artifact %s: %s" % (artifact, exc))

    note = note or ""
    if len(note.encode("utf-8")) > MAX_NOTE:
        note = _cut(note, MAX_NOTE - len(TRUNCATED.encode("utf-8"))) + TRUNCATED

    # Usage is a reproducible computation, not something a caller can pass in
    # (D2) -- so it is fetched here, not accepted as a parameter. Missing a
    # session id is not an error (D3): both columns stay empty dict and the
    # reason goes in usage_problems, the record still gets written.
    session_id = usage_collector.session_id_from_env()
    window_end = _now_ms()
    if session_id is None:
        orchestration, agents = {}, {}
        usage_problems = ["no session id: CLAUDE_CODE_SESSION_ID is not set"]
    else:
        since = _window_since(session_id)
        orchestration, agents, usage_problems = usage_collector.collect(
            session_id, os.getcwd(), since, window_end)

    record = {"ts": _now(), "stage": stage, "outcome": outcome,
              "artifact": artifact if named else None, "sha256": digest,
              "gate": gate, "note": note,
              "orchestration": orchestration, "agents": agents,
              "usage_problems": usage_problems,
              "window_end": window_end, "session_id": session_id}

    # D7: fit the central candidate -- record plus project and track, the
    # larger of the two things this call writes -- not the per-track shape.
    # D6: this runs before either write, so a refusal here (line is None)
    # leaves both files untouched; no orphan is possible on this path.
    central = dict(record)
    central["project"] = os.getcwd()
    central["track"] = os.path.basename(os.path.normpath(track_dir))

    line, why = _fit(central, limit=CENTRAL_FIT_LIMIT)
    if line is None:
        raise LedgerError(why)
    if why:
        print(why, file=sys.stderr)

    # D6: central write comes before synced is decided, which comes before
    # the per-track write -- per-track is append-only, so synced must be
    # known before that line is ever written, and it can only be known
    # after the central write has been attempted.
    central_path = usage_collector.central_ledger_path()
    try:
        os.makedirs(os.path.dirname(central_path), exist_ok=True)
    except OSError:
        pass  # _write_line below will surface the real reason
    first_write = not os.path.exists(central_path)
    try:
        _write_line(central_path, line)
        sync_error = None
    except OSError as exc:
        sync_error = str(exc)
    if sync_error is None and first_write:
        _mark_data_start()

    # Both writes share the same fitted core content (D7) -- the per-track
    # copy is that content minus project/track, plus this pair.
    per_track = dict(central)
    del per_track["project"]
    del per_track["track"]
    per_track["synced"] = sync_error is None
    if sync_error is not None:
        per_track["sync_error"] = _cut(sync_error, SYNC_ERROR_MAX)
        _fit_sync_error(per_track)

    _write_line(_path(track_dir), _encode(per_track))
    return per_track


def _fit_sync_error(per_track):
    """Shrinks or drops `per_track["sync_error"]` in place until the whole
    record encodes within MAX_RECORD (Major-2). SYNC_RESERVE is a fixed
    budget spent before this ever runs, not a guarantee: json.dumps doubles
    every backslash, and a Windows OSError message is mostly backslash-heavy
    paths, so 200 raw characters of it can still cost 400 encoded bytes --
    more than the reserve holds. Re-checked here, after encoding, rather
    than trusted."""
    while per_track.get("sync_error") and len(_encode(per_track)) > MAX_RECORD:
        over = len(_encode(per_track)) - MAX_RECORD
        current = per_track["sync_error"]
        keep = max(0, len(current.encode("utf-8")) - over)
        shorter = _cut(current, keep)
        if shorter == current:
            break  # cutting made no progress -- stop rather than loop forever
        per_track["sync_error"] = shorter
    if per_track.get("sync_error") and len(_encode(per_track)) > MAX_RECORD:
        del per_track["sync_error"]  # nothing left to drop but the field itself


def _mark_data_start():
    """Writes today's UTC date to the central ledger's start-date sibling,
    once (D10). The date is written down rather than derived from the
    ledger's earliest record: an empty ledger cannot answer "installed but
    never ran" versus "not installed" any other way."""
    path = usage_collector.data_start_path()
    if os.path.exists(path):
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d") + "\n")


def _write_line(path, line):
    """Add one line to the end of `path`, whole, without disturbing what is
    already there.

    POSIX gives this for free: O_APPEND makes the offset update and the write
    one atomic step, so a single unbuffered os.write cannot interleave.

    Windows does not. CPython's os.open goes through the CRT, whose _O_APPEND
    seeks to the end and then writes as two separate operations, so two
    processes can take the same offset and one silently overwrites the other.
    Measured, not assumed: 8 processes appending 50 records each lost 40 of
    them on this machine before the lock below existed. So on Windows the seek
    and the write happen inside an exclusive lock on byte 0 -- a byte no record
    ever needs, held for the microseconds the write takes."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND
                 | getattr(os, "O_BINARY", 0), 0o644)
    try:
        if os.name != "nt":
            os.write(fd, line)
            return
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        try:
            os.lseek(fd, 0, os.SEEK_END)
            os.write(fd, line)
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(fd)


def _fit(record, limit=MAX_RECORD):
    """Shrink `record` in place until it encodes within `limit`.

    Returns (line_bytes, explanation) -- or (None, reason) when even the last
    step is too big. `explanation` is empty when nothing had to be dropped.
    Truncating beats refusing: an attempt that really happened but has no
    record makes the count wrong, and the count is what gates the retry."""
    line = _encode(record)
    if len(line) <= limit:
        return line, ""

    mark = len(TRUNCATED.encode("utf-8"))
    had = len(record["note"].encode("utf-8"))
    budget = had - (len(line) - limit)      # bytes the note may still keep
    if budget > mark:
        record["note"] = _cut(record["note"], budget - mark) + TRUNCATED
    elif had > mark:
        # No room for text, but the marker fits where the note used to be, so
        # the reader still learns something was cut.
        record["note"] = TRUNCATED
    else:
        # The note was never big enough to be the problem; the marker would
        # make the record longer, not shorter.
        record["note"] = ""
    line = _encode(record)
    if len(line) <= limit:
        return line, "note truncated to fit %d bytes" % limit

    # Step 1 already emptied the note, so the only field left with slack is the
    # artifact path. Its basename still names the file; the directories do not.
    if record["artifact"]:
        record["artifact"] = os.path.basename(record["artifact"])
        line = _encode(record)
        if len(line) <= limit:
            return line, ("note dropped and artifact reduced to its basename "
                          "to fit %d bytes" % limit)

    # Step 3 (D5): the number of distinct models has no ceiling, so per-model
    # detail is the one field that can grow without bound. Collapse it to the
    # five token totals it came from -- the source transcript is gone in 30
    # days, but the total survives in the record forever.
    if record.get("orchestration") or record.get("agents"):
        record["orchestration"] = _collapse_usage(record.get("orchestration") or {})
        record["agents"] = _collapse_usage(record.get("agents") or {})
        record["usage_collapsed"] = True
        line = _encode(record)
        if len(line) <= limit:
            return line, ("usage detail collapsed to per-source totals "
                          "to fit %d bytes" % limit)

    return None, ("record is %d bytes with nothing left to drop (limit %d)"
                  % (len(line), limit))


def records(track_dir, stage=None):
    """Every record in file order. Missing file is zero records, not an error
    (R4); an unparseable line becomes a malformed placeholder rather than an
    exception (R5). With `stage`, only that stage's records -- plus every
    malformed line, which belongs to no stage but must stay visible."""
    try:
        with open(_path(track_dir), "rb") as fh:
            raw = fh.read()
    except OSError:
        return []

    out = []
    for number, text in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
        if not text.strip():
            continue
        try:
            record = json.loads(text)
            if not isinstance(record, dict):
                raise ValueError("not an object")
        except (ValueError, TypeError):
            out.append({"malformed": True, "line": number, "raw": text[:RAW_KEEP]})
            continue
        record["line"] = number
        out.append(record)

    if stage is None:
        return out
    return [r for r in out if r.get("malformed") or r.get("stage") == stage]


def streak(track_dir, stage):
    """This stage's records since it last passed or was skipped, that one not
    included, numbered from 1. Malformed lines are left out: they belong to no
    stage, so counting them here would push all six stages up by one."""
    clean = [r for r in records(track_dir, stage) if not r.get("malformed")]
    start = 0
    for index, record in enumerate(clean):
        if record.get("outcome") in ("passed", "skipped"):
            start = index + 1
    run = clean[start:]
    for number, record in enumerate(run, 1):
        record["attempt"] = number
    return run


def last_passed(track_dir, stage):
    """This stage's last `passed` record, or None. Only `passed` -- a skipped
    stage clears the retry count but has no one who let it through and no
    artifact to fingerprint."""
    found = None
    for record in records(track_dir, stage):
        if not record.get("malformed") and record.get("outcome") == "passed":
            found = record
    return found


def attempts(track_dir, stage):
    return sum(1 for r in streak(track_dir, stage)
               if r.get("outcome") in COUNTS_AS_RETRY)


def fingerprint(track_dir, stage):
    record = last_passed(track_dir, stage)
    return record.get("sha256") if record else None


def malformed_lines(track_dir):
    return [r["line"] for r in records(track_dir) if r.get("malformed")]


def _format_totals(totals):
    return " ".join("%s=%d" % (key, totals.get(key, 0))
                    for key in usage_collector.TOKEN_KEYS)


def _usage_lines(record):
    """Indented continuation lines for one record's usage, or [] when there
    is nothing to say (D8: the row above never changes). A bucket that is an
    empty dict prints nothing for that section -- an old record missing the
    keys entirely (D11) and a new record that genuinely saw no usage read
    the same way, on purpose: neither has anything to report. `usage_problems`
    is what tells the two apart from "unknown", by showing up on its own."""
    lines = []
    collapsed = record.get("usage_collapsed")
    for label in ("orchestration", "agents"):
        bucket = record.get(label) or {}
        if not bucket:
            continue
        if collapsed:
            lines.append("      %s (collapsed totals): %s"
                         % (label, _format_totals(bucket)))
        else:
            for model_id in sorted(bucket):
                lines.append("      %s %s: %s"
                             % (label, model_id, _format_totals(bucket[model_id])))
    problems = record.get("usage_problems") or []
    if problems:
        lines.append("      usage problems: %s" % "; ".join(problems))
    return lines


def show(track_dir, stage=None):
    rows = records(track_dir, stage)
    if not rows:
        print("no records in %s" % _path(track_dir))
        return 0
    for record in rows:
        if record.get("malformed"):
            print("%4d  malformed  %s" % (record["line"], record["raw"]))
            continue
        # The outcome column is as wide as the longest value in OUTCOMES, so
        # adding one there cannot silently break the alignment again.
        print("%4d  %s  %-8s  %-*s  %-5s  %s  %s" % (
            record.get("line", 0), record.get("ts", ""), record.get("stage", ""),
            max(len(o) for o in OUTCOMES), record.get("outcome", ""),
            record.get("gate", ""),
            record.get("artifact") or NO_ARTIFACT, record.get("note", "")))
        for line in _usage_lines(record):
            print(line)
    return 0


class ArgParser(argparse.ArgumentParser):
    # argparse's own error() exits 2, which this script reserves for "refused".
    # A usage mistake is a different failure and gets 1.
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(1)


def main():
    # Notes are prose a person wrote, so they carry whatever alphabet that
    # person uses, and `—` is the sentinel for "no artifact". On Windows a
    # piped stdout defaults to the ANSI codepage, so the caller reading this
    # output back gets bytes it cannot decode. The console path is already
    # UTF-8 (PEP 528), so this only changes the piped case -- the one the
    # track skill uses.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = ArgParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["append", "show"])
    ap.add_argument("--track-dir", required=True)
    ap.add_argument("--stage")
    ap.add_argument("--outcome")
    ap.add_argument("--artifact")
    ap.add_argument("--gate", default="auto")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    if args.command == "show":
        return show(args.track_dir, args.stage)

    if not args.stage or not args.outcome:
        ap.error("append needs --stage and --outcome")
    try:
        record = append(args.track_dir, args.stage, args.outcome,
                        args.artifact, args.gate, args.note)
    except LedgerError as exc:
        print(exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("cannot write the ledger: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
