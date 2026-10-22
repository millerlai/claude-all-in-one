"""#470: files this worktree and another worktree's track both change are
named before a merge finds them, and preflight passes them on as a WARN
that never blocks. Real repositories and worktrees."""
import os
import subprocess
import sys

import pytest

import preflight
import track_overlap

GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=t"]


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo)] + GIT_ID + list(args),
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def current(top, feature):
    root = top / ".cai" / "track"
    root.mkdir(parents=True, exist_ok=True)
    (root / "current").write_text(feature, encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    main = tmp_path / "main"
    subprocess.run(["git", "init", "-q", "-b", "main", str(main)], check=True)
    (main / ".gitignore").write_text(".cai/\n.claude/\n", encoding="utf-8")
    for name in ("shared.py", "a_only.py", "b_only.py"):
        (main / name).write_text("x = 1\n", encoding="utf-8")
    git(main, "add", "-A")
    git(main, "commit", "-q", "-m", "root")
    wts = {}
    for name in ("a", "b"):
        wt = main / ".claude" / "worktrees" / name
        git(main, "worktree", "add", "-q", "-b", "worktree-" + name, str(wt))
        current(wt, "feat-" + name)
        wts[name] = wt
    return main, wts


def overlaps(path):
    return track_overlap.overlaps(str(path))


def test_a_committed_change_on_both_sides_is_named(repo):
    _, wts = repo
    for name in ("a", "b"):
        (wts[name] / "shared.py").write_text("x = %r\n" % name, encoding="utf-8")
        (wts[name] / ("%s_only.py" % name)).write_text("y = 2\n", encoding="utf-8")
        git(wts[name], "commit", "-q", "-am", name)
    lines, code = overlaps(wts["a"])
    assert code == 0
    assert lines == ["overlap shared.py: feat-a (.claude/worktrees/a), feat-b (.claude/worktrees/b)"]


def test_uncommitted_and_untracked_changes_count_too(repo):
    _, wts = repo
    (wts["a"] / "shared.py").write_text("x = 3\n", encoding="utf-8")
    (wts["b"] / "shared.py").write_text("x = 4\n", encoding="utf-8")
    (wts["a"] / "new.py").write_text("", encoding="utf-8")
    (wts["b"] / "new.py").write_text("", encoding="utf-8")
    lines, _ = overlaps(wts["a"])
    assert [l.split(":")[0] for l in lines] == ["overlap new.py", "overlap shared.py"]


def test_no_shared_file_prints_nothing(repo):
    _, wts = repo
    (wts["a"] / "a_only.py").write_text("y = 2\n", encoding="utf-8")
    (wts["b"] / "b_only.py").write_text("y = 2\n", encoding="utf-8")
    assert overlaps(wts["a"]) == ([], 0)


def test_a_worktree_without_a_track_is_not_compared(repo):
    _, wts = repo
    (wts["b"] / ".cai" / "track" / "current").unlink()
    for name in ("a", "b"):
        (wts[name] / "shared.py").write_text("x = 5\n", encoding="utf-8")
    assert overlaps(wts["a"]) == ([], 0)


def test_the_main_checkout_with_no_track_is_labelled_so(repo):
    main, wts = repo
    (main / "shared.py").write_text("x = 6\n", encoding="utf-8")
    (wts["b"] / "shared.py").write_text("x = 7\n", encoding="utf-8")
    lines, _ = overlaps(main)
    assert lines == ["overlap shared.py: no track (.), feat-b (.claude/worktrees/b)"]


def test_outside_git_it_says_so_and_exits_2(tmp_path):
    lines, code = overlaps(tmp_path)
    assert code == 2 and "nothing to compare" in lines[0]


def test_preflight_passes_with_a_warn_line(repo):
    _, wts = repo
    for name in ("a", "b"):
        (wts[name] / "shared.py").write_text("x = 8\n", encoding="utf-8")
    ok, label = preflight.worktree_overlap(str(wts["a"]))
    assert ok is True
    assert label.startswith("worktree_overlap (WARN: 1 file(s) also changed by another")
    assert "shared.py: feat-a" in label


def test_preflight_with_nothing_shared_passes_quietly(repo):
    _, wts = repo
    assert preflight.worktree_overlap(str(wts["a"])) == (
        True, "worktree_overlap (no other worktree's track changes the same files)")


def test_preflight_never_blocks_when_it_cannot_look(tmp_path):
    ok, label = preflight.worktree_overlap(str(tmp_path))
    assert ok is True and label.startswith("worktree_overlap (not checked: ")


def test_preflight_caps_the_named_files(repo, monkeypatch):
    _, wts = repo
    names = ["f%02d.py" % i for i in range(preflight.MAX_CONFLICTS_SHOWN + 2)]
    for name in ("a", "b"):
        for f in names:
            (wts[name] / f).write_text("", encoding="utf-8")
    ok, label = preflight.worktree_overlap(str(wts["a"]))
    assert ok and "and 2 more" in label


def test_main_prints_the_lines(repo, capsys):
    _, wts = repo
    for name in ("a", "b"):
        (wts[name] / "shared.py").write_text("x = 9\n", encoding="utf-8")
    assert track_overlap.main(["--project-dir", str(wts["a"])]) == 0
    assert capsys.readouterr().out.startswith("overlap shared.py: ")
