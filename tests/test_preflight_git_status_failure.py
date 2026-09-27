"""`git status --porcelain` failing (non-zero exit, or `git()` returning
`None`) used to be read as an answer instead of a non-answer:

- `ship`'s `clean_tree` saw empty stdout on a 128 exit and called the tree
  clean (a check that never ran, reported PASS).
- `verify`'s `has_changes` folded any failed status into "not dirty", so a
  branch with a base diff still PASSed (uncommitted state never seen) and
  one without fell to the wrong label, "nothing to review".

Fixed by `_status_problem()` in preflight.py: `None` or a non-zero exit is
its own answer, checked before stdout is ever read, exactly as
`current_branch()` already treats `UNKNOWN_BRANCH` apart from a genuine
`None` (see `preflight.py`'s own docstring on that function).

docs/design/2026-09-26-preflight-git-status-failure-diagnosis.md, ## Failing
test. Diagnosis path -- these are the tests that pin the fix.
"""
import subprocess

import preflight


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@example.com",
                    "-c", "user.name=t"] + list(args),
                   capture_output=True, text=True, encoding="utf-8")


def make_repo(tmp_path, with_diff):
    """A real repo on a feature branch off `main`, so `find_base_ref` finds
    a local base. `with_diff` adds one commit on the feature branch so
    `verify()` sees a base diff; without it the branches are identical, so
    there is nothing to review once status also comes back clean."""
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
    """A six-row state.md fixture with verify's status set to done, so
    ship()'s status_check always passes -- these tests are about clean_tree,
    the same shape test_preflight_merge_check.py's make_track uses."""
    track = tmp_path / "track"
    track.mkdir()
    rows = [("intake", "", "—", ""), ("discover", "", "", ""),
            ("design", "", "", ""), ("build", "", "", ""),
            ("verify", "done", "—", ""), ("ship", "", "", "")]
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(track)


def stub_status(returncode, stdout="", stderr=""):
    """Replaces preflight.git with a fake that answers `status --porcelain`
    the given way and defers every other call to the real git -- same shape
    as test_preflight_merge_check.py's `--version` stub."""
    real_git = preflight.git

    def fake_git(cwd, *args, encoding=None):
        if args == ("status", "--porcelain"):
            if returncode is None:
                return None
            return subprocess.CompletedProcess(
                ["git", "status", "--porcelain"], returncode, stdout, stderr)
        return real_git(cwd, *args, encoding=encoding)

    return fake_git, real_git


def test_ship_status_exit_128_fails_clean_tree(tmp_path):
    repo = make_repo(tmp_path, with_diff=False)
    track = make_track(tmp_path)
    fake_git, real_git = stub_status(128, "", "fatal: simulated failure\n")
    try:
        preflight.git = fake_git
        result = preflight.ship(track, str(repo))
    finally:
        preflight.git = real_git
    assert result[1] == (False, "clean_tree (git status failed: fatal: simulated failure)")


def test_ship_status_exit_128_without_stderr_says_no_message(tmp_path):
    repo = make_repo(tmp_path, with_diff=False)
    track = make_track(tmp_path)
    fake_git, real_git = stub_status(128, "", "")
    try:
        preflight.git = fake_git
        result = preflight.ship(track, str(repo))
    finally:
        preflight.git = real_git
    assert result[1] == (False, "clean_tree (git status failed: no message)")


def test_ship_status_no_answer_fails_clean_tree(tmp_path):
    repo = make_repo(tmp_path, with_diff=False)
    track = make_track(tmp_path)
    fake_git, real_git = stub_status(None)
    try:
        preflight.git = fake_git
        result = preflight.ship(track, str(repo))
    finally:
        preflight.git = real_git
    assert result[1] == (False, "clean_tree (git status did not answer)")


def test_verify_status_exit_128_with_base_diff_fails(tmp_path):
    repo = make_repo(tmp_path, with_diff=True)
    fake_git, real_git = stub_status(128, "", "fatal: simulated failure\n")
    try:
        preflight.git = fake_git
        result = preflight.verify(str(tmp_path / "track"), str(repo))
    finally:
        preflight.git = real_git
    assert result == [(False, "has_changes (git status failed: fatal: simulated failure)")]


def test_verify_status_exit_128_never_says_nothing_to_review(tmp_path):
    repo = make_repo(tmp_path, with_diff=False)
    fake_git, real_git = stub_status(128, "", "fatal: simulated failure\n")
    try:
        preflight.git = fake_git
        result = preflight.verify(str(tmp_path / "track"), str(repo))
    finally:
        preflight.git = real_git
    assert result == [(False, "has_changes (git status failed: fatal: simulated failure)")]


def test_verify_status_no_answer_with_base_diff_fails(tmp_path):
    repo = make_repo(tmp_path, with_diff=True)
    fake_git, real_git = stub_status(None)
    try:
        preflight.git = fake_git
        result = preflight.verify(str(tmp_path / "track"), str(repo))
    finally:
        preflight.git = real_git
    assert result == [(False, "has_changes (git status did not answer)")]
