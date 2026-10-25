"""Readers of stage ids tolerate `retired` ones: a track begun when intake and
discover existed still has their rows, journal events and ledger records, and
every reader must skip or fold them (into design) without an error.

The shipped stages.json lists no retired stage yet, so each test substitutes a
four-stage file that does and points every module's own STAGES_JSON at it.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

import ledger
import pending
import preflight
import ticket
import timing
import timing_report
import timing_sources
import track_state
import usage_report
import viewer

SCRIPTS = os.path.dirname(ledger.__file__)
STAGES = ["design", "build", "verify", "ship"]
RETIRED = ["intake", "discover"]

OLD_ROWS = [("intake", "done", "—", ""), ("discover", "skipped", "—", "not needed"),
            ("design", "", "", ""), ("build", "", "", ""),
            ("verify", "", "", ""), ("ship", "", "", "")]


def stages_json(path, retired=RETIRED):
    body = {"stages": [{"id": s} for s in STAGES]}
    if retired is not None:
        body["retired"] = retired
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")
    return str(path)


@pytest.fixture
def four_stages(tmp_path, monkeypatch):
    path = stages_json(tmp_path / "stages" / "stages.json")
    for module in (ledger, track_state, pending, preflight):
        monkeypatch.setattr(module, "STAGES_JSON", path)
    return path


def make_track(tmp_path, rows=OLD_ROWS):
    root = tmp_path / "track"
    (root / "billing").mkdir(parents=True)
    (root / "current").write_text("billing", encoding="utf-8")
    lines = ["# fixture", "", "branch: feat/fixture", "started: 2026-08-29", "",
             "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (root / "billing" / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root, root / "billing"


def scripts_copy(tmp_path):
    """The scripts next to a four-stage stages.json, for the tests that run a
    script as a subprocess and so cannot be monkeypatched."""
    copy = tmp_path / "plugin" / "scripts"
    shutil.copytree(SCRIPTS, copy, ignore=shutil.ignore_patterns("__pycache__"))
    stages_json(tmp_path / "plugin" / "skills" / "track" / "stages.json")
    return str(copy)


# --- ledger -----------------------------------------------------------------

def test_retired_stage_ids_is_empty_when_the_key_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STAGES_JSON", stages_json(tmp_path / "s.json", None))
    assert ledger.retired_stage_ids() == ()
    assert ledger.folded("intake") == "intake"


def test_the_shipped_stages_json_retires_nothing():
    assert ledger.retired_stage_ids() == ()


def test_retired_stage_ids_raises_when_the_file_cannot_be_read(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STAGES_JSON", str(tmp_path / "missing.json"))
    with pytest.raises(OSError):
        ledger.retired_stage_ids()


def test_retired_stages_fold_into_the_merge_target(four_stages):
    assert ledger.retired_stage_ids() == ("intake", "discover")
    assert ledger.folded("discover") == ledger.MERGED_INTO == "design"
    assert ledger.folded("build") == "build"


# --- track_state / preflight ------------------------------------------------

def test_table_stage_ids_leaves_retired_rows_out(tmp_path, four_stages):
    _, track = make_track(tmp_path)
    assert track_state.table_stage_ids(str(track / "state.md")) == STAGES


def test_retired_rows_names_them_and_is_empty_without_state_md(tmp_path, four_stages):
    _, track = make_track(tmp_path)
    assert preflight.retired_rows(str(track)) == ["intake", "discover"]
    assert preflight.retired_rows(str(tmp_path / "nowhere")) == []


def test_retired_rows_is_empty_for_a_four_row_table(tmp_path, four_stages):
    _, track = make_track(tmp_path, OLD_ROWS[2:])
    assert preflight.retired_rows(str(track)) == []


def test_status_of_an_old_six_row_track_exits_0_silently(tmp_path):
    root, _ = make_track(tmp_path)
    done = subprocess.run([sys.executable, os.path.join(scripts_copy(tmp_path), "track_state.py"),
                           "status", "--track-root", str(root)],
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    assert "next: design" in done.stdout
    assert done.stderr == ""
    assert "intake" not in done.stdout


def test_status_still_exits_2_on_a_row_that_is_not_a_stage(tmp_path):
    rows = list(OLD_ROWS)
    rows[2] = ("desgin", "", "", "")
    root, _ = make_track(tmp_path, rows)
    done = subprocess.run([sys.executable, os.path.join(scripts_copy(tmp_path), "track_state.py"),
                           "status", "--track-root", str(root)],
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 2
    assert "unexpected desgin; missing design" in done.stderr


# --- pending ----------------------------------------------------------------

REPORT = ("## Pending questions\n1. Which?\n   Background: b\n"
          "   Options: (a) x; (b) y\n   Blocks: nothing\n")


def write_intake_pending(track):
    questions = [{"text": t, "answer": None} for t in pending.extract_questions(REPORT)]
    (track / pending.FILE_NAME).write_text(
        pending.render("intake", 1, questions, REPORT), encoding="utf-8")


def test_a_retired_stage_is_finished(tmp_path, four_stages):
    _, track = make_track(tmp_path, [("intake", "in-progress", "", "")] + OLD_ROWS[1:])
    assert pending._finished(str(track), "intake") is True
    assert pending._finished(str(track), "design") is False


def test_start_is_not_refused_by_a_retired_stages_pending_md(tmp_path, four_stages):
    _, track = make_track(tmp_path, [("intake", "in-progress", "", "")] + OLD_ROWS[1:])
    write_intake_pending(track)
    report = tmp_path / "report.md"
    report.write_text(REPORT, encoding="utf-8")

    pending.start(str(track), "design", 1, str(report))

    assert pending.load(str(track / pending.FILE_NAME))["stage"] == "design"


def test_status_prints_a_retired_stages_pending_md_as_ignored(tmp_path, four_stages):
    _, track = make_track(tmp_path, [("intake", "in-progress", "", "")] + OLD_ROWS[1:])
    write_intake_pending(track)
    lines = track_state.pending_lines(str(track))
    assert len(lines) == 1 and lines[0].endswith("ignored")
    assert "retired" in lines[0]


# --- timing -----------------------------------------------------------------

def event(kind, ident, stage="intake", **fields):
    return dict(format=1, event_id=ident, run_id="run", stage=stage,
                platform="codex", kind=kind, **fields)


def journal(stage):
    rows = [event("run_begin", "run", stage),
            event("actor_bind", "actor", stage, actor_id="main", session_id="s",
                  source_id="synthetic:v1", source_run_id="r", parent_actor_id=None),
            event("run_end", "end", stage),
            event("source_coverage", "cov", stage, source_id="synthetic:v1",
                  capture_id="c", start_token="a", end_token="b", actor_ids=["main"],
                  coverage_scope=sorted(timing.COVERAGE_SCOPE))]
    rows += [event(kind, "w" + kind, stage, actor_id="main", source_id="synthetic:v1",
                   activity_id="w", at_ms=ms)
             for kind, ms in (("work_begin", 0), ("work_end", 30000))]
    return rows


def test_a_retired_stages_event_is_not_malformed_and_reports_under_design(
        tmp_path, four_stages, monkeypatch):
    monkeypatch.setattr(timing_sources, "source_admitted",
                        lambda source, platform: source == "synthetic:v1")
    track = tmp_path / "t"
    track.mkdir()
    (track / timing.TIMING_NAME).write_text(
        "".join(json.dumps(row) + "\n" for row in journal("intake")), encoding="utf-8")

    events, problems = timing.read_events(str(track))
    assert problems == []
    assert len(events) == len(journal("intake"))

    report = timing_report.timing_report(str(track))
    assert list(report) == STAGES
    assert report["design"] == {"elapsed_ms": 30000, "timing_status": "complete",
                                "timing_reasons": []}
    assert report["build"]["timing_status"] == "no-data"


def test_an_unknown_stage_event_is_still_malformed(tmp_path, four_stages):
    with pytest.raises(ValueError, match="journal-malformed"):
        timing._validate(event("run_begin", "run", "bogus"))


# --- ticket -----------------------------------------------------------------

def test_comment_for_a_six_row_state_renders_the_four_stage_rows(tmp_path, four_stages):
    _, track = make_track(tmp_path)
    body = ticket.render_comment(str(track), "billing", "2026-10-25T00:00:00Z")
    rows = [line for line in body.splitlines() if line.startswith("| ")][2:]
    assert [r.split(" | ")[0][2:] for r in rows] == STAGES


def test_comment_names_the_expected_row_count_when_it_is_wrong(tmp_path, four_stages, capsys):
    _, track = make_track(tmp_path, OLD_ROWS[:4])
    assert ticket.render_comment(str(track), "billing", "2026-10-25T00:00:00Z") is None
    assert "state.md has 2 stage row(s), not 4" in capsys.readouterr().out


# --- usage_report -----------------------------------------------------------

def write_ledger(track, rows):
    track.mkdir(parents=True, exist_ok=True)
    (track / "ledger.jsonl").write_text(
        "".join(json.dumps(dict(outcome="passed", gate="auto", sha256=None, ts=ts,
                                stage=stage)) + "\n" for stage, ts in rows),
        encoding="utf-8")


def line_of(report, prefix):
    return [ln for ln in report.splitlines() if ln.startswith(prefix)][0]


def test_usage_counts_a_retired_stages_record_under_design(tmp_path, four_stages):
    track = tmp_path / "t"
    write_ledger(track, [("intake", "2026-09-01T00:00:00Z"), ("design", "2026-09-01T01:00:00Z"),
                         ("ship", "2026-09-01T03:00:00Z")])
    report = usage_report.track_report(str(track), {})
    assert not any(ln.startswith("intake") for ln in report.splitlines())
    assert "attempts=2" in line_of(report, "design")
    metrics = usage_report.metrics_report(str(track))
    assert "rework=2" in line_of(metrics, "design")


def test_the_track_cycle_starts_at_the_first_record(tmp_path, four_stages):
    old = tmp_path / "old"
    write_ledger(old, [("intake", "2026-09-01T00:00:00Z"), ("design", "2026-09-01T01:00:00Z"),
                       ("ship", "2026-09-01T03:00:00Z")])
    new = tmp_path / "new"
    write_ledger(new, [("design", "2026-09-01T01:00:00Z"), ("ship", "2026-09-01T03:00:00Z")])
    assert "track cycle: 3:00:00" in usage_report.metrics_report(str(old))
    assert "track cycle: 2:00:00" in usage_report.metrics_report(str(new))


# --- viewer -----------------------------------------------------------------

def test_the_page_stage_list_comes_from_stages_json(four_stages):
    assert "const STAGES = %s;" % json.dumps(ledger.stage_ids()) in viewer.with_stages(
        "const STAGES = __STAGES__;")
    assert "__STAGES__" not in viewer.PAGE_HTML


def test_the_served_page_lists_the_shipped_stages():
    assert "const STAGES = %s;" % json.dumps(track_state.stage_ids()) in viewer.PAGE_HTML
