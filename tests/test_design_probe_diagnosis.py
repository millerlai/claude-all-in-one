"""design_probe.py's diagnosis kind: the entry condition, and the cause.

Diagnosis mode exists for something broken rather than something missing, and
the line between those is not what the ticket called it. The check that
carries this file is `failing_test_named`: without a test that fails now and
would pass if an existing promise held, nothing was promised, so nothing is
broken -- and writing a root cause for a behaviour that was never guaranteed
produces a fix aimed at nothing.
"""
import design_probe


def verdicts(text, roots=(".", ".")):
    """{probe name: passed} -- the label minus its parenthesised detail."""
    return {label.split(" (")[0]: ok for ok, label
            in design_probe.PROBES["diagnosis"](design_probe.sections(text),
                                                text, roots)}


DIAGRAM = ('```mermaid\nflowchart TD\n  A["click"] --> B["writes pickedAt"]\n'
           '  B --> C["refreshIdea"]\n```\n')

DIAGNOSIS = """# t - diagnosis

## Status

draft

## Symptom

Double-clicking a bar on a second series opens the window on the first one,
every time, with the steps in the ticket.

## Failing test

`tests/test_window.py::test_second_series_opens_its_own_bar` fails now,
printing `AssertionError: expected QQQ, got SPY`. The promise it tests is the
existing `test_picked_bar_is_the_clicked_bar`, which has passed since 2026-08.

## Root cause

The handler closes over the series captured when it was wired, so a later
switch never reaches it (`chart/lightweight.ts:233`). Fixing the line the
trace points at would leave the same capture in the two other subscribers.

## Blast radius

Two other subscribers close over the same value the same way
(`chart/controller.ts:292`), so the crosshair has this bug too and nobody has
reported it yet.

## Fix

Read the series inside the handler instead of capturing it, at all three
sites. That is the cause: the capture, not the stale value it produced.

## Invariants preserved

The pickedAt path itself does not change, which is the stance's first
invariant; the existing subscription count stays at one per chart.

## Picture

%s
The faulty node is the capture, not the value it hands on.

## Out of scope

- The crosshair's copy of this bug, which ships as its own fix next week.
""" % DIAGRAM


def replace_section(text, heading, body):
    out, skipping = [], False
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            if skipping:
                skipping = False
            if line[3:].strip() == heading:
                out.append(line)
                out.append("\n" + body.rstrip("\n") + "\n\n")
                skipping = True
                continue
        if not skipping:
            out.append(line)
    return "".join(out)


def test_a_filled_diagnosis_passes_every_probe():
    got = verdicts(DIAGNOSIS)
    assert all(got.values()), [k for k, v in got.items() if not v]


def test_no_failing_test_named_fails():
    """The entry condition, checked rather than assumed. A diagnosis with no
    failing test is a claim about an expectation, and an expectation nobody
    wrote down is a requirement - stance mode's work, not this one's."""
    text = replace_section(
        DIAGNOSIS, "Failing test",
        "It obviously should not do that, and everyone agrees it is broken.")
    assert verdicts(text)["failing_test_named"] is False


def test_a_root_cause_with_no_evidence_fails():
    text = replace_section(
        DIAGNOSIS, "Root cause",
        "Probably a stale closure somewhere in the chart layer, most likely.")
    assert verdicts(text)["root_cause_cited"] is False


def test_an_unverified_root_cause_passes():
    """A blank admitted is better than a cause invented: a plausible-sounding
    one ends the search, and the next person never reopens it."""
    text = replace_section(
        DIAGNOSIS, "Root cause",
        "UNVERIFIED - reproducing needs the vendor build, which is not here.\n"
        "A trace with the flag on would settle it.")
    assert verdicts(text)["root_cause_cited"] is True


def test_a_diagnosis_with_no_diagram_fails():
    assert verdicts(DIAGNOSIS.replace(DIAGRAM, ""))["diagram_present"] is False


def test_prose_over_the_ceiling_fails():
    filler = "\n".join("One more line of detail that pushes this over."
                       for _ in range(design_probe.DIAGNOSIS_MAX_LINES))
    text = replace_section(DIAGNOSIS, "Out of scope", filler)
    assert verdicts(text)["within_one_page"] is False


def test_the_ceiling_is_higher_than_a_stance():
    """Stated as a relationship rather than two numbers, so that moving either
    keeps the reason: a diagnosis carries reproduction steps and the evidence
    behind the cause, and a stance carries neither."""
    assert design_probe.DIAGNOSIS_MAX_LINES > design_probe.STANCE_MAX_LINES


# A detail design whose sole upstream is an approved diagnosis: `## Reference`
# names it and nothing else. The diagnosis fixture above is written once and
# reused with its `## Status` promoted to `approved`, exactly as `build`
# would find one signed off at Gate 1.
STANCE_MIN = """# t - stance

## Use cases / Issues

- UC1 - the operator sees which run failed, without opening the log by hand.
"""

DECISIONS_MIN = """# t - decisions

## Reference

Stance doc: t-stance.md

## Tier 1

- nothing decided here yet
"""


def traceability_verdict(text, roots):
    """(passed, label) for just the `traceability` probe -- the generator is
    lazy, so this never requires the rest of the document to be complete."""
    secs = design_probe.sections(text)
    return next((ok, label) for ok, label in design_probe.PROBES["detail"](secs, text, roots)
                if label.startswith("traceability "))


def approved_diagnosis():
    return DIAGNOSIS.replace("draft", "approved 2026-09-25", 1)


def test_a_detail_after_a_diagnosis_passes_traceability(tmp_path):
    diag_path = tmp_path / "t-diagnosis.md"
    diag_path.write_text(approved_diagnosis(), encoding="utf-8")
    detail_text = "## Reference\n\nDiagnosis doc: t-diagnosis.md\n"
    ok, label = traceability_verdict(detail_text, (str(tmp_path), str(tmp_path)))
    assert ok is True
    assert str(diag_path) in label


def test_two_diagnoses_referenced_both_named(tmp_path):
    """AC3: more than one diagnosis in `## Reference` is a defined case, not
    an accident of which one happened to resolve first -- both paths show up
    in the label so a reader can check either."""
    diag1 = tmp_path / "a-diagnosis.md"
    diag2 = tmp_path / "b-diagnosis.md"
    diag1.write_text(approved_diagnosis(), encoding="utf-8")
    diag2.write_text(approved_diagnosis(), encoding="utf-8")
    detail_text = "## Reference\n\na-diagnosis.md\nb-diagnosis.md\n"
    ok, label = traceability_verdict(detail_text, (str(tmp_path), str(tmp_path)))
    assert ok is True
    assert str(diag1) in label and str(diag2) in label


def test_a_stance_with_heading_but_no_ids_still_fails(tmp_path):
    """AC4: no regression for the shape this probe already caught -- a
    heading present with nothing under it is still a gap, not "not
    applicable"."""
    stance_path = tmp_path / "t-stance.md"
    stance_path.write_text("# t - stance\n\n## Use cases / Issues\n\n"
                            "Nothing numbered here yet.\n", encoding="utf-8")
    detail_text = "## Reference\n\nStance doc: t-stance.md\n"
    ok, label = traceability_verdict(detail_text, (str(tmp_path), str(tmp_path)))
    assert ok is False
    assert "numbers no use cases" in label


def test_diagnosis_then_stance_still_traces_the_stance(tmp_path):
    """AC4: `[diagnosis, stance]` order skips the diagnosis (it has no `##
    Use cases / Issues` at all) and traces the stance that follows it --
    reaching UC1 passes, missing it still FAILs."""
    diag_path = tmp_path / "t-diagnosis.md"
    diag_path.write_text(approved_diagnosis(), encoding="utf-8")
    stance_path = tmp_path / "t-stance.md"
    stance_path.write_text(STANCE_MIN, encoding="utf-8")
    reference = "## Reference\n\nt-diagnosis.md\nt-stance.md\n"

    ok, label = traceability_verdict(reference + "\nUC1 is satisfied here.\n",
                                      (str(tmp_path), str(tmp_path)))
    assert ok is True
    assert "all 1 use case(s) reached" in label

    ok, label = traceability_verdict(reference + "\nNothing in this detail traces it.\n",
                                      (str(tmp_path), str(tmp_path)))
    assert ok is False
    assert "UC1" in label


def test_decisions_first_then_stance_still_traces_the_stance(tmp_path):
    """The fix's side effect the diagnosis calls out: a `## Reference` that
    lists the decisions document first used to FAIL for the same root cause
    as the diagnosis path, since decisions has no `## Use cases / Issues`
    either. It now traces the stance that follows -- reaching UC1 passes,
    missing it still FAILs, the same pair `test_diagnosis_then_stance_still_
    traces_the_stance` checks for the diagnosis-first order, so a fix that
    only handled the passing half of this path would not go unnoticed."""
    decisions_path = tmp_path / "t-decisions.md"
    decisions_path.write_text(DECISIONS_MIN, encoding="utf-8")
    stance_path = tmp_path / "t-stance.md"
    stance_path.write_text(STANCE_MIN, encoding="utf-8")
    reference = "## Reference\n\nt-decisions.md\nt-stance.md\n"

    ok, label = traceability_verdict(reference + "\nUC1 is satisfied here.\n",
                                      (str(tmp_path), str(tmp_path)))
    assert ok is True
    assert "all 1 use case(s) reached" in label

    ok, label = traceability_verdict(reference + "\nNothing in this detail traces it.\n",
                                      (str(tmp_path), str(tmp_path)))
    assert ok is False
    assert "UC1" in label
