"""ledger.py: the append-only attempt record behind UC1, UC3, UC5 and UC6.

The design is docs/design/2026-08-28-track-ledger-detail.md; each test names
the requirement it stands for so a failure says what broke, not just where.
"""
import hashlib
import json
import os
import subprocess
import sys

import ledger

LEDGER_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "plugins", "cai", "scripts", "ledger.py")


def run(*args):
    return subprocess.run([sys.executable, LEDGER_PY] + list(args),
                          capture_output=True, text=True, encoding="utf-8")


def read_lines(track_dir):
    with open(os.path.join(str(track_dir), "ledger.jsonl"), encoding="utf-8") as fh:
        return [line for line in fh.read().splitlines() if line]


def corrupt(track_dir, text):
    """Append text that is not JSON -- an interrupted write, as R5 describes."""
    with open(os.path.join(str(track_dir), "ledger.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(text + "\n")


# --- R4: an absent ledger is zero records, never an error ------------------

def test_absent_ledger_reads_as_zero(tmp_path):
    missing = str(tmp_path / "no-such-track")
    assert ledger.attempts(missing, "build") == 0
    assert ledger.records(missing) == []
    assert ledger.streak(missing, "build") == []
    assert ledger.last_passed(missing, "build") is None
    assert ledger.fingerprint(missing, "build") is None


# --- UC1: how many times has this stage been tried -------------------------

def test_three_failures_read_back_as_three(tmp_path):
    track = str(tmp_path)
    for n in range(3):
        ledger.append(track, "build", "failed", note="attempt %d" % n)

    assert ledger.attempts(track, "build") == 3
    assert [r["attempt"] for r in ledger.streak(track, "build")] == [1, 2, 3]
    # Another stage's count is untouched -- the streak is per stage.
    assert ledger.attempts(track, "verify") == 0


# --- UC3: why did it fail last time ---------------------------------------

def test_both_reasons_survive_a_later_pass(tmp_path):
    track = str(tmp_path)
    ledger.append(track, "build", "failed", note="unit 3 broke the row count")
    ledger.append(track, "build", "passed", note="row count restored")

    notes = [r["note"] for r in ledger.records(track, "build")]
    assert notes == ["unit 3 broke the row count", "row count restored"]


# --- B3: records / streak / last_passed are three different slices ---------

def test_the_three_readers_draw_different_boundaries(tmp_path):
    track = str(tmp_path)
    ledger.append(track, "design", "passed", gate="human", note="signed off")
    ledger.append(track, "design", "failed", note="reopened, still wrong")
    ledger.append(track, "design", "failed", note="still wrong")

    assert len(ledger.records(track, "design")) == 3
    run_since_pass = ledger.streak(track, "design")
    assert len(run_since_pass) == 2
    assert all(r["outcome"] == "failed" for r in run_since_pass)
    # The record that answers "who let it through" is the one the streak omits.
    assert ledger.last_passed(track, "design")["gate"] == "human"


def test_skipped_also_resets_the_streak(tmp_path):
    # D12: without this, five failures would lock the stage out for good --
    # it could never run again, so it could never produce a `passed`.
    track = str(tmp_path)
    for _ in range(5):
        ledger.append(track, "verify", "failed", note="flaky")
    assert ledger.attempts(track, "verify") == 5

    ledger.append(track, "verify", "skipped", artifact="—", note="reviewed by hand")
    assert ledger.attempts(track, "verify") == 0
    # ...but a skip is not a pass: there is still no one who let it through.
    assert ledger.last_passed(track, "verify") is None


# --- UC9: a provider that refused to serve did not produce an attempt ------

def test_provider_refusals_do_not_burn_the_retry_budget(tmp_path):
    track = str(tmp_path)
    for n in range(3):
        ledger.append(track, "build", "failed", note="unit %d still red" % n)
    for _ in range(5):
        ledger.append(track, "build", "unavailable",
                      note="429 rate_limit_error from the provider")

    # Eight records, three of which are this stage's fault.
    assert len(ledger.streak(track, "build")) == 8
    assert ledger.attempts(track, "build") == 3


def test_a_refusal_is_still_a_record_a_person_can_see(tmp_path):
    # Not counting it must not mean hiding it: five rate limits in a row is
    # something the person reading `show` needs to know happened.
    track = str(tmp_path)
    ledger.append(track, "verify", "unavailable", note="529 overloaded_error")

    done = run("show", "--track-dir", track)
    assert "unavailable" in done.stdout
    assert "529 overloaded_error" in done.stdout


def test_the_retry_count_is_defined_in_exactly_one_place(tmp_path):
    # attempts() must read COUNTS_AS_RETRY rather than repeat the list, or the
    # next outcome value added will be counted by accident.
    assert "unavailable" not in ledger.COUNTS_AS_RETRY
    assert set(ledger.COUNTS_AS_RETRY) <= set(ledger.OUTCOMES)


# --- UC5: the fingerprint is of the bytes on disk, unnormalised ------------

def test_fingerprint_is_the_sha256_of_the_artifact(tmp_path):
    track = str(tmp_path)
    doc = tmp_path / "spec-detail.md"
    doc.write_bytes(b"# spec\r\n\ttrailing space \n")

    ledger.append(track, "design", "passed", artifact=str(doc), gate="human")
    assert ledger.fingerprint(track, "design") == hashlib.sha256(
        doc.read_bytes()).hexdigest()

    doc.write_bytes(b"# spec\r\n\ttrailing space \n!")
    assert ledger.fingerprint(track, "design") != hashlib.sha256(
        doc.read_bytes()).hexdigest()


# --- R5: a broken line neither raises nor pollutes any stage's count -------

def test_a_malformed_line_is_visible_but_counts_for_nobody(tmp_path):
    track = str(tmp_path)
    ledger.append(track, "build", "failed", note="one real attempt")
    corrupt(track, '{"ts":"2026-08-29T00:00:00Z","stage":"bui')

    for stage in ledger.stage_ids():
        expected = 1 if stage == "build" else 0
        assert ledger.attempts(track, stage) == expected

    broken = [r for r in ledger.records(track) if r.get("malformed")]
    assert len(broken) == 1
    assert broken[0]["line"] == 2
    assert set(broken[0]) == {"malformed", "line", "raw"}
    assert ledger.malformed_lines(track) == [2]


def test_a_wholly_corrupt_ledger_still_answers(tmp_path):
    track = str(tmp_path)
    with open(os.path.join(track, "ledger.jsonl"), "wb") as fh:
        fh.write(b"\x00\x01\x02 not json at all\nnor this\n")

    assert ledger.attempts(track, "build") == 0
    assert len(ledger.malformed_lines(track)) == 2


# --- skip: `—` is "produced nothing", not a path that failed to resolve ----

def test_the_skip_sentinel_is_recorded_without_a_fingerprint(tmp_path):
    done = run("append", "--track-dir", str(tmp_path), "--stage", "design",
               "--outcome", "skipped", "--artifact", "—",
               "--note", "reusing the existing spec")
    assert done.returncode == 0, done.stderr
    record = json.loads(read_lines(tmp_path)[0])
    assert record["artifact"] is None
    assert record["sha256"] is None


# --- R3: the model may write the note, and nothing else -------------------

def test_the_cli_refuses_the_mechanical_fields(tmp_path):
    for flag, value in (("--ts", "2026-01-01T00:00:00Z"), ("--sha256", "0" * 64),
                        ("--attempt", "1")):
        done = run("append", "--track-dir", str(tmp_path), "--stage", "build",
                   "--outcome", "failed", flag, value)
        assert done.returncode == 1, "%s should be a usage error" % flag
        assert not os.path.exists(os.path.join(str(tmp_path), "ledger.jsonl"))


def test_an_unknown_outcome_is_refused_and_writes_nothing(tmp_path):
    done = run("append", "--track-dir", str(tmp_path), "--stage", "build",
               "--outcome", "exploded")
    assert done.returncode == 2
    assert "passed" in done.stderr and "failed" in done.stderr
    assert not os.path.exists(os.path.join(str(tmp_path), "ledger.jsonl"))


def test_an_unreadable_artifact_is_refused_and_names_the_path(tmp_path):
    done = run("append", "--track-dir", str(tmp_path), "--stage", "design",
               "--outcome", "passed", "--artifact", "docs/design/not-here.md")
    assert done.returncode == 2
    assert "not-here.md" in done.stderr
    assert not os.path.exists(os.path.join(str(tmp_path), "ledger.jsonl"))


# --- D3: an over-long note is truncated, never a refused record -----------

def test_an_over_long_note_is_truncated_not_rejected(tmp_path):
    track = str(tmp_path)
    record = ledger.append(track, "build", "failed", note="回" * 4000)

    assert record["note"].endswith(ledger.TRUNCATED)
    assert len(read_lines(track)[0].encode("utf-8")) + 1 <= ledger.MAX_RECORD
    # The mechanical fields are never what gets dropped.
    assert record["outcome"] == "failed" and record["stage"] == "build"
    assert ledger.attempts(track, "build") == 1


# --- UC6: a person can read the whole ledger, broken lines included --------

def test_show_prints_every_record_and_names_the_broken_lines(tmp_path):
    track = str(tmp_path)
    ledger.append(track, "build", "failed", note="first try")
    corrupt(track, "half a line")
    ledger.append(track, "verify", "passed", gate="human", note="looks right")

    done = run("show", "--track-dir", track)
    assert done.returncode == 0
    assert "first try" in done.stdout and "looks right" in done.stdout
    assert "malformed" in done.stdout and "half a line" in done.stdout

    narrowed = run("show", "--track-dir", track, "--stage", "build")
    assert "first try" in narrowed.stdout
    assert "looks right" not in narrowed.stdout
    # The broken line belongs to no stage, so hiding it here would make a
    # corrupt ledger look clean to anyone who narrowed the view.
    assert "malformed" in narrowed.stdout


# --- D1: the reason this script writes at all stays next to the code ------

def test_the_module_docstring_keeps_the_write_exception_on_the_record():
    assert "track_state.py:6" in ledger.__doc__
