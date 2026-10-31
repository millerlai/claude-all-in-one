"""The ship draft's reading budget.

The grounding rule asks every claim in the commit message and PR body to name a
source confirmed in this pass, and set no limit on how far a claim may reach.
On a branch with a large diff the drafting subagent re-diffed, grepped the whole
repository and opened source files to check claims about code the diff never
touched, for 20-30 minutes (measured over the 48 draft dispatches in this
machine's transcripts: 14 took over 10 minutes, and they read about 11 times as
much diff output as the rest). These tests pin the text that bounds that work.
"""
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE_SHIP = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "references", "stage-ship.md")


def _flat(path):
    with open(path, encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def _grounding_rule():
    text = _flat(STAGE_SHIP)
    start = text.index("## The grounding rule")
    return text[start:text.index("## Step 1", start)]


def test_the_grounding_rule_bounds_reading_to_the_diff():
    rule = _grounding_rule()
    assert "**Reading budget.**" in rule
    assert "bounded by the diff, not by the repository" in rule


def test_a_claim_about_the_rest_of_the_code_is_cut_not_researched():
    rule = _grounding_rule()
    assert "needs a repo-wide search to ground, so it is cut" in rule


def test_the_diff_is_read_once_and_a_large_one_is_summarised():
    rule = _grounding_rule()
    assert "each file's diff once" in rule
    assert "diff is large" in rule


def test_there_is_a_call_ceiling_after_which_research_stops():
    rule = _grounding_rule()
    assert "about 40 tool calls" in rule


def test_stage_ship_points_at_the_gate_options():
    # The main session runs ship, so it reads Gate 2's options itself.
    text = _flat(STAGE_SHIP)
    assert "`references/approval-gates.md` holds its options" in text
