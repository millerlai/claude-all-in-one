"""Text pins for verify's platform-review correctness (issue 481, AC7 and the
split of work between the main session and `verifier`).

`stage-verify.md`, the track `SKILL.md` and `agents/verifier.md` are prose the
model follows, so what they promise is checked the way
`test_human_in_the_loop_text.py` does: whitespace folded, one section at a
time. Only `plugins/cai` is pinned here; the Codex tree words Step 0.6
differently and is covered by its own override.
"""
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TREE = "plugins/cai"


def _flat(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def _stage_verify():
    return _flat(TREE, "skills", "track", "references", "stage-verify.md")


def _section(text, heading):
    """From `heading` to the next `## ` heading, whitespace already folded."""
    start = text.index(heading)
    end = text.find(" ## ", start + len(heading))
    return text[start:end if end > 0 else None]


def test_step2_treats_platform_findings_like_any_lens():
    # AC7: completed, re-judged by finding-severity.md, platform marks ignored.
    step2 = _section(_stage_verify(), "## Step 2")
    assert "A finding from the platform review gets the same treatment" in step2
    assert "`file:line`" in step2
    assert "failure scenario with concrete inputs" in step2
    assert "smallest fix" in step2
    assert "`finding-severity.md`'s definitions alone" in step2
    assert "never from the platform's own marks" in step2


def test_step_0_6_sits_between_0_5_and_0_75_and_is_the_main_sessions():
    text = _stage_verify()
    assert text.index("## Step 0.5") < text.index("## Step 0.6") < text.index("## Step 0.75")
    step = _section(text, "## Step 0.6")
    assert "main session's step" in step
    assert "`verifier` skips this step when its brief carries a `Platform review:` line" in step
    assert "resolve_review_command.py --platform claude" in step
    assert "`args`, word for word, adding no flag" in step
    # I1: a fallback never skips correctness.
    assert "Step 1 adds a `reviewer`" in step


def test_step_0_6_gives_every_non_call_path_a_reason():
    step = _section(_stage_verify(), "## Step 0.6")
    assert "`Platform review: not run (Step 0 stopped)`" in step
    assert "`Platform review: not run (provenance exit 2)`" in step
    assert "no `Platform review:` line at all" in step
    assert "`unclear` is a fallback" in step


def test_step1_has_three_lenses_and_a_fourth_only_on_fallback():
    step1 = _section(_stage_verify(), "## Step 1")
    assert "Three agents, in parallel, one message" in step1
    assert "Only on fallback" in step1
    assert "Four and not more" in step1  # the sentence docs/rule-provenance.md pins
    assert "From Step 0.6's platform review." in step1


def test_redispatch_reuses_the_platform_review_line():
    opening = _stage_verify().split("## The evidence rule")[0]
    assert "A re-dispatch never calls the platform review again" in opening
    skill = _flat(TREE, "skills", "track", "SKILL.md")
    assert "a re-dispatch reuses the earlier brief's line" in skill


def test_report_names_where_correctness_came_from():
    text = _stage_verify()
    assert "**Correctness source.**" in _section(text, "## Step 3")
    assert "where correctness came from" in _section(text, "## Report")


def test_verifier_integrates_the_platform_review_file_and_keeps_its_tools():
    text = _flat(TREE, "agents", "verifier.md")
    assert "`Platform review:` line points at it" in text
    assert "tools: Read, Grep, Glob, Agent, Bash, Write, Edit" in text
