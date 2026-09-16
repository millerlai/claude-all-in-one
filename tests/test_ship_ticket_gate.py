"""Unit 5: the pieces of AC17/AC18/AC20 that are this unit's own job --
closing the ticket joins the existing ship gate instead of adding a third,
and the confirmation for it can only ever originate from the main session.

AC16 lives in test_ticket_transition.py; AC19 was Unit 4's. What is left
here is text-level: `stage-ship.md`'s irreversible-operations list and "two
gates" claim, `SKILL.md`'s own "## Human gates" section still listing those
two and gaining no ticket-closing step, `agents/shipper.md` carrying no
interactive tool and handing the confirmation up rather than taking it,
`ticket-mirror.md`'s ship section naming the commit message and PR body, and
that same section -- with approval-gates.md's Gate 2 -- actually running
`ticket.py transition --confirmed-by-user`, the one place that flag is passed.
"""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO_ROOT, "plugins", "cai")
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


# --- stage-ship.md: closing the ticket joins the list, count stays two -----

def test_stage_ship_lists_closing_the_ticket_among_the_irreversible_ops():
    text = _flat(STAGE_SHIP)
    assert "merging" in text
    assert "tagging" in text
    assert "publishing" in text
    assert "closing" in text and "ticket" in text


def test_stage_ship_still_says_two_human_gates_not_three():
    text = _flat(STAGE_SHIP)
    assert "two human gates" in text
    assert "rather than adding a third" in text


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


# --- AC16's other half: the close is actually reachable from the ship ------
# --- confirmation, and from nowhere else ------------------------------------
#
# test_ticket_transition.py proves `ticket.py transition` refuses without the
# flag and calls the backend once with it. Nothing proved any shipped prose
# ever ran it: stage-ship.md listed "closing the linked ticket" and pointed at
# ticket-mirror.md, whose ship section named only `ticket.py project` -- so the
# close existed as a script no stage could reach, from #49 until this test.

def test_ticket_mirror_ship_section_runs_transition_with_the_flag():
    section = " ".join(_section(_text(TICKET_MIRROR), "## ship").split())
    assert "ticket.py transition" in section
    assert "--confirmed-by-user" in section


def test_approval_gates_gate_2_names_closing_the_ticket():
    section = " ".join(_section(_text(APPROVAL_GATES), "## Gate 2").split())
    assert "ticket.py transition" in section


def test_confirmed_by_user_is_passed_from_the_ship_confirmation_alone():
    # DD8: exactly one place an irreversible ticket close can originate from.
    # The flag may be named where that confirmation lives and in the script
    # that reads it -- no stage reference, agent or skill may pass it too.
    allowed = {TICKET_MIRROR, APPROVAL_GATES,
               os.path.join(PLUGIN, "scripts", "ticket.py")}
    carriers = set()
    for root, _dirs, files in os.walk(PLUGIN):
        for name in files:
            if not name.endswith((".md", ".py", ".json")):
                continue
            path = os.path.join(root, name)
            if "--confirmed-by-user" in _text(path):
                carriers.add(path)
    assert carriers <= allowed, sorted(carriers - allowed)
    assert TICKET_MIRROR in carriers


def test_shipper_md_never_closes_the_ticket_itself():
    assert "transition" not in _text(SHIPPER_MD)
