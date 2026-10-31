"""U2 of the plan-stage design: intake and discover are merged into `design`.

The shipped stages.json lists four stages and retires the other two. A track
begun before that still has rows, journal events and a pending.md for the
retired stages; every reader must take them with the real stages.json (the
sibling test_retired_stages.py patches a stand-in file instead).
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import ledger
import pending
import preflight
import ticket
import timing
import timing_report
import timing_sources
import track_state
from test_retired_stages import (OLD_ROWS, REPORT, journal, make_track,
                                 write_intake_pending)

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "cai"
PREFLIGHT_PY = os.path.join(os.path.dirname(ledger.__file__), "preflight.py")
STAGES = ["design", "build", "verify", "ship"]
VALID_INTAKE = ("# Intake\n\nAC1: it works.\n\n## Verification levels\n\n"
                "| AC | level | check |\n|---|---|---|\n| AC1 | manual | look |\n")


# --- R3: the stage list ------------------------------------------------------

def test_stages_json_has_four_stages_and_retires_intake_and_discover():
    data = json.loads((PLUGIN / "skills" / "track" / "stages.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in data["stages"]] == STAGES
    assert data["retired"] == ["intake", "discover"]
    design = data["stages"][0]
    assert (design["agent"], design["reference"], design["auto_invoke"]) == \
        (None, "references/stage-design.md", False)


# --- UC3 with the real stages.json ------------------------------------------

def test_an_old_intake_pending_md_does_not_block_design_start(tmp_path):
    _, track = make_track(tmp_path, [("intake", "in-progress", "", "")] + OLD_ROWS[1:])
    write_intake_pending(track)
    report = tmp_path / "report.md"
    report.write_text(REPORT, encoding="utf-8")

    pending.start(str(track), "design", 1, str(report))

    assert pending.load(str(track / pending.FILE_NAME))["stage"] == "design"


def test_old_intake_timing_events_are_not_malformed(tmp_path, monkeypatch):
    monkeypatch.setattr(timing_sources, "source_admitted",
                        lambda source, platform: source == "synthetic:v1")
    track = tmp_path / "t"
    track.mkdir()
    (track / timing.TIMING_NAME).write_text(
        "".join(json.dumps(row) + "\n" for row in journal("intake")), encoding="utf-8")

    events, problems = timing.read_events(str(track))
    assert problems == []
    assert list(timing_report.timing_report(str(track))) == STAGES


def test_a_four_row_state_md_produces_the_ticket_comment(tmp_path):
    _, track = make_track(tmp_path, OLD_ROWS[2:])
    body = ticket.render_comment(str(track), "billing", "2026-10-25T00:00:00Z")
    rows = [line for line in body.splitlines() if line.startswith("| ")][2:]
    assert [r.split(" | ")[0][2:] for r in rows] == STAGES


def test_a_six_row_state_md_still_reads_as_four_stages(tmp_path):
    _, track = make_track(tmp_path)
    assert track_state.table_stage_ids(str(track / "state.md")) == STAGES
    assert preflight.retired_rows(str(track)) == ["intake", "discover"]


# --- preflight ---------------------------------------------------------------

def run_preflight(stage, track, project):
    return subprocess.run(
        [sys.executable, PREFLIGHT_PY, stage, "--track-dir", str(track),
         "--project-dir", str(project)],
        capture_output=True, text=True, encoding="utf-8")


def state(tmp_path, rows, name="feature-x"):
    track = tmp_path / name
    track.mkdir(exist_ok=True)
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return track


FOUR = [("design", "", "", ""), ("build", "", "", ""),
        ("verify", "", "", ""), ("ship", "", "", "")]


def test_intake_and_discover_are_no_longer_preflight_stages():
    assert sorted(preflight.STAGES) == ["build", "design", "ship", "verify"]


def test_design_needs_no_intake_md_and_runs_the_start_checks_first(tmp_path):
    done = run_preflight("design", state(tmp_path, FOUR), tmp_path)
    labels = [l.split(" (")[0] for l in done.stdout.splitlines() if l[:5] in ("PASS ", "FAIL ")]
    assert "intake_document" not in " ".join(labels)
    # The three checks the intake stage used to run, then _design's.
    assert [l[5:] for l in labels[:4]] == ["not_main_branch", "reserved_name",
                                           "track_ignored", "artifact_named"]
    assert "PASS reserved_name" in done.stdout


def test_design_on_a_reserved_name_still_blocks(tmp_path):
    done = run_preflight("design", state(tmp_path, FOUR, "current"), tmp_path)
    assert "FAIL reserved_name" in done.stdout and done.returncode == 2


def test_build_with_design_done_and_no_intake_md_fails_intake_document(tmp_path):
    rows = [("design", "done", "—", "")] + FOUR[1:]
    done = run_preflight("build", state(tmp_path, rows), tmp_path)
    assert "FAIL intake_document" in done.stdout
    assert done.returncode == 2


def test_build_with_design_done_and_a_readable_intake_md_passes_it(tmp_path):
    rows = [("design", "done", "—", "")] + FOUR[1:]
    track = state(tmp_path, rows)
    (track / "intake.md").write_text(VALID_INTAKE, encoding="utf-8")
    done = run_preflight("build", track, tmp_path)
    assert "PASS intake_document" in done.stdout


def test_build_with_an_invalid_levels_table_fails_intake_document(tmp_path):
    rows = [("design", "done", "—", "")] + FOUR[1:]
    track = state(tmp_path, rows)
    (track / "intake.md").write_text(VALID_INTAKE.replace("manual", "bogus"), encoding="utf-8")
    assert "FAIL intake_document" in run_preflight("build", track, tmp_path).stdout


def test_build_before_design_is_done_owes_no_intake_md(tmp_path):
    done = run_preflight("build", state(tmp_path, FOUR), tmp_path)
    assert "intake_document" not in done.stdout


def test_an_old_track_that_skipped_intake_owes_no_intake_md(tmp_path):
    rows = [("intake", "skipped", "—", "x"), ("discover", "skipped", "—", "x"),
            ("design", "done", "—", "")] + FOUR[1:]
    done = run_preflight("build", state(tmp_path, rows), tmp_path)
    assert "FAIL intake_document" not in done.stdout


def test_an_old_track_with_a_done_intake_still_owes_one(tmp_path):
    rows = [("intake", "done", "—", ""), ("discover", "skipped", "—", "x"),
            ("design", "done", "—", "")] + FOUR[1:]
    done = run_preflight("build", state(tmp_path, rows), tmp_path)
    assert "FAIL intake_document" in done.stdout


# --- validate.py pins (R2, UC5) ---------------------------------------------

def _copy_repo(tmp_path):
    dest = tmp_path / "repo"
    shutil.copytree(REPO_ROOT, dest, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", ".coverage*"))
    return dest


def _validate(repo, section):
    return subprocess.run([sys.executable, "scripts/validate.py", section], cwd=repo,
                          capture_output=True, encoding="utf-8", env=dict(os.environ))


ROUTE_TEST = "Can you write a test that fails now and would pass if an existing promise"


def test_the_shipped_stage_design_has_exactly_one_route_decision():
    text = " ".join((PLUGIN / "skills" / "track" / "references" / "stage-design.md")
                    .read_text(encoding="utf-8").split())
    assert text.count(ROUTE_TEST) == 1


def test_validate_fails_when_stage_design_gains_a_second_route_decision(tmp_path):
    repo = _copy_repo(tmp_path)
    ref = repo / "plugins/cai/skills/track/references/stage-design.md"
    ref.write_text(ref.read_text(encoding="utf-8")
                   + "\n\n> " + ROUTE_TEST + " held?**\n", encoding="utf-8")
    result = _validate(repo, "track-stages")
    assert result.returncode != 0
    assert re.search(r"FAIL .*exactly one route decision", result.stdout), result.stdout


def test_validate_fails_when_the_standalone_discover_skill_is_gone(tmp_path):
    repo = _copy_repo(tmp_path)
    shutil.rmtree(repo / "plugins/cai/skills/discover")
    result = _validate(repo, "track-stages")
    assert result.returncode != 0
    assert re.search(r"FAIL .*skills/discover/SKILL.md still exists", result.stdout), result.stdout
