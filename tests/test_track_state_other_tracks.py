"""#204: `/cai:track status` names where each other active track stopped,
instead of listing bare names. `next:` stays reserved for the current track,
so an exit-2 path must still print none of it even when other tracks exist.
"""
import os
import subprocess
import sys

import ledger

SCRIPTS = os.path.dirname(ledger.__file__)
TRACK_STATE = os.path.join(SCRIPTS, "track_state.py")

FULL_ROWS = [("intake", "done", "—", ""), ("discover", "done", "—", ""),
             ("design", "done", "—", ""), ("build", "done", "—", ""),
             ("verify", "done", "—", ""), ("ship", "done", "—", "")]


def write_state(track_dir, rows):
    lines = ["# fixture", "", "branch: feat/fixture", "started: 2026-08-27", "",
             "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    os.makedirs(track_dir, exist_ok=True)
    with open(os.path.join(track_dir, "state.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def make_root(tmp_path, current, current_rows, others=()):
    """A track root with `current` pointing at a valid track built from
    `current_rows`, plus one directory per (name, rows-or-None) in `others`.
    `rows=None` leaves that other track with no state.md at all."""
    root = tmp_path / "track"
    write_state(str(root / current), current_rows)
    (root / "current").write_text(current, encoding="utf-8")
    for name, rows in others:
        if rows is None:
            (root / name).mkdir(parents=True)
        else:
            write_state(str(root / name), rows)
    return str(root)


def run(root):
    return subprocess.run([sys.executable, TRACK_STATE, "status", "--track-root", root],
                          capture_output=True, text=True, encoding="utf-8")


def test_other_track_shows_where_it_stopped(tmp_path):
    stopped_at_design = [("intake", "done", "—", ""), ("discover", "done", "—", ""),
                          ("design", "", "", ""), ("build", "", "", ""),
                          ("verify", "", "", ""), ("ship", "", "", "")]
    root = make_root(tmp_path, "first", FULL_ROWS, [("second", stopped_at_design)])

    done = run(root)
    assert done.returncode == 0, done.stderr
    assert "  second  stopped at: design (not started)" in done.stdout


def test_other_track_in_progress_shows_status(tmp_path):
    in_progress = [("intake", "done", "—", ""), ("discover", "done", "—", ""),
                   ("design", "done", "—", ""), ("build", "in-progress", "—", "unit 3 of 5"),
                   ("verify", "", "", ""), ("ship", "", "", "")]
    root = make_root(tmp_path, "first", FULL_ROWS, [("second", in_progress)])

    done = run(root)
    assert done.returncode == 0, done.stderr
    assert "  second  stopped at: build (in-progress)" in done.stdout


def test_finished_other_track(tmp_path):
    root = make_root(tmp_path, "first", FULL_ROWS, [("second", FULL_ROWS)])

    done = run(root)
    assert done.returncode == 0, done.stderr
    assert "  second  every stage done or skipped" in done.stdout


def test_other_track_without_state_md(tmp_path):
    root = make_root(tmp_path, "first", FULL_ROWS, [("second", None)])

    done = run(root)
    assert done.returncode == 0, done.stderr
    assert "  second  (no state.md)" in done.stdout


def test_other_track_with_bad_table_does_not_change_exit(tmp_path):
    short_rows = FULL_ROWS[:5]  # missing "ship" -- disagrees with stages.json
    root = make_root(tmp_path, "first", FULL_ROWS, [("second", short_rows)])

    done = run(root)
    assert done.returncode == 0, done.stderr
    assert "  second  (state.md disagrees with stages.json)" in done.stdout


def test_no_other_tracks_output_unchanged(tmp_path):
    root = make_root(tmp_path, "first", FULL_ROWS, [])

    done = run(root)
    assert done.returncode == 0, done.stderr
    assert "other active tracks: none" in done.stdout


def test_exit2_path_still_prints_no_next_even_with_other_tracks(tmp_path):
    illegal = [("intake", "passed", "—", ""), ("discover", "done", "—", ""),
               ("design", "done", "—", ""), ("build", "done", "—", ""),
               ("verify", "done", "—", ""), ("ship", "done", "—", "")]
    root = make_root(tmp_path, "first", illegal, [("second", FULL_ROWS)])

    done = run(root)
    assert done.returncode == 2
    assert "next:" not in done.stdout
    assert "  second  every stage done or skipped" in done.stdout
