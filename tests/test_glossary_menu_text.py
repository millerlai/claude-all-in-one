"""Text pins for the glossary steps of stage-build.md (#326).

The glossary menus, the check that gates them and the Step 6.2 write are prose
a model follows, so they are pinned the way `test_human_in_the_loop_text.py`
does it: whitespace folded, one section at a time, in both trees
(`plugins/cai` by hand, `plugins/cai-codex` regenerated from it).
"""
import os

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TREES = ["plugins/cai", "plugins/cai-codex"]

# How each tree tells the model to run the checker.
INVOKE = {
    "plugins/cai": "python ${CLAUDE_PLUGIN_ROOT}/scripts/glossary_check.py <that file>",
    "plugins/cai-codex": "<cai> glossary_check <that file>",
}
RAN = "the check ran only when its last line is `-- glossary: N entries checked, M flagged`"


def _flat(tree, name):
    path = os.path.join(ROOT, tree, "skills", "track", "references", name)
    with open(path, encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def _between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def _step_0_5(tree):
    return _between(_flat(tree, "stage-build.md"),
                    "**Which glossary terms join", "A Step 0.5 menu that closes on its own")


def _step_6_2(tree):
    return _between(_flat(tree, "stage-build.md"),
                    "**Write the merged terms into", "**Review.**")


@pytest.mark.parametrize("tree", TREES)
def test_step_0_5_runs_the_check_and_offers_nothing_it_flags(tree):
    item = _step_0_5(tree)
    assert INVOKE[tree] in item
    assert "A term it flags is rejected, and a rejected term is never an option" in item
    # The check "did not run" is told by its summary line, not by its exit code:
    # a wrong script path or a usage error exits 2 with no FAIL line.
    assert RAN in item
    assert "whatever the exit code, offers no term at all" in item


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_checks_again_and_writes_nothing_unchecked(tree):
    item = _step_6_2(tree)
    assert INVOKE[tree] in item
    assert "A term it flags is not written" in item
    assert "no further menu is asked" in item
    assert RAN in item
    assert "whatever the exit code, write nothing" in item


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_never_forces_a_gitignored_file_in(tree):
    item = _step_6_2(tree)
    assert "git check-ignore -q .claude/cai-context.md" in item
    assert "never `git add -f`" in item


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_does_not_recreate_a_heading_no_menu_named(tree):
    # AC3: a heading appears in a menu before it is written. A term typed in
    # free text never was an option, so a deleted `## Domain` / `## Process`
    # stays deleted and the report asks the person to put it back.
    item = _step_6_2(tree)
    assert ("when the file lacks that `## Domain` or `## Process` heading, "
            "the term is not written and the heading is not re-created") in item
    assert ("the report names the term and the missing heading and asks the "
            "person to add the heading back by hand and run again") in item
    # A heading a menu option named keeps the old rule.
    assert "a heading the menu named that the file lacks is added at the end of the file first" in item
    build = _flat(tree, "stage-build.md")
    assert "every free-text term left unwritten for a missing heading" in _between(
        build, "4. **Report.**", "Each deviation that changed an interface")


@pytest.mark.parametrize("tree", TREES)
def test_step_0_5_menu_shape(tree):
    item = _step_0_5(tree)
    assert "four at most to a menu" in item
    assert "nothing marked `(recommended)`" in item
    assert '"Merge none"' in item
    assert "Say in the four opening lines how many glossary menus" in item
    if tree == "plugins/cai":
        assert "multiSelect question" in item
    else:
        assert "numbered text list" in item
        assert "multiSelect" not in item


@pytest.mark.parametrize("tree", TREES)
def test_glossary_menus_skip_the_options_lint(tree):
    assert "Step 0.5's glossary menus skip the six fields and the lint" in _flat(
        tree, "pending-questions.md")
    gates = _flat(tree, "approval-gates.md")
    assert "menus carry none either" in gates
    assert "Step 0.5's glossary menus being the other" in gates


@pytest.mark.parametrize("tree", TREES)
def test_a_timed_out_glossary_menu_keeps_the_ones_already_answered(tree):
    assert "a glossary menu already answered still counts" in _flat(tree, "approval-gates.md")
    build = _flat(tree, "stage-build.md")
    assert "falls back to merge none for its own terms" in build
    assert "while a glossary menu already answered stands" in build
