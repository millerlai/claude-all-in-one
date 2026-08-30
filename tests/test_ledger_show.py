"""`show`'s continuation lines: the same fixed-width row as before, plus an
indented per-model usage breakdown underneath when the record has one.

D8 (docs/design/2026-08-30-track-usage-accounting-detail.md) requires the
existing row to stay byte-for-byte the same -- these tests write records
straight to ledger.jsonl rather than through `ledger.append()`, so each one
controls exactly which usage fields are present without needing a real
session transcript.
"""
import json
import os

import ledger
import usage_collector

BASE = {"ts": "2026-08-30T00:00:00Z", "stage": "build", "outcome": "passed",
        "artifact": None, "sha256": None, "gate": "auto", "note": "a note"}


def write_record(track_dir, **overrides):
    os.makedirs(track_dir, exist_ok=True)
    record = dict(BASE, **overrides)
    with open(os.path.join(track_dir, "ledger.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def totals(n):
    return {key: n for key in usage_collector.TOKEN_KEYS}


def main_line(out):
    """The first line of output -- the unchanged fixed-width row."""
    return out.splitlines()[0]


# --- one line per model, two sections -------------------------------------

def test_usage_prints_two_sections_one_line_per_model(tmp_path, capsys):
    track = str(tmp_path)
    write_record(track,
                 orchestration={"claude-opus-4-5-20251101": totals(10)},
                 agents={"claude-haiku-4-5-20251001": totals(3),
                        "claude-sonnet-4-5-20250929": totals(7)},
                 usage_problems=[])

    assert ledger.show(track) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()

    # The original row is untouched: line/ts/stage/outcome/gate/artifact/note.
    assert "build" in main_line(out) and "passed" in main_line(out)
    assert "a note" in main_line(out)

    assert any("orchestration" in ln and "claude-opus-4-5-20251101" in ln
              for ln in lines[1:])
    assert any("agents" in ln and "claude-haiku-4-5-20251001" in ln
              for ln in lines[1:])
    assert any("agents" in ln and "claude-sonnet-4-5-20250929" in ln
              for ln in lines[1:])
    # Continuation lines are indented, so they read as part of the row above.
    for ln in lines[1:]:
        assert ln.startswith(" ")


# --- D11 / backward compatibility: old records get no continuation --------

def test_old_record_without_usage_fields_prints_no_continuation(tmp_path, capsys):
    track = str(tmp_path)
    write_record(track)  # only the seven pre-existing keys

    assert ledger.show(track) == 0
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.strip()]

    assert len(lines) == 1


# --- usage_problems surfaces on its own line --------------------------------

def test_usage_problems_are_printed(tmp_path, capsys):
    track = str(tmp_path)
    reason = "no session id: CLAUDE_CODE_SESSION_ID is not set"
    write_record(track, orchestration={}, agents={}, usage_problems=[reason])

    ledger.show(track)
    out = capsys.readouterr().out
    assert reason in out


# --- a collapsed record reads as collapsed, not as one lone model ----------

def test_collapsed_record_shows_it_was_collapsed(tmp_path, capsys):
    track = str(tmp_path)
    write_record(track, orchestration=totals(100), agents=totals(50),
                 usage_problems=[], usage_collapsed=True)

    ledger.show(track)
    out = capsys.readouterr().out
    assert "collapsed" in out.lower()


# --- confirmed-empty and unknown must not both read as zero ---------------

def test_confirmed_empty_and_unknown_usage_read_differently(tmp_path, capsys):
    known_empty = str(tmp_path / "known-empty")
    write_record(known_empty, orchestration={}, agents={}, usage_problems=[])
    ledger.show(known_empty)
    confirmed_out = capsys.readouterr().out

    unknown = str(tmp_path / "unknown")
    write_record(unknown, orchestration={}, agents={}, usage_problems=["read failed"])
    ledger.show(unknown)
    unknown_out = capsys.readouterr().out

    confirmed_extra = confirmed_out.splitlines()[1:]
    unknown_extra = unknown_out.splitlines()[1:]
    assert confirmed_extra != unknown_extra
    # Neither reads as a literal zero token count -- there is nothing to
    # count, not a count of zero.
    assert "=0" not in confirmed_out
    assert "=0" not in unknown_out
