"""#253: `/cai:track cancel --reason "<why>"` ends a track that will not
finish. `/cai:track done` refuses while any row is empty or `in-progress`,
which left a track that was abandoned for outside reasons with no way out
short of moving directories by hand. The subcommand is prose the main session
follows -- there is no script behind it, as there is none behind `done` -- so
these tests pin what SKILL.md tells it to do (tests/test_track_done_routine.py
is the same kind of test for `done`)."""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_MD = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "SKILL.md")

HEADING = "## `/cai:track cancel"


def _text():
    with open(SKILL_MD, encoding="utf-8") as fh:
        return fh.read()


def _section():
    text = _text()
    start = text.index(HEADING)
    rest = text[start + len(HEADING):]
    m = re.search(r"\n## ", rest)
    return text[start:start + len(HEADING) + (m.start() if m else len(rest))]


def _flat(text):
    return " ".join(text.split())


def test_usage_block_and_argument_hint_list_cancel():
    text = _text()
    hint = next(l for l in text.splitlines() if l.startswith("argument-hint:"))
    assert 'cancel --reason' in hint
    usage = text[text.index("```"):text.index("```", text.index("```") + 3)]
    assert '/cai:track cancel --reason "<why>"' in usage


def test_reason_is_required():
    section = _flat(_section())
    assert "`--reason` is required" in section
    assert "refuse" in section


def test_records_the_reason_before_archiving():
    section = _flat(_section())
    assert "`.claude/track/<feature>/cancelled.md`" in section
    record_at = section.index("cancelled.md")
    move_at = section.index("move")
    assert record_at < move_at


def test_archives_into_done_and_clears_current_whatever_the_rows_say():
    section = _flat(_section())
    assert "`done/`" in section
    assert "`current`" in section
    assert "whatever the rows say" in section


def test_does_not_project_or_close_a_mirrored_ticket():
    # `done`'s ticket steps write `status: done` and offer to close the
    # ticket; neither is true of a track that was abandoned.
    section = _flat(_section())
    assert "--final" not in section
    assert "transition" not in section
    assert "ticket" in section and "stay as they are" in section
