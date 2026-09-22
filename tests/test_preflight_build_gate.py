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

DECISIONS_EMPTY_TIER1 = HLD + "\n## Tier 1\n\n"
DECISIONS_ONE_TIER1 = HLD + "\n## Tier 1\n\n### D1 -- pick one\n\nsome body\n"
DECISIONS_DIRTY_TITLE = HLD + "\n## Tier 1\n\n### ：這一輪要不要\n\nsome body\n"

# Two distinct entries whose first token sanitises to the same id: a colon
# right after the id survives nowhere -- `_tier1_id` strips it -- so a
# copy-paste slip that leaves the punctuation differing is enough to collide.
DECISIONS_COLLIDING_TIER1 = HLD + (
    "\n## Tier 1\n\n### D1 -- should we cache the result?\n\nsome body\n\n"
    "### D1: should we invalidate on write?\n\nsome other body\n"
)

VALID_DRAFT = """- **Dimension one**: what matters
- **Dimension two**: what matters more

Option A (recommended)
1. It is a thing.
2. Like a small analogy for a thing.
3. Nothing observable changes yet.
4. Costs a little time.
5. Reversibility is high.
6. Fits when nothing else does.

Option B
1. It is another thing.
2. Like a different analogy.
3. Something else changes.
4. Costs more time.
5. Reversibility is medium.
6. Fits when the first one does not.

Pick Option A if you would rather not weigh it, because it costs the least and is easy to undo.
"""

# Option B's field 5 is dropped -- its items run 1,2,3,4,6, which six_fields
# rejects.
DRAFT_MISSING_A_FIELD = """- **Dimension one**: what matters
- **Dimension two**: what matters more

Option A (recommended)
1. It is a thing.
2. Like a small analogy for a thing.
3. Nothing observable changes yet.
4. Costs a little time.
5. Reversibility is high.
6. Fits when nothing else does.

Option B
1. It is another thing.
2. Like a different analogy.
3. Something else changes.
4. Costs more time.
6. Fits when the first one does not.

Pick Option A if you would rather not weigh it, because it costs the least and is easy to undo.
"""


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
    track = make_track(tmp_path, "d-high-level.md")
    ledger.append(track, "design", "passed", gate="human")
    done = run(track, str(tmp_path))

    assert done.returncode == 0, done.stdout
    assert "PASS work_breakdown" in done.stdout
    assert "cuts the units instead" in done.stdout


def test_a_delta_design_with_no_work_breakdown_can_be_built(tmp_path):
    write_doc(tmp_path, "d-delta.md", HLD)
    track = make_track(tmp_path, "d-delta.md")
    ledger.append(track, "design", "passed", gate="human")
    done = run(track, str(tmp_path))

    assert done.returncode == 0, done.stdout
    assert "PASS work_breakdown" in done.stdout


# --- detail is the one kind that promises a schedule ----------------------

def test_a_detail_design_still_has_to_carry_one(tmp_path):
    write_doc(tmp_path, "d-detail.md", HLD)
    track = make_track(tmp_path, "d-detail.md")
    ledger.append(track, "design", "passed", gate="human")
    done = run(track, str(tmp_path))

    assert done.returncode == 2
    assert "FAIL work_breakdown" in done.stdout
    assert "is a detail design" in done.stdout


def test_a_detail_design_that_carries_one_passes(tmp_path):
    write_doc(tmp_path, "d-detail.md", DETAIL)
    track = make_track(tmp_path, "d-detail.md")
    ledger.append(track, "design", "passed", gate="human")
    done = run(track, str(tmp_path))

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


# --- design_signed_off: build refuses to start without a human's Approve ---

def test_no_design_record_at_all_blocks_build(tmp_path):
    write_doc(tmp_path, "d-high-level.md", HLD)
    done = run(make_track(tmp_path, "d-high-level.md"), str(tmp_path))

    assert done.returncode == 2
    assert "FAIL design_signed_off" in done.stdout


def test_a_passed_auto_record_does_not_count_as_sign_off(tmp_path):
    doc = write_doc(tmp_path, "d-high-level.md", HLD)
    track = make_track(tmp_path, "d-high-level.md")
    ledger.append(track, "design", "passed", artifact=doc, gate="auto")

    done = run(track, str(tmp_path))

    assert done.returncode == 2
    assert "FAIL design_signed_off" in done.stdout


def test_a_failed_human_record_does_not_count_as_sign_off(tmp_path):
    doc = write_doc(tmp_path, "d-high-level.md", HLD)
    track = make_track(tmp_path, "d-high-level.md")
    ledger.append(track, "design", "failed", artifact=doc, gate="human")

    done = run(track, str(tmp_path))

    assert done.returncode == 2
    assert "FAIL design_signed_off" in done.stdout


def test_an_approval_inside_design_does_not_sign_off_what_design_finished(tmp_path):
    """Issue #112, the ledger a live run left: the stance approval -- a stop
    inside `design`, not Gate 1 -- was recorded as passed+human, the finished
    design then passed as auto, and Gate 1 never ran. Any human record
    anywhere used to be enough, so build started on a design nobody signed."""
    stance = write_doc(tmp_path, "d-stance.md", HLD)
    detail = write_doc(tmp_path, "d-detail.md", DETAIL)
    track = make_track(tmp_path, "d-detail.md")
    ledger.append(track, "design", "passed", artifact=stance, gate="human")
    ledger.append(track, "design", "passed", artifact=detail, gate="auto")

    done = run(track, str(tmp_path))

    assert done.returncode == 2
    assert "FAIL design_signed_off" in done.stdout


def test_gate_1_after_the_stage_own_auto_record_signs_off(tmp_path):
    """The order every real run writes: the stage records its own pass as
    auto, and Gate 1's Approve lands after it."""
    doc = write_doc(tmp_path, "d-detail.md", DETAIL)
    track = make_track(tmp_path, "d-detail.md")
    ledger.append(track, "design", "passed", artifact=doc, gate="auto")
    ledger.append(track, "design", "passed", artifact=doc, gate="human")

    done = run(track, str(tmp_path))

    assert done.returncode == 0, done.stdout
    assert "PASS design_signed_off" in done.stdout


def test_a_failed_rerun_after_approval_does_not_erase_it(tmp_path):
    """A failed record is not a pass, so it does not replace the approval as
    the design build reads."""
    doc = write_doc(tmp_path, "d-detail.md", DETAIL)
    track = make_track(tmp_path, "d-detail.md")
    ledger.append(track, "design", "passed", artifact=doc, gate="human")
    ledger.append(track, "design", "failed", artifact=doc, gate="auto")

    done = run(track, str(tmp_path))

    assert done.returncode == 0, done.stdout
    assert "PASS design_signed_off" in done.stdout


# --- options_drafts: a decisions document's Tier 1 owes a draft per entry --

def test_v5_a_non_decisions_artifact_is_not_checked(tmp_path):
    write_doc(tmp_path, "d-high-level.md", HLD)
    track = make_track(tmp_path, "d-high-level.md")
    ledger.append(track, "design", "passed", gate="human")
    done = run(track, str(tmp_path))

    assert done.returncode == 0, done.stdout
    assert "PASS options_drafts (artifact is not a decisions document)" in done.stdout


def test_v5_an_empty_tier_1_is_not_checked(tmp_path):
    write_doc(tmp_path, "d-decisions.md", DECISIONS_EMPTY_TIER1)
    track = make_track(tmp_path, "d-decisions.md")
    ledger.append(track, "design", "passed", gate="human")
    done = run(track, str(tmp_path))

    assert done.returncode == 0, done.stdout
    assert "PASS options_drafts (## Tier 1 is empty -- nothing was owed)" in done.stdout


def test_v2_a_tier_1_entry_with_no_draft_on_disk_fails_and_names_it(tmp_path):
    write_doc(tmp_path, "d-decisions.md", DECISIONS_ONE_TIER1)
    track = make_track(tmp_path, "d-decisions.md")
    ledger.append(track, "design", "passed", gate="human")
    done = run(track, str(tmp_path))

    assert done.returncode == 2
    assert "FAIL options_drafts (missing options-D1.md" in done.stdout


def test_v3_a_complete_six_field_draft_passes(tmp_path):
    write_doc(tmp_path, "d-decisions.md", DECISIONS_ONE_TIER1)
    track = make_track(tmp_path, "d-decisions.md")
    (tmp_path / "track" / "options-D1.md").write_text(VALID_DRAFT, encoding="utf-8")
    ledger.append(track, "design", "passed", gate="human")
    done = run(track, str(tmp_path))

    assert done.returncode == 0, done.stdout
    assert "PASS options_drafts (1 draft(s) checked)" in done.stdout


def test_v4_a_draft_missing_a_field_fails_and_names_the_probe(tmp_path):
    write_doc(tmp_path, "d-decisions.md", DECISIONS_ONE_TIER1)
    track = make_track(tmp_path, "d-decisions.md")
    (tmp_path / "track" / "options-D1.md").write_text(DRAFT_MISSING_A_FIELD, encoding="utf-8")
    ledger.append(track, "design", "passed", gate="human")
    done = run(track, str(tmp_path))

    assert done.returncode == 2
    assert "FAIL options[D1] six_fields" in done.stdout


def test_v5b_a_dirty_tier_1_title_sanitises_to_a_buildable_path(tmp_path):
    write_doc(tmp_path, "d-decisions.md", DECISIONS_DIRTY_TITLE)
    track = make_track(tmp_path, "d-decisions.md")
    ledger.append(track, "design", "passed", gate="human")
    done = run(track, str(tmp_path))

    assert done.returncode == 2
    assert "FAIL options_drafts (missing options-1.md" in done.stdout


def test_two_tier1_entries_colliding_to_the_same_id_fail_instead_of_double_counting(tmp_path):
    """Two distinct decisions must not be satisfiable by one shared draft file.
    `Requirement gaps` #1 in the decisions doc: N Tier 1 entries need N drafts
    on disk, missing any one is FAIL -- a collision silently turns that into
    "N entries need 1 draft", which is not what was asked."""
    write_doc(tmp_path, "d-decisions.md", DECISIONS_COLLIDING_TIER1)
    track = make_track(tmp_path, "d-decisions.md")
    (tmp_path / "track" / "options-D1.md").write_text(VALID_DRAFT, encoding="utf-8")
    ledger.append(track, "design", "passed", gate="human")
    done = run(track, str(tmp_path))

    assert done.returncode == 2
    assert "FAIL options_drafts" in done.stdout
    assert "options-D1.md" in done.stdout
    assert "2 draft(s) checked" not in done.stdout


def test_a_passed_human_record_signs_off_the_design(tmp_path):
    doc = write_doc(tmp_path, "d-high-level.md", HLD)
    track = make_track(tmp_path, "d-high-level.md")
    ledger.append(track, "design", "passed", artifact=doc, gate="human")

    done = run(track, str(tmp_path))

    assert done.returncode == 0, done.stdout
    assert "PASS design_signed_off" in done.stdout
