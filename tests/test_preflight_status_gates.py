"""preflight's `ship` gate over ledger.COUNTS_AS_FINISHED, and `build`'s
intake_document check on a track begun when intake was still a stage.

Both gates used to be `bool(status)`, which let anything non-empty through --
`passed` and `in-progress` included, neither of which means the stage is
done (#61). The gate is `status in ledger.COUNTS_AS_FINISHED`, exactly
`("done", "skipped")`, not `status in ledger.STATUSES`: STATUSES' first
element is the empty string, so membership of it would be looser than the
`bool(status)` it replaces, not stricter. (The `discover` gate went with the
discover stage; the fixtures below keep the six rows an old track still has.)
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


VALID_INTAKE = ("# Intake\n\nAC1: it works.\n\n## Verification levels\n\n"
                "| AC | level | check |\n|---|---|---|\n| AC1 | manual | look |\n")
LEGACY_INTAKE = "# Intake\n\nAC1: it works.\n"
BAD_TABLE_INTAKE = ("# Intake\n\nAC1: it works.\n\n## Verification levels\n\n"
                    "| AC | level | check |\n|---|---|---|\n| AC1 | bogus | look |\n")


# --- intake_document (#376): a done intake owes a readable intake.md --------
# Checked by `build` now, and on a track that still has an intake row only when
# that row is `done` (the rule it was begun under).

def _intake_track(tmp_path, content):
    track = make_track(tmp_path, "done", "")
    if content is not None:
        (tmp_path / "track-done-empty" / "intake.md").write_text(content, encoding="utf-8")
    return track


def test_done_intake_without_intake_md_blocks(tmp_path):
    done = run("build", _intake_track(tmp_path, None), str(tmp_path))
    assert done.returncode == 2, done.stdout
    assert "FAIL intake_document" in done.stdout


def test_done_intake_with_invalid_table_blocks(tmp_path):
    done = run("build", _intake_track(tmp_path, BAD_TABLE_INTAKE), str(tmp_path))
    assert done.returncode == 2, done.stdout
    assert "FAIL intake_document" in done.stdout


def test_done_intake_with_legacy_document_does_not_block(tmp_path):
    done = run("build", _intake_track(tmp_path, LEGACY_INTAKE), str(tmp_path))
    assert "PASS intake_document" in done.stdout
    assert "FAIL intake_document" not in done.stdout


def test_done_intake_with_a_valid_document_passes(tmp_path):
    done = run("build", _intake_track(tmp_path, VALID_INTAKE), str(tmp_path))
    assert "PASS intake_document" in done.stdout


@pytest.mark.parametrize("status", ["skipped", "", "in-progress"])
def test_an_intake_that_is_not_done_owes_no_document(tmp_path, status):
    done = run("build", make_track(tmp_path, status, ""), str(tmp_path))
    assert "intake_document" not in done.stdout


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
