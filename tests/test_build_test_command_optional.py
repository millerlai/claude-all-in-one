"""Text pins: a missing test command never stops `build`, and a skip holds into `verify`.

Before build starts the main session settles the test command with the
person -- confirm what the resolver found, type one, or skip -- instead of
the build stage stopping on resolver exits 3 and 4. A skip leaves build and
verify doing every step except running tests. All of it is prose the model
follows, so it is pinned the way `test_human_in_the_loop_text.py` pins its
promises: whitespace folded, in both trees (`plugins/cai` by hand,
`plugins/cai-codex` regenerated from it).
"""
import os
import re

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TREES = ["plugins/cai", "plugins/cai-codex"]
SKIP_OPTION = '"Skip: build without a test command'
SKIP_LINE = "`Test command: skipped"


def _flat(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def _reference(tree, name):
    return _flat(tree, "skills", "track", "references", name)


def _section(text, heading):
    """From `heading` to the next `## ` heading, whitespace already folded."""
    start = text.index(heading)
    end = text.find(" ## ", start + len(heading))
    return text[start:end if end > 0 else None]


def _before_build(tree):
    return _section(_reference(tree, "test-command.md"), "## Before build")


def _menu_rows(section):
    """{first cell: whole row} for the menu table's data rows."""
    rows = re.findall(r"\| ([^|]+?) \| ([^|]+?) \|", section)
    return {first: rest for first, rest in rows if first not in ("Exit", "---")}


@pytest.mark.parametrize("tree", TREES)
def test_before_build_says_it_never_blocks(tree):
    section = _before_build(tree)
    assert "`build` never waits on a test command" in section
    assert "settled once, never a block" in section


@pytest.mark.parametrize("tree", TREES)
def test_every_resolver_outcome_but_declared_offers_skip(tree):
    rows = _menu_rows(_before_build(tree))
    assert set(rows) == {"0, `source` `declared`", "0, `source` `detected`", "3", "4", "5"}
    assert "None" in rows["0, `source` `declared`"]
    for exit_cell in ("0, `source` `detected`", "3", "4", "5"):
        assert SKIP_OPTION in rows[exit_cell], exit_cell


@pytest.mark.parametrize("tree", TREES)
def test_a_found_command_is_confirmed_not_used_silently(tree):
    rows = _menu_rows(_before_build(tree))
    assert '"Use `<command>` (recommended)"' in rows["0, `source` `detected`"]


@pytest.mark.parametrize("tree", TREES)
def test_no_command_found_can_be_typed_or_skipped(tree):
    row = _menu_rows(_before_build(tree))["4"]
    assert "free-text entry" in row
    assert SKIP_OPTION in row


@pytest.mark.parametrize("tree", TREES)
def test_exit_3_menu_stays_within_four_options(tree):
    # "Run all", the candidates and Skip: three candidates plus those two would
    # be five, past the menu's four.
    row = _menu_rows(_before_build(tree))["3"]
    assert "at most two" in row
    assert "With more than two" in row


@pytest.mark.parametrize("tree", TREES)
def test_a_chosen_command_is_recorded_and_a_skip_is_not(tree):
    section = _before_build(tree)
    assert "`record_test_command.py`" in section
    assert "write nothing to `.claude/cai.json`" in section
    assert "`Test command: skipped by the person before build`" in section


@pytest.mark.parametrize("tree", TREES)
def test_a_refused_recording_returns_to_the_menu(tree):
    # record_test_command.py exits 5 and writes nothing when cai.json cannot be
    # read; without a way back, a typed command on exit 5 would be a dead end.
    section = _before_build(tree)
    assert "When the recorder refuses" in section
    assert "start this section again, so the menu, Skip included, comes back" in section


@pytest.mark.parametrize("tree", TREES)
def test_a_skip_already_in_the_notes_is_not_asked_again(tree):
    section = _before_build(tree)
    assert "`.claude/track/<feature>/implementation-notes.md`" in section
    assert "a line starting `Test command: skipped`" in section


@pytest.mark.parametrize("tree", TREES)
def test_a_timed_out_menu_counts_as_skip(tree):
    assert "`Test command: skipped (the menu timed out)`" in _before_build(tree)
    timeout = _section(_reference(tree, "approval-gates.md"), "## A menu that closes on its own")
    assert ("| The test command before build (`test-command.md`) | Treated as Skip: nothing is "
            "written to `.claude/cai.json`, no detected command is used") in timeout


@pytest.mark.parametrize("tree", TREES)
def test_a_skip_holds_for_build_and_verify(tree):
    section = _before_build(tree)
    assert "Every later dispatch of `build` or `verify` carries the same line" in section
    assert "Each still does every other step of its own" in section


@pytest.mark.parametrize("tree", TREES)
def test_track_settles_it_before_dispatching_build(tree):
    text = _flat(tree, "skills", "track", "SKILL.md")
    assert "Before `build`'s dispatch in step 2" in text
    assert "`## Before build`" in text
    assert "A missing one never stops the stage" in text


@pytest.mark.parametrize("tree", TREES)
def test_build_gate_names_the_test_command_and_never_stops_on_it(tree):
    gate = _section(_reference(tree, "stage-build.md"), "## Step 0 ")
    assert "The test command is settled, or skipped — never a stop." in gate
    assert "Standing alone you are the main session: run that section now." in gate


@pytest.mark.parametrize("tree", TREES)
def test_build_runs_no_resolver_after_a_skip(tree):
    step = _section(_reference(tree, "stage-build.md"), "## Step 1 ")
    assert "Then run no resolver" in step
    assert "`skipped: no test command`" in step
    # Copied into the notes, where the main session reads it before later dispatches.
    assert "copied into the notes verbatim" in step


@pytest.mark.parametrize("tree", TREES)
def test_build_skip_leaves_out_only_the_test_runs(tree):
    step = _section(_reference(tree, "stage-build.md"), "## Step 3 ")
    assert "With the test command skipped, no unit runs a test." in step
    assert "Everything else in this stage still runs." in step
    assert "no test harness is added" in step
    assert "`done (unverified)`" in step


@pytest.mark.parametrize("tree", TREES)
def test_build_report_carries_the_skip(tree):
    build = _reference(tree, "stage-build.md")
    assert "`not run: test command skipped`" in _section(build, "## Step 6 ")
    report = _section(build, "## Report")
    assert "the test command included when it was" in report
    assert "one more item saying no unit ran a test" in report


@pytest.mark.parametrize("tree", TREES)
def test_verify_skip_leaves_out_only_the_tests(tree):
    rule = _section(_reference(tree, "stage-verify.md"), "## The evidence rule")
    assert "only the tests are left out" in rule
    assert "every other step below still runs" in rule
    assert "`tests-not-run`" in rule


@pytest.mark.parametrize("path", [
    ("plugins/cai", "agents", "verifier.md"),
    ("plugins/cai-codex", "agents", "cai_verifier.toml"),
])
def test_verifier_runs_no_test_command_after_a_skip(path):
    text = _flat(*path)
    assert SKIP_LINE in text
    assert "run neither the resolver nor any test command, do every other step" in text


@pytest.mark.parametrize("tree", TREES)
def test_approval_gates_lists_the_stop_outside_the_reference_count(tree):
    gates = _reference(tree, "approval-gates.md")
    other = _section(gates, "## The other stops")
    assert "`test-command.md`'s `## Before build`" in other
    assert "the test-command menu before build also wait in that run and are not counted here" in other
