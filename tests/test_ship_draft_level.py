"""The level a ship draft is written at.

stage-ship.md said nothing about tests, so a drafting subagent enumerated them:
a PR body listed seven existing tests with the assertion each one changed, new
test files, and "719 tests pass" -- detail no reader acts on, and numbers that
earlier drafts have got wrong. Producing it also meant parsing test titles and
counting lines across the whole tests/ tree. These tests pin the text that asks
for behaviour-level prose instead, with the one exception that was the reason
for the long list: an acceptance criterion that asks for it.
"""
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE_SHIP = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "references", "stage-ship.md")


def _flat(path):
    with open(path, encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def _step(heading, next_heading):
    text = _flat(STAGE_SHIP)
    start = text.index(heading)
    return text[start:text.index(next_heading, start)]


def test_step_4_asks_for_behaviour_not_function_or_constant_names():
    step4 = _step("## Step 4", "## Step 5")
    assert "**Write at the level of behaviour.**" in step4
    assert "not which function, constant or parameter was edited" in step4


def test_tests_are_described_by_behaviour_never_counted_or_listed():
    step4 = _step("## Step 4", "## Step 5")
    assert "never a count, a list of test names or assertions" in step4
    assert "error-handling and edge-case tests" in step4
    assert 'Report the run as "tests pass", with no number' in step4


def test_an_acceptance_criterion_that_asks_for_more_wins_and_is_named():
    step4 = _step("## Step 4", "## Step 5")
    assert "asks for something more specific" in step4
    assert "name the criterion that asked" in step4


def test_the_release_note_follows_the_same_level():
    step7 = _step("## Step 7", "## Rollback")
    assert "follow Step 4's *Write at the level of behaviour*" in step7

