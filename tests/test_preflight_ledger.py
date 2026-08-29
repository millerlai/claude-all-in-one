"""preflight's three ledger checks: UC2, UC5, UC7, UC8, D12, D14, R1.

`discover` is the stage most of these run against: it needs a state.md with a
filled-in intake row and nothing else, so a failure here is about the ledger
rather than about git or a design document.
"""
import os
import subprocess
import sys

import ledger
import preflight

PREFLIGHT_PY = os.path.join(os.path.dirname(ledger.__file__), "preflight.py")

ROWS = [("intake", "done", "—", ""), ("discover", "", "", ""),
        ("design", "", "", ""), ("build", "", "", ""),
        ("verify", "", "", ""), ("ship", "", "", "")]


def make_track(tmp_path, rows=ROWS):
    track = tmp_path / "track"
    track.mkdir()
    lines = ["# fixture", "", "branch: feat/fixture", "started: 2026-08-29", "",
             "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(track)


def run(stage, track, project=".", **env):
    return subprocess.run(
        [sys.executable, PREFLIGHT_PY, stage, "--track-dir", track,
         "--project-dir", project],
        capture_output=True, text=True, encoding="utf-8",
        env=dict(os.environ, **env))


# --- UC7: the cap blocks at N, not at N-1 ---------------------------------

def test_the_cap_lets_four_through_and_stops_the_fifth(tmp_path):
    track = make_track(tmp_path)
    for n in range(4):
        ledger.append(track, "discover", "failed", note="try %d" % n)

    done = run("discover", track)
    assert done.returncode == 0, done.stdout
    assert "PASS ledger_attempts (4 of 5)" in done.stdout

    ledger.append(track, "discover", "failed", note="the fifth and last")
    done = run("discover", track)
    assert done.returncode == 2
    assert "FAIL ledger_attempts (5 of 5" in done.stdout


def test_the_blocking_message_carries_the_reasons_and_the_ways_out(tmp_path):
    track = make_track(tmp_path)
    for n in range(5):
        ledger.append(track, "discover", "failed", note="unknown %d still open" % n)

    out = run("discover", track).stdout
    for n in range(5):
        assert "unknown %d still open" % n in out
    assert "/cai:track skip discover" in out
    assert "CAI_TRACK_MAX_ATTEMPTS" in out
    assert "ledger.jsonl" in out


# --- D14: the cap is a setting, so it can never be the reason you are stuck -

def test_the_environment_overrides_the_cap(tmp_path):
    track = make_track(tmp_path)
    for n in range(5):
        ledger.append(track, "discover", "failed", note="try %d" % n)

    assert run("discover", track).returncode == 2
    assert run("discover", track, CAI_TRACK_MAX_ATTEMPTS="10").returncode == 0

    unlimited = run("discover", track, CAI_TRACK_MAX_ATTEMPTS="0")
    assert unlimited.returncode == 0
    assert "no cap" in unlimited.stdout


def test_an_unusable_setting_falls_back_to_the_default(tmp_path):
    track = make_track(tmp_path)
    for n in range(5):
        ledger.append(track, "discover", "failed", note="try %d" % n)

    for bad in ("abc", "", "-3", "5.5"):
        done = run("discover", track, CAI_TRACK_MAX_ATTEMPTS=bad)
        assert done.returncode == 2, "%r should behave as unset" % bad
        assert "5 of 5" in done.stdout


# --- UC9: rate limits must not lock out a stage nobody did wrong in --------

def test_provider_refusals_never_reach_the_cap(tmp_path):
    track = make_track(tmp_path)
    for _ in range(8):
        ledger.append(track, "discover", "unavailable",
                      note="429 rate_limit_error from the provider")

    done = run("discover", track)
    assert done.returncode == 0, done.stdout
    assert "PASS ledger_attempts (0 of 5)" in done.stdout


def test_refusals_and_real_failures_are_counted_apart(tmp_path):
    track = make_track(tmp_path)
    for n in range(3):
        ledger.append(track, "discover", "failed", note="unknown %d open" % n)
    for _ in range(5):
        ledger.append(track, "discover", "unavailable", note="529 overloaded_error")

    done = run("discover", track)
    assert done.returncode == 0
    assert "PASS ledger_attempts (3 of 5)" in done.stdout


def test_the_blocking_message_shows_the_refusals_it_did_not_count(tmp_path):
    # Not counted is not the same as not shown. Someone at the cap needs to see
    # that five of the eight lines were the provider, not their code.
    track = make_track(tmp_path)
    for n in range(5):
        ledger.append(track, "discover", "failed", note="unknown %d open" % n)
    ledger.append(track, "discover", "unavailable", note="429 rate_limit_error")

    out = run("discover", track).stdout
    assert "FAIL ledger_attempts (5 of 5" in out
    assert "unavailable -- 429 rate_limit_error" in out


# --- D12: a skip clears the cap, so the stage is never locked out for good --

def test_a_skip_reopens_a_capped_stage(tmp_path):
    track = make_track(tmp_path)
    for n in range(5):
        ledger.append(track, "discover", "failed", note="try %d" % n)
    assert run("discover", track).returncode == 2

    ledger.append(track, "discover", "skipped", artifact="—", note="doing it by hand")
    done = run("discover", track)
    assert done.returncode == 0
    assert "PASS ledger_attempts (0 of 5)" in done.stdout


# --- UC8: a corrupt ledger is loud on every stage and blocks none of them ---

def test_broken_lines_are_reported_by_every_stage_and_block_nothing(tmp_path):
    track = make_track(tmp_path)
    ledger.append(track, "discover", "failed", note="one real attempt")
    with open(os.path.join(track, "ledger.jsonl"), "a", encoding="utf-8") as fh:
        fh.write('{"stage":"disc\n')

    for stage in ledger.stage_ids():
        out = run(stage, track).stdout
        assert "PASS ledger_intact (1 malformed line(s) at 2)" in out, stage

    # discover has nothing else wrong with it, so a broken ledger alone must
    # not be what stops it -- that is R5, and UC8 is the visibility half.
    assert run("discover", track).returncode == 0


def test_a_clean_ledger_still_says_so(tmp_path):
    track = make_track(tmp_path)
    assert "PASS ledger_intact (0 malformed)" in run("discover", track).stdout


# --- R1/R4: a track with no ledger behaves exactly as it did before ---------

def test_a_track_without_a_ledger_is_not_blocked(tmp_path):
    track = make_track(tmp_path)
    done = run("discover", track)
    assert done.returncode == 0
    assert "PASS ledger_attempts (0 of 5)" in done.stdout
    assert "PASS ledger_intact (0 malformed)" in done.stdout


# --- UC5: build reads the document that was signed off, or it does not run --

def test_a_design_changed_after_sign_off_stops_build(tmp_path):
    project = tmp_path / "project"
    (project / "docs" / "design").mkdir(parents=True)
    doc = project / "docs" / "design" / "thing-detail.md"
    doc.write_text("# thing\n\n## Work breakdown\n\n| Unit |\n", encoding="utf-8")

    rows = list(ROWS)
    rows[2] = ("design", "done", "docs/design/thing-detail.md", "")
    track = make_track(tmp_path, rows)
    ledger.append(track, "design", "passed", artifact=str(doc), gate="human",
                  note="signed off")

    ok = run("build", track, str(project))
    assert "PASS artifact_unchanged" in ok.stdout, ok.stdout

    doc.write_text("# thing\n\n## Work breakdown\n\n| Unit |\n ", encoding="utf-8")
    changed = run("build", track, str(project))
    assert changed.returncode == 2
    assert "FAIL artifact_unchanged" in changed.stdout
    assert "changed since sign-off" in changed.stdout


def test_build_without_a_recorded_sign_off_is_not_second_guessed(tmp_path):
    # R4 again: no ledger means no fingerprint to compare, which is a track
    # that predates this feature -- not a track whose design was tampered with.
    project = tmp_path / "project"
    (project / "docs" / "design").mkdir(parents=True)
    doc = project / "docs" / "design" / "thing-detail.md"
    doc.write_text("# thing\n\n## Work breakdown\n\n| Unit |\n", encoding="utf-8")

    rows = list(ROWS)
    rows[2] = ("design", "done", "docs/design/thing-detail.md", "")
    track = make_track(tmp_path, rows)

    done = run("build", track, str(project))
    assert done.returncode == 0
    assert "PASS artifact_unchanged (no signed-off design recorded)" in done.stdout


def test_the_fingerprint_is_taken_from_the_ledger_not_state_md(tmp_path):
    # state.md's artifact cell can be overwritten by a later stage; the record
    # of what passed cannot. Point the cell at a different file and the check
    # must still be about the document that was actually signed off.
    project = tmp_path / "project"
    (project / "docs" / "design").mkdir(parents=True)
    signed = project / "docs" / "design" / "signed-detail.md"
    signed.write_text("# signed\n\n## Work breakdown\n\n| Unit |\n", encoding="utf-8")
    other = project / "docs" / "design" / "other-detail.md"
    other.write_text("# other\n\n## Work breakdown\n\n| Unit |\n", encoding="utf-8")

    rows = list(ROWS)
    rows[2] = ("design", "done", "docs/design/other-detail.md", "")
    track = make_track(tmp_path, rows)
    ledger.append(track, "design", "passed", artifact=str(signed), gate="human")

    signed.write_text("# signed, edited\n", encoding="utf-8")
    done = run("build", track, str(project))
    assert done.returncode == 2
    assert "signed-detail.md" in done.stdout


# --- the helpers themselves, called directly --------------------------------

def test_max_attempts_reads_the_environment(monkeypatch):
    monkeypatch.delenv(preflight.MAX_ATTEMPTS_ENV, raising=False)
    assert preflight.max_attempts() == preflight.DEFAULT_MAX_ATTEMPTS
    monkeypatch.setenv(preflight.MAX_ATTEMPTS_ENV, "12")
    assert preflight.max_attempts() == 12
    monkeypatch.setenv(preflight.MAX_ATTEMPTS_ENV, "0")
    assert preflight.max_attempts() == 0
    monkeypatch.setenv(preflight.MAX_ATTEMPTS_ENV, "not a number")
    assert preflight.max_attempts() == preflight.DEFAULT_MAX_ATTEMPTS
