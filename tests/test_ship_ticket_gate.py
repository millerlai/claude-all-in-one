"""Unit 5's original AC17/AC18/AC20 text-level checks, updated for
track-issue-status-sync Unit 1: closing the ticket no longer joins the ship
gate at all -- it moved to `/cai:track done`'s close menu
(`tests/test_ticket_done.py`), so ship's own text and Gate 2 now carry no
close.

AC16 lives in test_ticket_transition.py; AC19 was Unit 4's. What is left
here is text-level: `stage-ship.md`'s irreversible-operations list no longer
names closing the ticket, still says "two human gates", `SKILL.md`'s own
"## Human gates" section still listing those two and gaining no
ticket-closing step, `agents/shipper.md` carrying no interactive tool and
handing the confirmation up rather than taking it (and never closing the
ticket itself), and `ticket-mirror.md`'s ship section naming the commit
message and PR body while no longer running `ticket.py transition` at all.
"""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE_SHIP = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "references", "stage-ship.md")
APPROVAL_GATES = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "references", "approval-gates.md")
SKILL_MD = os.path.join(REPO_ROOT, "plugins", "cai", "skills", "track", "SKILL.md")
SHIPPER_MD = os.path.join(REPO_ROOT, "plugins", "cai", "agents", "shipper.md")
TICKET_MIRROR = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "references", "ticket-mirror.md")


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _flat(path):
    return " ".join(_text(path).split())


def _section(text, heading):
    start = text.index(heading)
    rest = text[start + len(heading):]
    m = re.search(r"\n## ", rest)
    end = start + len(heading) + (m.start() if m else len(rest))
    return text[start:end]


# --- stage-ship.md: closing the ticket does not join the list -------------

def test_stage_ship_does_not_list_closing_the_ticket_among_the_irreversible_ops():
    text = _flat(STAGE_SHIP)
    assert "merging" in text
    assert "tagging" in text
    assert "publishing" in text
    assert "and closing the linked ticket" not in text
    assert "closing the ticket is not one of this stage's operations" in text.lower()
    assert "/cai:track done" in text


def test_stage_ship_still_says_two_human_gates():
    text = _flat(STAGE_SHIP)
    assert "two human gates" in text


# --- SKILL.md: the AC17 guard for this unit specifically, on top of -------
# --- unit 4's own version of the test -------------------------------------

def test_skill_md_human_gates_section_still_lists_those_two_and_no_ticket_step():
    # Was "byte-identical to HEAD". That is the same stale form the test
    # below already migrated away from, for the reason written out there: it
    # says nothing once the change is committed, and before that it fails on
    # any unrelated edit a later feature legitimately makes to this routing
    # file -- which is what #74 did, adding how the two gates are voiced.
    #
    # AC17 is not "nobody ever touches this section"; it is that closing the
    # ticket did not become a gate in it. So assert the list: exactly the two
    # gates, and no ticket step among them.
    section = _section(_text(SKILL_MD), "## Human gates")
    assert "Exactly two stages stop for a person, never more" in section
    assert "After `design`" in section
    assert "Before the irreversible operations in `ship`" in section
    assert "ticket" not in section.lower()


def test_skill_md_gained_no_ticket_closing_step_of_its_own():
    # Was "the whole file is byte-identical to HEAD". That form is the one
    # test_track_skill_ticket_pointer.py already records as stopping to mean
    # anything once the change is committed, and on an uncommitted branch it
    # fails on any later unrelated edit to a routing file that other features
    # legitimately add a pointer line to. AC17 is not "nobody ever touches
    # SKILL.md"; it is that closing the ticket did not become a step here.
    # The section test above holds the gate count, this holds the absence.
    #
    # 2026-09-16: a second line now names the reference -- the one routing a
    # ticket-shaped `/cai:track` argument -- so the count stopped being a
    # usable proxy, exactly as the paragraph above anticipated. What AC17
    # asserts is the *absence* of a closing step, so assert that directly
    # rather than through a number that any legitimate pointer line breaks.
    ticket_lines = [ln for ln in _text(SKILL_MD).splitlines() if "ticket" in ln.lower()]
    assert ticket_lines, "SKILL.md should still point at the ticket reference"
    assert all("ticket-mirror.md" in ln for ln in ticket_lines)
    assert not any("clos" in ln.lower() for ln in ticket_lines)


# --- AC18: shipper.md is a zero-line diff, and never gains an interactive --
# --- tool -- the confirmation must stay the main session's alone -----------

def test_shipper_md_hands_the_confirmation_up_instead_of_taking_it():
    # Was "byte-identical to HEAD", the same stale form as above. AC18's
    # content is that the confirmation authority never moves into the
    # subagent -- which a zero-line diff only ever guarded by accident. The
    # tools-line test below holds the negative half (no interactive tool);
    # this holds the positive one, added 2026-09-03 once it became clear the
    # platform strips AskUserQuestion from subagents whatever `tools:` says,
    # so "wait for confirmation" was an instruction shipper could not follow.
    text = _flat(SHIPPER_MD)
    assert "pending-questions.md" in text
    assert "cannot ask" in text
    assert "the gate does not move, only who voices it" in text


def test_shipper_md_tools_line_has_no_interactive_tool():
    text = _text(SHIPPER_MD)
    m = re.search(r"^tools:\s*(.*)$", text, re.MULTILINE)
    assert m is not None
    tools_line = m.group(1)
    # AskUserQuestion (or any bare "Ask"/interactive prompt tool) would let a
    # subagent take the confirmation itself -- the design requires that
    # authority stay with the main session alone.
    assert "Ask" not in tools_line
    assert "Interactive" not in tools_line


# --- AC20: the ship section names both the commit message and the PR body -

def test_ticket_mirror_ship_section_says_the_number_must_be_resolvable():
    # Scoped to the ship section itself, not the whole file -- ticket.py
    # read already appears earlier, in the intake section, so a whole-file
    # substring check would pass even if ship still named show.
    section = " ".join(_section(_text(TICKET_MIRROR), "## ship").split())
    assert "resolve" in section
    assert "ticket.py read" in section
    assert "ticket.py show" not in section


def test_ticket_mirror_ship_section_names_commit_message_and_pr_body_once_each():
    text = _flat(TICKET_MIRROR)
    assert "commit message" in text
    assert "PR body" in text
    assert "once" in text


# --- AC16's other half moved: the close is no longer reachable from ship ---
# --- at all -- see tests/test_ticket_done.py for where it is reachable now -

def test_ticket_mirror_ship_section_does_not_run_transition():
    section = " ".join(_section(_text(TICKET_MIRROR), "## ship").split())
    assert "ticket.py transition" not in section
    assert "--confirmed-by-user" not in section


def test_approval_gates_gate_2_does_not_name_closing_the_ticket():
    section = " ".join(_section(_text(APPROVAL_GATES), "## Gate 2").split())
    assert "ticket.py transition" not in section
    assert "closing the ticket" not in section.lower()


def test_shipper_md_never_closes_the_ticket_itself():
    assert "transition" not in _text(SHIPPER_MD)


# --- #195: a closing keyword is never allowed in the commit message or PR --
# --- body -- only `Refs #N`, since only /cai:track done's menu closes it ---

def test_ticket_mirror_ship_section_requires_refs_form_and_forbids_closing_keyword():
    section = _section(_text(TICKET_MIRROR), "## ship")
    flat = " ".join(section.split())
    assert "`Refs #" in flat
    assert "closing keyword" in flat


def test_stage_ship_step4_and_step7_name_refs_form():
    text = _text(STAGE_SHIP)
    for heading in ("## Step 4", "## Step 7"):
        section = " ".join(_section(text, heading).split())
        assert "`Refs #" in section, heading
        assert "closing keyword" in section, heading


def test_shipper_md_forbids_closing_keyword():
    flat = _flat(SHIPPER_MD)
    assert "`Refs #" in flat
    assert "closing keyword" in flat
