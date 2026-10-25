"""U3 of the plan-stage design: the short path's `intake.md` and its `## Signals`.

A change with no hard-to-undo signal writes only `intake.md`, which Gate 1
then signs. `design_probe.py --kind intake` is what makes "three rows, each
with evidence" a checked fact instead of a sentence the model remembers.
"""
import os
import subprocess
import sys

import design_probe
import ledger
import preflight
import verify_plan

PREFLIGHT_PY = os.path.join(os.path.dirname(ledger.__file__), "preflight.py")
PROBE_PY = os.path.join(os.path.dirname(ledger.__file__), "design_probe.py")

LEVELS = ("## Verification levels\n\n| AC | level | check |\n|---|---|---|\n"
          "| AC1 | test | tests/test_x.py::test_y |\n")


def signals(rows):
    return ("## Signals\n\n| Row | Verdict | Evidence |\n|---|---|---|\n"
            + "".join("| %s | %s | %s |\n" % r for r in rows) + "\n")


GOOD_ROWS = [("Blast radius", "low", "one caller, `plugins/cai/scripts/foo.py:12`"),
             ("Found out when", "low", "the unit test fails, tests/test_x.py:3"),
             ("Undo cost", "low", "revert the commit; https://example.com/doc")]


def intake(rows=GOOD_ROWS, levels=LEVELS, signal_text=None):
    return ("# Intake\n\nAC1: it works.\n\n## Recommended approach\n\nDo the thing.\n\n"
            + (signal_text if signal_text is not None else signals(rows)) + levels)


def verdicts(text):
    """{probe name: passed}; the label up to its parenthesised detail."""
    return {label.split(" (")[0]: ok for ok, label
            in design_probe.PROBES["intake"](design_probe.sections(text), text, (".", "."))}


def failing(text):
    return [label for ok, label
            in design_probe.PROBES["intake"](design_probe.sections(text), text, (".", "."))
            if not ok]


def run_kind(tmp_path, text):
    doc = tmp_path / "intake.md"
    doc.write_text(text, encoding="utf-8")
    return subprocess.run([sys.executable, PROBE_PY, "--kind", "intake", str(doc)],
                          capture_output=True, text=True, encoding="utf-8")


# --- R1: the probe ----------------------------------------------------------

def test_a_complete_intake_passes_with_exit_0(tmp_path):
    done = run_kind(tmp_path, intake())
    assert done.returncode == 0, done.stdout
    assert "FAIL" not in done.stdout


def test_a_missing_row_fails_and_names_it():
    rows = [r for r in GOOD_ROWS if r[0] != "Found out when"]
    bad = failing(intake(rows))
    assert any("Found out when" in label for label in bad), bad


def test_rows_out_of_order_fail():
    bad = failing(intake([GOOD_ROWS[1], GOOD_ROWS[0], GOOD_ROWS[2]]))
    assert any(label.startswith("signal_order") for label in bad), bad


def test_a_fourth_row_fails():
    bad = failing(intake(GOOD_ROWS + [("Extra", "low", "a.py:1")]))
    assert any(label.startswith("signal_rows") for label in bad), bad


def test_a_missing_signals_section_fails():
    bad = failing(intake(signal_text=""))
    assert any(label.startswith("signals_section") for label in bad), bad


def test_a_wrong_header_fails():
    text = intake(signal_text=signals(GOOD_ROWS).replace("Verdict", "Call"))
    assert any(label.startswith("signals_header") for label in failing(text))


def test_a_bad_verdict_fails_and_names_the_row():
    rows = [GOOD_ROWS[0], ("Found out when", "medium", "tests/test_x.py:3"), GOOD_ROWS[2]]
    bad = failing(intake(rows))
    assert any("Found out when" in label and "verdict" in label for label in bad), bad


def test_low_and_high_rows_need_a_citation():
    for verdict in ("low", "high"):
        rows = [GOOD_ROWS[0], GOOD_ROWS[1], ("Undo cost", verdict, "it is easy, trust me")]
        bad = failing(intake(rows))
        assert any("Undo cost" in label and "evidence" in label for label in bad), (verdict, bad)


def test_an_unanswerable_row_with_a_reason_and_no_citation_passes():
    rows = [GOOD_ROWS[0], GOOD_ROWS[1],
            ("Undo cost", "unanswerable", "no deploy config in this repo to read")]
    assert failing(intake(rows)) == []


def test_an_unanswerable_row_with_no_reason_fails():
    rows = [GOOD_ROWS[0], GOOD_ROWS[1], ("Undo cost", "unanswerable", "TBD")]
    bad = failing(intake(rows))
    assert any("Undo cost" in label for label in bad), bad


def test_an_invalid_levels_table_fails():
    bad = failing(intake(levels=LEVELS.replace("| test |", "| bogus |")))
    assert any(label.startswith("verification_levels") for label in bad), bad


def test_levels_are_read_through_verify_plan(monkeypatch):
    seen = []
    real = verify_plan.read_levels
    monkeypatch.setattr(verify_plan, "read_levels", lambda t: seen.append(1) or real(t))
    verdicts(intake())
    assert seen


# --- R1: preflight ----------------------------------------------------------

def make_track(tmp_path, text):
    track = tmp_path / "track"
    track.mkdir()
    rows = [("design", "done", "intake.md", ""), ("build", "", "", ""),
            ("verify", "", "", ""), ("ship", "", "", "")]
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (track / "intake.md").write_text(text, encoding="utf-8")
    # Gate 1: the Approve fingerprints intake.md itself.
    ledger.append(str(track), "design", "passed", artifact=str(track / "intake.md"),
                  gate="human")
    return str(track)


def run_build(track, project):
    return subprocess.run([sys.executable, PREFLIGHT_PY, "build", "--track-dir", track,
                           "--project-dir", str(project)],
                          capture_output=True, text=True, encoding="utf-8")


def test_the_document_kind_of_intake_md_is_intake():
    assert preflight.document_kind("intake.md") == "intake"
    assert preflight.document_kind("some/dir/intake.md") == "intake"
    assert preflight.document_kind("my-intake.md") is None
    assert preflight.document_kind("x-detail.md") == "detail"


def test_build_accepts_a_signed_short_path_intake(tmp_path):
    done = run_build(make_track(tmp_path, intake()), tmp_path)
    assert done.returncode == 0, done.stdout
    assert "PASS design_signed_off" in done.stdout
    assert "PASS artifact_unchanged" in done.stdout
    assert "signal_rows" in done.stdout
    assert "options_drafts (artifact is not a decisions document)" in done.stdout


def test_build_refuses_an_intake_with_a_signals_row_missing(tmp_path):
    track = make_track(tmp_path, intake(GOOD_ROWS[:2]))
    done = run_build(track, tmp_path)
    assert done.returncode == 2
    assert "FAIL signal" in done.stdout


def test_editing_a_signed_intake_is_caught(tmp_path):
    track = make_track(tmp_path, intake())
    with open(os.path.join(track, "intake.md"), "a", encoding="utf-8") as fh:
        fh.write("\nlate edit\n")
    done = run_build(track, tmp_path)
    assert "FAIL artifact_unchanged" in done.stdout and done.returncode == 2


def test_design_stage_runs_the_intake_probe_on_an_intake_row(tmp_path):
    track = make_track(tmp_path, intake(GOOD_ROWS[:2]))
    checks = preflight._design(track, str(tmp_path))
    assert any(not ok and "signal" in label for ok, label in checks), checks


# --- UC4: verify still reads the levels -------------------------------------

def test_verify_plan_reads_levels_the_same_with_or_without_a_signals_section():
    plain = verify_plan.read_levels("# Intake\n\nAC1: it works.\n\n" + LEVELS)
    short = verify_plan.read_levels(intake())
    assert plain["status"] == "ok"
    assert short == plain or (short["status"], short["rows"]) == (plain["status"], plain["rows"])
