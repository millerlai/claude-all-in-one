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

It imports nothing from this repo, on purpose. track_state.py already imports
preflight, and preflight imports this file; a third edge back to either of them
would close the cycle. So stage_ids() and ArgParser below are copied from
track_state.py:31-33 and :133-138 rather than imported. Deliberate duplication,
bought with a dependency cycle removed -- do not "fix" it.

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

HERE = os.path.dirname(os.path.abspath(__file__))
STAGES_JSON = os.path.join(HERE, "..", "skills", "track", "stages.json")
LEDGER_NAME = "ledger.jsonl"

OUTCOMES = ("passed", "failed", "blocked", "skipped")
GATES = ("auto", "human")

# A record has to land in one write, and one write is only atomic up to a size
# the platform decides. 4096 is the user's call (2026-08-29); the note gets
# whatever is left after the mechanical fields.
MAX_RECORD = 4096
MAX_NOTE = 3840
TRUNCATED = "…[truncated]"

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

    record = {"ts": _now(), "stage": stage, "outcome": outcome,
              "artifact": artifact if named else None, "sha256": digest,
              "gate": gate, "note": note}

    line, why = _fit(record)
    if line is None:
        raise LedgerError(why)
    if why:
        print(why, file=sys.stderr)

    _write_line(_path(track_dir), line)
    return record


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


def _fit(record):
    """Shrink `record` in place until it encodes within MAX_RECORD.

    Returns (line_bytes, explanation) -- or (None, reason) when even the last
    step is too big. `explanation` is empty when nothing had to be dropped.
    Truncating beats refusing: an attempt that really happened but has no
    record makes the count wrong, and the count is what gates the retry."""
    line = _encode(record)
    if len(line) <= MAX_RECORD:
        return line, ""

    mark = len(TRUNCATED.encode("utf-8"))
    had = len(record["note"].encode("utf-8"))
    budget = had - (len(line) - MAX_RECORD)      # bytes the note may still keep
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
    if len(line) <= MAX_RECORD:
        return line, "note truncated to fit %d bytes" % MAX_RECORD

    # Step 1 already emptied the note, so the only field left with slack is the
    # artifact path. Its basename still names the file; the directories do not.
    if record["artifact"]:
        record["artifact"] = os.path.basename(record["artifact"])
        line = _encode(record)
        if len(line) <= MAX_RECORD:
            return line, ("note dropped and artifact reduced to its basename "
                          "to fit %d bytes" % MAX_RECORD)

    return None, ("record is %d bytes with nothing left to drop (limit %d)"
                  % (len(line), MAX_RECORD))


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
               if r.get("outcome") in ("failed", "blocked"))


def fingerprint(track_dir, stage):
    record = last_passed(track_dir, stage)
    return record.get("sha256") if record else None


def malformed_lines(track_dir):
    return [r["line"] for r in records(track_dir) if r.get("malformed")]


def show(track_dir, stage=None):
    rows = records(track_dir, stage)
    if not rows:
        print("no records in %s" % _path(track_dir))
        return 0
    for record in rows:
        if record.get("malformed"):
            print("%4d  malformed  %s" % (record["line"], record["raw"]))
            continue
        print("%4d  %s  %-8s  %-7s  %-5s  %s  %s" % (
            record.get("line", 0), record.get("ts", ""), record.get("stage", ""),
            record.get("outcome", ""), record.get("gate", ""),
            record.get("artifact") or NO_ARTIFACT, record.get("note", "")))
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
