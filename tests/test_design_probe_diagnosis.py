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
