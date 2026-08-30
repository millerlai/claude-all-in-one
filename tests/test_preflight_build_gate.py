"""preflight's `build` gate over the three design kinds.

`## Work breakdown` lives in design_probe.py's DETAIL_HEADINGS and in no
other kind's list, and only design-detail.md.tpl carries the heading. The
gate used to demand it of whatever the design row named, which made a
signed-off high-level or delta design unbuildable -- and the obvious repair,
editing the heading in, landed after sign-off and tripped artifact_unchanged
on the next run. These tests hold both halves shut.
"""
import os
import subprocess
import sys

import ledger
import preflight

PREFLIGHT_PY = os.path.join(os.path.dirname(ledger.__file__), "preflight.py")

HLD = "# x\n\n## Status\napproved 2026-08-30\n"
DETAIL = HLD + "\n## Work breakdown\n\n| # | Unit |\n|---|---|\n| 1 | a |\n"


def make_track(tmp_path, artifact):
    """A track sitting at `build`, with intake/discover/design all done and
    the design row naming `artifact`."""
    track = tmp_path / "track"
    track.mkdir(exist_ok=True)  # the drift test remakes it once per kind
    rows = [("intake", "done", "—", ""), ("discover", "done", "—", ""),
            ("design", "done", artifact, ""), ("build", "", "", ""),
            ("verify", "", "", ""), ("ship", "", "", "")]
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(track)


def write_doc(tmp_path, name, text):
    doc = tmp_path / name
    doc.write_text(text, encoding="utf-8")
    return str(doc)


def run(track, project):
    return subprocess.run(
        [sys.executable, PREFLIGHT_PY, "build", "--track-dir", track,
         "--project-dir", project],
        capture_output=True, text=True, encoding="utf-8")


# --- the kinds that never carry a schedule --------------------------------

def test_a_high_level_design_with_no_work_breakdown_can_be_built(tmp_path):
    write_doc(tmp_path, "d-high-level.md", HLD)
    done = run(make_track(tmp_path, "d-high-level.md"), str(tmp_path))

    assert done.returncode == 0, done.stdout
    assert "PASS work_breakdown" in done.stdout
    assert "cuts the units instead" in done.stdout


def test_a_delta_design_with_no_work_breakdown_can_be_built(tmp_path):
    write_doc(tmp_path, "d-delta.md", HLD)
    done = run(make_track(tmp_path, "d-delta.md"), str(tmp_path))

    assert done.returncode == 0, done.stdout
    assert "PASS work_breakdown" in done.stdout


# --- detail is the one kind that promises a schedule ----------------------

def test_a_detail_design_still_has_to_carry_one(tmp_path):
    write_doc(tmp_path, "d-detail.md", HLD)
    done = run(make_track(tmp_path, "d-detail.md"), str(tmp_path))

    assert done.returncode == 2
    assert "FAIL work_breakdown" in done.stdout
    assert "is a detail design" in done.stdout


def test_a_detail_design_that_carries_one_passes(tmp_path):
    write_doc(tmp_path, "d-detail.md", DETAIL)
    done = run(make_track(tmp_path, "d-detail.md"), str(tmp_path))

    assert done.returncode == 0, done.stdout
    assert "PASS work_breakdown (d-detail.md)" in done.stdout


# --- the trap the two checks used to form together ------------------------

def test_a_signed_off_high_level_design_needs_no_edit_to_get_past_build(tmp_path):
    """The regression in full. Sign-off fingerprints the document; the old
    gate then refused it for a heading its template never had, and adding
    the heading changed the file the fingerprint was taken from. Passing
    both checks on the *unmodified* signed-off document is the only state
    that leaves the person a way forward."""
    doc = write_doc(tmp_path, "d-high-level.md", HLD)
    track = make_track(tmp_path, "d-high-level.md")
    ledger.append(track, "design", "passed", artifact=doc, gate="human")

    done = run(track, str(tmp_path))

    assert done.returncode == 0, done.stdout
    assert "PASS artifact_unchanged" in done.stdout
    assert "PASS work_breakdown" in done.stdout


def test_editing_a_signed_off_document_is_still_caught(tmp_path):
    """The other half stays armed: artifact_unchanged is what makes sign-off
    mean anything, and this change must not have loosened it."""
    doc = write_doc(tmp_path, "d-high-level.md", HLD)
    track = make_track(tmp_path, "d-high-level.md")
    ledger.append(track, "design", "passed", artifact=doc, gate="human")
    write_doc(tmp_path, "d-high-level.md", HLD + "\n## Work breakdown\n")

    done = run(track, str(tmp_path))

    assert done.returncode == 2
    assert "FAIL artifact_unchanged" in done.stdout


def test_preflight_and_design_probe_agree_on_who_needs_a_schedule(tmp_path):
    """The two files that decide this must not drift apart again: the gate
    demands a work breakdown of exactly the kind whose heading list has one."""
    import design_probe

    needs = {kind for kind, headings in
             (("hld", design_probe.HLD_HEADINGS),
              ("detail", design_probe.DETAIL_HEADINGS),
              ("delta", design_probe.DELTA_HEADINGS))
             if "Work breakdown" in headings}
    assert needs == {"detail"}

    for suffix, kind in preflight.SUFFIX_KIND.items():
        write_doc(tmp_path, "d" + suffix, HLD)
        done = run(make_track(tmp_path, "d" + suffix), str(tmp_path))
        blocked = "FAIL work_breakdown" in done.stdout
        assert blocked == (kind in needs), (kind, done.stdout)
