"""preflight's `discover` and `ship` gates over ledger.COUNTS_AS_FINISHED.

Both used to gate on `bool(status)`, which let anything non-empty through --
`passed` and `in-progress` included, neither of which means the stage is
done (#61). The gate is `status in ledger.COUNTS_AS_FINISHED`, exactly
`("done", "skipped")`, not `status in ledger.STATUSES`: STATUSES' first
element is the empty string, so membership of it would be looser than the
`bool(status)` it replaces, not stricter.
"""
import os
import subprocess
import sys

import pytest

import ledger

PREFLIGHT_PY = os.path.join(os.path.dirname(ledger.__file__), "preflight.py")


def make_track(tmp_path, intake_status, verify_status):
    """A six-row state.md fixture with the intake and verify rows set to the
    given statuses -- not a git repo, so ship's other two checks
    (clean_tree, not_main_branch) always FAIL here; ship's own tests assert
    on the verify_status line in stdout, never on the exit code."""
    track = tmp_path / ("track-%s-%s" % (intake_status or "empty", verify_status or "empty"))
    track.mkdir()
    rows = [("intake", intake_status, "—", ""), ("discover", "", "", ""),
            ("design", "", "", ""), ("build", "", "", ""),
            ("verify", verify_status, "—", ""), ("ship", "", "", "")]
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(track)


def run(stage, track, project):
    return subprocess.run(
        [sys.executable, PREFLIGHT_PY, stage, "--track-dir", track,
         "--project-dir", project],
        capture_output=True, text=True, encoding="utf-8")


# --- discover: exit code and PASS/FAIL both carry the answer ---------------

@pytest.mark.parametrize("status", ["passed", "in-progress"])
def test_discover_blocks_statuses_that_are_not_finished(tmp_path, status):
    track = make_track(tmp_path, status, "")
    done = run("discover", track, str(tmp_path))
    assert done.returncode == 2, done.stdout
    assert "FAIL intake_status" in done.stdout


@pytest.mark.parametrize("status", ["done", "skipped"])
def test_discover_passes_finished_statuses(tmp_path, status):
    track = make_track(tmp_path, status, "")
    done = run("discover", track, str(tmp_path))
    assert done.returncode == 0, done.stdout
    assert "PASS intake_status" in done.stdout


def test_discover_blocks_an_empty_status(tmp_path):
    track = make_track(tmp_path, "", "")
    done = run("discover", track, str(tmp_path))
    assert done.returncode == 2, done.stdout
    assert "FAIL intake_status" in done.stdout
    assert "is empty" in done.stdout


# --- ship: verify_status is one check among three, so only the label is
#     asserted on, never the exit code (clean_tree/not_main_branch always
#     FAIL against a plain fixture directory that is not a git repo) --------

@pytest.mark.parametrize("status", ["passed", "in-progress"])
def test_ship_fails_verify_status_for_statuses_that_are_not_finished(tmp_path, status):
    track = make_track(tmp_path, "", status)
    done = run("ship", track, str(tmp_path))
    assert "FAIL verify_status" in done.stdout


@pytest.mark.parametrize("status", ["done", "skipped"])
def test_ship_passes_verify_status_for_finished_statuses(tmp_path, status):
    track = make_track(tmp_path, "", status)
    done = run("ship", track, str(tmp_path))
    assert "PASS verify_status" in done.stdout


def test_ship_fails_verify_status_for_an_empty_status(tmp_path):
    track = make_track(tmp_path, "", "")
    done = run("ship", track, str(tmp_path))
    assert "FAIL verify_status" in done.stdout
    assert "is empty" in done.stdout
