"""A git call that failed, or did not answer, was read as the nearest normal
answer (#191): `rev-parse` not answering said "not a git repository",
`diff --quiet` exiting 128 said "nothing to review", and `check-ignore`
exiting 128 said "NOT ignored".

docs/design/2026-09-29-preflight-git-errors-diagnosis.md, ## Failing test
4-7 and 10. Stubs replace `preflight.git` in the shape of
tests/test_preflight_git_status_failure.py and defer every other call to the
real git.
"""
import subprocess

import pytest

import preflight
import track_start

GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=t"]


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo)] + GIT_ID + list(args),
                   capture_output=True, text=True, encoding="utf-8")


def make_repo(tmp_path, with_diff=False):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-b", "main", str(repo)],
                   capture_output=True, text=True)
    (repo / "f.txt").write_text("orig\n", encoding="utf-8")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-m", "root")
    git(repo, "checkout", "-b", "feat")
    if with_diff:
        (repo / "f.txt").write_text("changed\n", encoding="utf-8")
        git(repo, "add", "f.txt")
        git(repo, "commit", "-m", "feat advances")
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


def stub(monkeypatch, prefix, returncode=None, stderr=""):
    """`preflight.git` answers a call starting with `prefix` the given way
    (None when `returncode` is None) and defers everything else to real git."""
    real_git = preflight.git

    def fake_git(cwd, *args, encoding=None):
        if args[:len(prefix)] == prefix:
            if returncode is None:
                return None
            return subprocess.CompletedProcess(["git", *args], returncode, "", stderr)
        return real_git(cwd, *args, encoding=encoding)

    monkeypatch.setattr(preflight, "git", fake_git)


def test_verify_diff_quiet_exit_128_names_the_failure(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    stub(monkeypatch, ("diff", "--quiet"), 128, "fatal: bad revision\n")

    assert preflight.verify(str(tmp_path / "track"), str(repo)) == [
        (False, "has_changes (git diff failed: fatal: bad revision)")]


def test_verify_diff_quiet_no_answer_names_the_failure(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    stub(monkeypatch, ("diff", "--quiet"))

    assert preflight.verify(str(tmp_path / "track"), str(repo)) == [
        (False, "has_changes (git diff did not answer)")]


def test_verify_diff_quiet_failure_escapes_control_chars(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    stub(monkeypatch, ("diff", "--quiet"), 128, "fatal: bad \x1b[2K\x08 path\n")

    assert preflight.verify(str(tmp_path / "track"), str(repo)) == [
        (False, "has_changes (git diff failed: fatal: bad \\x1b[2K\\x08 path)")]


def test_verify_diff_quiet_failure_does_not_block_a_dirty_tree(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    (repo / "f.txt").write_text("dirty\n", encoding="utf-8")
    stub(monkeypatch, ("diff", "--quiet"), 128, "fatal: bad revision\n")

    result = preflight.verify(str(tmp_path / "track"), str(repo))

    assert result[0][0] is True


def test_verify_diff_quiet_exit_1_is_a_diff(tmp_path):
    repo = make_repo(tmp_path, with_diff=True)

    result = preflight.verify(str(tmp_path / "track"), str(repo))

    assert result[0][0] is True
    assert result[0][1].startswith("has_changes (diff from main")


def _intake(repo, track):
    return preflight.intake(track, str(repo))[0]


def _ship(repo, track):
    result = preflight.ship(track, str(repo))
    return result[1:4]


SEVEN_CALLERS = [
    ("intake", lambda repo, track: _intake(repo, track),
     (False, "not_main_branch (git did not answer)")),
    ("track_ignored", lambda repo, track: preflight.track_ignored(track, str(repo)),
     (True, "track_ignored (git did not answer)")),
    ("verify", lambda repo, track: preflight.verify(track, str(repo)),
     [(False, "has_changes (git did not answer)")]),
    ("untracked_since_start",
     lambda repo, track: preflight.untracked_since_start(track, str(repo)),
     (True, "untracked_since_start (not checked: git did not answer)")),
    ("docs_not_in_git", lambda repo, track: preflight.docs_not_in_git(track, str(repo)),
     (True, "docs_not_in_git (not checked: git did not answer)")),
    ("ship", lambda repo, track: _ship(repo, track),
     [(False, "clean_tree (git did not answer)"),
      (False, "not_main_branch (git did not answer)"),
      (True, "merges_cleanly (not checked: git did not answer)")]),
    ("track_start", lambda repo, track: track_start.start(track, str(repo)),
     (2, "git did not answer -- stopping")),
]


@pytest.mark.parametrize("name,call,expected", SEVEN_CALLERS,
                         ids=[c[0] for c in SEVEN_CALLERS])
def test_is_git_repo_no_answer_is_not_called_not_a_repo(
        tmp_path, monkeypatch, name, call, expected):
    repo = make_repo(tmp_path)
    track = make_track(tmp_path)
    stub(monkeypatch, ("rev-parse", "--is-inside-work-tree"))

    result = call(repo, track)

    assert "is not a git repository" not in str(result)
    assert result == expected


def test_track_ignored_check_ignore_exit_128_names_the_failure(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    stub(monkeypatch, ("check-ignore",), 128, "fatal: simulated failure\n")

    assert preflight.track_ignored(make_track(tmp_path), str(repo)) == (
        True, "track_ignored (git check-ignore failed: fatal: simulated failure)")


def test_track_ignored_check_ignore_failure_escapes_control_chars(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    stub(monkeypatch, ("check-ignore",), 128, "fatal: bad \x1b[2K\x08 path\n")

    assert preflight.track_ignored(make_track(tmp_path), str(repo)) == (
        True, "track_ignored (git check-ignore failed: fatal: bad \\x1b[2K\\x08 path)")


def test_track_ignored_exit_1_is_still_not_ignored(tmp_path):
    repo = make_repo(tmp_path)
    # Inside the repo: check-ignore exits 128, not 1, for a path outside it.
    track = repo / ".claude" / "track" / "x"

    result = preflight.track_ignored(str(track), str(repo))

    assert result[0] is True
    assert "is NOT ignored" in result[1]


def test_verify_base_ref_no_answer_names_the_failure(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    real_git = preflight.git

    def fake_git(cwd, *args, encoding=None):
        if args[:2] == ("symbolic-ref", "--short") or args[:3] == ("rev-parse", "--verify", "--quiet"):
            return None
        return real_git(cwd, *args, encoding=encoding)

    monkeypatch.setattr(preflight, "git", fake_git)

    assert preflight.verify(str(tmp_path / "track"), str(repo)) == [
        (False, "has_changes (git did not answer while finding the base ref)")]


def test_verify_base_ref_no_answer_does_not_block_a_dirty_tree(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    (repo / "f.txt").write_text("dirty\n", encoding="utf-8")
    real_git = preflight.git

    def fake_git(cwd, *args, encoding=None):
        if args[:2] == ("symbolic-ref", "--short") or args[:3] == ("rev-parse", "--verify", "--quiet"):
            return None
        return real_git(cwd, *args, encoding=encoding)

    monkeypatch.setattr(preflight, "git", fake_git)

    result = preflight.verify(str(tmp_path / "track"), str(repo))

    assert result[0][0] is True
