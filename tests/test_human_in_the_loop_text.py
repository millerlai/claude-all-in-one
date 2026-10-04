"""Text pins for the reduce-the-human-in-the-loop track.

`stage-build.md`, `stage-verify.md`, `approval-gates.md` and `agents/verifier.md`
are prose the model follows, so what they promise is checked the way
`test_question_timeout.py` does: whitespace folded, one section at a time, in
both trees (`plugins/cai` by hand, `plugins/cai-codex` regenerated from it).

Each unit of the track appends its own block below.
"""
import os

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TREES = ["plugins/cai", "plugins/cai-codex"]


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


# --- Unit 1: verify exits (R2, AC2; D2, D5) ---------------------------------

HAND_UP = "`## Pending questions`"


@pytest.mark.parametrize("tree", TREES)
def test_verify_opening_hands_questions_up(tree):
    # R2: the opening paragraph must do for stage-verify what stage-build.md
    # and stage-ship.md do -- a subagent cannot ask, so it hands up.
    text = _reference(tree, "stage-verify.md")
    opening = text[:text.index("## The evidence rule")]
    assert HAND_UP in opening
    assert "references/pending-questions.md" in opening


@pytest.mark.parametrize("tree", TREES)
def test_verify_requirement_decisions_are_handed_up(tree):
    text = _reference(tree, "stage-verify.md")
    assert HAND_UP in _section(text, "## Step 3")
    assert HAND_UP in _section(text, "## Fixing")


@pytest.mark.parametrize("tree", TREES)
def test_verify_provenance_exit_2_is_handed_up(tree):
    section = _section(_reference(tree, "stage-verify.md"), "## Step 0.5")
    assert HAND_UP in section
    # The ledger is still never edited to turn the red green.
    assert "Never edit the ledger's citations" in section


@pytest.mark.parametrize("tree", TREES)
def test_verify_parked_proposal_is_handed_up_with_its_requirement(tree):
    fixing = _section(_reference(tree, "stage-verify.md"), "## Fixing")
    assert "parked proposal" in fixing
    assert "which requirement" in fixing


@pytest.mark.parametrize("tree", TREES)
def test_verify_no_longer_contradicts_itself(tree):
    # :134 told the subagent to wait for an answer while :147-149 said the
    # stage never stops for one.
    text = _reference(tree, "stage-verify.md")
    assert "never stops for an answer" not in text
    assert "never waits for an answer" in text


@pytest.mark.parametrize("tree", TREES)
def test_verify_answered_changes_are_not_re_reviewed(tree):
    # D2 = A: no second pass of the four lenses, said in the report.
    text = _reference(tree, "stage-verify.md")
    assert "not reviewed by the four lenses" in text


@pytest.mark.parametrize("tree", TREES)
def test_verify_takes_its_requirements_from_the_track(tree):
    # D5: under a track the requirement is the design row's documents plus
    # intake.md's acceptance criteria.
    step1 = _section(_reference(tree, "stage-verify.md"), "## Step 1")
    # Not the literal `state.md`: validate.py allows only stage-build.md to
    # name that file (the note cell has one declared owner).
    assert "design row of the track's state table" in step1
    assert "/intake.md`" in step1


@pytest.mark.parametrize("tree", TREES)
def test_verify_report_lists_changed_paths_and_says_it_did_not_commit(tree):
    report = _section(_reference(tree, "stage-verify.md"), "## Report")
    assert "changed or added" in report
    assert "did not commit" in report
    assert "clean_tree" in report


def test_verifier_agent_hands_questions_up():
    text = _flat("plugins", "cai", "agents", "verifier.md")
    assert "Pending questions" in text
    assert "never commit" in text


def test_codex_verifier_agent_hands_questions_up():
    text = _flat("plugins", "cai-codex", "agents", "cai_verifier.toml")
    assert "Pending questions" in text


# --- Unit 2: approval-gates (AC4, AC6; D6) -----------------------------------

VERIFY_CHANGES = "## Verify's changes, inside a track"


def _gate2(tree):
    text = _reference(tree, "approval-gates.md")
    return _section(text, "## Gate 2")


@pytest.mark.parametrize("tree", TREES)
def test_gate2_lists_verify_left_open_and_interface_deviations(tree):
    gate2 = _gate2(tree)
    assert "track_state.py left-open" in gate2
    assert "`[build]` and `[verify]`" in gate2
    assert "interface" in gate2


@pytest.mark.parametrize("tree", TREES)
def test_gate2_adds_no_menu_for_the_list(tree):
    # I8: only more to list; the two options stay the two options.
    assert "adds no menu" in _gate2(tree)


@pytest.mark.parametrize("tree", TREES)
def test_main_session_commits_verify_changes_by_reported_paths(tree):
    section = _section(_reference(tree, "approval-gates.md"), VERIFY_CHANGES)
    assert "git add -- <the paths verify reported>" in section
    assert "Never `git add -A`" in section
    assert "git status --porcelain" in section
    assert "Step 0.5" in section


@pytest.mark.parametrize("tree", TREES)
def test_verify_changes_commit_only_after_passed(tree):
    section = _section(_reference(tree, "approval-gates.md"), VERIFY_CHANGES)
    assert "passed" in section
    assert "hands a question up commits nothing" in section


@pytest.mark.parametrize("tree", TREES)
def test_no_commit_answer_leaves_changes_for_the_person(tree):
    section = _section(_reference(tree, "approval-gates.md"), VERIFY_CHANGES)
    assert "working tree" in section
    assert "clean_tree" in section
    assert "person commits" in section


@pytest.mark.parametrize("tree", TREES)
def test_verify_never_gets_its_own_commit_menu(tree):
    section = _section(_reference(tree, "approval-gates.md"), VERIFY_CHANGES)
    assert "no menu asks again" in section


# --- Unit 3: build Step 0.5 up front (AC4, AC5; D1) --------------------------

def _build(tree):
    return _reference(tree, "stage-build.md")


@pytest.mark.parametrize("tree", TREES)
def test_build_opening_keeps_the_hand_up_and_the_validate_anchor(tree):
    text = _build(tree)
    opening = text[:text.index("## Two situations")]
    assert "Step 0.5's answers" in opening
    assert "`## Pending questions`" in opening


@pytest.mark.parametrize("tree", TREES)
def test_build_first_pass_asks_before_any_unit_starts(tree):
    # D1 = A: the first pass sizes, schedules and hands Step 0.5 up; nothing
    # is started until the answers come back.
    step = _section(_build(tree), "## Step 0.5")
    assert "`## Pending questions`" in step
    assert "no unit starts" in step
    assert "no commit is made" in step
    assert "one round" in step


@pytest.mark.parametrize("tree", TREES)
def test_build_opening_no_longer_lets_units_run_ahead_of_the_answers(tree):
    # The old wording ("finish what the answer does not block -- the four
    # sizing lines are not blocked") is what let a build finish every unit
    # before Step 0.5 was answered.
    text = _build(tree)
    opening = text[:text.index("## Two situations")]
    assert "the four sizing lines are not blocked" not in opening


@pytest.mark.parametrize("tree", TREES)
def test_build_lane_is_asked_only_when_alongside_names_a_pair(tree):
    step = _section(_build(tree), "## Step 0.5")
    assert "only when the `Alongside` column" in step
    assert "sequential" in step


@pytest.mark.parametrize("tree", TREES)
def test_build_commit_answer_covers_verify_and_says_what_no_means(tree):
    step = _section(_build(tree), "## Step 0.5")
    assert "verify" in step
    assert "working tree" in step
    assert "`clean_tree`" in step
    assert "the person commits" in step


@pytest.mark.parametrize("tree", TREES)
def test_gates_file_describes_step_0_5_as_one_round(tree):
    text = _reference(tree, "approval-gates.md")
    start = text.index("- `stage-build.md` Step 0.5 —")
    bullet = text[start:text.index(" - Gate 2's triage menu", start)]
    assert "one round" in bullet
    assert "up to three turns" not in bullet


# --- Unit 4: build mid-run stops (AC3) --------------------------------------

STEP_HEADINGS = [
    "## Step 1 —", "## Step 2 —", "## Step 3 —", "## Step 4 —",
    "## Step 5 — Deviations",
]


@pytest.mark.parametrize("tree", TREES)
@pytest.mark.parametrize("heading", STEP_HEADINGS)
def test_every_mid_run_stop_hands_up_and_blocks_only_what_it_touches(
        tree, heading):
    # AC3: only the affected units stop, the rest go on, the question goes
    # up under `## Pending questions`.
    section = _section(_build(tree), heading)
    assert "`## Pending questions`" in section
    assert "`blocked`" in section


@pytest.mark.parametrize("tree", TREES)
def test_step_1_defines_the_affected_units_and_that_the_others_continue(tree):
    section = _section(_build(tree), "## Step 1 —")
    assert "the others keep going" in section
    assert "`Depends on`" in section
    assert "ownership map" in section


@pytest.mark.parametrize("tree", TREES)
def test_step_3_second_red_blocks_the_unit_instead_of_stopping_the_run(tree):
    section = _section(_build(tree), "## Step 3 —")
    assert "Still red" in section
    assert "stop and report" not in section


@pytest.mark.parametrize("tree", TREES)
def test_step_5_interface_deviation_blocks_its_dependants(tree):
    section = _section(_build(tree), "## Step 5 — Deviations")
    assert "changes an interface another unit depends on" in section
    assert "those depending on it" in section


# --- Unit 5: build Step 6 (AC1; D3, D4) --------------------------------------

@pytest.mark.parametrize("tree", TREES)
def test_step_6_3_is_skipped_under_a_track_and_unchanged_standing_alone(tree):
    # I4: one run of the four lenses per diff. Under a track that run is the
    # verify stage's; standing alone there is no verify stage after build.
    step = _section(_build(tree), "## Step 6 —")
    start = step.index("3. **")
    item = step[start:step.index("4. **Report.**", start)]
    assert "Under a track" in item
    assert "skip" in item
    assert "reviewed by the verify stage" in item
    assert "Standing alone" in item
    assert "Run `stage-verify.md` over the whole branch" in item


@pytest.mark.parametrize("tree", TREES)
def test_step_6_4_review_verdict_names_the_verify_stage_under_a_track(tree):
    step = _section(_build(tree), "## Step 6 —")
    item = step[step.index("4. **Report.**"):]
    assert "reviewed by the verify stage" in item
    assert "changed an interface" in item


@pytest.mark.parametrize("tree", TREES)
def test_report_lists_interface_deviations_under_left_open(tree):
    # D4: left-open prints it as a [build] line at Gate 2.
    report = _section(_build(tree), "## Report")
    assert "left open" in report
    assert "manual step" in report
    assert "changed an interface" in report


# --- Review fixes (verify lenses over the branch) ----------------------------

@pytest.mark.parametrize("tree", TREES)
def test_commit_no_does_not_claim_clean_tree_stops_untracked_files(tree):
    # preflight's clean_tree ignores untracked files, so a new test file
    # verify adds would ship missing unless the person is told.
    gates = _section(_reference(tree, "approval-gates.md"), VERIFY_CHANGES)
    assert "untracked" in gates
    assert "squash omits" in gates
    build = _section(_build(tree), "## Step 0.5")
    assert "stops on the tracked ones" in build
    report = _section(_reference(tree, "stage-verify.md"), "## Report")
    assert "stops on the tracked ones" in report


@pytest.mark.parametrize("tree", TREES)
def test_step_1_records_the_step_0_5_answers_for_a_re_dispatch(tree):
    step = _section(_build(tree), "## Step 1 —")
    assert "never asks Step 0.5 again" in step


@pytest.mark.parametrize("tree", TREES)
def test_verify_re_dispatch_resumes_at_fixing(tree):
    text = _reference(tree, "stage-verify.md")
    opening = text[:text.index("## The evidence rule")]
    assert "do not run Steps 0.5 to 2 again" in opening


@pytest.mark.parametrize("tree", TREES)
def test_a_named_requirement_beats_the_track_default(tree):
    # A ship fix round names its own requirement (the person's sentence).
    step1 = _section(_reference(tree, "stage-verify.md"), "## Step 1")
    assert "When the dispatch brief names a requirement" in step1


@pytest.mark.parametrize("tree", TREES)
def test_verify_report_points_the_main_session_at_the_commit_section(tree):
    report = _section(_reference(tree, "stage-verify.md"), "## Report")
    assert "Verify's changes, inside a track" in report


@pytest.mark.parametrize("tree", TREES)
def test_left_open_bullet_carries_the_not_reviewed_caveat(tree):
    report = _section(_reference(tree, "stage-verify.md"), "## Report")
    assert "not reviewed by the four lenses" in report


@pytest.mark.parametrize("tree", TREES)
def test_step_0_5_commit_bullet_says_yes_covers_verify(tree):
    step = _section(_build(tree), "## Step 0.5")
    assert "covers the verify stage's changes too" in step
    assert "the person is not asked again" in step
    assert "commits verify's changes by the paths verify reports" in step


# --- Verify-stage fixes (lenses over the branch, second pass) ---------------

@pytest.mark.parametrize("tree", TREES)
def test_verify_re_dispatch_after_step_0_5_starts_over(tree):
    # Step 0.5 stops before any lens runs, so that round's report has no
    # findings; a re-dispatch that skipped Steps 0.5 to 2 would review nothing.
    text = _reference(tree, "stage-verify.md")
    opening = text[:text.index("## The evidence rule")]
    assert "no lens has run" in opening
    assert "start again at Step 0" in opening
    assert "do not run Steps 0.5 to 2 again" in opening


@pytest.mark.parametrize("tree", TREES)
def test_verify_changes_with_no_reported_path_commit_nothing(tree):
    # A Ready verdict with no fixes lists no path; `git commit` would fail.
    section = _section(_reference(tree, "approval-gates.md"), VERIFY_CHANGES)
    assert "reported no changed path" in section
    assert "run neither command" in section


@pytest.mark.parametrize("tree", TREES)
def test_verify_changes_section_leaves_the_fix_round_to_its_own_step(tree):
    # A fix round's verify is also a verify `passed`; two sections must not
    # both commit it, or disagree when Step 0.5 answered no.
    section = _section(_reference(tree, "approval-gates.md"), VERIFY_CHANGES)
    assert "A fix round" in section
    assert "its own step 2" in section


@pytest.mark.parametrize("tree", TREES)
def test_verify_report_lists_added_paths_across_every_round(tree):
    # The failing test verify writes first is usually a new, untracked file,
    # and a re-dispatch must not lose the first round's fixes.
    report = _section(_reference(tree, "stage-verify.md"), "## Report")
    assert "changed or added" in report
    assert "new test files included" in report
    assert "across every round" in report


def test_verifier_agent_lists_added_paths():
    text = _flat("plugins", "cai", "agents", "verifier.md")
    assert "changed or added" in text


@pytest.mark.parametrize("tree", TREES)
def test_blocked_units_uncommitted_edits_stay_out_of_later_commits(tree):
    # AC3 lets the other units keep going; their commits must not sweep in
    # the blocked unit's half-done files.
    section = _section(_build(tree), "## Step 1 —")
    assert "blocked unit's uncommitted edits stay out" in section
    assert "its own paths" in section
