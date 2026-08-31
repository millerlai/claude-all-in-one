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
    assert "review the other two lenses" in text


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


def test_states_ship_confirmation_gains_a_separate_item():
    text = _flat()
    assert "separately" in text or "separate" in text


def test_states_stderr_must_never_go_into_note():
    text = _flat()
    assert "--note" in text
    assert "stderr" in text
