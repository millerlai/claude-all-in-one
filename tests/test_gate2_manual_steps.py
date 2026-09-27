"""Issue #205: build reports what it could not verify automatically as
numbered manual steps (`references/stage-build.md` Step 6.4), but neither
`## Report` nor Gate 2 (`references/approval-gates.md`) brought them back to
the person before ship's irreversible commands ran. So a fix could be
shipped before its live reproduction was checked.
"""
import os

from test_track_state_left_open import make_track, run

REFS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins", "cai", "skills", "track", "references")
STAGE_BUILD = os.path.join(REFS, "stage-build.md")
APPROVAL_GATES = os.path.join(REFS, "approval-gates.md")


def _report_section(text):
    start = text.index("## Report")
    try:
        end = text.index("\n## ", start + 1)
    except ValueError:
        end = len(text)
    return text[start:end]


def test_build_report_hands_up_manual_steps_as_left_open():
    with open(STAGE_BUILD, encoding="utf-8") as fh:
        report = _report_section(fh.read())

    assert "left open" in report
    assert "manual step" in report


def _gate2_section(text):
    start = text.index("## Gate 2")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def test_gate2_lists_build_left_open_lines():
    with open(APPROVAL_GATES, encoding="utf-8") as fh:
        gate2 = _gate2_section(fh.read())

    assert "track_state.py left-open" in gate2
    assert "[build]" in gate2


def test_gate2_says_what_to_do_standing_alone():
    with open(APPROVAL_GATES, encoding="utf-8") as fh:
        gate2 = _gate2_section(fh.read())

    assert "nothing" in gate2 and "to read" in " ".join(gate2.split())


def test_left_open_prints_build_manual_steps(tmp_path):
    rows = [("intake", "done", "—", ""), ("discover", "done", "—", ""),
             ("design", "done", "—", ""),
             ("build", "done", "—", "Left open: run X by hand; check Y"),
             ("verify", "", "", ""), ("ship", "", "", "")]
    root, _ = make_track(tmp_path, rows)

    done = run("left-open", "--track-root", root)
    assert done.returncode == 0, done.stderr
    assert "- [build] run X by hand" in done.stdout
