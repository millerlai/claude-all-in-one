"""branch_sweep's classification, against real git repositories.

The case that justifies the file is `squash_merged_branch_is_deletable`: it is
the one `git branch --merged` cannot answer, and the reason the script reads
three signals instead of the one every other tool reads. The rest guard the
safety policy around it -- held, ahead and gone must survive every merge signal,
because each of them names a branch whose deletion would either fail or lose the
only copy of something. Backup branches left behind by `ship` before it squashes
are covered too.
"""
import json
import subprocess
import sys

import pytest

import branch_sweep
import fake_gh

GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=t"]


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo)] + GIT_ID + list(args),
                          capture_output=True, text=True, encoding="utf-8")
    return done.stdout.strip(), done.returncode


def init_repo(path, remote):
    """A repo on `main` with one commit, pushed to a real bare remote.

    The remote has to be real. Faking an upstream with `update-ref
    refs/remotes/origin/x` alone does not work -- `git branch
    --set-upstream-to` rejects it with "not a branch" unless the remote is
    configured -- and a test that skipped it would leave `%(upstream:track)`
    empty, which is exactly the field the ahead and gone cases turn on.
    """
    subprocess.run(["git", "init", "--bare", str(remote)],
                   capture_output=True, text=True)
    subprocess.run(["git", "init", "-b", "main", str(path)],
                   capture_output=True, text=True)
    git(path, "remote", "add", "origin", str(remote))
    git(path, "commit", "--allow-empty", "-m", "root")
    git(path, "push", "-u", "origin", "main")
    return path


def commit_on(repo, branch, message):
    """Branch off main, add one empty commit, return to main."""
    git(repo, "checkout", "-b", branch, "main")
    git(repo, "commit", "--allow-empty", "-m", message)
    sha, _ = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "main")
    return sha


def push(repo, branch):
    git(repo, "push", "-u", "origin", branch)


def delete_on_remote(repo, branch):
    """What a merge does for itself where the remote deletes head branches."""
    git(repo, "push", "origin", "--delete", branch)
    git(repo, "fetch", "--prune")


def use_fake_gh(monkeypatch, merged=(), mode="ok", stderr="", exit_code="1"):
    """Point the script's gh seam at tests/fake_gh.py, answering `merged` as
    `gh pr list --json number,headRefName,mergedAt` would.

    Each entry in `merged` is a 2-tuple (number, head) -- omitting `mergedAt`
    from the row, same as a `gh` predating that field -- or a 3-tuple
    (number, head, merged_at), which adds it."""
    rows = []
    for entry in merged:
        row = {"number": entry[0], "headRefName": entry[1]}
        if len(entry) == 3:
            row["mergedAt"] = entry[2]
        rows.append(row)
    monkeypatch.setenv(branch_sweep.CLI_ENV, fake_gh.cli_argv())
    monkeypatch.setenv("FAKE_GH_MODE", mode)
    monkeypatch.setenv("FAKE_GH_STDOUT", json.dumps(rows))
    monkeypatch.setenv("FAKE_GH_STDERR", stderr)
    monkeypatch.setenv("FAKE_GH_EXIT", exit_code)


def statuses(repo):
    rows, note = branch_sweep.sweep("main", cwd=str(repo))
    return {name: status for name, status, _ in rows}, note


def why(repo, branch):
    rows, _ = branch_sweep.sweep("main", cwd=str(repo))
    return next(w for name, _, w in rows if name == branch)


@pytest.fixture
def repo(tmp_path):
    return init_repo(tmp_path / "repo", tmp_path / "remote.git")


def test_squash_merged_branch_is_deletable(repo, monkeypatch):
    """The whole point: git's own ancestry check says nothing about it."""
    commit_on(repo, "feat/squashed", "work")
    push(repo, "feat/squashed")
    use_fake_gh(monkeypatch, merged=[(106, "feat/squashed")])

    ancestry, _ = git(repo, "branch", "--merged", "main",
                      "--format=%(refname:short)")
    assert "feat/squashed" not in ancestry.splitlines()

    found, note = statuses(repo)
    assert found["feat/squashed"] == "deletable"
    assert note is None
    assert why(repo, "feat/squashed") == "pr: #106 merged"


def test_ancestry_merged_branch_is_deletable_without_any_pr(repo, monkeypatch):
    commit_on(repo, "feat/ff", "work")
    git(repo, "merge", "--ff-only", "feat/ff")
    use_fake_gh(monkeypatch, merged=[])

    found, _ = statuses(repo)
    assert found["feat/ff"] == "deletable"
    assert why(repo, "feat/ff") == "ancestry: already on main"


def test_branch_held_by_a_worktree_is_never_deletable(repo, tmp_path,
                                                      monkeypatch):
    commit_on(repo, "feat/held", "work")
    push(repo, "feat/held")
    git(repo, "worktree", "add", str(tmp_path / "wt"), "feat/held")
    use_fake_gh(monkeypatch, merged=[(102, "feat/held")])

    found, _ = statuses(repo)
    assert found["feat/held"] == "held"


def test_unpushed_commits_outrank_a_merged_pr(repo, monkeypatch):
    """A squash-merged branch committed to afterwards holds the only copy of
    those commits, so the merge signal must not win."""
    commit_on(repo, "feat/kept-going", "work")
    push(repo, "feat/kept-going")
    git(repo, "checkout", "feat/kept-going")
    git(repo, "commit", "--allow-empty", "-m", "after the merge")
    git(repo, "checkout", "main")
    use_fake_gh(monkeypatch, merged=[(99, "feat/kept-going")])

    found, _ = statuses(repo)
    assert found["feat/kept-going"] == "ahead"
    assert "1 commit(s)" in why(repo, "feat/kept-going")


def test_gone_upstream_is_reported_but_not_deletable(repo, monkeypatch):
    """Deleting a remote branch is not evidence anything was merged."""
    commit_on(repo, "feat/vanished", "work")
    push(repo, "feat/vanished")
    delete_on_remote(repo, "feat/vanished")
    use_fake_gh(monkeypatch, merged=[])

    found, _ = statuses(repo)
    assert found["feat/vanished"] == "gone"


def test_unmerged_branch_is_kept(repo, monkeypatch):
    commit_on(repo, "feat/live", "work")
    use_fake_gh(monkeypatch, merged=[])

    found, _ = statuses(repo)
    assert found["feat/live"] == "keep"


def test_base_branch_is_not_a_candidate(repo, monkeypatch):
    use_fake_gh(monkeypatch, merged=[])
    found, _ = statuses(repo)
    assert "main" not in found


def test_missing_gh_degrades_to_the_other_signals(repo, monkeypatch):
    """No gh on the machine: ancestry still decides, and the note says why a
    squash-merged branch could only read as keep."""
    commit_on(repo, "feat/ff", "work")
    git(repo, "merge", "--ff-only", "feat/ff")
    commit_on(repo, "feat/squashed", "work")
    monkeypatch.setenv(branch_sweep.CLI_ENV,
                       json.dumps([sys.executable, "-c",
                                   "raise SystemExit(127)"]))

    found, note = statuses(repo)
    assert found["feat/ff"] == "deletable"
    assert found["feat/squashed"] == "keep"
    assert note is not None


def test_gh_auth_failure_is_classified_and_never_echoed(repo, monkeypatch):
    """gh's 401 carries a credential-bearing api.github.com URL, so only the
    classified word may reach the output."""
    secret = "gh: Bad credentials (HTTP 401) https://x:TOKEN@api.github.com"
    commit_on(repo, "feat/live", "work")
    use_fake_gh(monkeypatch, mode="fail", stderr=secret)

    _, note = statuses(repo)
    assert note == "not-authenticated"

    rows, note = branch_sweep.sweep("main", cwd=str(repo))
    out = "\n".join(branch_sweep.render(rows, note, "main"))
    assert "TOKEN" not in out and "api.github.com" not in out


def test_delete_removes_only_the_deletable_ones(repo, tmp_path, monkeypatch):
    commit_on(repo, "feat/squashed", "work")
    push(repo, "feat/squashed")
    commit_on(repo, "feat/live", "work")
    commit_on(repo, "feat/held", "work")
    git(repo, "worktree", "add", str(tmp_path / "wt"), "feat/held")
    use_fake_gh(monkeypatch, merged=[(106, "feat/squashed"),
                                     (107, "feat/held")])

    assert branch_sweep.main(["--repo", str(repo), "--delete"]) == 0

    remaining, _ = git(repo, "for-each-ref", "--format=%(refname:short)",
                       "refs/heads")
    names = set(remaining.splitlines())
    assert "feat/squashed" not in names
    assert {"main", "feat/live", "feat/held"} <= names


def test_delete_prints_the_sha_that_undoes_it(repo, capsys, monkeypatch):
    sha = commit_on(repo, "feat/squashed", "work")
    push(repo, "feat/squashed")
    use_fake_gh(monkeypatch, merged=[(106, "feat/squashed")])

    branch_sweep.main(["--repo", str(repo), "--delete"])

    out = capsys.readouterr().out
    assert "git branch feat/squashed " + sha[:7] in out


def test_default_run_changes_nothing(repo, monkeypatch):
    commit_on(repo, "feat/squashed", "work")
    push(repo, "feat/squashed")
    use_fake_gh(monkeypatch, merged=[(106, "feat/squashed")])

    assert branch_sweep.main(["--repo", str(repo)]) == 0

    remaining, _ = git(repo, "for-each-ref", "--format=%(refname:short)",
                       "refs/heads")
    assert "feat/squashed" in remaining.splitlines()


def test_a_base_that_does_not_exist_exits_two(repo, capsys, monkeypatch):
    """Otherwise `--merged` just fails and every branch silently loses its
    ancestry signal -- a mistyped base would return a shorter table, not an
    error."""
    commit_on(repo, "feat/ff", "work")
    git(repo, "merge", "--ff-only", "feat/ff")
    use_fake_gh(monkeypatch, merged=[])

    assert branch_sweep.main(["--repo", str(repo), "--base", "mian"]) == 2
    assert "no such branch: mian" in capsys.readouterr().err


def test_outside_a_repository_exits_two(tmp_path, capsys):
    assert branch_sweep.main(["--repo", str(tmp_path)]) == 2
    assert "not a git repository" in capsys.readouterr().err


MERGED_AFTER = "2999-01-01T00:00:00Z"
MERGED_BEFORE = "2000-01-01T00:00:00Z"


def test_backup_of_a_squash_merged_source_is_deletable(repo, monkeypatch):
    commit_on(repo, "feat/squashed", "work")
    push(repo, "feat/squashed")
    use_fake_gh(monkeypatch, merged=[(106, "feat/squashed", MERGED_AFTER)])
    git(repo, "branch", "backup/feat/squashed-20260926-194453", "feat/squashed")

    found, _ = statuses(repo)
    assert found["backup/feat/squashed-20260926-194453"] == "deletable"
    assert why(repo, "backup/feat/squashed-20260926-194453") == (
        "backup of feat/squashed: pr #106 merged")


def test_backup_is_deletable_after_its_source_was_deleted(repo, monkeypatch):
    commit_on(repo, "feat/squashed", "work")
    push(repo, "feat/squashed")
    use_fake_gh(monkeypatch, merged=[(106, "feat/squashed", MERGED_AFTER)])
    git(repo, "branch", "backup/feat/squashed-20260926-194453", "feat/squashed")
    git(repo, "branch", "-D", "feat/squashed")

    found, _ = statuses(repo)
    assert found["backup/feat/squashed-20260926-194453"] == "deletable"
    assert why(repo, "backup/feat/squashed-20260926-194453") == (
        "backup of feat/squashed: pr #106 merged")


def test_backup_with_dashes_and_a_word_suffix_is_recognised(repo, monkeypatch):
    commit_on(repo, "fix/diagnosis-recognition-shape", "work")
    push(repo, "fix/diagnosis-recognition-shape")
    use_fake_gh(monkeypatch, merged=[
        (106, "fix/diagnosis-recognition-shape", MERGED_AFTER)])
    git(repo, "branch",
        "backup/fix-diagnosis-recognition-shape-20260926-presquash",
        "fix/diagnosis-recognition-shape")

    found, _ = statuses(repo)
    backup = "backup/fix-diagnosis-recognition-shape-20260926-presquash"
    assert found[backup] == "deletable"
    assert why(repo, backup) == (
        "backup of fix/diagnosis-recognition-shape: pr #106 merged")


def test_backup_of_an_unmerged_source_is_kept(repo, monkeypatch):
    commit_on(repo, "feat/live", "work")
    push(repo, "feat/live")
    use_fake_gh(monkeypatch, merged=[])
    git(repo, "branch", "backup/feat/live-20260926-194453", "feat/live")

    found, _ = statuses(repo)
    assert found["backup/feat/live-20260926-194453"] == "keep"
    assert why(repo, "backup/feat/live-20260926-194453") == "no merge signal"


def test_backups_are_kept_when_gh_is_unavailable(repo, monkeypatch):
    commit_on(repo, "feat/squashed", "work")
    push(repo, "feat/squashed")
    git(repo, "branch", "backup/feat/squashed-20260926-194453", "feat/squashed")
    use_fake_gh(monkeypatch, mode="fail", stderr="gh: some failure")

    found, note = statuses(repo)
    assert found["backup/feat/squashed-20260926-194453"] == "keep"
    assert note is not None


def test_backup_held_by_a_worktree_is_held(repo, tmp_path, monkeypatch):
    commit_on(repo, "feat/squashed", "work")
    push(repo, "feat/squashed")
    git(repo, "branch", "backup/feat/squashed-20260926-194453", "feat/squashed")
    git(repo, "worktree", "add", str(tmp_path / "wt"),
        "backup/feat/squashed-20260926-194453")
    use_fake_gh(monkeypatch, merged=[(106, "feat/squashed", MERGED_AFTER)])

    found, _ = statuses(repo)
    assert found["backup/feat/squashed-20260926-194453"] == "held"


def test_delete_prints_the_sha_that_undoes_a_backup(repo, capsys, monkeypatch):
    commit_on(repo, "feat/squashed", "work")
    push(repo, "feat/squashed")
    backup = "backup/feat/squashed-20260926-194453"
    git(repo, "branch", backup, "feat/squashed")
    sha, _ = git(repo, "rev-parse", backup)
    use_fake_gh(monkeypatch, merged=[(106, "feat/squashed", MERGED_AFTER)])

    branch_sweep.main(["--repo", str(repo), "--delete"])

    out = capsys.readouterr().out
    assert "git branch " + backup + " " + sha[:7] in out


def test_backup_made_after_its_source_merged_is_kept(repo, monkeypatch):
    commit_on(repo, "feat/squashed", "work")
    push(repo, "feat/squashed")
    use_fake_gh(monkeypatch, merged=[(106, "feat/squashed", MERGED_BEFORE)])
    git(repo, "branch", "backup/feat/squashed-20260926-194453", "feat/squashed")

    found, _ = statuses(repo)
    assert found["backup/feat/squashed-20260926-194453"] == "keep"
    assert why(repo, "backup/feat/squashed-20260926-194453") == (
        "backup of feat/squashed: pr #106 merged before its last commit")


def test_the_longest_matching_source_names_the_backup(repo, monkeypatch):
    commit_on(repo, "feat/a-b", "work")
    push(repo, "feat/a-b")
    use_fake_gh(monkeypatch, merged=[(1, "feat/a", MERGED_AFTER),
                                     (2, "feat/a-b", MERGED_AFTER)])
    git(repo, "branch", "backup/feat/a-b-20260926-120000", "feat/a-b")

    found, _ = statuses(repo)
    backup = "backup/feat/a-b-20260926-120000"
    assert found[backup] == "deletable"
    assert why(repo, backup) == "backup of feat/a-b: pr #2 merged"


def test_the_as_is_spelling_wins_a_tie_over_a_slash_substitution(repo, monkeypatch):
    """DD2: equal-length match, the as-is spelling wins over the `/`-to-`-`
    substitution -- even though the substituted head has the higher PR
    number, which would win if that were the only tie-break left."""
    commit_on(repo, "fix-thing", "work")
    push(repo, "fix-thing")
    use_fake_gh(monkeypatch, merged=[(1, "fix-thing", MERGED_AFTER),
                                     (2, "fix/thing", MERGED_AFTER)])
    git(repo, "branch", "backup/fix-thing-20260926-120000", "fix-thing")

    found, _ = statuses(repo)
    backup = "backup/fix-thing-20260926-120000"
    assert found[backup] == "deletable"
    assert why(repo, backup) == "backup of fix-thing: pr #1 merged"


def test_a_backup_with_no_suffix_is_not_a_backup(repo, monkeypatch):
    commit_on(repo, "feat/squashed", "work")
    push(repo, "feat/squashed")
    use_fake_gh(monkeypatch, merged=[(106, "feat/squashed", MERGED_AFTER)])
    git(repo, "branch", "backup/feat/squashed", "feat/squashed")

    found, _ = statuses(repo)
    assert found["backup/feat/squashed"] == "keep"
    assert why(repo, "backup/feat/squashed") == "no merge signal"


def test_backup_without_a_merge_time_is_kept(repo, monkeypatch):
    commit_on(repo, "feat/squashed", "work")
    push(repo, "feat/squashed")
    use_fake_gh(monkeypatch, merged=[(106, "feat/squashed")])
    git(repo, "branch", "backup/feat/squashed-20260926-194453", "feat/squashed")

    found, _ = statuses(repo)
    assert found["backup/feat/squashed-20260926-194453"] == "keep"
    assert found["feat/squashed"] == "deletable"
    assert why(repo, "feat/squashed") == "pr: #106 merged"
