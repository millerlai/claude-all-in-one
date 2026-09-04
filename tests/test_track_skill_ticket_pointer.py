"""Unit 4 / AC24: the one line `SKILL.md` gains to route ticket mirroring to
the main session (never a dispatched subagent), and the constraints around
it.

Nothing here duplicates `scripts/validate.py`'s own ceiling number or its
line-counting formula -- that duplication (a body line count computed with
`wc -l` in the design docs, `find("\\n---", 3)` + `splitlines()` in
`validate.py` itself, off by one from each other) is exactly what let AC24's
budget go stale until this unit's own `git stash` + a real run of
`validate.py` caught it. These tests instead run the real script and read
its own printed numbers, or read `SKILL.md` directly with the same formula
`validate.py` uses, quoted here only because there is nowhere else to get it
from without importing a script that is not written to be imported (it runs
its checks as a side effect of module load).
"""
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_MD = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "SKILL.md")
VALIDATE = os.path.join(REPO_ROOT, "scripts", "validate.py")


def _skill_body_lines():
    # Same formula as scripts/validate.py's own TRACK_SKILL check -- quoted
    # here, not reimplemented differently, so a future edit to one is the
    # one place both need to be kept honest against a real `validate.py`
    # run below (see test_validate_reports_the_same_body_line_count).
    with open(SKILL_MD, encoding="utf-8") as fh:
        text = fh.read()
    start = text.find("\n---", 3) + 4 if text.startswith("---") else 0
    return len(text[start:].splitlines())


_VALIDATE_RESULT = []


def _run_validate():
    """One real `validate.py` run, shared by every test that reads it.

    It takes tens of seconds, and three tests here need its output; paying
    for it once per test took this suite from 13 seconds to 90. A suite
    that slow is one people stop running under time pressure, and then the
    checkpoints it guards are decoration. The run is still real and still
    against the working tree -- only the process count changes."""
    if not _VALIDATE_RESULT:
        _VALIDATE_RESULT.append(subprocess.run(
            [sys.executable, VALIDATE], cwd=REPO_ROOT,
            capture_output=True, text=True, encoding="utf-8"))
    return _VALIDATE_RESULT[0]


def _read_skill_md():
    with open(SKILL_MD, encoding="utf-8") as fh:
        return fh.read()


def _section(text, heading):
    """`heading`'s own block: from the heading line up to (not including)
    the next `## ` heading, or end of file."""
    start = text.index(heading)
    rest = text[start + len(heading):]
    m = re.search(r"\n## ", rest)
    end = start + len(heading) + (m.start() if m else len(rest))
    return text[start:end]


# --- validate.py itself is the source of truth, not a copied number --------

def test_validate_exits_0_with_zero_fail_lines():
    result = _run_validate()
    assert result.returncode == 0
    fail_lines = [l for l in result.stdout.splitlines() if l.startswith("FAIL")]
    assert fail_lines == []


def test_validate_reports_the_same_body_line_count_as_computed_here():
    # Cross-checks the local formula against the real script's own output,
    # rather than trusting either one alone -- this is the exact class of
    # bug AC24 went stale from (two formulas, silently disagreeing).
    result = _run_validate()
    m = re.search(
        r"skills/track/SKILL\.md is within its (\d+)-line ceiling \((\d+)\)",
        result.stdout)
    assert m is not None, result.stdout
    ceiling, reported = int(m.group(1)), int(m.group(2))
    assert reported == _skill_body_lines()
    assert reported <= ceiling


def test_skill_md_body_is_122_lines():
    """120 before ticket mirroring, plus one pointer line each for it and
    for `references/pending-questions.md` (2026-09-03).

    This also carries what a `git diff --numstat HEAD` assertion used to:
    that a feature added one line and no more. That form only worked
    before the change was committed -- once it is in HEAD the diff is empty
    and the assertion cannot say anything. A line count is the same
    guarantee stated in a way that survives being committed.

    122 is also the ceiling in scripts/validate.py, so this file now has no
    headroom at all: the next feature that needs a pointer here raises the
    ceiling deliberately, which is what that constant's comment asks for."""
    assert _skill_body_lines() == 122


# --- '## Human gates' still says what it has always said --------------------

def test_human_gates_still_names_exactly_two_and_no_more():
    """The rule this feature had to fit inside, asserted by content.

    Closing a ticket joins ship's existing list of irreversible operations;
    it does not become a third gate. This was originally written as
    "byte-identical to HEAD", which stops meaning anything the moment the
    change is committed -- HEAD then contains the very text being compared,
    so it passes no matter what happened to it. Asserting the sentences
    themselves keeps working, and fails if someone later edits the rule."""
    section = _section(_read_skill_md(), "## Human gates")
    assert "Exactly two stages stop for a person, never more" in section
    assert "After `design`" in section
    assert "Before the irreversible operations in `ship`" in section
    # auto_invoke is explicitly not a third gate -- the sentence that says
    # so is the one a later edit is most likely to drop.
    assert "it is not a third human gate" in section


# --- the always-on budget never moved (AC3) --------------------------------

def test_always_on_budget_is_unchanged_at_5427():
    # references/ticket-mirror.md has no frontmatter, so it is invisible to
    # this budget (scripts/validate.py:216-221 only globs agents/*.md and
    # skills/*/SKILL.md); the one added SKILL.md line is body text, not a
    # frontmatter description, so it does not count either -- ticket
    # mirroring's AC3 still holds, it added nothing here.
    #
    # 5451 -> 5427 on 2026-09-03, in two steps, and the direction is the
    # point. `verifier`'s description was rewritten from "reads a diff
    # through one lens" to what it actually does -- dispatch the three --
    # for -15; `designer`'s dropped the claim that it "stops for
    # AskUserQuestion", which the platform never let a subagent do, for -9.
    # This stays an equality rather than a ceiling (validate.py already has
    # the ceiling) so a description that quietly grows fails here; the
    # number moves only with a note like this one saying why.
    result = _run_validate()
    m = re.search(r"always-on description budget: (\d+) chars", result.stdout)
    assert m is not None, result.stdout
    assert int(m.group(1)) == 5427


# --- the added line itself carries the load-bearing instruction ------------

def test_added_line_names_main_session_not_subagent_and_the_reference_path():
    lines = [l for l in _read_skill_md().splitlines() if "ticket-mirror.md" in l]
    assert len(lines) == 1
    line = lines[0]
    assert "main session" in line
    assert "not a subagent" in line
    assert "${CLAUDE_PLUGIN_ROOT}/skills/track/references/ticket-mirror.md" in line
    assert "/cai:track skip" in line
