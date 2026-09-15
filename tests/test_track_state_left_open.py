"""PB-08 (issue #92): `track_state.py left-open` reads state.md's fixed
`Left open:` marker out of each stage's note cell and prints it, so
`/cai:track done` can relay it before a track is archived and its notes
become harder to find.
"""
import os
import subprocess
import sys

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
    assert done.stdout.count("- [") == 3
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("- [")]
    assert lines == [
        "- [verify] Minor A in foo.py",
        "- [verify] parked proposal B",
        "- [ship] tag v1.2 waiting on the person",
    ]


def test_no_marker_anywhere_exits_0_with_a_fallback_and_no_bullets(tmp_path):
    root, track_dir = make_track(tmp_path, NO_MARKER_ROWS)

    done = run("left-open", "--track-root", root)
    assert done.returncode == 0, done.stderr
    assert "billing" in done.stdout
    assert 'no "Left open:" marker' in done.stdout
    assert os.path.join(track_dir, "state.md") in done.stdout
    assert done.stdout.count("- [") == 0


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
    assert track_state.left_open_items(text) == [
        ("verify", "Minor A in foo.py"),
        ("verify", "parked proposal B"),
        ("ship", "tag v1.2 waiting on the person"),
    ]
