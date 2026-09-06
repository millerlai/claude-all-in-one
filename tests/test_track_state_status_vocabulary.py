"""UC4 follow-up (issue #46): a status column written outside the
vocabulary state.md actually has -- e.g. a ledger.OUTCOMES word like
"passed" landing in the status cell -- must fail the gate instead of
silently being treated as "not done" everywhere but reported nowhere.
"""
import os
import subprocess
import sys

import ledger

SCRIPTS = os.path.dirname(ledger.__file__)

ROWS = [("intake", "done", "—", ""), ("discover", "done", "—", ""),
        ("design", "skipped", "—", "not needed"),
        ("build", "in-progress", "—", "unit 3 of 5"),
        ("verify", "", "", ""), ("ship", "", "", "")]


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


def test_a_legal_table_still_exits_0_and_names_the_next_stage(tmp_path):
    root, _ = make_track(tmp_path)

    done = run("status", "--track-root", root)
    assert done.returncode == 0, done.stderr
    assert "next: build" in done.stdout


def test_an_illegal_status_exits_2_and_prints_no_next_line(tmp_path):
    rows = list(ROWS)
    rows[0] = ("intake", "passed", "—", "")
    root, _ = make_track(tmp_path, rows)

    done = run("status", "--track-root", root)
    assert done.returncode == 2
    assert "next:" not in done.stdout
    assert "current:" in done.stdout


def test_the_message_names_the_stage_the_value_and_the_four_legal_ones(tmp_path):
    rows = list(ROWS)
    rows[0] = ("intake", "passed", "—", "")
    root, _ = make_track(tmp_path, rows)

    done = run("status", "--track-root", root)
    assert done.returncode == 2
    for expected in ("intake", "passed", "in-progress", "done", "skipped", "(empty)"):
        assert expected in done.stderr


def test_two_illegal_rows_each_print_their_own_line_in_stage_order(tmp_path):
    # Design's failure-modes table: "multiple bad rows -- each prints its own
    # stderr line, in stages.json order, seen all at once." A regression that
    # reports only the first bad row, or reorders them, must go red here.
    rows = list(ROWS)
    rows[0] = ("intake", "passed", "—", "")
    rows[3] = ("build", "fooled", "—", "unit 3 of 5")
    root, _ = make_track(tmp_path, rows)

    done = run("status", "--track-root", root)
    assert done.returncode == 2
    legal = "(empty), in-progress, done, skipped"
    intake_line = "unknown status for intake: passed (expected one of %s)" % legal
    build_line = "unknown status for build: fooled (expected one of %s)" % legal
    assert intake_line in done.stderr
    assert build_line in done.stderr
    assert done.stderr.index(intake_line) < done.stderr.index(build_line)
