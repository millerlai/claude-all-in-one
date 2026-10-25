"""Unit 2: marker_for and render_comment (AC11).

render_comment is a pure function of state.md's four rows -- these tests
build state.md fixtures directly, the same shape tests/test_preflight_ledger.py's
make_track() writes, rather than driving a real track through the skill.
"""
import open_items
import preflight
import ticket

STAGE_IDS = ["design", "build", "verify", "ship"]

LONG_NOTE = "x" * 250


def make_state_md(track_dir, rows):
    lines = ["# fixture", "", "branch: feat/fixture", "started: 2026-08-29", "",
             "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track_dir / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


FOUR_ROWS = [
    ["design", "done", "docs/design/x-detail.md", "HLD and detail both signed off"],
    ["build", "skipped", "—",
     "reason: four unknowns already closed at the program layer, user decided to skip"],
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
    make_state_md(tmp_path, FOUR_ROWS)
    body = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    assert body is not None

    for stage, status, artifact, note in FOUR_ROWS:
        assert ("| %s | %s | " % (stage, status)) in body

    # marker is the first line, load-bearing for find-back
    assert body.splitlines()[0] == "[cai track: ticket-integration]"
    assert body.rstrip().splitlines()[-1] == "updated 2026-08-31T00:00:00Z"


def test_render_comment_never_leaks_the_artifact_column(tmp_path):
    make_state_md(tmp_path, FOUR_ROWS)
    body = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    for stage, status, artifact, note in FOUR_ROWS:
        if artifact and artifact != "—":
            assert artifact not in body


def test_render_comment_skipped_rows_reason_reaches_the_body(tmp_path):
    make_state_md(tmp_path, FOUR_ROWS)
    body = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    assert "reason: four unknowns already closed" in body


def test_render_comment_truncates_a_note_over_200_chars(tmp_path):
    make_state_md(tmp_path, FOUR_ROWS)
    body = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    assert LONG_NOTE not in body               # the untruncated 250-char note is gone
    assert ("x" * 200) in body                 # but the first 200 chars survive
    assert ticket.ELLIPSIS in body              # and an ellipsis marker replaces the rest


def test_render_comment_returns_none_when_state_md_is_missing(tmp_path):
    assert ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z") is None


def test_render_comment_returns_none_when_row_count_is_not_four(tmp_path):
    make_state_md(tmp_path, FOUR_ROWS[:3])
    assert ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z") is None


def test_render_comment_is_a_pure_function_of_its_inputs(tmp_path):
    make_state_md(tmp_path, FOUR_ROWS)
    body1 = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    body2 = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    assert body1 == body2


# --- Unit 5: the status line, and the `final` left-open projection -----------

ROWS_WITH_LEFT_OPEN = [
    ["design", "done", "docs/design/x-detail.md",
     "HLD and detail both signed off. Left open: whether ship Gate 2 keeps a close "
     "item; status-line wording and whether it names the login"],
    ["build", "done", "—", "tests green"],
    ["verify", "done", "—", "reviewer approved"],
    ["ship", "done", "—", "PR opened"],
]


def test_render_comment_default_status_line_is_in_progress(tmp_path):
    make_state_md(tmp_path, FOUR_ROWS)
    body = ticket.render_comment(str(tmp_path), "ticket-integration", "2026-08-31T00:00:00Z")
    lines = body.splitlines()
    assert lines[0] == "[cai track: ticket-integration]"
    assert lines[1] == "status: in-progress"


def test_render_comment_final_false_status_line_is_in_progress(tmp_path):
    make_state_md(tmp_path, FOUR_ROWS)
    body = ticket.render_comment(str(tmp_path), "ticket-integration",
                                  "2026-08-31T00:00:00Z", final=False)
    assert body.splitlines()[1] == "status: in-progress"


def test_render_comment_final_true_status_line_is_done(tmp_path):
    make_state_md(tmp_path, FOUR_ROWS)
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

    # No record: each Left open entry is an imported item nobody decided, so
    # its line ends with that state.
    bullet_lines = [ln for ln in lines if ln.startswith("- [")]
    assert bullet_lines == [
        "- [%s] %s (undecided)" % (stage, ticket._truncate_note(item))
        for stage, item in expected]


def _write_record(track_dir, items):
    record = {"branch": "feat/fixture", "applied": [], "items": items}
    (track_dir / open_items.FILE_NAME).write_text(open_items.render(record),
                                                  encoding="utf-8")


def _item(n, stage, what):
    return {"id": "open-%d" % n, "state": "undecided", "stage": stage,
            "kind": "unfixed-minor", "severity": "minor", "where": "a.py:1", "what": what,
            "why": "left alone", "picked": None, "url": None, "target": None,
            "source": "report", "quoted": None}


def test_render_comment_final_true_renders_items_then_reminders(tmp_path):
    make_state_md(tmp_path, ROWS_WITH_LEFT_OPEN)
    _write_record(tmp_path, [_item(1, "verify", "Minor A"),
                             _item(2, "build", "y" * 250)])

    body = ticket.render_comment(str(tmp_path), "ticket-integration",
                                 "2026-08-31T00:00:00Z", final=True)
    lines = body.splitlines()
    # Items end with their state word, cut or not; a reminder is no item and
    # carries none.
    assert lines[lines.index("left open:") + 1:-2] == [
        "- [verify] Minor A (undecided)",
        "- [build] " + "y" * 200 + ticket.ELLIPSIS + " (undecided)",
        "- [design] whether ship Gate 2 keeps a close item",
        "- [design] status-line wording and whether it names the login",
    ]


ISSUE = "https://github.com/o/r/issues/7"
NOTE = "https://github.com/o/r/pull/9#issuecomment-123"


def _decided(n, state, url=None):
    item = _item(n, "verify", "Minor %d" % n)
    item.update({"state": state, "url": url})
    return item


def test_render_comment_final_true_item_line_ends_with_state_word(tmp_path):
    make_state_md(tmp_path, FOUR_ROWS)
    items = [_decided(1, "fixed"), _decided(2, "accepted"),
             _decided(3, "filed", ISSUE), _decided(4, "noted", NOTE),
             _decided(5, "fix-pending"), _decided(6, "undecided")]
    _write_record(tmp_path, items)

    body = ticket.render_comment(str(tmp_path), "ticket-integration",
                                 "2026-08-31T00:00:00Z", final=True)
    bullets = [ln for ln in body.splitlines() if ln.startswith("- [")]
    # The words are `open_items.state_word`'s, the ones `left-open` prints.
    assert bullets == ["- [verify] Minor %d (%s)" % (n, open_items.state_word(item))
                       for n, item in enumerate(items, 1)]
    assert bullets[2] == "- [verify] Minor 3 (filed %s)" % ISSUE
    assert bullets[4] == "- [verify] Minor 5 (fix pending)"


def test_render_comment_final_true_state_word_survives_a_long_item(tmp_path):
    make_state_md(tmp_path, FOUR_ROWS)
    item = _decided(1, "filed", ISSUE)
    item["what"] = "z" * 250
    _write_record(tmp_path, [item])

    body = ticket.render_comment(str(tmp_path), "ticket-integration",
                                 "2026-08-31T00:00:00Z", final=True)
    bullets = [ln for ln in body.splitlines() if ln.startswith("- [")]
    assert bullets == ["- [verify] " + "z" * 200 + ticket.ELLIPSIS
                       + " (filed %s)" % ISSUE]


def test_render_comment_final_true_drops_a_url_that_is_not_an_issue_or_note(tmp_path):
    # The record is a file a person may have edited; its url goes to a public
    # ticket, so only the shapes `record-url` itself accepts are printed.
    make_state_md(tmp_path, FOUR_ROWS)
    _write_record(tmp_path, [_decided(1, "filed", "C:\\Users\\x\\err.txt"),
                             _decided(2, "noted", "fatal: could not read")])

    body = ticket.render_comment(str(tmp_path), "ticket-integration",
                                 "2026-08-31T00:00:00Z", final=True)
    bullets = [ln for ln in body.splitlines() if ln.startswith("- [")]
    assert bullets == ["- [verify] Minor 1 (filed)", "- [verify] Minor 2 (noted)"]
    assert "Users" not in body and "fatal" not in body


def test_render_comment_final_true_unreadable_record_falls_back(tmp_path, capsys):
    make_state_md(tmp_path, ROWS_WITH_LEFT_OPEN)
    (tmp_path / open_items.FILE_NAME).write_text("not a record\n", encoding="utf-8")

    body = ticket.render_comment(str(tmp_path), "ticket-integration",
                                 "2026-08-31T00:00:00Z", final=True)
    printed = capsys.readouterr().out.strip().splitlines()
    assert len(printed) == 1 and open_items.FILE_NAME in printed[0]
    bullets = [ln for ln in body.splitlines() if ln.startswith("- [")]
    assert bullets == ["- [design] whether ship Gate 2 keeps a close item",
                       "- [design] status-line wording and whether it names the login"]


def test_render_comment_final_true_left_open_none_when_no_items(tmp_path):
    make_state_md(tmp_path, FOUR_ROWS)  # no "Left open:" marker anywhere
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
        ["design", "done", "—", "note. Left open: " + long_item],
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
