"""Unit 2: marker_for and render_comment (AC11).

render_comment is a pure function of state.md's six rows -- these tests
build state.md fixtures directly, the same shape tests/test_preflight_ledger.py's
make_track() writes, rather than driving a real track through the skill.
"""
import preflight
import ticket

STAGE_IDS = ["intake", "discover", "design", "build", "verify", "ship"]

LONG_NOTE = "x" * 250


def make_state_md(track_dir, rows):
    lines = ["# fixture", "", "branch: feat/fixture", "started: 2026-08-29", "",
             "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track_dir / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


SIX_ROWS = [
    ["intake", "done", "docs/design/x-intake.md", "seven decisions signed off"],
    ["discover", "skipped", "—",
     "reason: four unknowns already closed at the program layer, user decided to skip"],
    ["design", "done", "docs/design/x-detail.md", "HLD and detail both signed off"],
    ["build", "", "", ""],
    ["verify", "", "", ""],
    ["ship", "", "", LONG_NOTE],
]


# --- marker_for ---------------------------------------------------------------

def test_marker_for_has_brackets_and_the_feature_name():
    assert ticket.marker_for("ticket-integration") == "[cai track: ticket-integration]"


def test_marker_for_is_not_a_substring_of_a_similarly_named_feature():
    short = ticket.marker_for("ticket")
    long_feature_marker = ticket.marker_for("ticket-integration")
    assert short not in long_feature_marker


# --- AC11: render_comment matches state.md row for row -----------------------

def test_render_comment_matches_state_md_row_for_row(tmp_path):
    make_state_md(tmp_path, SIX_ROWS)
    body = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    assert body is not None

    for stage, status, artifact, note in SIX_ROWS:
        assert ("| %s | %s | " % (stage, status)) in body

    # marker is the first line, load-bearing for find-back
    assert body.splitlines()[0] == "[cai track: ticket-integration]"
    assert body.rstrip().splitlines()[-1] == "updated 2026-08-31T00:00:00Z"


def test_render_comment_never_leaks_the_artifact_column(tmp_path):
    make_state_md(tmp_path, SIX_ROWS)
    body = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    for stage, status, artifact, note in SIX_ROWS:
        if artifact and artifact != "—":
            assert artifact not in body


def test_render_comment_skipped_rows_reason_reaches_the_body(tmp_path):
    make_state_md(tmp_path, SIX_ROWS)
    body = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    assert "reason: four unknowns already closed" in body


def test_render_comment_truncates_a_note_over_200_chars(tmp_path):
    make_state_md(tmp_path, SIX_ROWS)
    body = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    assert LONG_NOTE not in body               # the untruncated 250-char note is gone
    assert ("x" * 200) in body                 # but the first 200 chars survive
    assert ticket.ELLIPSIS in body              # and an ellipsis marker replaces the rest


def test_render_comment_returns_none_when_state_md_is_missing(tmp_path):
    assert ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z") is None


def test_render_comment_returns_none_when_row_count_is_not_six(tmp_path):
    make_state_md(tmp_path, SIX_ROWS[:5])
    assert ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z") is None


def test_render_comment_is_a_pure_function_of_its_inputs(tmp_path):
    make_state_md(tmp_path, SIX_ROWS)
    body1 = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    body2 = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    assert body1 == body2


# --- Unit 5: the status line, and the `final` left-open projection -----------

ROWS_WITH_LEFT_OPEN = [
    ["intake", "done", "docs/design/x-intake.md",
     "signed off. Left open: whether ship Gate 2 keeps a close item; status-"
     "line wording and whether it names the login"],
    ["discover", "skipped", "—",
     "reason: four unknowns already closed at the program layer"],
    ["design", "done", "docs/design/x-detail.md", "HLD and detail both signed off"],
    ["build", "done", "—", "tests green"],
    ["verify", "done", "—", "reviewer approved"],
    ["ship", "done", "—", "PR opened"],
]


def test_render_comment_default_status_line_is_in_progress(tmp_path):
    make_state_md(tmp_path, SIX_ROWS)
    body = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    lines = body.splitlines()
    assert lines[0] == "[cai track: ticket-integration]"
    assert lines[1] == "status: in-progress"


def test_render_comment_final_false_status_line_is_in_progress(tmp_path):
    make_state_md(tmp_path, SIX_ROWS)
    body = ticket.render_comment(str(tmp_path), "ticket-integration",
                                  "2026-08-31T00:00:00Z", final=False)
    assert body.splitlines()[1] == "status: in-progress"


def test_render_comment_final_true_status_line_is_done(tmp_path):
    make_state_md(tmp_path, SIX_ROWS)
    body = ticket.render_comment(str(tmp_path), "ticket-integration",
                                  "2026-08-31T00:00:00Z", final=True)
    assert body.splitlines()[1] == "status: done"


def test_render_comment_non_final_body_has_no_left_open_block(tmp_path):
    make_state_md(tmp_path, ROWS_WITH_LEFT_OPEN)
    body = ticket.render_comment(str(tmp_path), "ticket-integration",
                                  "2026-08-31T00:00:00Z", final=False)
    assert "left open" not in body
    assert "\n\n" not in body  # today's exact shape: no blank lines at all
    assert body.rstrip().splitlines()[-1] == "updated 2026-08-31T00:00:00Z"


def test_render_comment_final_true_left_open_list_matches_preflight(tmp_path):
    make_state_md(tmp_path, ROWS_WITH_LEFT_OPEN)
    with open(tmp_path / "state.md", encoding="utf-8") as fh:
        text = fh.read()
    expected = preflight.left_open_items(text)
    assert expected  # sanity: the fixture actually carries left-open items

    body = ticket.render_comment(str(tmp_path), "ticket-integration",
                                  "2026-08-31T00:00:00Z", final=True)
    lines = body.splitlines()
    assert "left open:" in lines

    bullet_lines = [ln for ln in lines if ln.startswith("- [")]
    assert bullet_lines == [
        "- [%s] %s" % (stage, ticket._truncate_note(item)) for stage, item in expected]


def test_render_comment_final_true_left_open_none_when_no_items(tmp_path):
    make_state_md(tmp_path, SIX_ROWS)  # no "Left open:" marker anywhere
    body = ticket.render_comment(str(tmp_path), "ticket-integration",
                                  "2026-08-31T00:00:00Z", final=True)
    assert "left open: none" in body.splitlines()
    assert "left open:" not in [ln for ln in body.splitlines() if ln != "left open: none"]


def test_render_comment_final_true_has_blank_lines_around_left_open_block(tmp_path):
    make_state_md(tmp_path, ROWS_WITH_LEFT_OPEN)
    body = ticket.render_comment(str(tmp_path), "ticket-integration",
                                  "2026-08-31T00:00:00Z", final=True)
    lines = body.splitlines()
    left_open_idx = lines.index("left open:")
    assert lines[left_open_idx - 1] == ""  # blank line before the block
    assert lines[-1] == "updated 2026-08-31T00:00:00Z"
    assert lines[-2] == ""  # blank line before the final "updated" line


def test_truncate_note_boundary_is_exactly_200_chars():
    # NOTE_LIMIT's own off-by-one: 200 chars survive whole, 201 chars are cut
    # to 200 plus the ellipsis. No existing test pins this edge -- every other
    # truncation test here uses a note far past the limit (250 chars), so an
    # off-by-one in _truncate_note's `<=` (e.g. `<`) would pass everything else.
    at_limit = "x" * ticket.NOTE_LIMIT
    over_limit = "x" * (ticket.NOTE_LIMIT + 1)
    assert ticket._truncate_note(at_limit) == at_limit
    assert ticket._truncate_note(over_limit) == at_limit + ticket.ELLIPSIS


def test_render_comment_final_true_note_cut_at_200_chars(tmp_path):
    long_item = "y" * 250
    rows = [
        ["intake", "done", "—", "note. Left open: " + long_item],
        ["discover", "done", "—", ""],
        ["design", "done", "—", ""],
        ["build", "done", "—", ""],
        ["verify", "done", "—", ""],
        ["ship", "done", "—", ""],
    ]
    make_state_md(tmp_path, rows)
    body = ticket.render_comment(str(tmp_path), "ticket-integration",
                                  "2026-08-31T00:00:00Z", final=True)
    assert long_item not in body
    assert ("y" * 200) in body
    assert ticket.ELLIPSIS in body
