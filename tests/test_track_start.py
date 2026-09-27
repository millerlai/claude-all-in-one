"""track_start.py: putting a new track on a feature branch before intake's
preflight ever runs.

`preflight.py:358-366` FAILs `not_main_branch` whenever the branch is
`main`/`master`, and nothing in the track procedure branched first
(#193). These tests run track_start.start() against real git repositories
rather than mocking git, the same choice test_branch_sweep.py and
test_preflight_merge_check.py make -- the behaviour worth pinning here is
what git itself does across a fast-forward, a diverged pull, and an unborn
HEAD, not what a fake would be told to say.
"""
import os
import pathlib
import subprocess

import pytest

import preflight
import track_start

GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=t"]


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo)] + GIT_ID + list(args),
                          capture_output=True, text=True, encoding="utf-8")
    return done.stdout.strip(), done.returncode


def init_repo(path):
    """A repo on `main` with one commit, no remote."""
    subprocess.run(["git", "init", "-b", "main", str(path)],
                   capture_output=True, text=True)
    git(path, "commit", "--allow-empty", "-m", "root")
    return path


def init_repo_with_remote(path, remote):
    """Same as test_branch_sweep.py's init_repo: a real bare remote, since
    `@{u}` needs a configured remote-tracking branch, not just a ref."""
    subprocess.run(["git", "init", "--bare", str(remote)],
                   capture_output=True, text=True)
    subprocess.run(["git", "init", "-b", "main", str(path)],
                   capture_output=True, text=True)
    git(path, "remote", "add", "origin", str(remote))
    git(path, "commit", "--allow-empty", "-m", "root")
    git(path, "push", "-u", "origin", "main")
    return path


def track_dir_for(tmp_path, feature):
    return str(tmp_path / ".claude" / "track" / feature)


def test_on_main_without_upstream_creates_track_branch_and_skips_pull(tmp_path):
    repo = init_repo(tmp_path / "repo")
    code, message = track_start.start(track_dir_for(tmp_path, "feat-a"), str(repo))
    assert code == 0
    assert "skipped the pull" in message
    branch, _ = git(repo, "symbolic-ref", "--short", "HEAD")
    assert branch == "track/feat-a"


def test_on_main_with_upstream_fast_forwards_before_branching(tmp_path):
    remote = tmp_path / "remote.git"
    repo = init_repo_with_remote(tmp_path / "repo", remote)

    # Advance the remote from a second clone, so the local repo can fast-
    # forward without any local commit of its own. The bare remote's HEAD
    # symref still points at its pre-push default (`master`), which is why
    # a plain clone leaves nothing checked out ("remote HEAD refers to
    # nonexistent ref") -- checking out `main` explicitly follows the
    # already-fetched remote-tracking branch instead.
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", str(remote), str(clone)],
                   capture_output=True, text=True)
    git(clone, "checkout", "main")
    git(clone, "commit", "--allow-empty", "-m", "upstream advances")
    git(clone, "push", "origin", "main")
    remote_tip, _ = git(clone, "rev-parse", "HEAD")

    code, message = track_start.start(track_dir_for(tmp_path, "feat-b"), str(repo))
    assert code == 0
    branch, _ = git(repo, "symbolic-ref", "--short", "HEAD")
    assert branch == "track/feat-b"
    head, _ = git(repo, "rev-parse", "HEAD")
    assert head == remote_tip


def test_pull_failure_stops_and_creates_nothing(tmp_path):
    remote = tmp_path / "remote.git"
    repo = init_repo_with_remote(tmp_path / "repo", remote)

    # Diverge: the remote gets a commit from elsewhere, and the local repo
    # gets a different commit of its own -- neither is an ancestor of the
    # other, so `pull --ff-only` cannot resolve it.
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", str(remote), str(clone)],
                   capture_output=True, text=True)
    git(clone, "checkout", "main")
    git(clone, "commit", "--allow-empty", "-m", "remote-only commit")
    git(clone, "push", "origin", "main")
    git(repo, "commit", "--allow-empty", "-m", "local-only commit")

    track_dir = track_dir_for(tmp_path, "feat-c")
    code, message = track_start.start(track_dir, str(repo))
    assert code == 2
    assert "git pull --ff-only failed" in message
    branch, _ = git(repo, "symbolic-ref", "--short", "HEAD")
    assert branch == "main"
    _, rc = git(repo, "rev-parse", "--verify", "--quiet", "refs/heads/track/feat-c")
    assert rc != 0
    assert not os.path.isdir(track_dir)


def test_existing_local_branch_stops(tmp_path):
    repo = init_repo(tmp_path / "repo")
    git(repo, "branch", "track/feat-d")
    code, message = track_start.start(track_dir_for(tmp_path, "feat-d"), str(repo))
    assert code == 2
    assert "track/feat-d" in message
    branch, _ = git(repo, "symbolic-ref", "--short", "HEAD")
    assert branch == "main"


def test_existing_remote_branch_stops(tmp_path):
    remote = tmp_path / "remote.git"
    repo = init_repo_with_remote(tmp_path / "repo", remote)
    # Push under the track name without ever creating it locally.
    git(repo, "push", "origin", "main:refs/heads/track/feat-e")
    git(repo, "fetch", "origin")

    code, message = track_start.start(track_dir_for(tmp_path, "feat-e"), str(repo))
    assert code == 2
    assert "track/feat-e" in message
    _, rc = git(repo, "rev-parse", "--verify", "--quiet", "refs/heads/track/feat-e")
    assert rc != 0


def test_on_feature_branch_does_nothing(tmp_path):
    repo = init_repo(tmp_path / "repo")
    git(repo, "checkout", "-b", "other")
    code, message = track_start.start(track_dir_for(tmp_path, "feat-f"), str(repo))
    assert code == 0
    assert "other" in message
    branch, _ = git(repo, "symbolic-ref", "--short", "HEAD")
    assert branch == "other"
    _, rc = git(repo, "rev-parse", "--verify", "--quiet", "refs/heads/track/feat-f")
    assert rc != 0


def test_detached_head_does_nothing(tmp_path):
    repo = init_repo(tmp_path / "repo")
    head, _ = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "--detach", head)
    code, message = track_start.start(track_dir_for(tmp_path, "feat-g"), str(repo))
    assert code == 0
    assert "detached HEAD" in message
    branch, _ = git(repo, "symbolic-ref", "--short", "HEAD")
    assert branch == ""
    _, rc = git(repo, "rev-parse", "--verify", "--quiet", "refs/heads/track/feat-g")
    assert rc != 0


def test_illegal_ref_name_stops(tmp_path):
    repo = init_repo(tmp_path / "repo")
    code, message = track_start.start(track_dir_for(tmp_path, "a..b"), str(repo))
    assert code == 2
    branch, _ = git(repo, "symbolic-ref", "--short", "HEAD")
    assert branch == "main"


def test_unborn_main_can_branch(tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-b", "main", str(repo)],
                   capture_output=True, text=True)
    code, message = track_start.start(track_dir_for(tmp_path, "feat-h"), str(repo))
    assert code == 0
    branch, _ = git(repo, "symbolic-ref", "--short", "HEAD")
    assert branch == "track/feat-h"


def test_git_not_answering_stops(tmp_path, monkeypatch):
    repo = init_repo(tmp_path / "repo")
    real_git = preflight.git

    def fake_git(cwd, *args, encoding=None):
        if args == ("symbolic-ref", "--short", "HEAD"):
            return None
        return real_git(cwd, *args, encoding=encoding)

    monkeypatch.setattr(preflight, "git", fake_git)
    code, message = track_start.start(track_dir_for(tmp_path, "feat-i"), str(repo))
    assert code == 2
    assert "git did not answer" in message


def test_intake_preflight_passes_after_track_start(tmp_path):
    repo = init_repo(tmp_path / "repo")
    track_dir = track_dir_for(tmp_path, "feat-j")
    code, _ = track_start.start(track_dir, str(repo))
    assert code == 0

    checks = preflight.intake(track_dir, str(repo))
    branch_check = checks[0]
    assert branch_check[0] is True, branch_check


def test_skill_md_runs_track_start_before_creating_state_md():
    skill = pathlib.Path(__file__).resolve().parent.parent / \
        "plugins" / "cai" / "skills" / "track" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    section_start = text.index("## `/cai:track <feature>`")
    section_end = text.index("## Running a stage")
    section = text[section_start:section_end]
    assert "scripts/track_start.py" in section
    assert section.index("scripts/track_start.py") < \
        section.index("Create `.claude/track/<feature>/state.md`")
