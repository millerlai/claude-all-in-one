"""Actions release orchestration, using local git remotes and no live API calls."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import release
import release_actions as actions
from test_release import NEXT_VERSION, _run_git, _stub_tools, repo_pair


@pytest.fixture
def candidate_repo(repo_pair):
    origin, work = repo_pair

    def make(*, extra=None, manifest_version=None, notes=True, tag=False):
        assert release.prepare(NEXT_VERSION, repo=work) == 0
        if extra:
            path = work / extra
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("unexpected", encoding="utf-8")
        if manifest_version:
            path = work / release.PRODUCT_MANIFEST
            path.write_text(release.set_version(path.read_text(encoding="utf-8"), manifest_version),
                            encoding="utf-8")
        if not notes:
            (work / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
        _run_git(["add", "-A"], cwd=work)
        _run_git(["commit", "-m", f"chore(release): v{NEXT_VERSION}"], cwd=work)
        head = _run_git(["rev-parse", "HEAD"], cwd=work).stdout.strip()
        _run_git(["push", "-u", "origin", f"release/v{NEXT_VERSION}"], cwd=work)
        if tag:
            _run_git(["tag", "-a", f"v{NEXT_VERSION}", "-m", "candidate"], cwd=work)
            _run_git(["push", "origin", f"refs/tags/v{NEXT_VERSION}"], cwd=work)
        _run_git(["switch", "main"], cwd=work)
        _run_git(["branch", "-D", f"release/v{NEXT_VERSION}"], cwd=work)
        return work, head

    return make


def test_candidate_accepts_reviewed_release_and_returns_main_parent(candidate_repo):
    repo, head = candidate_repo()
    assert actions.candidate(NEXT_VERSION, head, repo) == actions.git(repo, "rev-parse", "origin/main")
    assert actions.git(repo, "branch", "--show-current") == "main"


@pytest.mark.parametrize("version,head", [("--help", "a" * 40), (NEXT_VERSION, "abc"),
                                         (NEXT_VERSION, "$(touch x)"), (NEXT_VERSION, "A" * 40)])
def test_candidate_refuses_invalid_inputs_before_git(monkeypatch, version, head, tmp_path):
    monkeypatch.setattr(actions, "git", lambda *args: pytest.fail("git called for invalid input"))
    with pytest.raises(ValueError):
        actions.candidate(version, head, tmp_path)


def test_candidate_refuses_changed_branch(candidate_repo):
    repo, head = candidate_repo()
    with pytest.raises(ValueError, match="approved head"):
        actions.candidate(NEXT_VERSION, "a" * 40, repo)


@pytest.mark.parametrize("extra", ["scripts/unsafe.py", ".github/workflows/unsafe.yml", "plugins/cai/unsafe.py"])
def test_candidate_refuses_changes_to_source_or_workflows(candidate_repo, extra):
    repo, head = candidate_repo(extra=extra)
    with pytest.raises(ValueError, match="outside the release set"):
        actions.candidate(NEXT_VERSION, head, repo)


def test_candidate_refuses_wrong_manifest(candidate_repo):
    repo, head = candidate_repo(manifest_version="0.0.1")
    with pytest.raises(ValueError, match="manifest"):
        actions.candidate(NEXT_VERSION, head, repo)


def test_candidate_refuses_missing_notes(candidate_repo):
    repo, head = candidate_repo(notes=False)
    with pytest.raises(ValueError, match="no release notes"):
        actions.candidate(NEXT_VERSION, head, repo)


def test_candidate_refuses_new_tag_when_main_advanced(candidate_repo):
    repo, head = candidate_repo()
    (repo / "new.txt").write_text("new", encoding="utf-8")
    _run_git(["add", "new.txt"], cwd=repo)
    _run_git(["commit", "-m", "main advanced"], cwd=repo)
    _run_git(["push", "origin", "main"], cwd=repo)
    with pytest.raises(ValueError, match="main advanced"):
        actions.candidate(NEXT_VERSION, head, repo)


def test_candidate_can_resume_tagged_release_after_main_advanced(candidate_repo):
    repo, head = candidate_repo(tag=True)
    (repo / "new.txt").write_text("new", encoding="utf-8")
    _run_git(["add", "new.txt"], cwd=repo)
    _run_git(["commit", "-m", "main advanced"], cwd=repo)
    _run_git(["push", "origin", "main"], cwd=repo)
    assert actions.candidate(NEXT_VERSION, head, repo) == actions.git(repo, "rev-parse", f"{head}^")


def test_candidate_refuses_conflicting_tag(candidate_repo):
    repo, head = candidate_repo()
    _run_git(["tag", "-a", f"v{NEXT_VERSION}", "-m", "wrong commit"], cwd=repo)
    _run_git(["push", "origin", f"refs/tags/v{NEXT_VERSION}"], cwd=repo)
    with pytest.raises(ValueError, match="existing tag"):
        actions.candidate(NEXT_VERSION, head, repo)


def test_gate_runs_tests_for_already_committed_candidate(candidate_repo, monkeypatch):
    repo, head = candidate_repo()
    monkeypatch.setattr(actions, "wait_ci", lambda *args: None)
    calls = []
    monkeypatch.setattr(release, "local_gate", lambda path: calls.append(path) or [])
    assert actions.execute("gate", NEXT_VERSION, head, repo) == 0
    assert calls == [repo]
    assert actions.git(repo, "rev-parse", "HEAD") == head


def test_gate_stops_on_validation_failure(candidate_repo, monkeypatch):
    repo, head = candidate_repo()
    monkeypatch.setattr(actions, "wait_ci", lambda *args: None)
    monkeypatch.setattr(release, "local_gate", lambda path: ["FAIL validation"])
    with pytest.raises(RuntimeError, match="FAIL validation"):
        actions.execute("gate", NEXT_VERSION, head, repo)
    assert release._remote_tags(repo) == []


@pytest.mark.parametrize("tagged,expected", [(False, "cut"), (True, "verify")])
def test_cut_resumes_from_remote_branch_and_uses_verify_for_existing_tag(candidate_repo, monkeypatch,
                                                                       tagged, expected):
    repo, head = candidate_repo(tag=tagged)
    monkeypatch.setattr(actions, "wait_ci", lambda *args: None)
    monkeypatch.setattr(release, "local_gate", lambda path: [])
    assert actions.execute("gate", NEXT_VERSION, head, repo) == 0
    calls = []
    monkeypatch.setattr(release, "cut", lambda *args, **kwargs: calls.append("cut") or 0)
    monkeypatch.setattr(release, "verify", lambda *args, **kwargs: calls.append("verify") or 0)
    assert actions.execute("cut", NEXT_VERSION, head, repo) == 0
    assert calls == [expected]


def test_ci_wait_ignores_old_success_and_pending_runs(monkeypatch, tmp_path):
    head = "a" * 40
    responses = iter([[], [{"headSha": "b" * 40, "status": "completed", "conclusion": "success"}],
                      [{"headSha": head, "status": "in_progress", "conclusion": ""}],
                      [{"headSha": head, "status": "completed", "conclusion": "success"}]])
    calls = []
    def fake_gh(repo, *args):
        calls.append(args)
        return json.dumps(next(responses))
    monkeypatch.setattr(actions, "gh", fake_gh)
    monkeypatch.setattr(actions.time, "sleep", lambda seconds: None)
    actions.wait_ci(tmp_path, head, "main", "push")
    assert len(calls) == 4
    assert all("--commit" in call and head in call and "push" in call for call in calls)


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped"])
def test_ci_wait_refuses_unsuccessful_run(monkeypatch, tmp_path, conclusion):
    head = "a" * 40
    monkeypatch.setattr(actions, "gh", lambda *args: json.dumps([
        {"headSha": head, "status": "completed", "conclusion": conclusion}]))
    with pytest.raises(RuntimeError, match="CI failed"):
        actions.wait_ci(tmp_path, head, "main", "push")


def test_ci_wait_times_out_if_no_run_appears(monkeypatch, tmp_path):
    monkeypatch.setattr(actions, "gh", lambda *args: "[]")
    with pytest.raises(RuntimeError, match="timed out"):
        actions.wait_ci(tmp_path, "a" * 40, "main", "push", seconds=0)


@pytest.fixture
def orchestration(monkeypatch, tmp_path):
    head = "a" * 40
    info = {"number": 123, "state": "OPEN", "headRefOid": head, "baseRefName": "main",
            "mergeCommit": {"oid": "b" * 40}}
    calls = []
    monkeypatch.setattr(actions, "candidate", lambda *args: "c" * 40)
    monkeypatch.setattr(actions, "git", lambda *args: head)
    monkeypatch.setattr(actions, "wait_ci", lambda *args: calls.append(("wait", *args[1:])))
    def fake_gh(repo, *args):
        calls.append(args)
        if args[:2] == ("pr", "view"):
            return json.dumps(info)
        if args[:2] == ("release", "view"):
            return json.dumps({"isDraft": False, "publishedAt": "2026-10-03T00:00:00Z"})
        if args[:2] == ("pr", "merge"):
            info["state"] = "MERGED"
        return ""
    monkeypatch.setattr(actions, "gh", fake_gh)
    return tmp_path, head, info, calls


def test_publish_waits_for_exact_head_ci_before_publish(orchestration, monkeypatch):
    repo, head, info, calls = orchestration
    monkeypatch.setattr(release, "publish", lambda *args, **kwargs: calls.append(("publish",)) or 0)
    assert actions.execute("publish", NEXT_VERSION, head, repo) == 0
    assert calls.index(("wait", head, f"release/v{NEXT_VERSION}", "pull_request")) < calls.index(("publish",))
    assert not any(c[:2] == ("pr", "merge") for c in calls)


@pytest.mark.parametrize("field,value", [("headRefOid", "d" * 40), ("baseRefName", "other")])
def test_publish_refuses_changed_pr_before_publishing(orchestration, monkeypatch, field, value):
    repo, head, info, calls = orchestration
    info[field] = value
    monkeypatch.setattr(release, "publish", lambda *args, **kwargs: pytest.fail("published changed PR"))
    with pytest.raises(ValueError, match="head/base"):
        actions.execute("publish", NEXT_VERSION, head, repo)


def test_merge_uses_merge_and_full_approved_head_then_checks_merge_ci(orchestration):
    repo, head, info, calls = orchestration
    assert actions.execute("merge", NEXT_VERSION, head, repo) == 0
    assert ("pr", "merge", "123", "--merge", "--match-head-commit", head) in calls
    assert ("wait", "b" * 40, "main", "push") in calls


def test_merge_retry_does_not_merge_twice(orchestration):
    repo, head, info, calls = orchestration
    info["state"] = "MERGED"
    assert actions.execute("merge", NEXT_VERSION, head, repo) == 0
    assert not any(c[:2] == ("pr", "merge") for c in calls)
    assert ("wait", "b" * 40, "main", "push") in calls


def test_merge_retry_after_remote_branch_was_deleted(candidate_repo, monkeypatch):
    repo, head = candidate_repo(tag=True)
    _run_git(["merge", "--no-ff", head, "-m", "merge release"], cwd=repo)
    merge_head = actions.git(repo, "rev-parse", "HEAD")
    _run_git(["push", "origin", "main"], cwd=repo)
    _run_git(["push", "origin", "--delete", f"release/v{NEXT_VERSION}"], cwd=repo)
    info = {"number": 123, "state": "MERGED", "headRefOid": head, "baseRefName": "main",
            "mergeCommit": {"oid": merge_head}}
    calls = []
    def fake_gh(repo, *args):
        calls.append(args)
        if args[:2] == ("pr", "view"):
            return json.dumps(info)
        if args[:2] == ("release", "view"):
            return json.dumps({"isDraft": False, "publishedAt": "2026-10-03T00:00:00Z"})
        pytest.fail(f"unexpected write operation: {args}")
    monkeypatch.setattr(actions, "gh", fake_gh)
    monkeypatch.setattr(actions, "wait_ci", lambda *args: calls.append(("wait", *args[1:])))
    assert actions.execute("merge", NEXT_VERSION, head, repo) == 0
    assert ("wait", merge_head, "main", "push") in calls


@pytest.mark.parametrize("state", ["OPEN", "CLOSED"])
def test_missing_remote_branch_is_not_a_merge_retry_without_merged_pr(candidate_repo, monkeypatch, state):
    repo, head = candidate_repo(tag=True)
    _run_git(["push", "origin", "--delete", f"release/v{NEXT_VERSION}"], cwd=repo)
    info = {"number": 123, "state": state, "headRefOid": head, "baseRefName": "main", "mergeCommit": None}
    monkeypatch.setattr(actions, "gh", lambda *args: json.dumps(info))
    with pytest.raises(ValueError, match="only allowed after merge"):
        actions.execute("merge", NEXT_VERSION, head, repo)


def test_merge_refuses_draft_release(orchestration, monkeypatch):
    repo, head, info, calls = orchestration
    original = actions.gh
    def fake_gh(repo, *args):
        if args[:2] == ("release", "view"):
            return json.dumps({"isDraft": True, "publishedAt": None})
        return original(repo, *args)
    monkeypatch.setattr(actions, "gh", fake_gh)
    with pytest.raises(ValueError, match="published"):
        actions.execute("merge", NEXT_VERSION, head, repo)
    assert not any(c[:2] == ("pr", "merge") for c in calls)
