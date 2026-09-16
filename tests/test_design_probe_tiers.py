"""design_probe.py's stance and decisions kinds: the budgets and the bars.

The old single design document failed by being unreviewable -- long enough
that signing it meant "I gave up reading". These two kinds exist to keep what
a person signs small, so the checks that matter here are the ones that fail a
document for being too big or for letting an unevidenced choice through
unopposed. Both are mechanical, which is the point: a ceiling enforced by
remembering is a ceiling nobody keeps.
"""
import design_probe


def verdicts(kind, text, roots=(".", ".")):
    """{probe name: passed} -- the label minus its parenthesised detail, so a
    test asserts on the probe rather than on its wording."""
    run = design_probe.PROBES[kind]
    return {label.split(" (")[0]: ok
            for ok, label in run(design_probe.sections(text), text, roots)}


def detail(kind, text, probe, roots=(".", ".")):
    run = design_probe.PROBES[kind]
    return next(label for _, label in run(design_probe.sections(text), text, roots)
                if label.startswith(probe + " "))


DIAGRAM = '```mermaid\nflowchart TD\n  A["one"] --> B["two"]\n```\n'

STANCE = """# t — stance

## Status

draft

## Optimises for

Reaching the judge without spending the only gesture the chart has.

## Sacrifices

- The card list is not visible while the form is open, and that is deliberate.

## Invariants

**This system's:**

- The pickedAt path does not change; only who writes into it changes here.

**Cross-project:**

- Nothing the test environment cannot observe may become part of the design.

## Rejected stances

- Keeping the click gesture and adding a button, which leaves the defect there.

## Use cases / Issues

- UC1 — the operator judges one bar and gets a verdict back afterwards.

## Overview

%s
A sentence saying what to look at in the diagram above.

## Out of scope

- Dragging the window, which nobody asked for and nothing here resembles.
""" % DIAGRAM


def replace_section(text, heading, body):
    """Swap one `## ` section's body, leaving the rest of the document alone."""
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


# --- stance -----------------------------------------------------------------

def test_a_filled_stance_passes_every_probe():
    assert all(verdicts("stance", STANCE).values())


def test_invariants_that_are_only_labels_do_not_count():
    """The conflict test reads this list and nothing else. A section carrying
    the two bold headers and no entries under them looks filled and switches
    the gate off, which is the failure worth catching mechanically."""
    text = replace_section(STANCE, "Invariants",
                           "**This system's:**\n\n**Cross-project:**")
    assert verdicts("stance", text)["invariants_listed"] is False


def test_a_stance_with_no_diagram_fails():
    assert verdicts("stance", STANCE.replace(DIAGRAM, ""))["diagram_present"] is False


def test_prose_over_the_ceiling_fails():
    filler = "\n".join("Another sentence that pushes this past the ceiling."
                       for _ in range(design_probe.STANCE_MAX_LINES))
    text = replace_section(STANCE, "Out of scope", filler)
    assert verdicts("stance", text)["within_one_page"] is False


def test_diagrams_are_not_charged_to_the_ceiling():
    """A picture is what makes the rest readable. Charging the budget for one
    would push the author to drop the cheapest thing that helps, so the fenced
    block is excluded -- a stance stays passable however tall its diagram."""
    tall = ('```mermaid\nflowchart TD\n'
            + "".join('  N%d["n"] --> N%d["n"]\n' % (i, i + 1) for i in range(200))
            + '```\n')
    text = STANCE.replace(DIAGRAM, tall)
    assert verdicts("stance", text)["within_one_page"] is True


def test_sacrifices_is_required():
    """The heading people skip. Without it the next reader "fixes" what was
    given up on purpose, so an empty one is a probe failure twice over."""
    text = replace_section(STANCE, "Sacrifices", "")
    got = verdicts("stance", text)
    assert got["sacrifices_listed"] is False
    assert got["headings_complete"] is False


# --- decisions --------------------------------------------------------------

def entry(name, cite="`store/state.ts:274`", diagram=DIAGRAM, when="next test run"):
    return "### %s — does it?\n\n%s\nChose A, because %s rules out the rest.\n" \
           "**Found out when:** %s\n\n" % (name, diagram, cite, when)


def decisions_doc(tier1=None, tier2=None, gaps="", stance_name="stance.md"):
    tier1 = entry("D1") if tier1 is None else tier1
    tier2 = entry("D2") if tier2 is None else tier2
    return """# t — decisions

## Reference

- Stance: `%s` — status: approved

## Feasibility

| Id | Capability | Verdict | Evidence |
|---|---|---|---|
| C1 | the store holds plain UI state | verified | `store/state.ts:274` |

## Ruled out

| Option | Invariant it violates | Evidence |
|---|---|---|
| showModal | nothing untestable may ship | C1 |

## Requirement gaps

%s

## Tier 1

%s

## Tier 2

%s

## Tier 3

| Decision | Chose | Instead of | Found out when |
|---|---|---|---|
| the dialog tag | dialog | a plain div | next test run |
""" % (stance_name, gaps or "", tier1, tier2)


def written(tmp_path, doc, stance=STANCE.replace("draft", "approved 2026-09-16", 1)):
    (tmp_path / "stance.md").write_text(stance, encoding="utf-8")
    return doc, (str(tmp_path), str(tmp_path))


def test_a_filled_decisions_document_passes_every_probe(tmp_path):
    doc, roots = written(tmp_path, decisions_doc())
    got = verdicts("decisions", doc, roots)
    assert all(got.values()), [k for k, v in got.items() if not v]


def test_a_draft_stance_blocks_the_queue(tmp_path):
    """Weighing options against a trade nobody agreed to is how a stance gets
    replaced one implementation detail at a time."""
    doc, roots = written(tmp_path, decisions_doc(), stance=STANCE)
    assert verdicts("decisions", doc, roots)["stance_is_approved"] is False


def test_tier1_over_budget_fails(tmp_path):
    over = "".join(entry("D%d" % i) for i in range(design_probe.TIER1_MAX + 1))
    doc, roots = written(tmp_path, decisions_doc(tier1=over))
    assert verdicts("decisions", doc, roots)["tier1_within_budget"] is False


def test_tier2_over_budget_fails(tmp_path):
    over = "".join(entry("D%d" % i) for i in range(design_probe.TIER2_MAX + 1))
    doc, roots = written(tmp_path, decisions_doc(tier2=over))
    assert verdicts("decisions", doc, roots)["tier2_within_budget"] is False


def test_a_tier1_entry_without_a_diagram_fails(tmp_path):
    """Tier 1 is the one place a person holds two designs in their head at
    once. Two pictures do that faster than two columns of prose."""
    doc, roots = written(tmp_path, decisions_doc(tier1=entry("D1", diagram="")))
    assert verdicts("decisions", doc, roots)["tier1_entries_drawn"] is False


def test_a_tier2_entry_without_a_citation_fails(tmp_path):
    """Nothing reviews what is scanned, so a preference with no evidence
    behind it arrives unopposed. The bar for Tier 2 is a citation."""
    doc, roots = written(tmp_path, decisions_doc(tier2=entry("D2", cite="it reads better")))
    assert verdicts("decisions", doc, roots)["tier2_entries_cite"] is False


def test_a_missing_found_out_when_fails(tmp_path):
    blank = "### D1 — does it?\n\n%s\nChose A, per `a.ts:1`.\n\n" % DIAGRAM
    doc, roots = written(tmp_path, decisions_doc(tier1=blank))
    assert verdicts("decisions", doc, roots)["states_when_found_out"] is False


def test_a_gap_with_no_exit_fails(tmp_path):
    """An assumption about user behaviour with neither a veto condition nor a
    way to settle it is a guess, and a guess may not be used as grounds."""
    rows = ("| # | The behavioural assumption | Veto condition, or path | Deletes |\n"
            "|---|---|---|---|\n"
            "| G1 | the operator stops watching after pressing |  |  |\n")
    doc, roots = written(tmp_path, decisions_doc(gaps=rows))
    assert verdicts("decisions", doc, roots)["gaps_have_an_exit"] is False


def test_the_gap_count_is_reported_and_never_fails(tmp_path):
    """One round with gaps is a design doing its job; three rounds running is
    the requirements stage asking to be fixed. Only a number kept across
    rounds can tell those apart, so this probe counts and never blocks."""
    rows = ("| # | The behavioural assumption | Veto condition, or path | Deletes |\n"
            "|---|---|---|---|\n"
            "| G1 | the operator stops watching | the chart stays visible | option B |\n"
            "| G2 | nobody reads the strip | measure one week of use | none yet |\n")
    doc, roots = written(tmp_path, decisions_doc(gaps=rows))
    assert verdicts("decisions", doc, roots)["requirement_gaps"] is True
    assert "2 this round" in detail("decisions", doc, "requirement_gaps", roots)


# --- the legacy kind --------------------------------------------------------

def test_a_high_level_design_carrying_build_spec_headings_fails():
    """The failure that started this: a high-level design growing into the
    document downstream of it, so that neither is the length it was for."""
    text = ("## Status\n\ndraft\n\n## Use cases / Issues\n\n- UC1 — a thing\n\n"
            "## Work breakdown\n\n| Unit | Done when |\n|---|---|\n| one | it is |\n")
    assert verdicts("hld", text)["no_detail_headings"] is False
