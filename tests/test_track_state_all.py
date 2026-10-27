"""#469: `track_state.py status --all` lists every git worktree's current
track, so a session left in the main checkout sees the tracks running in
worktrees (each worktree keeps its own .cai/). Real repositories and
worktrees; reads only."""
import os
import shutil
import subprocess
import sys

import pytest

import pending
import track_state

SCRIPT = os.path.join(os.path.dirname(track_state.__file__), "track_state.py")
GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=t"]
STAGES = ("design", "build", "verify", "ship")
REPORT = ("## Pending questions\n"
          "1. Commit per unit?\n   Background: a\n   Options: b\n   Blocks: c\n"
          "   Why asked: gate - r\n"
          "2. Parallel lane?\n   Background: a\n   Options: b\n   Blocks: c\n"
          "   Why asked: gate - r\n")


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo)] + GIT_ID + list(args),
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def track(top, feature, statuses):
    d = top / ".cai" / "track" / feature
    d.mkdir(parents=True)
    rows = ["| stage | status | artifact | note |", "|---|---|---|---|"]
    rows += ["| %s | %s |  |  |" % (sid, st) for sid, st in zip(STAGES, statuses)]
    (d / "state.md").write_text("# t\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
    (top / ".cai" / "track" / "current").write_text(feature, encoding="utf-8")
    return d


@pytest.fixture
def repo(tmp_path):
    main = tmp_path / "main"
    subprocess.run(["git", "init", "-q", "-b", "main", str(main)], check=True)
    git(main, "commit", "-q", "--allow-empty", "-m", "root")
    for name in ("login-fix", "export-csv"):
        git(main, "worktree", "add", "-q", "-b", "worktree-" + name,
            str(main / ".claude" / "worktrees" / name))
    return main


def run(cwd):
    return subprocess.run([sys.executable, SCRIPT, "status", "--all"], cwd=str(cwd),
                          capture_output=True, text=True, encoding="utf-8")


def rows(out):
    return [line.split() for line in out.splitlines()]


def test_one_row_per_worktree_with_its_track_and_next_stage(repo):
    wts = repo / ".claude" / "worktrees"
    track(wts / "login-fix", "login-fix", ["done", "done", "", ""])
    d = track(wts / "export-csv", "export-csv", ["done", "in-progress", "", ""])
    report = repo.parent / "report.md"
    report.write_text(REPORT, encoding="utf-8")
    pending.start(str(d), "build", 1, str(report))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    got = rows(result.stdout)
    assert got[0] == ["worktree", "branch", "track", "next", "pending"]
    assert got[1] == [".", "main", "-", "-", "-"]
    by_track = {r[2]: r for r in got[2:]}
    assert by_track["login-fix"] == [".claude/worktrees/login-fix", "worktree-login-fix",
                                     "login-fix", "verify", "-"]
    assert by_track["export-csv"] == [".claude/worktrees/export-csv", "worktree-export-csv",
                                      "export-csv", "build", "(in-progress)", "2", "questions"]


def test_the_same_table_from_inside_a_worktree(repo):
    wts = repo / ".claude" / "worktrees"
    track(wts / "login-fix", "login-fix", ["done"] * 4)
    got = rows(run(wts / "login-fix").stdout)
    assert got[1][0] == "."
    assert [".claude/worktrees/login-fix", "worktree-login-fix", "login-fix", "done", "-"] in got


def test_a_broken_track_costs_its_row_only(repo):
    wts = repo / ".claude" / "worktrees"
    d = track(wts / "login-fix", "login-fix", ["done"] * 4)
    (d / "state.md").unlink()
    track(wts / "export-csv", "export-csv", ["done"] * 4)
    (wts / "export-csv" / ".cai" / "track" / "export-csv" / "state.md").write_text(
        "| stage | status |\n|---|---|\n| design | done |\n", encoding="utf-8")
    result = run(repo)
    assert result.returncode == 0
    assert "(no state.md)" in result.stdout
    assert "(state.md disagrees with stages.json)" in result.stdout


def test_a_worktree_whose_directory_is_gone_is_named(repo):
    shutil.rmtree(repo / ".claude" / "worktrees" / "export-csv")
    out = run(repo).stdout
    assert "(directory gone; git worktree prune)" in out
    assert out.count("\n") == 4


def test_an_unreadable_pending_file_costs_one_cell(repo):
    d = track(repo / ".claude" / "worktrees" / "login-fix", "login-fix", ["done", "", "", ""])
    (d / "pending.md").write_text("not a pending file\n", encoding="utf-8")
    assert "(unreadable pending.md)" in run(repo).stdout


def test_outside_git_it_is_the_ordinary_status(tmp_path):
    track(tmp_path, "solo", ["done", "", "", ""])
    result = run(tmp_path)
    assert result.returncode == 0
    assert result.stdout.startswith("current: solo\n")


def test_all_goes_with_status_only(tmp_path):
    result = subprocess.run([sys.executable, SCRIPT, "resolve", "--all"], cwd=str(tmp_path),
                            capture_output=True, text=True)
    assert result.returncode == 1 and "--all goes with status only" in result.stderr


def test_a_detached_worktree_says_so(repo):
    sha = git(repo, "rev-parse", "HEAD")
    git(repo, "worktree", "add", "-q", "--detach", str(repo.parent / "loose"), sha)
    out = run(repo).stdout
    # `git worktree list` prints forward slashes on Windows too, and a worktree
    # outside the main checkout is shown by that path as git gave it.
    assert (repo.parent / "loose").as_posix() in out and "(detached HEAD)" in out
