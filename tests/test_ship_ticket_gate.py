"""Unit 5: the pieces of AC17/AC18/AC20 that are this unit's own job --
closing the ticket joins the existing ship gate instead of adding a third,
and the confirmation for it can only ever originate from the main session.

AC16 lives in test_ticket_transition.py; AC19 was Unit 4's. What is left
here is text-level: `stage-ship.md`'s irreversible-operations list and "two
gates" claim, `SKILL.md`'s own "## Human gates" section staying untouched,
`agents/shipper.md` staying a zero-line diff with no interactive tool, and
`ticket-mirror.md`'s ship section naming the commit message and PR body.
"""
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE_SHIP = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "references", "stage-ship.md")
SKILL_MD = os.path.join(REPO_ROOT, "plugins", "cai", "skills", "track", "SKILL.md")
SHIPPER_MD = os.path.join(REPO_ROOT, "plugins", "cai", "agents", "shipper.md")
TICKET_MIRROR = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "references", "ticket-mirror.md")


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _flat(path):
    return " ".join(_text(path).split())


def _git(*args):
    return subprocess.run(
        ["git"] + list(args), cwd=REPO_ROOT,
        capture_output=True, text=True, encoding="utf-8", check=True).stdout


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


# --- SKILL.md: unit 5 touches nothing here; this is the AC17 guard for -----
# --- this unit specifically, on top of unit 4's own version of the test ----

def test_skill_md_human_gates_section_is_byte_identical_to_head():
    head_text = _git("show", "HEAD:plugins/cai/skills/track/SKILL.md")
    before = _section(head_text, "## Human gates")
    after = _section(_text(SKILL_MD), "## Human gates")
    assert after == before


def test_skill_md_diff_against_head_is_empty():
    # Unit 5's own file list says SKILL.md is not touched at all -- unlike
    # unit 4, which added its one line and is already in HEAD.
    numstat = _git("diff", "--numstat", "HEAD", "--",
                    "plugins/cai/skills/track/SKILL.md")
    assert numstat.strip() == ""


# --- AC18: shipper.md is a zero-line diff, and never gains an interactive --
# --- tool -- the confirmation must stay the main session's alone -----------

def test_shipper_md_diff_against_head_is_empty():
    numstat = _git("diff", "--numstat", "HEAD", "--", "plugins/cai/agents/shipper.md")
    assert numstat.strip() == ""


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
