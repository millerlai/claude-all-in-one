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
    # #385: the answer is Gate 1's now, not Step 0.5's.
    assert "Gate 1" in section
    assert "`commit_answer`" in section
    assert "Step 0.5" not in section


@pytest.mark.parametrize("tree", TREES)
def test_verify_changes_commit_only_after_passed(tree):
    section = _section(_reference(tree, "approval-gates.md"), VERIFY_CHANGES)
    assert "passed" in section
    assert "hands a question up commits nothing" in section


@pytest.mark.parametrize("tree", TREES)
def test_verify_changes_act_on_the_main_sessions_own_line(tree):
    section = _section(_reference(tree, "approval-gates.md"), VERIFY_CHANGES)
    assert "never the report's" in section
    assert "it changes nothing" in section
    assert "or its report is no longer in hand" in section


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
    # #374: one hand-up, and a stop that spends none of pending-questions.md's rounds.
    assert "one hand-up" in step
    assert "does not count as one of its three rounds" in " ".join(step.split())


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
    assert "one hand-up" in bullet
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
    # #385: under a track the notes carry the commit_answer line verbatim and
    # lose to this run's own line, so a re-signed design is not committed
    # against a stale yes.
    assert "the `commit_answer` line this build acted on, copied verbatim" in step
    assert "the line wins when the notes disagree" in step


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


# --- Unit 2 of default-commit-per-unit (#385): Gate 1 carries the answer ----

def _gate1(tree):
    return _section(_reference(tree, "approval-gates.md"), "## Gate 1")


@pytest.mark.parametrize("tree", TREES)
def test_gate_1_has_four_options_in_order(tree):
    section = _gate1(tree)
    positions = [section.index(label) for label in (
        "| Approve |", "| Approve without commits |",
        "| Changes requested |", "| Reject |")]
    assert positions == sorted(positions)
    for needle in ("`commit: yes`", "`commit: no`", "--gate human",
                   "Neither option is marked"):
        assert needle in section, needle
    # AC2: "Approve" is consent only because the menu says what it consents
    # to, and "Approve without commits" says what stays off.
    for needle in ("one local commit per verified unit", "nothing is pushed",
                   "the parallel lane is off"):
        assert needle in section, needle


@pytest.mark.parametrize("tree", TREES)
def test_gate_1_table_rows_are_not_marked_recommended(tree):
    text = _reference(tree, "approval-gates.md")
    start = text.index("| Option | What it does | |---|---|")
    table = text[start:text.index("**That order is not a preference.**", start)]
    assert "(recommended)" not in table


@pytest.mark.parametrize("tree", TREES)
def test_stance_approval_lists_its_own_three_options(tree):
    text = _reference(tree, "approval-gates.md")
    assert "Approve, Changes requested, Reject" in text
    assert "Same three options as Gate 1" not in text


@pytest.mark.parametrize("tree", TREES)
def test_gate_1_says_how_the_answer_reaches_build(tree):
    section = _gate1(tree)
    assert "in every build dispatch brief" in section
    assert "a re-dispatch carrying an answer included" in section
    # The line is never taken from a stored report: a resumed round runs
    # preflight again for that line alone.
    assert "take it from that report" not in section
    assert "never one copied from a report" in section
    assert "for that line alone" in section
    assert "whatever the exit code" in section
    assert "record nothing for that run" in section
    assert "missing or differs from yours" in section
    assert "yours still decides" in section
    assert "quote yours in the next dispatch" in section
    assert "`commit_answer`" in section


@pytest.mark.parametrize("tree", TREES)
def test_gate_1_never_re_asks_for_an_unchanged_document(tree):
    assert "do not put Gate 1 again for an unchanged document" in _gate1(tree)


@pytest.mark.parametrize("tree", TREES)
def test_no_commit_option_and_unreadable_are_described(tree):
    text = _reference(tree, "approval-gates.md")
    row = text[text.index("| Approve without commits |"):]
    row = row[:row.index(" | Changes requested |")]
    assert '"Commit: no"' in row
    verify = _section(text, VERIFY_CHANGES)
    assert "unreadable" in verify


@pytest.mark.parametrize("tree", TREES)
def test_gate_1_rows_each_write_their_own_marker(tree):
    # The prose under the table names both markers without saying which option
    # writes which, so a swap between the rows would invert the consent and
    # still satisfy the needles in test_gate_1_has_four_options_in_order.
    section = _gate1(tree)
    approve = section[section.index("| Approve |"):
                      section.index("| Approve without commits |")]
    without = section[section.index("| Approve without commits |"):
                      section.index("| Changes requested |")]
    assert "`--note` starts with `commit: yes`" in approve
    assert "`commit: no`" not in approve
    assert "`--note` starts with `commit: no`" in without
    assert "`commit: yes`" not in without


@pytest.mark.parametrize("tree", TREES)
def test_diagnosis_signoff_says_which_menu_the_main_session_asks(tree):
    # DD of component 3: stage-design.md's side is pinned above; this is the
    # side the main session reads when it puts the menu.
    text = _reference(tree, "approval-gates.md")
    start = text.index("- `stage-design.md`'s diagnosis sign-off")
    bullet = text[start:text.index("- `stage-design.md`'s Tier 1 entries", start)]
    assert "the stance approval's three options" in bullet
    assert "Gate 1's four" in bullet
    assert "with neither written, ask the four" in bullet
    assert "is not recorded when Detail follows" in bullet


@pytest.mark.parametrize("tree", TREES)
def test_pending_questions_lists_the_four_option_gate_1(tree):
    text = _reference(tree, "pending-questions.md")
    assert "Approve, Approve without commits or Reject at Gate 1" in text


@pytest.mark.parametrize("tree", TREES)
def test_stage_design_names_the_route_and_the_legacy_gate(tree):
    text = _reference(tree, "stage-design.md")
    assert "`Next: Detail`" in text
    assert "`Next: build`" in text
    assert "with four options" in text
    assert "with three options" not in text


@pytest.mark.parametrize("tree", TREES)
def test_step_0_5_item_counts_two_questions_under_a_track(tree):
    text = _reference(tree, "approval-gates.md")
    start = text.index("- `stage-build.md` Step 0.5 —")
    bullet = text[start:text.index(" - Gate 2's triage menu", start)]
    assert "one hand-up" in bullet
    assert "up to three turns" not in bullet
    assert "Up to two decisions under a track" in bullet


# --- Unit 3 of default-commit-per-unit (#385): build and verify read it -----

REPORT_LINE = "the `commit_answer` line this run acted on, verbatim"


@pytest.mark.parametrize("tree", TREES)
def test_build_commit_per_unit_is_never_asked_under_a_track(tree):
    step = _section(_build(tree), "## Step 0.5")
    assert "Under a track this is never asked" in step
    assert "`commit_answer`" in step
    assert "no `commit_answer` line at all is no" in step
    # DD10: Codex's main session reads this file itself, so there is no brief
    # for the line to be quoted in -- it is in the preflight output it saw.
    assert "in the preflight output you read yourself" in step
    assert "Repeat that line verbatim" in step
    # standing alone keeps the question, and the reason behind it
    assert "Standing alone, ask once for the whole run" in step
    assert "`workflow.md` says never commit unless asked" in step


@pytest.mark.parametrize("tree", TREES)
def test_a_saved_report_in_the_brief_is_a_trace_not_the_answer(tree):
    # I10: a re-dispatch carries the round's whole report in its brief, and
    # that report repeats the line its pass acted on -- a yes that a later
    # re-sign may have turned into a no. The agent cannot read the ledger, so
    # the rule that picks between the two lines has to be in its own file.
    step = _section(_build(tree), "## Step 0.5")
    assert ("the line you act on is the one the dispatch quotes outside "
            "that report") in step
    verify = _reference(tree, "stage-verify.md")
    opening = verify[:verify.index("## The evidence rule")]
    assert ("the line you repeat is the one the dispatch quotes outside "
            "that report") in opening


@pytest.mark.parametrize("tree", TREES)
def test_build_first_pass_does_not_stop_with_nothing_to_ask(tree):
    step = _section(_build(tree), "## Step 0.5")
    assert "With no question to hand up, the first pass does not stop" in step
    assert "and the commit answer is yes" in step


@pytest.mark.parametrize("tree", TREES)
def test_build_lane_and_closeout_read_the_commit_answer(tree):
    text = _build(tree)
    assert "The commit answer is yes: Gate 1's" in _section(text, "## Step 4")
    close = _section(text, "## Step 6")
    assert "Gate 1's under a track" in close
    assert "Step 0.5 answered commit-per-unit" not in close


@pytest.mark.parametrize("tree", TREES)
def test_build_and_verify_reports_repeat_the_commit_answer_line(tree):
    assert REPORT_LINE in _section(_build(tree), "## Report")
    verify = _reference(tree, "stage-verify.md")
    report = _section(verify, "## Report")
    assert REPORT_LINE in report
    assert "Gate 1" in report
    opening = verify[:verify.index("## The evidence rule")]
    assert "Repeat the `commit_answer` line from your brief verbatim" in opening


@pytest.mark.parametrize("tree", TREES)
def test_track_skill_has_the_main_session_quote_the_commit_answer(tree):
    assert "`commit_answer`" in _flat(tree, "skills", "track", "SKILL.md")


# --- Fix round of default-commit-per-unit (review of PR #387) ---------------

@pytest.mark.parametrize("tree", TREES)
def test_step_3_commits_only_when_the_commit_answer_is_yes(tree):
    # C5: Step 3 is the text a build subagent follows unit by unit, in order.
    # An unconditional "5. Commit" committed against a no, whatever Step 0.5
    # said above it.
    section = _section(_build(tree), "## Step 3 —")
    start = section.index("5. **Commit**")
    item = section[start:section.index("**With the test command skipped", start)]
    assert item.startswith("5. **Commit** only when the commit answer is yes")
    assert "`commit_answer`" in item
    assert "commit nothing" in item
    assert "working tree" in item
    assert "`uncommitted`" in item
    # the test-command-skipped paragraph must not re-order the two
    skipped = section[section.index("**With the test command skipped"):]
    assert "committed as usual" not in skipped
    assert "as item 5 says" in skipped


@pytest.mark.parametrize("tree", TREES)
def test_a_stuck_unit_does_not_make_the_others_commit_as_usual(tree):
    section = _section(_build(tree), "## Step 1 —")
    assert "committed as usual" not in section
    assert "as Step 3's item 5 says" in section


@pytest.mark.parametrize("tree", TREES)
def test_gate_1_only_a_label_answers_it(tree):
    # P1: a typed `approved` maps by name to Approve in the model's head.
    section = _gate1(tree)
    assert "is not one of the four option labels verbatim" in section
    assert "is not an approval" in section
    assert "put the menu again" in section
    assert "never inferred from prose" in section


@pytest.mark.parametrize("tree", TREES)
def test_gate_1_note_is_exactly_the_marker(tree):
    # P4: the note is a double-quoted shell word; text from the design
    # document or a ticket in it would run if it held a backtick or `$(`.
    section = _gate1(tree)
    assert "The note is exactly `commit: yes` or `commit: no`" in section
    assert "double-quoted shell word" in section
    assert "what was approved" not in section
    assert "`; ` and one line" not in section


@pytest.mark.parametrize("tree", TREES)
def test_gate_1_exactly_one_commit_answer_line_counts(tree):
    # C1: a ledger note once printed a second `commit_answer` line after the
    # genuine one. preflight.py now escapes that, and the reader's rule is
    # the second fence.
    section = _gate1(tree)
    assert "exactly one `commit_answer` line counts" in section
    assert "two or more, or two that disagree, is no" in section


@pytest.mark.parametrize("tree", TREES)
def test_a_resumed_run_reports_a_signing_fail_without_stopping(tree):
    # P3, inside DD4 (b): the resume is still not stopped by another line,
    # but a document edited after sign-off is said to the person.
    section = _gate1(tree)
    assert "let none of its other lines stop the resume" in section
    assert "`FAIL design_signed_off`" in section
    assert "`FAIL artifact_unchanged`" in section
    assert "in one line" in section
    pending = _section(_reference(tree, "pending-questions.md"),
                       "## Resuming a saved round")
    assert "`FAIL design_signed_off`" in pending
    assert "`FAIL artifact_unchanged`" in pending
    assert "stops nothing" in pending
