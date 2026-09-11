"""preflight's `verify` gate: `has_changes` carries a change's size when git
can say what it is, and never fakes a `0 files, 0 lines` when it can't.

`change_size()` promises `(files, lines)` or `None`, never `(0, 0)` -- a
caller reading `0 files, 0 lines` would misread "couldn't tell" as "nothing
changed", which is the opposite of what `has_changes` FAIL already means.
This file is the one place that promise is checked end to end, through the
subprocess boundary `verify()` actually runs behind.
"""
import os
import re
import subprocess
import sys

import ledger

PREFLIGHT_PY = os.path.join(os.path.dirname(ledger.__file__), "preflight.py")


def init_repo(path):
    subprocess.run(["git", "init", str(path)], capture_output=True, text=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.email=t@example.com",
                    "-c", "user.name=t", "commit", "--allow-empty", "-m", "root"],
                   capture_output=True, text=True)


def run_verify(track, project):
    return subprocess.run(
        [sys.executable, PREFLIGHT_PY, "verify", "--track-dir", str(track),
         "--project-dir", str(project)],
        capture_output=True, text=True, encoding="utf-8")


def has_changes_line(stdout):
    for line in stdout.splitlines():
        if "has_changes (" in line:
            return line
    return ""


def test_a_modified_tracked_file_puts_two_numbers_in_the_label(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    init_repo(project)
    tracked = project / "tracked.txt"
    tracked.write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "tracked.txt"],
                   capture_output=True, text=True)
    subprocess.run(["git", "-C", str(project), "-c", "user.email=t@example.com",
                    "-c", "user.name=t", "commit", "-m", "add"],
                   capture_output=True, text=True)
    tracked.write_text("committed\nand modified\n", encoding="utf-8")

    track = tmp_path / "track"
    track.mkdir()
    done = run_verify(track, project)

    assert "has_changes (" in done.stdout
    assert " files, " in done.stdout
    assert " lines)" in done.stdout


def test_an_untracked_only_tree_falls_back_to_todays_wording(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    init_repo(project)
    (project / "scratch.txt").write_text("nobody has committed this\n", encoding="utf-8")

    track = tmp_path / "track"
    track.mkdir()
    done = run_verify(track, project)

    assert "0 files, 0 lines" not in done.stdout
    line = has_changes_line(done.stdout)
    assert line
    assert not re.search(r"\d", line)


def test_a_directory_that_is_not_a_repo_says_so_and_prints_no_zeroes(tmp_path):
    project = tmp_path / "not-a-repo"
    project.mkdir()

    track = tmp_path / "track"
    track.mkdir()
    done = run_verify(track, project)

    assert "has_changes (" in done.stdout
    assert "0 files, 0 lines" not in done.stdout
