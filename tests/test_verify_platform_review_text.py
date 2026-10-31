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
    assert "in the main session, which holds the Skill tool" in step
    assert "Run Steps 0, 0.5 and this one in order" in step
    assert "resolve_review_command.py --platform claude" in step
    assert "`args`, word for word, adding no flag" in step
    # I1: a fallback never skips correctness.
    assert "Step 1 adds a `reviewer`" in step


def test_step_0_6_gives_every_non_call_path_a_reason():
    step = _section(_stage_verify(), "## Step 0.6")
    assert "When Step 0 stopped or Step 0.5 exited 2, call nothing" in step
    assert "`unclear` is a fallback" in step
    # No brief carries a `Platform review:` line any more: the main session
    # that ran Step 0.6 reads its own file in Step 1.
    assert "`Platform review:`" not in step


def test_step1_has_three_lenses_and_a_fourth_only_on_fallback():
    step1 = _section(_stage_verify(), "## Step 1")
    assert "Three agents, in parallel, one message" in step1
    assert "Only on fallback" in step1
    assert "Four and not more" in step1  # the sentence docs/rule-provenance.md pins
    assert "From Step 0.6's platform review." in step1


def test_step1_treats_a_reading_never_set_as_a_fallback():
    # codex_review.py writes `reading: pending`; when the main session forgets to
    # replace it, correctness would be skipped with nothing in the report.
    step1 = _section(_stage_verify(), "## Step 1")
    assert "still says `reading: pending`" in step1.split("add a fourth")[0]


def test_step1_treats_an_unclear_reading_as_a_fallback():
    # Step 0.6 says `unclear` is a fallback; Step 1 must agree or correctness is skipped.
    step1 = _section(_stage_verify(), "## Step 1")
    assert "`reading: unclear`" in step1.split("add a fourth")[0]


def test_one_run_calls_the_platform_review_once():
    opening = _stage_verify().split("## The evidence rule")[0]
    assert "One run calls the platform review once" in opening


def test_report_names_where_correctness_came_from():
    text = _stage_verify()
    assert "**Correctness source.**" in _section(text, "## Step 3")
    assert "where correctness came from" in _section(text, "## Report")


def test_step1_reads_the_platform_review_file_the_main_session_wrote():
    step1 = _section(_stage_verify(), "## Step 1")
    assert "Under a track, read the platform review file before dispatching" in step1
