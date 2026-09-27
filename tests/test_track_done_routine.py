"""#203: `/cai:track done` ends with one line naming the post-merge routine
(switch to the base branch, `git pull`, `/cai:git-sweep`) that a person has
typed by hand at the end of nearly every track. Nothing here runs that
routine -- it only checks that SKILL.md's `## /cai:track done` section says
it, once, after the move, and never as part of the ticket/close vocabulary
those other sections already own (tests/test_ticket_done.py,
tests/test_ship_ticket_gate.py)."""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_MD = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "SKILL.md")

HEADING = "## `/cai:track done`"


def _text():
    with open(SKILL_MD, encoding="utf-8") as fh:
        return fh.read()


def _section(text, heading):
    start = text.index(heading)
    rest = text[start + len(heading):]
    m = re.search(r"\n## ", rest)
    end = start + len(heading) + (m.start() if m else len(rest))
    return text[start:end]


def _done_section():
    return _section(_text(), HEADING)


def test_done_section_names_the_post_merge_routine():
    section = _done_section()
    assert "/cai:git-sweep" in section
    assert "git pull" in section
    assert "base branch" in section


def test_routine_is_not_run_by_the_session():
    section = _done_section()
    lines = [ln for ln in section.splitlines() if "/cai:git-sweep" in ln]
    assert len(lines) == 1
    assert "yourself" in lines[0]


def test_routine_line_comes_after_the_move():
    section = _done_section()
    move_at = section.index("Then move `.claude/track/<feature>/`")
    routine_at = section.index("/cai:git-sweep")
    assert routine_at > move_at


def test_routine_line_names_neither_ticket_nor_close():
    section = _done_section()
    lines = [ln for ln in section.splitlines() if "/cai:git-sweep" in ln]
    line = lines[0]
    assert "ticket" not in line.lower()
    assert "clos" not in line.lower()
