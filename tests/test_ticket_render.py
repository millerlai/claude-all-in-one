"""Unit 2: marker_for and render_comment (AC11).

render_comment is a pure function of state.md's six rows -- these tests
build state.md fixtures directly, the same shape tests/test_preflight_ledger.py's
make_track() writes, rather than driving a real track through the skill.
"""
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
