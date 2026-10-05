"""Unit 4: `plugins/cai/skills/track/references/ticket-mirror.md`.

This file is read by the main session, not dispatched to a subagent, and it
has to be reachable through `ticket-mirror.md`'s own text rather than only
through prose elsewhere -- so these tests read the file's content directly,
the same way `scripts/validate.py`'s always-on budget and BOM checks do.
The one line `SKILL.md` gains to point at this file, and the ceiling around
it, are `test_track_skill_ticket_pointer.py`'s job, not this file's.
"""
import os

REFERENCE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..",
    "plugins", "cai", "skills", "track", "references", "ticket-mirror.md")


def _text():
    with open(REFERENCE, encoding="utf-8") as fh:
        return fh.read()


def _flat():
    # Markdown soft-wraps a sentence across lines for width, same as every
    # other reference file -- collapsing that back to single spaces is what
    # lets a phrase-level assertion below match regardless of where the
    # editor happened to break the line.
    return " ".join(_text().split())


def test_file_exists():
    assert os.path.isfile(REFERENCE)


def test_no_utf8_bom():
    with open(REFERENCE, "rb") as fh:
        head = fh.read(3)
    assert head != b"\xef\xbb\xbf"


def test_no_frontmatter():
    # references/ files cost 0 chars of the always-on budget only when they
    # carry no `description:` frontmatter for scripts/validate.py's
    # frontmatter_description() to pick up (scripts/validate.py:216-221).
    assert not _text().startswith("---")


# --- AC19: the ticket body reaches the verify stage's conformance lens, --
# --- but only when the integration is on and reachable -------------------

def test_states_ticket_body_becomes_written_requirement_for_conformance_lens():
    text = _flat()
    assert "conformance" in text
    assert "written requirement" in text
    assert "body" in text


def test_states_fallback_to_existing_stage_verify_behaviour():
    text = _flat()
    assert "stage-verify.md:47-50" in text
    assert "no written requirement" in text
    assert "review the other three lenses" in text


# --- the rest of the design's stage-by-stage list --------------------------

def test_states_intake_reads_ticket_once():
    text = _flat()
    assert "intake" in text
    assert "ticket.py read" in text


def test_states_verify_reads_once_when_intake_was_skipped():
    text = _flat()
    assert "intake was skipped" in text


def test_states_project_after_every_state_md_write_including_skip():
    text = _flat()
    assert "ticket.py project" in text
    assert "/cai:track skip" in text


def test_states_ship_resolves_number_before_quoting():
    text = _flat()
    assert "resolve" in text
    # the ship section specifically -- ticket.py read already appears
    # earlier, in the intake section, so the phrase anchors this to ship,
    # not to intake, and to a resolution that actually calls a backend.
    assert "resolve it with `ticket.py read" in text
    assert "resolve it with `ticket.py show" not in text


def test_ship_row_is_projected_without_a_question_of_its_own():
    # R2: ship's ticket comment is no longer a separate confirmation; its row
    # is written like every other stage's.
    text = _flat()
    assert "one more confirmation item" not in text
    assert "asked on its own turn" not in text
    assert "ship's own row is projected like every other stage's" in text
    assert "no question of its own" in text


def test_the_manual_does_not_promise_a_ship_ticket_question():
    # R2: the manual describes the same behaviour as the reference file.
    with open(os.path.join(os.path.dirname(REFERENCE), "..", "..", "..", "..", "..",
                           "MANUAL.md"), encoding="utf-8") as fh:
        manual = " ".join(fh.read().split())
    assert "asks on its own turn whether to update the comment" not in manual
    assert "the comment one last time" in manual  # `done` still rewrites it


def test_states_stderr_must_never_go_into_note():
    text = _flat()
    assert "--note" in text
    assert "stderr" in text


# --- Starting a track from a ticket ----------------------------------------
#
# `SKILL.md` is at its line ceiling, so the procedure lives here and SKILL.md
# carries one pointer to it. These tests pin both halves of that split: the
# section has to exist here, and it has to say the things the split moved out
# of SKILL.md.


def test_has_a_starting_from_a_ticket_section():
    assert "## Starting from a ticket" in _text()


def test_states_the_ref_is_not_a_directory_name():
    text = _flat()
    assert "://" in text
    assert "not a directory name" in text


def test_names_read_with_ref_and_no_track_dir():
    """The capability this procedure rests on: seeing a ticket without first
    committing a track to it."""
    text = _flat()
    assert "read --ref" in text
    assert "no `--track-dir`" in text


def test_asks_before_naming_the_directory():
    text = _flat()
    assert "AskUserQuestion" in text


def test_warns_that_pointing_late_is_silent():
    """The failure that has no error message: a track pointed after intake
    ran is indistinguishable from one that never had a ticket."""
    text = _flat()
    assert "before the" in text and "first stage runs" in text
    assert "quietly unlinked" in text


# --- Unit 6: the claim menu, the naming-collision rule, the claim -----------
# --- projection before intake's dispatch ------------------------------------


def test_states_claims_line_and_claim_menu():
    text = _flat()
    assert "claims: <n>" in text
    assert "[cai track: <name>]" in text
    assert "A claim is a notice, not a lock" in text
    assert "Continue — name a new track" in text
    assert "with Stop recommended" in text


def test_states_resume_offer_and_naming_of_further_claims():
    text = _flat()
    assert "local: resumable" in text
    assert 'offer "Resume <name>" for each of the first two such lines' in text
    assert "the first of them recommended in place of Stop" in text
    assert "name any further one in the message for `/cai:track <name>`" in text
    assert "local: finished" in text


def test_states_resume_writes_current_and_carries_on():
    text = _flat()
    assert "Resume writes `<name>` alone into `.claude/track/current`" in text
    assert "carries on exactly as `/cai:track <name>` does" in text


def test_states_claim_check_failure_category():
    text = _flat()
    assert "read: <category>" in text
    assert 'never as "no claims"' in text


def test_states_naming_collision_rule():
    text = _flat()
    assert "Never a name a listed claim carries" in text
    assert "add `-2`, then `-3`" in text
    assert "edit that claim's comment in place" in text


def test_states_free_text_refusal_rule():
    text = _flat()
    assert "exactly matches a listed claim's name is refused" in text
    assert "say which claim carries it, and ask again" in text


def test_states_claim_projection_before_intake_dispatch():
    text = _flat()
    assert "Right after that read, run `ticket.py project" in text
    assert "unless the read said this track has no ticket pointer" in text
    assert "status: in-progress` over six still-empty rows" in text
    assert "A failed projection prints one line; dispatch intake anyway" in text
