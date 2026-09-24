"""usage_report.py's `metrics` subcommand -- issue #85's four numbers per
stage (first_pass, cycle, rework, human_signed) -- and the CLI that wraps
it. Follows tests/test_report.py's style: `ledger.usage_collector.collect`
is monkeypatched so `ledger.append()` never touches a real transcript, and
`ledger._now()` is monkeypatched to a fixed timestamp so cycle times are
deterministic (ledger.py:108-109).
"""
import os
import subprocess
import sys

import ledger
import usage_report


def _append(track, stage, outcome, monkeypatch, ts, artifact=None, gate="auto",
           session_id="sess-fixed"):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", session_id)
    monkeypatch.setattr(ledger.usage_collector, "collect",
                        lambda *a, **k: ({}, {}, []))
    monkeypatch.setattr(ledger, "_now", lambda: ts)
    return ledger.append(track, stage, outcome, artifact=artifact, gate=gate)


def _line(report, stage):
    return [l for l in report.splitlines() if l.startswith(stage)][0]


# --- (a) fixed sample: every case in one ledger -----------------------------

def test_fixed_sample_all_four_numbers(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    artifact = tmp_path / "design.md"
    artifact.write_text("design doc", encoding="utf-8")

    # intake: blocked (preflight refusal, counts as a first-try failure)
    # then passed -- two attempts, first_pass 0.
    _append(track, "intake", "blocked", monkeypatch, "2026-09-01T00:00:00Z")
    _append(track, "intake", "passed", monkeypatch, "2026-09-01T00:05:00Z")

    # discover: skipped -- never an attempt.
    _append(track, "discover", "skipped", monkeypatch, "2026-09-01T00:06:00Z")

    # design: auto-passed then human-signed, same artifact/sha -- one attempt.
    _append(track, "design", "passed", monkeypatch, "2026-09-01T01:00:00Z",
           artifact=str(artifact), gate="auto")
    _append(track, "design", "passed", monkeypatch, "2026-09-01T01:00:05Z",
           artifact=str(artifact), gate="human")

    # build: unavailable -- a provider refusal, never an attempt.
    _append(track, "build", "unavailable", monkeypatch, "2026-09-01T02:00:00Z")

    with open(os.path.join(track, "ledger.jsonl"), "a", encoding="utf-8") as fh:
        fh.write("{not json\n")

    report = usage_report.metrics_report(track)

    intake_line = _line(report, "intake")
    assert "first_pass=0" in intake_line
    assert "rework=2" in intake_line
    assert "cycle=0:05:00" in intake_line
    assert "human_signed=0/2" in intake_line

    design_line = _line(report, "design")
    assert "first_pass=1" in design_line
    assert "rework=1" in design_line
    assert "human_signed=1/1" in design_line
    assert "cycle=0:00:05" in design_line

    discover_line = _line(report, "discover")
    assert "first_pass=%s" % usage_report.NO_DATA in discover_line
    assert "rework=%s" % usage_report.NO_DATA in discover_line

    build_line = _line(report, "build")
    assert "first_pass=%s" % usage_report.NO_DATA in build_line
    # A no-attempt stage carries no number at all -- every column, not just
    # the two a typo in the NO_DATA print would leave intact (verify, 2026-09-13).
    for line in (discover_line, build_line):
        assert "cycle=%s" % usage_report.NO_DATA in line
        assert "human_signed=%s" % usage_report.NO_DATA in line

    # TOTAL: only intake (2 attempts, first_pass 0, 0 human) and design
    # (1 attempt, first_pass 1, 1 human) had attempts -- discover (skipped)
    # and build (unavailable only) stay out of every denominator (issue #85:
    # 沒有 attempt 的 stage 不入分母).
    total_line = _line(report, "TOTAL")
    assert "first_pass=1/2" in total_line
    assert "rework=3" in total_line
    assert "human_signed=1/3" in total_line

    assert "1 malformed line(s) skipped." in report
    assert "gate not walked" not in report


def test_two_passes_without_artifact_are_two_attempts(tmp_path, monkeypatch):
    # verify normally records no artifact, so both rows carry sha256 null.
    # Two independent passes (the stage was sent back and re-run) are two
    # attempts: "same sha" means a shared fingerprint, and null is not one
    # (correctness lens, 2026-09-13).
    track = str(tmp_path / "track")
    os.makedirs(track)
    _append(track, "verify", "passed", monkeypatch, "2026-09-01T00:00:00Z")
    _append(track, "verify", "passed", monkeypatch, "2026-09-01T00:10:00Z")

    report = usage_report.metrics_report(track)

    verify_line = _line(report, "verify")
    assert "rework=2" in verify_line
    assert "human_signed=0/2" in verify_line


# --- (b) empty and single-record ledgers ------------------------------------

def test_empty_ledger_prints_no_data_for_every_stage(tmp_path):
    track = str(tmp_path / "track")
    os.makedirs(track)

    report = usage_report.metrics_report(track)

    for stage in ledger.stage_ids():
        assert "first_pass=%s" % usage_report.NO_DATA in _line(report, stage)
    assert "track cycle: %s" % usage_report.NO_DATA in report


def test_single_record_ledger(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    _append(track, "intake", "passed", monkeypatch, "2026-09-01T00:00:00Z")

    report = usage_report.metrics_report(track)

    intake_line = _line(report, "intake")
    assert "first_pass=1" in intake_line
    assert "rework=1" in intake_line
    assert "cycle=0:00:00" in intake_line
    assert "human_signed=0/1" in intake_line


# --- (c) a passed stage with no human gate anywhere is called out ----------

def test_design_passed_without_human_gate_prints_footnote(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    _append(track, "design", "passed", monkeypatch, "2026-09-01T00:00:00Z")

    report = usage_report.metrics_report(track)

    assert "gate not walked: design" in report


def test_ship_passed_with_human_gate_has_no_footnote(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    _append(track, "ship", "passed", monkeypatch, "2026-09-01T00:00:00Z", gate="human")

    report = usage_report.metrics_report(track)

    assert "gate not walked" not in report


def test_design_whose_approve_is_for_another_document_prints_footnote(tmp_path, monkeypatch):
    """Issue #128, the #112 ledger: the stance approved, then the finished
    design passed as auto. preflight.py refuses build on it, so the report
    must not count the gate as walked just because a human row exists."""
    track = str(tmp_path / "track")
    os.makedirs(track)
    stance = tmp_path / "d-stance.md"
    stance.write_text("stance", encoding="utf-8")
    detail = tmp_path / "d-detail.md"
    detail.write_text("detail", encoding="utf-8")
    _append(track, "design", "passed", monkeypatch, "2026-09-01T00:00:00Z",
            artifact=str(stance), gate="human")
    _append(track, "design", "passed", monkeypatch, "2026-09-01T00:10:00Z",
            artifact=str(detail), gate="auto")

    report = usage_report.metrics_report(track)

    assert "gate not walked: design" in report


def test_design_approved_before_its_own_pass_has_no_footnote(tmp_path, monkeypatch):
    """Issue #128. Gate 1 handed up as a pending question lands before the
    stage's own pass, on the same document -- walked, the same answer
    preflight.py gives, even though the last row is auto."""
    track = str(tmp_path / "track")
    os.makedirs(track)
    doc = tmp_path / "d-detail.md"
    doc.write_text("detail", encoding="utf-8")
    _append(track, "design", "passed", monkeypatch, "2026-09-01T00:00:00Z",
            artifact=str(doc), gate="human")
    _append(track, "design", "passed", monkeypatch, "2026-09-01T00:10:00Z",
            artifact=str(doc), gate="auto")

    report = usage_report.metrics_report(track)

    assert "gate not walked" not in report


def test_design_approve_without_an_artifact_prints_footnote(tmp_path, monkeypatch):
    """Issue #128. An Approve appended without --artifact carries no sha, so
    it ties to no document; preflight.py refuses build on it, and the report
    says the gate was not walked."""
    track = str(tmp_path / "track")
    os.makedirs(track)
    doc = tmp_path / "d-detail.md"
    doc.write_text("detail", encoding="utf-8")
    _append(track, "design", "passed", monkeypatch, "2026-09-01T00:00:00Z",
            artifact=str(doc), gate="auto")
    _append(track, "design", "passed", monkeypatch, "2026-09-01T00:10:00Z", gate="human")

    report = usage_report.metrics_report(track)

    assert "gate not walked: design" in report


# --- (d) central aggregation over two tracks --------------------------------

def test_central_metrics_aggregates_across_tracks(tmp_path, monkeypatch):
    central_path = tmp_path / "central" / "usage.jsonl"
    monkeypatch.setenv("CAI_USAGE_LEDGER", str(central_path))
    # Pre-write the import-day marker (D10) to a date before the fixed
    # 2026-09-01 timestamps below -- otherwise ledger.append()'s own
    # _mark_data_start() would stamp it with the real host clock's today,
    # which would postdate our fixed-past records and exclude them from
    # the --days window.
    os.makedirs(central_path.parent, exist_ok=True)
    (central_path.parent / "usage-start.txt").write_text("2026-01-01\n", encoding="utf-8")

    track_a = str(tmp_path / "proj-a" / "track")
    track_b = str(tmp_path / "proj-b" / "track")
    os.makedirs(track_a)
    os.makedirs(track_b)

    # track a: build passes first try -- one attempt, cycle 0.
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path / "proj-a"))
    _append(track_a, "build", "passed", monkeypatch, "2026-09-01T00:00:00Z",
           session_id="sess-a")

    # track b: build fails once then passes -- two attempts, cycle 10s.
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path / "proj-b"))
    _append(track_b, "build", "failed", monkeypatch, "2026-09-01T00:00:00Z",
           session_id="sess-b")
    _append(track_b, "build", "passed", monkeypatch, "2026-09-01T00:00:10Z",
           session_id="sess-b")

    report = usage_report.central_metrics_report(str(central_path), 30)

    build_line = _line(report, "build")
    # first_pass: one of two tracks passed first try.
    assert "first_pass=1/2" in build_line
    # rework: (1 + 2) / 2 tracks == 1.5.
    assert "rework=1.50" in build_line
    # human_signed: neither track used a human gate -- 0 of (1 + 2) attempts.
    assert "human_signed=0/3" in build_line
    # cycle: (0 + 10) / 2 tracks == 5s.
    assert "cycle=0:00:05" in build_line


def test_central_metrics_no_central_ledger_exits_with_no_data_message(tmp_path):
    central_path = tmp_path / "central" / "usage.jsonl"

    report = usage_report.central_metrics_report(str(central_path), 30)

    assert "No cross-project data yet" in report


# --- CLI: metrics exits 0 for both forms ------------------------------------

SCRIPTS = os.path.dirname(usage_report.__file__)


def test_cli_metrics_track_dir_exits_zero(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-cli")
    monkeypatch.setattr(ledger.usage_collector, "collect", lambda *a, **k: ({}, {}, []))
    ledger.append(track, "intake", "passed")

    done = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "usage_report.py"),
         "metrics", "--track-dir", track],
        capture_output=True)

    assert done.returncode == 0, done.stderr
    text = done.stdout.decode("utf-8")
    assert "intake" in text
    assert "first_pass=1" in text


def test_cli_metrics_days_exits_zero_with_no_central_ledger(tmp_path, monkeypatch):
    env = dict(os.environ)
    env["CAI_USAGE_LEDGER"] = str(tmp_path / "central" / "usage.jsonl")
    done = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "usage_report.py"),
         "metrics", "--days", "7"],
        capture_output=True, env=env)

    assert done.returncode == 0, done.stderr
    text = done.stdout.decode("utf-8")
    assert "no" in text.lower()
