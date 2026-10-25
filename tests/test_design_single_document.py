"""U4 of the plan-stage design: the long path's single `-design.md`.

Stance, Decisions and Detail used to be three files, and Gate 1 fingerprinted
only the one the design row named, so editing the stance after sign-off went
unnoticed (stage-design.md's "known gap"). One file with four sections, checked
by `design_probe.py --kind design` and fingerprinted whole, closes it.

The old kinds (`stance`, `decisions`, `detail`, `diagnosis`, `hld`, `delta`,
`intake`) are not retested here: tests/test_design_probe_tiers.py,
tests/test_design_probe_diagnosis.py, tests/test_intake_signals.py and
scripts/validate.py's PROBE_CASES already hold each one's result, and they pass
unchanged -- the new kind is additive.
"""
import hashlib
import os
import subprocess
import sys

import design_probe
import ledger
import preflight
from test_preflight_build_gate import VALID_DRAFT

SCRIPTS = os.path.dirname(ledger.__file__)
PROBE_PY = os.path.join(SCRIPTS, "design_probe.py")
PREFLIGHT_PY = os.path.join(SCRIPTS, "preflight.py")

DIAGRAM = '```mermaid\nflowchart TD\n  A["one"] --> B["two"]\n```\n'
SEQ = '```mermaid\nsequenceDiagram\n  A->>B: go\n```\n'

STANCE = """## Stance

### Status

%(status)s

### Optimises for

Reaching the judge without spending the only gesture the chart has.

### Sacrifices

- The card list is not visible while the form is open, and that is deliberate.

### Invariants

**This system's:**

- The pickedAt path does not change; only who writes into it changes here.

**Cross-project:**

- Nothing the test environment cannot observe may become part of the design.

### Rejected stances

- Keeping the click gesture and adding a button, which leaves the defect there.

### Use cases / Issues

- UC1 — the operator judges one bar and gets a verdict back afterwards.

### Overview

""" + DIAGRAM + """A sentence saying what to look at in the diagram above.

### Out of scope

- Dragging the window, which nobody asked for and nothing here resembles.
"""


def tier1(n=1, decided=True):
    out = ""
    for i in range(1, n + 1):
        out += ("#### D%d — does it?\n\n%s\nChose A, because `src.py:2` rules out the rest.\n\n"
                "- **Found out when:** next test run\n" % (i, DIAGRAM))
        if decided:
            out += "- **Decided:** A — the user, 2026-10-25\n"
        out += "\n"
    return out


def decisions(tier1_text=None):
    return """## Decisions

### Reference

The `## Stance` section of this file — status: approved 2026-10-25

### Feasibility

| Id | Capability | Verdict | Evidence |
|---|---|---|---|
| C1 | the store holds plain UI state | verified | `src.py:2` |

### Ruled out

| Option | Invariant it violates | Evidence |
|---|---|---|
| showModal | nothing untestable may ship | C1 |

### Requirement gaps

### Tier 1

""" + (tier1() if tier1_text is None else tier1_text) + """### Tier 2

#### D9 — the dialog tag?

Chose dialog, because `src.py:3` shows no other tag. **Found out when:** next test run

### Tier 3

| Decision | Chose | Instead of | Found out when |
|---|---|---|---|
| the dialog tag | dialog | a plain div | next test run |
"""


def detail(ac="AC: intake.md sha256 %s"):
    return """## Detail

### Reference

The `## Stance` and `## Decisions` sections of this file
""" + ac + """

#### Traceability

| From the referenced document | Satisfied by | Status |
|---|---|---|
| UC1 | the collector | covered |

### Requirement

UC1 from the Stance section is what this document satisfies.

### Glossary

| Term | Definition | Where it lives |
|---|---|---|
| Collector | reads the session log, one record per run | src.py:2 |

### Budgets

| What | Number | Where it comes from |
|---|---|---|
| runs per night | up to 400 | the operator's own estimate |

### Design decisions

Polling beat interception because UC1 never needs to block a live call.

### Diagrams

""" + DIAGRAM * 3 + SEQ + """
### Implementation spec

The Collector exposes read_runs(path) -> list[Record]; errors surface to caller.

### Naming

Every file this produces gets a spelled-out name; no abbreviation is invented.

### Change points

- src.py - gains one function. No new dependency.

### Failure modes

- The log file is missing: the collector emits nothing and reports that.

### Rollout

- Ships in one piece; rollback is reverting the commit, no data is written.

### Verification

- UC1: unit test over a fixture log, asserting one record per run.

### Work breakdown

| Unit | Depends on | Can run alongside | Done when |
|---|---|---|---|
| U1 collector | nothing | — | its unit test is green |
"""

DIAGNOSIS = """## Diagnosis

### Status

approved 2026-10-25

### Symptom

Pressing the bar twice drops the verdict; reproduced by tests/test_bar.py every time.

### Failing test

tests/test_bar.py::test_double_press fails with a missing verdict.

### Root cause

The handler overwrites the pending verdict at `src.py:2`, so the second press wins.

### Blast radius

Only the bar handler writes the pending verdict, per `src.py:3`.

### Fix

Queue the second press instead of overwriting the first.

### Invariants preserved

The pickedAt path does not change.

### Picture

""" + DIAGRAM + """The faulty node is the overwrite.

### Out of scope

- Reworking the handler beyond the overwrite, which nothing here needs.
"""


def doc(status="approved 2026-10-25", with_diagnosis=False, d=None, t1=None, det=None):
    parts = ["# t — design\n\n"]
    if with_diagnosis:
        parts.append(DIAGNOSIS + "\n")
    parts.append((STANCE % {"status": status}) + "\n")
    parts.append((decisions() if t1 is None else decisions(t1)) + "\n")
    parts.append(detail() if det is None else det)
    return "".join(parts)


def project(tmp_path):
    (tmp_path / "src.py").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    return str(tmp_path)


def verdicts(text, tmp_path):
    root = project(tmp_path)
    return {label.split(" (")[0]: ok for ok, label in design_probe.PROBES["design"](
        design_probe.sections(text), text, (root, root))}


def failing(text, tmp_path):
    root = project(tmp_path)
    return [label for ok, label in design_probe.PROBES["design"](
        design_probe.sections(text), text, (root, root)) if not ok]


def run_probe(tmp_path, text):
    root = project(tmp_path)
    path = tmp_path / "2026-10-25-t-design.md"
    path.write_text(text, encoding="utf-8")
    return subprocess.run([sys.executable, PROBE_PY, "--kind", "design",
                           "--project-dir", root, str(path)],
                          capture_output=True, text=True, encoding="utf-8")


# --- R4: the probe -----------------------------------------------------------

def test_a_complete_four_section_document_exits_0(tmp_path):
    done = run_probe(tmp_path, doc(with_diagnosis=True))
    assert done.returncode == 0, done.stdout
    assert "FAIL" not in done.stdout


def test_a_document_without_a_diagnosis_section_also_passes(tmp_path):
    done = run_probe(tmp_path, doc())
    assert done.returncode == 0, done.stdout


def test_a_stance_alone_is_a_legal_partial_document(tmp_path):
    """Stance mode writes its section before the others exist."""
    done = run_probe(tmp_path, "# t — design\n\n" + STANCE % {"status": "draft"})
    assert done.returncode == 0, done.stdout


def test_detail_without_decisions_fails(tmp_path):
    text = "# t — design\n\n" + (STANCE % {"status": "approved 2026-10-25"}) + "\n" + detail()
    bad = failing(text, tmp_path)
    assert any(label.startswith("section_needs") and "Detail" in label for label in bad), bad


def test_decisions_without_stance_fails(tmp_path):
    bad = failing("# t — design\n\n" + decisions(), tmp_path)
    assert any(label.startswith("section_needs") and "Decisions" in label for label in bad), bad


def test_sections_out_of_order_fail(tmp_path):
    text = ("# t — design\n\n" + decisions() + "\n"
            + (STANCE % {"status": "approved 2026-10-25"}) + "\n" + detail())
    bad = failing(text, tmp_path)
    assert any(label.startswith("section_order") for label in bad), bad


def test_a_diagnosis_after_the_stance_fails_the_order(tmp_path):
    text = ("# t — design\n\n" + (STANCE % {"status": "approved 2026-10-25"}) + "\n"
            + DIAGNOSIS)
    assert any(label.startswith("section_order") for label in failing(text, tmp_path))


def test_a_document_with_none_of_the_four_sections_fails(tmp_path):
    bad = failing("# t — design\n\n## Elsewhere\n\ntext\n", tmp_path)
    assert any(label.startswith("design_sections") for label in bad), bad


def test_a_draft_stance_blocks_the_decisions_section(tmp_path):
    bad = failing(doc(status="draft"), tmp_path)
    assert any(label.startswith("stance_is_approved") and "still draft" in label
               for label in bad), bad


def test_a_malformed_status_is_its_own_failure(tmp_path):
    bad = failing(doc(status="looks fine to me"), tmp_path)
    assert any(label.startswith("status_is_well_formed") for label in bad), bad


def test_a_malformed_diagnosis_status_is_its_own_failure(tmp_path):
    text = doc(with_diagnosis=True).replace("approved 2026-10-25\n\n### Symptom",
                                            "ok\n\n### Symptom", 1)
    bad = failing(text, tmp_path)
    assert any(label.startswith("status_is_well_formed") and "[Diagnosis]" in label
               for label in bad), bad


def test_a_stance_section_over_the_ceiling_fails(tmp_path):
    filler = "".join("Another sentence that pushes this past the ceiling.\n"
                     for _ in range(design_probe.STANCE_MAX_LINES))
    text = doc().replace("### Out of scope\n", "### Out of scope\n\n" + filler, 1)
    assert verdicts(text, tmp_path)["within_one_page"] is False


def test_the_ceiling_counts_the_stance_section_only(tmp_path):
    """The whole file is far over 80 lines; the Stance section is not."""
    text = doc()
    assert len([ln for ln in text.splitlines() if ln.strip()]) > design_probe.STANCE_MAX_LINES
    assert verdicts(text, tmp_path)["within_one_page"] is True


def test_every_stance_probe_still_runs_on_its_section(tmp_path):
    text = doc().replace("### Sacrifices", "### Costs", 1)
    bad = failing(text, tmp_path)
    assert any(label.startswith("headings_complete") and "[Stance]" in label
               for label in bad), bad


def test_the_detail_section_is_checked_as_a_detail_design(tmp_path):
    text = doc().replace("### Rollout", "### Shipping", 1)
    assert any(label.startswith("headings_complete") and "[Detail]" in label
               for label in failing(text, tmp_path))


def test_traceability_looks_for_stance_ids_only_inside_detail(tmp_path):
    """UC1 is written in the Stance section; Detail must carry it itself."""
    det = detail().replace("UC1", "the use case")
    bad = failing(doc(det=det), tmp_path)
    assert any(label.startswith("traceability") for label in bad), bad


def test_the_decisions_probe_reads_the_stance_of_the_same_file(tmp_path):
    """No sibling .md exists, and nothing in Reference names one."""
    got = verdicts(doc(), tmp_path)
    assert got["reference_resolves"] is True
    assert got["stance_is_approved"] is True


# --- UC1: Tier 1 at #### ----------------------------------------------------

def test_tier1_entries_at_four_hashes_are_counted(tmp_path):
    root = project(tmp_path)
    text = doc(t1=tier1(design_probe.TIER1_MAX + 1))
    labels = [label for ok, label in design_probe.PROBES["design"](
        design_probe.sections(text), text, (root, root))]
    assert any(label.startswith("tier1_within_budget (%d," % (design_probe.TIER1_MAX + 1))
               for label in labels), labels
    assert verdicts(text, tmp_path)["tier1_within_budget"] is False


def test_a_tier1_entry_without_a_diagram_fails(tmp_path):
    t1 = tier1().replace(DIAGRAM, "")
    assert verdicts(doc(t1=t1), tmp_path)["tier1_entries_drawn"] is False


def test_an_undecided_tier1_entry_blocks_the_detail_section(tmp_path):
    bad = failing(doc(t1=tier1(decided=False)), tmp_path)
    assert any(label.startswith("tier1_decided") for label in bad), bad


def test_an_undecided_tier1_entry_is_fine_while_decisions_is_the_last_section(tmp_path):
    """The person answers Tier 1 one at a time, before Detail exists."""
    text = ("# t — design\n\n" + (STANCE % {"status": "approved 2026-10-25"}) + "\n"
            + decisions(tier1(decided=False)))
    assert failing(text, tmp_path) == []


def test_tier1_drafts_reports_a_missing_options_draft_for_a_design_file(tmp_path):
    track = tmp_path / "track"
    track.mkdir()
    checks = preflight.tier1_drafts(doc(), "docs/design/x-design.md", str(tmp_path / "x-design.md"),
                                    str(track), str(tmp_path))
    assert any(not ok and "missing options-D1.md" in label for ok, label in checks), checks


def test_tier1_drafts_passes_a_design_file_whose_draft_exists(tmp_path):
    track = tmp_path / "track"
    track.mkdir()
    (track / "options-D1.md").write_text(VALID_DRAFT, encoding="utf-8")
    checks = preflight.tier1_drafts(doc(), "docs/design/x-design.md", str(tmp_path / "x-design.md"),
                                    str(track), str(tmp_path))
    assert all(ok for ok, _ in checks), checks
    assert "1 draft(s) checked" in checks[0][1]


def test_tier1_drafts_with_no_tier1_entry_owes_nothing(tmp_path):
    checks = preflight.tier1_drafts(doc(t1="\n"), "x-design.md", "x-design.md",
                                    str(tmp_path), str(tmp_path))
    assert all(ok for ok, _ in checks), checks


def test_the_kind_table_knows_design_md():
    assert preflight.document_kind("docs/design/2026-10-25-t-design.md") == "design"
    assert preflight.document_kind("intake.md") == "intake"


# --- the build gate ----------------------------------------------------------

INTAKE = ("# Intake\n\nAC1: it works.\n\n## Verification levels\n\n"
          "| AC | level | check |\n|---|---|---|\n| AC1 | manual | look |\n")


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def make_track(tmp_path, artifact, rows=None):
    track = tmp_path / "track"
    track.mkdir(exist_ok=True)
    rows = rows or [("design", "done", artifact, ""), ("build", "", "", ""),
                    ("verify", "", "", ""), ("ship", "", "", "")]
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (track / "intake.md").write_text(INTAKE, encoding="utf-8")
    return track


def sign(track, document):
    ledger.append(str(track), "design", "passed", artifact=str(document), gate="human")


def run_build(track, project_dir):
    return subprocess.run([sys.executable, PREFLIGHT_PY, "build", "--track-dir", str(track),
                           "--project-dir", str(project_dir)],
                          capture_output=True, text=True, encoding="utf-8")


def signed_design(tmp_path, ac=None):
    """A long-path track at build: -design.md carrying the AC line for the
    track's own intake.md, signed at Gate 1."""
    track = make_track(tmp_path, "x-design.md")
    (track / "options-D1.md").write_text(VALID_DRAFT, encoding="utf-8")  # Tier 1's D1
    line = ac if ac is not None else "AC: intake.md sha256 %s" % sha(track / "intake.md")
    document = tmp_path / "x-design.md"
    document.write_text(doc(det=detail().replace("AC: intake.md sha256 %s", line)),
                        encoding="utf-8")
    sign(track, document)
    return track, document


def test_a_signed_design_file_with_a_matching_ac_line_builds(tmp_path):
    track, _ = signed_design(tmp_path)
    done = run_build(track, tmp_path)
    assert done.returncode == 0, done.stdout
    assert "PASS intake_unchanged" in done.stdout
    assert "PASS intake_document" in done.stdout
    assert "PASS artifact_unchanged" in done.stdout


def test_editing_the_stance_section_after_sign_off_is_caught(tmp_path):
    track, document = signed_design(tmp_path)
    text = document.read_text(encoding="utf-8")
    document.write_text(text.replace("Reaching the judge", "Reaching a judge", 1),
                        encoding="utf-8")
    done = run_build(track, tmp_path)
    assert done.returncode == 2
    assert "FAIL artifact_unchanged" in done.stdout


# --- UC4: intake.md changed after the AC line was written -------------------

def test_intake_edited_after_the_ac_line_fails(tmp_path):
    track, _ = signed_design(tmp_path)
    with open(track / "intake.md", "a", encoding="utf-8") as fh:
        fh.write("\nAC2: a late addition.\n")
    done = run_build(track, tmp_path)
    assert done.returncode == 2
    line = next(ln for ln in done.stdout.splitlines() if "intake_unchanged" in ln)
    assert line.startswith("FAIL intake_unchanged (intake.md changed after sign-off:")
    assert " != " in line and sha(track / "intake.md") in line
    assert "re-sign Gate 1" in done.stdout


def test_a_design_file_with_no_ac_line_fails_and_says_who_adds_it(tmp_path):
    track = make_track(tmp_path, "x-design.md")
    document = tmp_path / "x-design.md"
    document.write_text(doc(), encoding="utf-8")  # the template placeholder only
    sign(track, document)
    done = run_build(track, tmp_path)
    assert done.returncode == 2
    line = next(ln for ln in done.stdout.splitlines() if "intake_unchanged" in ln)
    assert line.startswith("FAIL") and "main session" in line and "Gate 1" in line


def test_intake_document_still_runs_in_build(tmp_path):
    track, _ = signed_design(tmp_path)
    os.remove(track / "intake.md")
    done = run_build(track, tmp_path)
    assert "FAIL intake_document" in done.stdout


def test_an_ac_line_inside_a_comment_does_not_count(tmp_path):
    track = make_track(tmp_path, "x-design.md")
    document = tmp_path / "x-design.md"
    document.write_text(doc(det=detail().replace(
        "AC: intake.md sha256 %s",
        "<!-- AC: intake.md sha256 %s -->" % sha(track / "intake.md"))), encoding="utf-8")
    sign(track, document)
    assert "FAIL intake_unchanged" in run_build(track, tmp_path).stdout


def test_a_design_file_ending_at_decisions_takes_its_ac_line_at_the_end(tmp_path):
    # Build accepts a row that stops at Stance or Decisions (no Detail section).
    track = make_track(tmp_path, "x-design.md")
    (track / "options-D1.md").write_text(VALID_DRAFT, encoding="utf-8")
    document = tmp_path / "x-design.md"
    document.write_text(doc(det="AC: intake.md sha256 %s\n" % sha(track / "intake.md")),
                        encoding="utf-8")
    sign(track, document)
    done = run_build(track, tmp_path)
    assert "PASS intake_unchanged" in done.stdout, done.stdout
    document.write_text(doc(det="AC: intake.md sha256 %s\n" % ("0" * 64)), encoding="utf-8")
    sign(track, document)
    assert "FAIL intake_unchanged (intake.md changed after sign-off:" in \
        run_build(track, tmp_path).stdout


def test_a_short_path_intake_is_covered_by_gate_1_itself(tmp_path):
    track = make_track(tmp_path, "intake.md")
    sign(track, track / "intake.md")
    checks = preflight.intake_unchanged(str(track), str(tmp_path))
    assert len(checks) == 1 and checks[0][0] is True
    assert "Gate 1" in checks[0][1]


def test_an_old_kind_is_not_checked(tmp_path):
    for name in ("x-stance.md", "x-high-level.md", "x-delta.md"):
        track = make_track(tmp_path, name)
        (tmp_path / name).write_text("# x\n", encoding="utf-8")
        checks = preflight.intake_unchanged(str(track), str(tmp_path))
        assert len(checks) == 1 and checks[0][0] is True, (name, checks)
        assert "not checked" in checks[0][1], checks


def test_the_check_is_silent_when_the_design_row_names_nothing(tmp_path):
    track = make_track(tmp_path, "")
    assert preflight.intake_unchanged(str(track), str(tmp_path)) == []


# --- UC2: the bug track ------------------------------------------------------

def diagnosis_doc(ac_line=None):
    text = ("# t — diagnosis\n\n## Status\n\napproved 2026-10-25\n\n## Symptom\n\nIt breaks.\n\n"
            "## Failing test\n\ntests/test_bar.py::test_double_press fails.\n")
    if ac_line:
        text += "\n" + ac_line + "\n"
    return text + "\n## Root cause\n\nThe handler overwrites at `src.py:2`.\n"


def test_a_bug_track_with_a_matching_ac_line_builds(tmp_path):
    track = make_track(tmp_path, "x-diagnosis.md")
    document = tmp_path / "x-diagnosis.md"
    document.write_text(diagnosis_doc("AC: intake.md sha256 %s" % sha(track / "intake.md")),
                        encoding="utf-8")
    sign(track, document)
    done = run_build(track, tmp_path)
    assert done.returncode == 0, done.stdout
    assert "PASS intake_unchanged" in done.stdout


def test_a_bug_track_without_an_ac_line_fails(tmp_path):
    track = make_track(tmp_path, "x-diagnosis.md")
    document = tmp_path / "x-diagnosis.md"
    document.write_text(diagnosis_doc(), encoding="utf-8")
    sign(track, document)
    done = run_build(track, tmp_path)
    assert done.returncode == 2
    assert "FAIL intake_unchanged" in done.stdout


def test_a_bug_track_whose_intake_changed_fails(tmp_path):
    track = make_track(tmp_path, "x-diagnosis.md")
    document = tmp_path / "x-diagnosis.md"
    document.write_text(diagnosis_doc("AC: intake.md sha256 %s" % ("0" * 64)),
                        encoding="utf-8")
    sign(track, document)
    done = run_build(track, tmp_path)
    assert "FAIL intake_unchanged (intake.md changed after sign-off:" in done.stdout


# --- the diagnosis -> Detail route: a stand-alone -detail.md ------------------

def detail_doc(ac_line=None):
    text = "# t — detail\n\n## Reference\n\nThe diagnosis of this track.\n"
    return text + ("\n" + ac_line + "\n" if ac_line else "") + "\n## Requirement\n\nUC1.\n"


def test_a_new_track_detail_row_with_a_matching_ac_line_passes(tmp_path):
    track = make_track(tmp_path, "x-detail.md")
    document = tmp_path / "x-detail.md"
    document.write_text(detail_doc("AC: intake.md sha256 %s" % sha(track / "intake.md")),
                        encoding="utf-8")
    sign(track, document)
    checks = preflight.intake_unchanged(str(track), str(tmp_path))
    assert checks and checks[0][0] is True and "matches" in checks[0][1], checks


def test_a_new_track_detail_row_without_an_ac_line_fails(tmp_path):
    track = make_track(tmp_path, "x-detail.md")
    document = tmp_path / "x-detail.md"
    document.write_text(detail_doc(), encoding="utf-8")
    sign(track, document)
    checks = preflight.intake_unchanged(str(track), str(tmp_path))
    assert checks and checks[0][0] is False and "no `AC:" in checks[0][1], checks


def test_a_new_track_detail_row_whose_intake_changed_fails(tmp_path):
    track = make_track(tmp_path, "x-detail.md")
    document = tmp_path / "x-detail.md"
    document.write_text(detail_doc("AC: intake.md sha256 %s" % sha(track / "intake.md")),
                        encoding="utf-8")
    sign(track, document)
    with open(track / "intake.md", "a", encoding="utf-8") as fh:
        fh.write("\nAC2: late.\n")
    checks = preflight.intake_unchanged(str(track), str(tmp_path))
    assert checks and checks[0][0] is False and "changed after sign-off" in checks[0][1], checks


def test_an_old_six_row_track_with_a_detail_row_and_no_line_still_passes(tmp_path):
    rows = [("intake", "done", "intake.md", ""), ("discover", "skipped", "", ""),
            ("design", "done", "x-detail.md", ""), ("build", "", "", ""),
            ("verify", "", "", ""), ("ship", "", "", "")]
    track = make_track(tmp_path, "x-detail.md", rows)
    document = tmp_path / "x-detail.md"
    document.write_text(detail_doc(), encoding="utf-8")
    sign(track, document)
    checks = preflight.intake_unchanged(str(track), str(tmp_path))
    assert checks and checks[0][0] is True and "not checked" in checks[0][1], checks


# --- UC3: an old six-row track into build ------------------------------------

def test_an_old_six_row_track_signed_without_an_ac_line_still_builds(tmp_path):
    rows = [("intake", "skipped", "", ""), ("discover", "skipped", "", ""),
            ("design", "done", "x-diagnosis.md", ""), ("build", "", "", ""),
            ("verify", "", "", ""), ("ship", "", "", "")]
    track = make_track(tmp_path, "x-diagnosis.md", rows)
    os.remove(track / "intake.md")  # a skipped intake owes none
    document = tmp_path / "x-diagnosis.md"
    document.write_text(diagnosis_doc(), encoding="utf-8")
    sign(track, document)
    done = run_build(track, tmp_path)
    assert done.returncode == 0, done.stdout
    line = next(ln for ln in done.stdout.splitlines() if "intake_unchanged" in ln)
    assert line.startswith("PASS") and "before the upgrade" in line


def test_an_old_track_that_does_carry_an_ac_line_is_still_compared(tmp_path):
    rows = [("intake", "done", "intake.md", ""), ("discover", "skipped", "", ""),
            ("design", "done", "x-diagnosis.md", ""), ("build", "", "", ""),
            ("verify", "", "", ""), ("ship", "", "", "")]
    track = make_track(tmp_path, "x-diagnosis.md", rows)
    document = tmp_path / "x-diagnosis.md"
    document.write_text(diagnosis_doc("AC: intake.md sha256 %s" % ("0" * 64)),
                        encoding="utf-8")
    sign(track, document)
    assert "FAIL intake_unchanged" in run_build(track, tmp_path).stdout
