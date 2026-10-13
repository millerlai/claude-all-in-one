"""PB-08 (issue #92): `track_state.py left-open` reads state.md's fixed
`Left open:` marker out of each stage's note cell and prints it, so
`/cai:track done` can relay it before a track is archived and its notes
become harder to find.
"""
import os
import subprocess
import sys

import open_items
import preflight
import track_state

SCRIPTS = os.path.dirname(track_state.__file__)

ROWS = [("intake", "done", "—", ""), ("discover", "done", "—", ""),
        ("design", "done", "—", ""), ("build", "done", "—", ""),
        ("verify", "done", "—",
         "Ready. 2 Minors documented. Left open: Minor A in foo.py; "
         "parked proposal B"),
        ("ship", "done", "—", "Shipped. Left open: tag v1.2 waiting on the person")]

NO_MARKER_ROWS = [("intake", "done", "—", ""), ("discover", "done", "—", ""),
                   ("design", "done", "—", ""), ("build", "done", "—", ""),
                   ("verify", "done", "—",
                    "nothing fixed, nothing parked. 6 Minors documented, not fixed"),
                   ("ship", "", "", "")]


def make_track(tmp_path, rows=ROWS):
    root = tmp_path / "track"
    (root / "billing").mkdir(parents=True)
    (root / "current").write_text("billing", encoding="utf-8")
    lines = ["# fixture", "", "branch: feat/fixture", "started: 2026-08-29", "",
             "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (root / "billing" / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(root), str(root / "billing")


def run(*args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "track_state.py"), *args],
                          capture_output=True, text=True, encoding="utf-8")


def test_items_from_multiple_rows_print_in_table_order_under_one_header(tmp_path):
    root, _ = make_track(tmp_path)

    done = run("left-open", "--track-root", root)
    assert done.returncode == 0, done.stderr
    assert "Left open by billing:" in done.stdout
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("- ")]
    # I8: no record, so every `Left open:` entry is an undecided item.
    assert lines == [
        "- open-1 [verify] Minor A in foo.py (undecided)",
        "- open-2 [verify] parked proposal B (undecided)",
        "- open-3 [ship] tag v1.2 waiting on the person (undecided)",
    ]
    assert "Reminders:" not in done.stdout


def test_no_marker_anywhere_exits_0_with_a_fallback_and_no_bullets(tmp_path):
    root, track_dir = make_track(tmp_path, NO_MARKER_ROWS)

    done = run("left-open", "--track-root", root)
    assert done.returncode == 0, done.stderr
    assert "billing" in done.stdout
    assert 'no "Left open:" marker' in done.stdout
    assert os.path.join(track_dir, "state.md") in done.stdout
    assert [ln for ln in done.stdout.splitlines() if ln.startswith("- ")] == []


def test_no_current_file_exits_2(tmp_path):
    root = tmp_path / "track"
    root.mkdir()

    done = run("left-open", "--track-root", str(root))
    assert done.returncode == 2
    assert "no active track" in done.stderr


def test_left_open_items_splits_on_semicolon_and_strips():
    text = "\n".join([
        "| stage | status | artifact | note |",
        "|---|---|---|---|",
        "| verify | done | — | Ready. Left open: Minor A in foo.py; parked proposal B |",
        "| ship | done | — | Shipped. Left open: tag v1.2 waiting on the person |",
        "| build | done | — | nothing left open here |",
    ])
    assert preflight.left_open_items(text) == [
        ("verify", "Minor A in foo.py"),
        ("verify", "parked proposal B"),
        ("ship", "tag v1.2 waiting on the person"),
    ]


# --- the open-items record (unit 2): id-first lines, state words, reminders ---

def make_item(n, stage="verify", what="a finding", where=None, state="undecided",
              url=None, source="report", kind=None):
    return {"id": "open-%d" % n, "state": state, "stage": stage,
            "kind": kind or ("deviation" if stage == "build" else "unfixed-minor"),
            "where": where, "what": what, "why": "left alone", "picked": None,
            "url": url, "target": None, "source": source, "quoted": None}


def write_record(track_dir, items, applied=()):
    record = {"branch": "feat/fixture", "applied": list(applied), "items": items}
    with open(os.path.join(track_dir, open_items.FILE_NAME), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write(open_items.render(record))


def item_lines(stdout):
    return [ln for ln in stdout.splitlines() if ln.startswith("- open-")]


def test_five_items_from_two_stages_print_one_line_each(tmp_path):
    root, track_dir = make_track(tmp_path, NO_MARKER_ROWS)
    write_record(track_dir, [
        make_item(1, "build", "Renamed the flag value", "plugins/cai/a.py:3"),
        make_item(2, "build", "Skipped the live check"),
        make_item(3, "verify", "Minor A", "foo.py:10"),
        make_item(4, "verify", "Minor B", "bar.py"),
        make_item(5, "verify", "Proposal C", "baz.py:1"),
    ])

    done = run("left-open", "--track-root", root)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[0] == "Left open by billing:"
    assert item_lines(done.stdout) == [
        "- open-1 [build] plugins/cai/a.py:3 — Renamed the flag value (undecided)",
        "- open-2 [build] Skipped the live check (undecided)",
        "- open-3 [verify] foo.py:10 — Minor A (undecided)",
        "- open-4 [verify] bar.py — Minor B (undecided)",
        "- open-5 [verify] baz.py:1 — Proposal C (undecided)",
    ]
    assert "Reminders:" not in done.stdout


def test_every_state_prints_its_ac8_word_in_the_id_first_layout(tmp_path):
    root, track_dir = make_track(tmp_path, NO_MARKER_ROWS)
    url = "https://github.com/o/r/issues/7"
    states = [("undecided", None, "undecided"),
              ("fix-pending", None, "fix pending"),
              ("queued-issue", None, "queued: issue once the PR is open"),
              ("queued-note", None, "queued: note once the PR is open"),
              ("filing", None, "filing: result unknown, check GitHub"),
              ("filed", url, "filed " + url),
              ("noted", url + "#c1", "noted " + url + "#c1"),
              ("accepted", None, "accepted"),
              ("fixed", None, "fixed")]
    write_record(track_dir, [make_item(n, "verify", "finding %d" % n, "f%d.py" % n,
                                       state=s, url=u)
                             for n, (s, u, _) in enumerate(states, 1)])

    done = run("left-open", "--track-root", root)
    assert done.returncode == 0, done.stderr
    assert item_lines(done.stdout) == [
        "- open-%d [verify] f%d.py — finding %d (%s)" % (n, n, n, word)
        for n, (_, _, word) in enumerate(states, 1)]


def test_reminders_print_after_the_items_in_todays_shape(tmp_path):
    root, track_dir = make_track(tmp_path)  # state.md carries three Left open: entries
    write_record(track_dir, [make_item(1, "verify", "Minor Z", "z.py:2")])

    done = run("left-open", "--track-root", root)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        "Left open by billing:",
        "- open-1 [verify] z.py:2 — Minor Z (undecided)",
        "Reminders:",
        "- [verify] Minor A in foo.py",
        "- [verify] parked proposal B",
        "- [ship] tag v1.2 waiting on the person",
    ]


def test_a_state_md_entry_already_imported_is_not_a_reminder(tmp_path):
    root, track_dir = make_track(tmp_path)
    write_record(track_dir, [
        make_item(1, "verify", "Minor A in foo.py", state="accepted", source="state.md"),
        make_item(2, "verify", "parked proposal B", source="state.md"),
        make_item(3, "ship", "tag v1.2 waiting on the person", source="state.md")])

    done = run("left-open", "--track-root", root)
    assert done.returncode == 0, done.stderr
    assert "Reminders:" not in done.stdout
    assert item_lines(done.stdout)[0] == (
        "- open-1 [verify] Minor A in foo.py (accepted)")


def test_only_reminders_still_print_the_header_then_reminders(tmp_path):
    root, track_dir = make_track(tmp_path)
    write_record(track_dir, [])

    done = run("left-open", "--track-root", root)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[:2] == ["Left open by billing:", "Reminders:"]
    assert item_lines(done.stdout) == []


def test_empty_record_and_no_reminders_keeps_the_fallback_line(tmp_path):
    root, track_dir = make_track(tmp_path, NO_MARKER_ROWS)
    write_record(track_dir, [])

    done = run("left-open", "--track-root", root)
    assert done.returncode == 0, done.stderr
    assert 'no "Left open:" marker' in done.stdout


def test_unreadable_record_prints_one_line_then_state_md_as_today(tmp_path):
    root, track_dir = make_track(tmp_path)
    record_path = os.path.join(track_dir, "open-items.md")
    with open(record_path, "w", encoding="utf-8") as fh:
        fh.write("not a record\n")

    done = run("left-open", "--track-root", root)
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert lines[0].startswith("open items: ")
    assert lines[0].endswith("; read " + record_path)
    assert lines[1:] == [
        "Left open by billing:",
        "- [verify] Minor A in foo.py",
        "- [verify] parked proposal B",
        "- [ship] tag v1.2 waiting on the person",
    ]


def test_unknown_format_record_falls_back_the_same_way(tmp_path):
    root, track_dir = make_track(tmp_path)
    with open(os.path.join(track_dir, "open-items.md"), "w", encoding="utf-8") as fh:
        fh.write("# open items\nformat: 99\nbranch: none\nitems: 0\napplied: none\n")

    done = run("left-open", "--track-root", root)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[0].startswith("open items: ")
    assert "- [verify] Minor A in foo.py" in done.stdout.splitlines()
