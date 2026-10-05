"""#272: on Windows a bare "git" is looked up in the *calling* process's current
directory before PATH, unless NoDefaultCurrentDirectoryInExePath is set; the
`cwd=` argument only moves the child. Each helper that runs automatically
(hook, status line, stage preflight, track start, test resolver) has to reach
the real git even when a git.exe sits in the directory it was started from.

A copy of whoami.exe stands in for the planted program: harmless, and its
output can never look like real git's.
"""
import os
import shutil
import subprocess

import pytest

import bash_guard
import branch_sweep
import preflight
import resolve_test_command
import ship_pr_findings
import statusline
import ticket_backend
import track_start

pytestmark = pytest.mark.skipif(os.name != "nt", reason="the current-directory lookup is Windows only")


@pytest.fixture
def planted(tmp_path, monkeypatch):
    """(repo, sub): a committed repo and a subdirectory of it, with the process
    sitting in another directory that holds a fake git.exe."""
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    sub = repo / "sub"
    sub.mkdir()
    # Asked before moving into the planted directory, which would answer instead.
    branch = subprocess.run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    evil = tmp_path / "evil"
    evil.mkdir()
    for name in ("git.exe", "gh.exe"):
        shutil.copy(os.path.join(os.environ["SystemRoot"], "System32", "whoami.exe"), evil / name)
    # Unset, or the test passes for the wrong reason: a shell may already set it.
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.chdir(evil)
    return repo, sub, branch


def same(path, repo):
    return os.path.normcase(os.path.realpath(path.strip())) == os.path.normcase(os.path.realpath(str(repo)))


@pytest.mark.parametrize("helper", [bash_guard.git, preflight.git, track_start.git],
                         ids=["bash_guard", "preflight", "track_start"])
def test_git_helper_runs_the_real_git(planted, helper):
    repo, _, _ = planted
    done = helper(str(repo), "rev-parse", "--show-toplevel")
    assert done is not None and done.returncode == 0
    assert same(done.stdout, repo)


def test_statusline_branch_comes_from_the_real_git(planted):
    repo, _, branch = planted
    assert branch and statusline.git_branch(str(repo)) == branch


def test_resolver_root_comes_from_the_real_git(planted):
    repo, sub, _ = planted
    # A planted git makes find_root fall back to the subdirectory itself.
    assert same(resolve_test_command.find_root(str(sub)), repo)


# Started on request rather than automatically, but from the same directory.

def test_branch_sweep_runs_the_real_git(planted):
    repo, _, _ = planted
    out, code = branch_sweep.git(["rev-parse", "--show-toplevel"], cwd=str(repo))
    assert code == 0 and same(out, repo)


@pytest.fixture
def real_gh(monkeypatch):
    if not shutil.which("gh"):
        pytest.skip("gh is not installed")
    monkeypatch.delenv(ticket_backend.CLI_ENV, raising=False)
    monkeypatch.delenv(ship_pr_findings.CLI_ENV, raising=False)


def test_ticket_backend_runs_the_real_gh(real_gh, planted):
    repo, _, _ = planted
    done, _ = ticket_backend.run(["--version"], cwd=str(repo))
    assert done is not None and done.returncode == 0
    assert done.stdout.startswith("gh version")


def test_ship_pr_findings_runs_the_real_gh(real_gh, planted):
    repo, _, _ = planted
    out, _ = ship_pr_findings.run_gh(["--version"], str(repo))
    assert out.startswith("gh version")
