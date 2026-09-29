"""`preflight.git()` without `encoding` decoded with the console locale,
strictly: a non-ASCII filename or branch name that locale could not decode
made stdout `None` beside a real returncode on Windows, and raised
`UnicodeDecodeError` out of `git()` on POSIX (#190).

docs/design/2026-09-29-preflight-git-errors-diagnosis.md, ## Failing test 1-3.

Each test builds a real repo first, then pins `locale.getencoding` to ASCII --
`subprocess` looks it up per call -- so the decode fails on Linux CI too. Under
Python's UTF-8 mode that lookup is skipped, so there is nothing to reproduce.
"""
import locale
import subprocess
import sys

import pytest

import preflight

pytestmark = pytest.mark.skipif(
    sys.flags.utf8_mode, reason="UTF-8 mode ignores the locale encoding")

GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=t"]


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo)] + GIT_ID + list(args),
                   capture_output=True, text=True, encoding="utf-8")


def make_repo(tmp_path, branch="track/x"):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-b", "main", str(repo)],
                   capture_output=True, text=True)
    (repo / "f.txt").write_text("orig\n", encoding="utf-8")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-m", "root")
    git(repo, "switch", "-c", branch)
    return repo


def make_track(tmp_path):
    track = tmp_path / "track"
    track.mkdir()
    rows = [("intake", "", "—", ""), ("discover", "", "", ""),
            ("design", "", "", ""), ("build", "", "", ""),
            ("verify", "done", "—", ""), ("ship", "", "", "")]
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(track)


def test_ship_untracked_non_ascii_name_does_not_raise(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    track = make_track(tmp_path)
    (repo / "測試檔案.txt").write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(locale, "getencoding", lambda: "ascii")

    result = preflight.ship(track, str(repo))

    assert result[1] == (True, "clean_tree (working tree is clean, or holds only "
                         "untracked files, which the squash neither includes nor touches)")


def test_verify_quotepath_false_non_ascii_name_does_not_raise(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    git(repo, "config", "core.quotePath", "false")
    (repo / "€.txt").write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(locale, "getencoding", lambda: "ascii")

    result = preflight.verify(str(tmp_path / "track"), str(repo))

    assert result == [(True, "has_changes (uncommitted changes)")]


def test_current_branch_non_ascii_branch(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, branch="track/測試")
    monkeypatch.setattr(locale, "getencoding", lambda: "ascii")

    assert preflight.current_branch(str(repo)) == "track/測試"
