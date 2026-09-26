"""track-issue-status-sync Unit 1: `/cai:track done`'s close menu, the one
place `ticket.py transition --confirmed-by-user` can now originate from.

Before this unit the close lived in ship's own confirmation
(`tests/test_ship_ticket_gate.py:159-185`, HEAD). This file carries what
moved: the done section's text in `ticket-mirror.md`, the carrier scan that
used to prove the ship confirmation was the sole origin (now the done
section instead), and `SKILL.md:130`'s widened hook line.

`--final` itself is Unit 5's job (`render_comment`/`project`'s `final`
argument) -- this file only proves the done section *names* `--final`, per
the brief: unit 1 does not implement it.
"""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO_ROOT, "plugins", "cai")
TICKET_MIRROR = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "references", "ticket-mirror.md")
APPROVAL_GATES = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "references", "approval-gates.md")
SKILL_MD = os.path.join(REPO_ROOT, "plugins", "cai", "skills", "track", "SKILL.md")
TICKET_PY = os.path.join(REPO_ROOT, "plugins", "cai", "scripts", "ticket.py")

HEADING = "## /cai:track done: the final state, then the close"


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


def _done_section():
    return " ".join(_section(_text(TICKET_MIRROR), HEADING).split())


# --- the section exists, and SKILL.md's hook line names it -----------------

def test_ticket_mirror_has_the_done_section():
    assert HEADING in _text(TICKET_MIRROR)


def test_skill_md_hook_line_names_ticket_mirror_and_never_says_clos():
    lines = [ln for ln in _text(SKILL_MD).splitlines()
             if "ticket-mirror.md" in ln and "left-open" in ln]
    assert len(lines) == 1
    line = lines[0]
    assert "ticket-mirror.md" in line
    assert "clos" not in line.lower()


# --- the final projection, named but not built here -------------------------

def test_done_section_names_final_projection():
    section = _done_section()
    assert "--final" in section
    assert "ticket.py project" in section


# --- the close menu itself: resolving the number, the two options, no ------
# --- recommendation, and only the first runs transition ---------------------

def test_done_section_resolves_the_number_via_read_track_dir_done():
    section = _done_section()
    assert "ticket.py read --track-dir" in section
    assert ".claude/track/done/<feature>" in section


def test_done_section_close_menu_has_no_recommendation():
    section = _done_section()
    assert "Close #<number>" in section
    assert "Leave it open" in section
    assert "no `(recommended)`" in section


def test_done_section_runs_transition_only_on_close():
    section = _done_section()
    assert "ticket.py transition" in section
    assert "--confirmed-by-user" in section
    assert "On anything else, run nothing" in section


# --- DD8's guarantee moved: the flag's carriers are exactly these three, ---
# --- and only inside ticket-mirror.md's done section ------------------------

def test_confirmed_by_user_is_passed_from_the_done_close_menu_alone():
    allowed = {TICKET_MIRROR, APPROVAL_GATES, TICKET_PY}
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


def test_confirmed_by_user_in_ticket_mirror_only_under_the_done_heading():
    text = _text(TICKET_MIRROR)
    assert "--confirmed-by-user" not in _section(text, "## ship")
    assert "--confirmed-by-user" in _section(text, HEADING)


def test_approval_gates_names_the_close_menu_as_a_stop():
    text = _flat(APPROVAL_GATES)
    assert "close menu at `/cai:track done`" in text
    assert "Close #<number>" in text
    assert "Leave it open" in text
