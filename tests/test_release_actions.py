"""Actions release orchestration, using local git remotes and no live API calls."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import release
import release_actions as actions
from test_release import (CURRENT_VERSION, NEXT_VERSION, REAL_PLUGIN_JSON, _run_git, _stub_tools,
                          repo_pair)


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


def test_merge_marks_a_draft_release_pr_ready_before_merging(orchestration):
    repo, head, info, calls = orchestration
    info["isDraft"] = True
    assert actions.execute("merge", NEXT_VERSION, head, repo) == 0
    merge = ("pr", "merge", "123", "--merge", "--match-head-commit", head)
    assert calls.index(("pr", "ready", "123")) < calls.index(merge)


def test_merge_does_not_mark_a_ready_release_pr_ready_again(orchestration):
    repo, head, info, calls = orchestration
    info["isDraft"] = False
    assert actions.execute("merge", NEXT_VERSION, head, repo) == 0
    assert not any(c[:2] == ("pr", "ready") for c in calls)


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


# ------------------------------------------------------------------- notes

COPILOT_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "copilot"
NOTES_DATE = "2026-10-06"


def _section(numbers, verdict="no"):
    bullets = "\n".join(f"- A visible change. (#{n})" for n in numbers)
    return (f"## v{{{{NEW_VERSION}}}} — {NOTES_DATE}\n\nOne sentence.\n\n"
            "Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later.\n\n"
            "### What to do when you update\n\n"
            "- **Claude Code** — `/plugin update cai`. Moves to {{NEW_VERSION}}.\n"
            "- **Codex** — `codex plugin add cai-codex@claude-all-in-one`.\n\n"
            f"### Guard\n\n{bullets}\n\nTRACK_FORMAT_CHANGED: {verdict}")


def _session(reply, fixture="locked-docs-only.jsonl"):
    """The real locked-down session from the smoke test, with its reply swapped."""
    lines = []
    for line in (COPILOT_FIXTURES / fixture).read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event["type"] == "assistant.message":
            event["data"]["content"] = reply
        lines.append(json.dumps(event))
    return subprocess.CompletedProcess(["copilot"], 0, "\n".join(lines) + "\n", "")


@pytest.fixture
def released_repo(repo_pair):
    """main as it stands after CURRENT_VERSION shipped, plus one user-facing
    and one maintainer-only PR."""
    origin, work = repo_pair
    url = release.repository_git_url(REAL_PLUGIN_JSON)
    for market in release.MARKETPLACES:
        path = work / market.file
        path.write_text(release.pin_marketplace(path.read_text(encoding="utf-8"), market, url,
                                                f"v{CURRENT_VERSION}"), encoding="utf-8")
    (work / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## v{CURRENT_VERSION} — 2026-10-05\n\nRequires Claude Code 2.1.283 or "
        "later and codex-cli 0.157.1 or later.\n", encoding="utf-8")
    _run_git(["add", "-A"], cwd=work)
    _run_git(["commit", "-m", f"chore(release): v{CURRENT_VERSION}"], cwd=work)
    _run_git(["tag", "-a", f"v{CURRENT_VERSION}", "-m", "served"], cwd=work)

    def change(path, subject):
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(subject, encoding="utf-8")
        _run_git(["add", "-A"], cwd=work)
        _run_git(["commit", "-m", subject], cwd=work)

    change("plugins/cai/scripts/guard.py", "fix(guard): block a thing (#901)")
    change("scripts/tool.py", "fix(scripts): a maintainer tool (#902)")
    _run_git(["push", "origin", "main", f"refs/tags/v{CURRENT_VERSION}"], cwd=work)
    files = {901: ["plugins/cai/scripts/guard.py"], 902: ["scripts/tool.py"],
             903: ["plugins/cai/skills/track/SKILL.md"]}

    def pr(repo, number):
        return {"number": number, "title": f"PR {number}", "body": "Body.",
                "files": [{"path": p} for p in files[number]]}

    return work, change, pr


def _patch_version():
    major, minor, patch = release.parse_version(CURRENT_VERSION)
    return f"{major}.{minor}.{patch + 1}"


def test_notes_commits_a_candidate_that_check_accepts(released_repo):
    work, change, pr = released_repo
    prompts = []
    def copilot(prompt):
        prompts.append(prompt)
        return _session(_section([901]))

    version = actions.notes(None, work, pr=pr, copilot=copilot, today=NOTES_DATE)

    assert version == _patch_version()
    assert "#901 PR 901" in prompts[0] and "#902 PR 902" in prompts[0]
    assert actions.git(work, "log", "-1", "--format=%s") == f"chore(release): v{version}"
    section = release.extract_section((work / "CHANGELOG.md").read_text(encoding="utf-8"), version)
    assert f"Moves to {version}." in section and "(#901)" in section
    assert "{{NEW_VERSION}}" not in section
    head = actions.git(work, "rev-parse", "HEAD")
    _run_git(["push", "origin", f"release/v{version}"], cwd=work)
    _run_git(["switch", "--detach", "origin/main"], cwd=work)
    assert actions.candidate(version, head, work) == actions.git(work, "rev-parse", "origin/main")


def test_notes_uses_the_maintainer_version_over_the_suggestion(released_repo):
    work, change, pr = released_repo
    version = actions.notes(NEXT_VERSION, work, pr=pr, copilot=lambda p: _session(_section([901])),
                            today=NOTES_DATE)
    assert version == NEXT_VERSION
    assert actions.git(work, "branch", "--show-current") == f"release/v{NEXT_VERSION}"


def test_notes_ignores_a_maintainer_only_feat_when_suggesting_the_version(released_repo):
    # v1.45.1 was suggested as 1.46.0 because #299, a feat(release) that only
    # touched scripts/ and .github/, counted as a new feature.
    work, change, pr = released_repo
    change("scripts/release_notes.py", "feat(release): a maintainer feature (#904)")
    _run_git(["push", "origin", "main"], cwd=work)
    def with_904(repo, number):
        if number == 904:
            return {"number": 904, "title": "PR 904", "body": "",
                    "files": [{"path": "scripts/release_notes.py"}]}
        return pr(repo, number)
    version = actions.notes(None, work, pr=with_904, today=NOTES_DATE,
                            copilot=lambda p: _session(_section([901])))
    assert version == _patch_version()


def test_notes_suggests_minor_when_the_model_reports_a_track_format_change(released_repo):
    work, change, pr = released_repo
    change("plugins/cai/skills/track/SKILL.md", "fix(track): rename a state field (#903)")
    _run_git(["push", "origin", "main"], cwd=work)
    version = actions.notes(None, work, pr=pr, today=NOTES_DATE,
                            copilot=lambda p: _session(_section([901, 903], verdict="yes")))
    major, minor, _ = release.parse_version(CURRENT_VERSION)
    assert version == f"{major}.{minor + 1}.0"


@pytest.mark.parametrize("session,expected", [
    (lambda: _session(_section([901]), fixture="view-only-mcp-connected.jsonl"), "offered tools"),
    (lambda: _session(_section([])), "does not mention #901"),
    (lambda: _session(_section([901, 902])), "cites #902"),
    (lambda: subprocess.CompletedProcess(["copilot"], 1, "", "auth failed"), "copilot exited 1"),
])
def test_notes_rejects_a_bad_session_before_touching_the_tree(released_repo, session, expected):
    work, change, pr = released_repo
    with pytest.raises(RuntimeError, match=expected):
        actions.notes(None, work, pr=pr, copilot=lambda p: session(), today=NOTES_DATE)
    assert actions.git(work, "branch", "--show-current") == "main"
    assert actions.git(work, "status", "--porcelain") == ""
    assert "release/v" not in actions.git(work, "branch", "--list", "release/*")


def test_notes_stops_before_copilot_without_a_user_facing_pr(released_repo, monkeypatch):
    work, change, pr = released_repo
    def maintainer_only(repo, number):
        return {**pr(repo, number), "files": [{"path": "scripts/tool.py"}]}
    with pytest.raises(ValueError, match="no user-facing pull request"):
        actions.notes(None, work, pr=maintainer_only, today=NOTES_DATE,
                      copilot=lambda p: pytest.fail("copilot called"))


@pytest.mark.parametrize("argv", [["notes", NEXT_VERSION, "a" * 40], ["check", NEXT_VERSION],
                                  ["merge"]])
def test_main_refuses_arguments_that_do_not_fit_the_command(argv):
    with pytest.raises(SystemExit) as exc:
        actions.main(argv)
    assert exc.value.code == 2
