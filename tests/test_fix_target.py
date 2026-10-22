"""fix_target: classify, ready, changes, pushable and report for /cai:fix.

`gh` is faked through CAI_GH_CLI (tests/fake_gh.py, `script` mode); git is the
real one, run only inside tmp_path. `ready` ends in `git fetch origin`, which
would reach the network, so those tests replace fix_target.git for that one
call and let every other git call through.
"""
import json
import re
import shlex
import subprocess
from pathlib import Path

import pytest

import fake_gh
import fix_target as ft
import ship_pr_findings as spf

REPO_ROOT = Path(__file__).resolve().parent.parent
APPROVAL_GATES = (REPO_ROOT / "plugins" / "cai" / "skills" / "track"
                  / "references" / "approval-gates.md")
HOST_REMOTE = ft.Remote("github.com", "o", "r")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def git(repo, *args, check=True):
    return subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", *args],
        cwd=repo, check=check, capture_output=True, encoding="utf-8")


def write(repo, rel, text="x\n"):
    p = Path(repo) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def commit_all(repo, message="c"):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


DECLARED = json.dumps({"test": {"commands": ["python -m pytest"]}})


def make_repo(tmp_path, files=None, origin=True, name="repo"):
    """A committed repo on `main`; with `origin`, a GitHub-looking remote whose
    remote-tracking branch and origin/HEAD point at the first commit."""
    repo = tmp_path / name
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    for rel, text in (files or {".cai/cai.json": DECLARED, "a.txt": "a\n"}).items():
        write(repo, rel, text)
    commit_all(repo, "init")
    if origin:
        git(repo, "remote", "add", "origin", "https://github.com/o/r")
        git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    return repo


class Gh:
    def __init__(self, tmp_path, monkeypatch):
        self.script = tmp_path / "gh-script.json"
        self.log = tmp_path / "gh-log.txt"
        monkeypatch.setenv(spf.CLI_ENV, fake_gh.cli_argv())
        monkeypatch.setenv("FAKE_GH_MODE", "script")
        monkeypatch.setenv("FAKE_GH_SCRIPT", str(self.script))
        monkeypatch.setenv("FAKE_GH_LOG", str(self.log))
        self.set()

    def set(self, user=None, repo=None):
        ok = {"stdout": "", "stderr": "", "exit": 0}
        entries = [{"match": "api user",
                    "responses": [user or dict(ok, stdout="miller\n")]},
                   {"match": "api repos/o/r", "responses": [repo or dict(ok, stdout="{}")]}]
        self.script.write_text(json.dumps(entries), encoding="utf-8")

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in
                self.log.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture
def gh(tmp_path, monkeypatch):
    return Gh(tmp_path, monkeypatch)


@pytest.fixture
def no_fetch(monkeypatch):
    """`git fetch origin` succeeds without touching the network."""
    real = ft.git

    def fake(args, cwd, timeout=ft.GIT_TIMEOUT):
        return "" if list(args[:2]) == ["fetch", "origin"] else real(args, cwd, timeout)

    monkeypatch.setattr(ft, "git", fake)


def run(capsys, *argv):
    code = ft.main(list(argv))
    return code, capsys.readouterr().out


# ---------------------------------------------------------------------------
# parse_remote and classify (AC2, AC31)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://github.com/o/r",
    "https://github.com/o/r.git",
    "https://github.com/o/r/",
    "https://token@github.com/o/r.git",
    "git@github.com:o/r.git",
    "git@github.com:o/r",
    "ssh://git@github.com/o/r.git",
    "ssh://git@github.com:22/o/r",
])
def test_parse_remote_accepts_the_three_shapes(url):
    assert ft.parse_remote(url) == ft.Remote("github.com", "o", "r")


@pytest.mark.parametrize("url", ["", "ftp://github.com/o/r", "/tmp/o/r",
                                 "https://github.com/o", "https://github.com/o/r/x/y",
                                 "git@github.com:r", "http://github.com/o/r"])
def test_parse_remote_rejects_other_shapes(url):
    assert ft.parse_remote(url) is None


def test_classify_without_a_remote_is_rejected():
    got = ft.classify("https://github.com/o/r/issues/1", None)
    assert isinstance(got, ft.Rejection) and got.reason == "no-remote"
    assert ft.classify(None, None).reason == "no-remote"


def test_classify_no_argument_is_the_current_branchs_pull_request():
    got = ft.classify(None, HOST_REMOTE)
    assert got == ft.Target("review-threads", "github.com", "o", "r", None, None, None)
    assert ft.classify("  ", HOST_REMOTE) == got


def test_classify_issue_url_ignores_what_follows_the_number():
    url = "https://github.com/o/r/issues/142"
    want = ft.Target("issue", "github.com", "o", "r", 142, None, url)
    assert ft.classify(url, HOST_REMOTE) == want
    for tail in ("/", "#issuecomment-9", "?x=1", "/comments"):
        got = ft.classify(url + tail, HOST_REMOTE)
        assert got.kind == "issue" and got.number == 142


def test_classify_issues_list_url():
    got = ft.classify("https://github.com/o/r/issues", HOST_REMOTE)
    assert got.kind == "issue-list" and got.number is None
    assert ft.classify("https://github.com/o/r/issues/", HOST_REMOTE).kind == "issue-list"
    assert ft.classify("https://GITHUB.com/O/R/issues", HOST_REMOTE).kind == "issue-list"


@pytest.mark.parametrize("url", ["https://github.com/o/r/issues?q=label:bug",
                                 "https://github.com/o/r/issues?q=is%3Aopen",
                                 "https://github.com/o/r/issues#top"])
def test_classify_list_url_with_a_query_or_fragment_is_rejected(url):
    got = ft.classify(url, HOST_REMOTE)
    assert got.reason == "unrecognised"
    assert "filter" in got.message.lower()


def test_classify_pull_request_url():
    got = ft.classify("https://github.com/o/r/pull/328/files#diff", HOST_REMOTE)
    assert (got.kind, got.number) == ("review-threads", 328)
    assert got.url == "https://github.com/o/r/pull/328/files#diff"


def test_classify_other_repository_is_rejected_for_every_github_shape():
    for path in ("issues/1", "issues", "pull/2"):
        got = ft.classify("https://github.com/o/other/" + path, HOST_REMOTE)
        assert got.reason == "other-repository"
        got = ft.classify("https://github.com/p/r/" + path, HOST_REMOTE)
        assert got.reason == "other-repository"


def test_classify_jira_ticket_upper_cases_the_key():
    got = ft.classify("https://acme.atlassian.net/browse/abc-12?x=1#c", HOST_REMOTE)
    assert (got.kind, got.host, got.key) == ("jira-ticket", "acme.atlassian.net", "ABC-12")
    assert ft.classify("https://jira.corp/prefix/browse/A_B2-7/", HOST_REMOTE).key == "A_B2-7"


def test_classify_jira_url_drops_query_and_fragment_before_it_reaches_a_command_line():
    # The skill hands this url and host to fix_jira.py on a shell command line;
    # '$(', '&' and ';' in a pasted query must not survive classify.
    got = ft.classify("https://acme.atlassian.net/browse/ABC-12?x=$(id)&y=1;z#c$(id)",
                      HOST_REMOTE)
    assert got.url == "https://acme.atlassian.net/browse/ABC-12"
    got = ft.classify("https://jira.corp:8443/prefix/browse/A_B2-7/", HOST_REMOTE)
    assert got.url == "https://jira.corp:8443/prefix/browse/A_B2-7"


@pytest.mark.parametrize("arg", [
    "https://acme.atlassian.net/$(id)/browse/ABC-12",
    "https://acme.atlassian.net/a;b/browse/ABC-12",
    "https://ac$me.atlassian.net/browse/ABC-12",
    "https://acme.atlassian.net:99999/browse/ABC-12",
])
def test_classify_jira_url_with_a_shell_character_in_host_or_path_is_rejected(arg):
    got = ft.classify(arg, HOST_REMOTE)
    assert isinstance(got, ft.Rejection) and got.reason == "unrecognised"


@pytest.mark.parametrize("arg", [
    "142", "#142", "ABC-12", "not a url", "ftp://github.com/o/r/issues/1",
    "https://acme.atlassian.net/issues/?jql=project%3DABC",
    "https://acme.atlassian.net/jira/software/projects/ABC/boards/1",
    "https://acme.atlassian.net/jira/software/c/projects/ABC/boards/1?selectedIssue=ABC-1",
    "https://acme.atlassian.net/browse/ABC",
    "https://other.example/o/r/issues",
    "https://github.com/o/r/pulls",
    "https://github.com/o/r",
])
def test_classify_unrecognised_shapes(arg):
    got = ft.classify(arg, HOST_REMOTE)
    assert isinstance(got, ft.Rejection) and got.reason == "unrecognised"
    for shape in ("issues/<number>", "pull/<number>", "/browse/"):
        assert shape in got.message


def test_classify_is_deterministic():
    arg = "https://github.com/o/r/issues/5"
    assert ft.classify(arg, HOST_REMOTE) == ft.classify(arg, HOST_REMOTE)


def test_classify_command_prints_one_json_object(tmp_path, capsys):
    repo = make_repo(tmp_path)
    code, out = run(capsys, "classify", "--project-dir", str(repo),
                    "https://github.com/o/r/issues/7")
    assert code == 0
    got = json.loads(out)
    assert list(got) == list(ft.Target._fields)
    assert got["kind"] == "issue" and got["number"] == 7


def test_classify_command_rejection_is_one_line_exit_2(tmp_path, capsys):
    repo = make_repo(tmp_path)
    code, out = run(capsys, "classify", "--project-dir", str(repo), "142")
    assert code == 2
    assert out.startswith("rejected unrecognised: ") and out.count("\n") == 1


def test_classify_command_without_origin_is_no_remote(tmp_path, capsys):
    repo = make_repo(tmp_path, origin=False)
    code, out = run(capsys, "classify", "--project-dir", str(repo))
    assert code == 2 and out.startswith("rejected no-remote: ")


def test_usage_error_is_exit_1():
    with pytest.raises(SystemExit) as exc:
        ft.main(["ready", "--no-such-flag"])
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# ready (AC3)
# ---------------------------------------------------------------------------

def stopped(capsys, repo):
    code, out = run(capsys, "ready", "--project-dir", str(repo))
    assert code == 2
    first = out.splitlines()[0]
    reason = re.match(r"stopped ([\w-]+): ", first)
    assert reason and out.count("\n") == 1
    return reason.group(1), first


def test_ready_succeeds_and_prints_the_facts(tmp_path, capsys, gh, no_fetch):
    repo = make_repo(tmp_path)
    code, out = run(capsys, "ready", "--project-dir", str(repo))
    got = json.loads(out)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    assert code == 0
    assert Path(got["root"]).resolve() == repo.resolve()
    assert (got["start_ref"], got["default_branch"], got["base_ref"]) == \
        ("main", "main", "origin/main")
    assert got["base_sha"] == head and "start_detached" not in got
    assert (got["login"], got["owner"], got["repo"]) == ("miller", "o", "r")
    assert got["test"]["status"] == "resolved"
    assert got["test"]["commands"][0]["command"] == "python -m pytest"


def test_ready_from_a_detached_head_records_the_sha(tmp_path, capsys, gh, no_fetch):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "--detach")
    code, out = run(capsys, "ready", "--project-dir", str(repo))
    got = json.loads(out)
    assert code == 0 and got["start_detached"] is True
    assert got["start_ref"] == git(repo, "rev-parse", "HEAD").stdout.strip()


def test_ready_not_a_repository(tmp_path, capsys, gh):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert stopped(capsys, plain)[0] == "not-a-repository"
    assert gh.calls() == []


def test_ready_no_remote(tmp_path, capsys, gh):
    assert stopped(capsys, make_repo(tmp_path, origin=False))[0] == "no-remote"
    assert gh.calls() == []


@pytest.mark.parametrize("staged", [False, True])
def test_ready_dirty_tree_stops_before_any_network_call(tmp_path, capsys, gh, staged):
    repo = make_repo(tmp_path)
    write(repo, "a.txt", "changed\n")
    if staged:
        git(repo, "add", "a.txt")
    assert stopped(capsys, repo)[0] == "dirty-tree"
    assert gh.calls() == []


def test_ready_allows_untracked_files_and_records_each_path(tmp_path, capsys, gh, no_fetch):
    repo = make_repo(tmp_path)
    paths = ["notes.txt", "dir with space/草稿.txt", ".github/workflows/local.yml"]
    for path in paths:
        write(repo, path)
    code, out = run(capsys, "ready", "--project-dir", str(repo))
    assert code == 0
    assert sorted(json.loads(out)["untracked_paths"]) == sorted(paths)
    assert len(gh.calls()) == 2
    assert all((repo / path).read_text(encoding="utf-8") == "x\n" for path in paths)


def test_ready_no_default_branch_names_the_fix(tmp_path, capsys, gh):
    repo = make_repo(tmp_path)
    git(repo, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
    reason, line = stopped(capsys, repo)
    assert reason == "no-default-branch"
    assert "git remote set-head origin --auto" in line


def test_ready_gh_not_found(tmp_path, capsys, monkeypatch):
    repo = make_repo(tmp_path)
    monkeypatch.setenv(spf.CLI_ENV, str(tmp_path / "no-such-gh"))
    assert stopped(capsys, repo)[0] == "not-found"


def test_ready_gh_not_authenticated(tmp_path, capsys, gh):
    repo = make_repo(tmp_path)
    gh.set(user={"stdout": "", "stderr": "To get started with GitHub CLI, "
                 "please run:  gh auth login", "exit": 4})
    assert stopped(capsys, repo)[0] == "not-authenticated"


def test_ready_gh_other_failure_is_exit_n(tmp_path, capsys, gh):
    repo = make_repo(tmp_path)
    gh.set(user={"stdout": "", "stderr": "boom", "exit": 7})
    assert stopped(capsys, repo)[0] == "exit-7"


def test_ready_repository_not_on_github(tmp_path, capsys, gh):
    repo = make_repo(tmp_path)
    gh.set(repo={"stdout": "", "stderr": "gh: Not Found (HTTP 404)", "exit": 1})
    assert stopped(capsys, repo)[0] == "no-github-repo"
    assert [c[1] for c in gh.calls()] == ["user", "repos/o/r"]


def test_ready_repository_check_reports_unreachable(tmp_path, capsys, gh):
    repo = make_repo(tmp_path)
    gh.set(repo={"stdout": "", "stderr": "error connecting to api.github.com", "exit": 1})
    assert stopped(capsys, repo)[0] == "unreachable"


def test_ready_fetch_failed_uses_the_sixty_second_budget(tmp_path, capsys, gh, monkeypatch):
    repo = make_repo(tmp_path)
    real = ft.git
    seen = []

    def fake(args, cwd, timeout=ft.GIT_TIMEOUT):
        if list(args[:2]) == ["fetch", "origin"]:
            seen.append(timeout)
            return None
        return real(args, cwd, timeout)

    monkeypatch.setattr(ft, "git", fake)
    assert stopped(capsys, repo)[0] == "fetch-failed"
    assert seen == [60]


def test_ready_test_command_unknown(tmp_path, capsys, gh, no_fetch):
    repo = make_repo(tmp_path, files={"a.txt": "a\n"})
    assert stopped(capsys, repo)[0] == "test-command-unknown"


def test_ready_test_command_several_names_the_recorder(tmp_path, capsys, gh, no_fetch):
    repo = make_repo(tmp_path, files={"a.txt": "a\n", "tox.ini": "[tox]\n",
                                      "noxfile.py": "\n"})
    reason, line = stopped(capsys, repo)
    assert reason == "test-command-several"
    assert "record_test_command.py" in line


def test_ready_test_command_invalid(tmp_path, capsys, gh, no_fetch):
    repo = make_repo(tmp_path, files={".cai/cai.json": json.dumps(
        {"test": {"commands": []}}), "a.txt": "a\n"})
    assert stopped(capsys, repo)[0] == "test-command-invalid"


# ---------------------------------------------------------------------------
# is_held (AC6, I7)
# ---------------------------------------------------------------------------

HELD_NAMES = ["requirements.txt", "requirements-dev.txt", "pyproject.toml", "setup.py",
              "package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock",
              "pnpm-lock.yaml", "bun.lock", "bun.lockb", "go.mod", "go.sum",
              "Cargo.toml", "Cargo.lock", "Gemfile", "Gemfile.lock", "pom.xml"]


@pytest.mark.parametrize("name", HELD_NAMES)
def test_is_held_for_every_listed_file_name_at_any_depth(name):
    assert ft.is_held(name)
    assert ft.is_held("sub/dir/" + name)
    assert ft.is_held(name.upper())


@pytest.mark.parametrize("path", [".github/workflows/ci.yml", ".GITHUB/x", "./.github/x",
                                  ".github/"])
def test_is_held_for_github_directory(path):
    assert ft.is_held(path)


@pytest.mark.parametrize("path", ["src/app.py", "README.md", "github/x.yml",
                                  "docs/.github", "requirements.md", "my_requirements.txt",
                                  "package.jsonc", "tests/test_setup.py"])
def test_is_held_is_false_for_ordinary_paths(path):
    assert not ft.is_held(path)


def test_is_held_covers_every_name_approval_gates_lists():
    text = APPROVAL_GATES.read_text(encoding="utf-8")
    section = text[text.index("Likewise, if the"):text.index("before adding them.")]
    names = re.findall(r"`([^`\n]+)`", section)
    assert len(names) >= 12
    for name in names:
        assert ft.is_held(name.replace("*", "-dev")), name


# ---------------------------------------------------------------------------
# compare_changes, changes (D4)
# ---------------------------------------------------------------------------

def test_compare_changes_match():
    got = ft.compare_changes(["a.py", "t/test_a.py"], ["t/test_a.py", "a.py"])
    assert got == ft.Changes("match", [], [], [])


def test_compare_changes_none():
    assert ft.compare_changes([], ["a.py"]).verdict == "none"
    assert ft.compare_changes([], []).verdict == "none"


def test_compare_changes_mismatch_lists_both_sides():
    got = ft.compare_changes(["a.py", "b.py"], ["a.py", "c.py"])
    assert (got.verdict, got.unreported, got.missing) == ("mismatch", ["b.py"], ["c.py"])


def test_compare_changes_reports_held_paths_even_on_a_match():
    got = ft.compare_changes(["a.py", "package.json"], ["a.py", "package.json"])
    assert (got.verdict, got.held) == ("match", ["package.json"])


def test_parse_porcelain_counts_both_sides_of_a_rename():
    raw = "R  new name.py\0old.py\0?? dir/u.txt\0 M m.py\0"
    assert ft.parse_porcelain(raw) == ["new name.py", "old.py", "dir/u.txt", "m.py"]
    assert ft.parse_porcelain("") == []


def changes_args(repo, tmp_path, head, branch, reported):
    reported_file = tmp_path / "reported.txt"
    reported_file.write_text("\n".join(reported) + "\n", encoding="utf-8")
    return ["changes", "--project-dir", str(repo), "--expect-head", head,
            "--expect-branch", branch, "--reported-file", str(reported_file),
            "--pathspec-out", str(tmp_path / "paths.bin")]


def head_of(repo):
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def test_changes_match_exit_0_and_pathspec_file(tmp_path, capsys):
    repo = make_repo(tmp_path)
    head = head_of(repo)
    write(repo, "a.txt", "changed\n")
    write(repo, "dir with space/new file.txt")
    code, out = run(capsys, *changes_args(
        repo, tmp_path, head, "main", [".\\dir with space\\new file.txt", " a.txt ", ""]))
    assert code == 0 and out.splitlines() == ["changes match"]
    raw = (tmp_path / "paths.bin").read_bytes()
    assert sorted(raw.decode("utf-8").split("\0")) == ["a.txt", "dir with space/new file.txt"]
    # the file is what `git add` is given, so prove git reads it back
    git(repo, "add", "--pathspec-from-file=" + str(tmp_path / "paths.bin"),
        "--pathspec-file-nul")
    status = git(repo, "status", "--porcelain", "-z").stdout.split("\0")
    assert sorted(s for s in status if s) == ["A  dir with space/new file.txt", "M  a.txt"]


def test_changes_mismatch_lists_unreported_and_missing(tmp_path, capsys):
    repo = make_repo(tmp_path)
    head = head_of(repo)
    write(repo, "a.txt", "changed\n")
    write(repo, "extra.txt")
    code, out = run(capsys, *changes_args(repo, tmp_path, head, "main",
                                          ["a.txt", "gone.txt"]))
    assert code == 3
    assert out.splitlines() == ["changes mismatch", "unreported extra.txt",
                                "missing gone.txt"]


def test_changes_snapshot_keeps_new_unreported_files_and_held_paths(tmp_path, capsys):
    repo = make_repo(tmp_path)
    ready_file = write(tmp_path, "ready.json", json.dumps({"untracked_paths": ["notes.txt"]}))
    write(repo, "notes.txt")
    write(repo, "extra.txt")
    write(repo, ".github/workflows/new.yml")
    code, out = run(capsys, *changes_args(repo, tmp_path, head_of(repo), "main", []),
                    "--ready-file", str(ready_file))
    assert code == 3
    assert out.splitlines() == ["changes mismatch", "held .github/workflows/new.yml",
                                "unreported .github/workflows/new.yml", "unreported extra.txt"]
    assert set((tmp_path / "paths.bin").read_text().split("\0")) == {
        ".github/workflows/new.yml", "extra.txt"}


@pytest.mark.parametrize("contents", ["not json", "{}", "[]", '{"untracked_paths": "notes.txt"}',
                                     '{"untracked_paths": [1]}'])
def test_changes_invalid_ready_file_does_not_write_pathspec(tmp_path, capsys, contents):
    repo = make_repo(tmp_path)
    ready_file = write(tmp_path, "ready.json", contents)
    code, out = run(capsys, *changes_args(repo, tmp_path, head_of(repo), "main", []),
                    "--ready-file", str(ready_file))
    assert code == 1
    assert not (tmp_path / "paths.bin").exists()


def test_changes_none_when_the_tree_is_clean(tmp_path, capsys):
    repo = make_repo(tmp_path)
    code, out = run(capsys, *changes_args(repo, tmp_path, head_of(repo), "main", ["a.txt"]))
    assert code == 3 and out.splitlines()[0] == "changes none"
    assert (tmp_path / "paths.bin").read_bytes() == b""


def test_changes_held_path_blocks_even_when_reported(tmp_path, capsys):
    repo = make_repo(tmp_path)
    head = head_of(repo)
    write(repo, ".github/workflows/ci.yml")
    code, out = run(capsys, *changes_args(repo, tmp_path, head, "main",
                                          [".github/workflows/ci.yml"]))
    assert code == 3
    assert out.splitlines() == ["changes match", "held .github/workflows/ci.yml"]


def test_changes_head_moved_by_a_new_commit(tmp_path, capsys):
    repo = make_repo(tmp_path)
    head = head_of(repo)
    write(repo, "a.txt", "two\n")
    commit_all(repo, "agent commit")
    write(repo, "b.txt")
    code, out = run(capsys, *changes_args(repo, tmp_path, head, "main", ["b.txt"]))
    assert code == 3 and out.splitlines()[0] == "changes head-moved"
    assert (tmp_path / "paths.bin").read_bytes() == b"b.txt"


def test_changes_head_moved_by_another_branch(tmp_path, capsys):
    repo = make_repo(tmp_path)
    head = head_of(repo)
    git(repo, "switch", "-q", "-c", "elsewhere")
    write(repo, "a.txt", "changed\n")
    code, out = run(capsys, *changes_args(repo, tmp_path, head, "main", ["a.txt"]))
    assert code == 3 and out.splitlines()[0] == "changes head-moved"


def test_changes_head_moved_when_head_has_no_branch(tmp_path, capsys):
    repo = make_repo(tmp_path)
    head = head_of(repo)
    git(repo, "checkout", "-q", "--detach")
    write(repo, "a.txt", "changed\n")
    code, out = run(capsys, *changes_args(repo, tmp_path, head, "main", ["a.txt"]))
    assert code == 3 and out.splitlines()[0] == "changes head-moved"


def test_changes_git_failure_is_exit_2(tmp_path, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()
    code, out = run(capsys, *changes_args(plain, tmp_path, "0" * 40, "main", ["a"]))
    assert code == 2 and out.startswith("stopped ")


def test_changes_escapes_control_characters_in_paths(tmp_path, capsys, monkeypatch):
    # Windows cannot hold such a file name, so git's answer is faked.
    repo = make_repo(tmp_path)
    head = head_of(repo)
    real = ft.git
    monkeypatch.setattr(ft, "git", lambda args, cwd, timeout=ft.GIT_TIMEOUT: (
        "?? evil\nheld forged\0" if args[:1] == ["status"] else real(args, cwd, timeout)))
    code, out = run(capsys, *changes_args(repo, tmp_path, head, "main", []))
    assert code == 3
    assert "unreported evil\\x0aheld forged" in out.splitlines()


# ---------------------------------------------------------------------------
# pushable (I3, I7)
# ---------------------------------------------------------------------------

def branch_with(repo, name="fix/1-x", files=None, commits=1):
    git(repo, "switch", "-q", "-c", name, "--no-track", "origin/main")
    for n in range(commits):
        for rel, text in (files or {f"f{n}.txt": f"{n}\n"}).items():
            write(repo, rel, text)
        commit_all(repo, f"c{n}")


def pushable(capsys, repo, base="origin/main"):
    return run(capsys, "pushable", "--project-dir", str(repo), "--base", base)


def test_pushable_ok_counts_commits(tmp_path, capsys):
    repo = make_repo(tmp_path)
    branch_with(repo, commits=2)
    code, out = pushable(capsys, repo)
    assert code == 0 and out.splitlines() == ["pushable fix/1-x 2"]


def test_pushable_detached_head(tmp_path, capsys):
    repo = make_repo(tmp_path)
    branch_with(repo)
    git(repo, "checkout", "-q", "--detach")
    code, out = pushable(capsys, repo)
    assert code == 3 and out.splitlines() == ["not-pushable detached-head"]


def test_pushable_refuses_the_default_branch_and_main_and_master(tmp_path, capsys):
    repo = make_repo(tmp_path)
    write(repo, "f.txt")
    commit_all(repo)
    assert pushable(capsys, repo) == (3, "not-pushable default-branch\n")
    git(repo, "switch", "-q", "-c", "master")
    assert pushable(capsys, repo) == (3, "not-pushable default-branch\n")


def test_pushable_refuses_a_default_branch_with_another_name(tmp_path, capsys):
    repo = make_repo(tmp_path)
    git(repo, "update-ref", "refs/remotes/origin/trunk", "HEAD")
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    git(repo, "switch", "-q", "-c", "trunk")
    write(repo, "f.txt")
    commit_all(repo)
    assert pushable(capsys, repo, "origin/trunk") == (3, "not-pushable default-branch\n")


@pytest.mark.parametrize("staged", [False, True])
def test_pushable_dirty_tree(tmp_path, capsys, staged):
    repo = make_repo(tmp_path)
    branch_with(repo)
    write(repo, "a.txt", "changed\n")
    if staged:
        git(repo, "add", "a.txt")
    assert pushable(capsys, repo) == (3, "not-pushable dirty-tree\n")


def test_pushable_allows_untracked_files(tmp_path, capsys):
    repo = make_repo(tmp_path)
    branch_with(repo)
    write(repo, ".github/workflows/local.yml")
    assert pushable(capsys, repo) == (0, "pushable fix/1-x 1\n")


@pytest.mark.parametrize("existing_state", ["untracked", "staged", "reported", "staged-reported"])
def test_fix_preserves_existing_untracked_files(tmp_path, capsys, gh, no_fetch,
                                               existing_state):
    repo = make_repo(tmp_path)
    existing = "dir with space/草稿.txt"
    write(repo, existing, "personal notes\n")
    code, out = run(capsys, "ready", "--project-dir", str(repo))
    assert code == 0
    ready_file = write(tmp_path, "ready.json", out)
    git(repo, "switch", "-q", "-c", "fix/417", "--no-track", "origin/main")
    head = head_of(repo)
    write(repo, "a.txt", "fixed\n")
    write(repo, "new test.txt")
    reported = ["a.txt", "new test.txt"]
    if existing_state.startswith("staged"):
        git(repo, "add", existing)
    if "reported" in existing_state:
        reported.append(existing)
    code, out = run(capsys, *changes_args(repo, tmp_path, head, "fix/417", reported),
                    "--ready-file", str(ready_file))
    if existing_state.startswith("staged"):
        assert code == 2 and out.startswith("stopped pre-existing-untracked: ")
        assert not (tmp_path / "paths.bin").exists()
        assert (repo / existing).read_text(encoding="utf-8") == "personal notes\n"
        return
    if existing_state == "reported":
        assert code == 3 and out.startswith("changes mismatch\n")
        assert "missing " + existing in out
        return
    assert code == 0 and out == "changes match\n"
    assert set((tmp_path / "paths.bin").read_text(encoding="utf-8").split("\0")) == set(reported)
    git(repo, "add", "--pathspec-from-file=" + str(tmp_path / "paths.bin"),
        "--pathspec-file-nul")
    git(repo, "commit", "-q", "-m", "fix")
    assert pushable(capsys, repo) == (0, "pushable fix/417 1\n")
    git(repo, "switch", "-q", "main")
    assert (repo / existing).read_text(encoding="utf-8") == "personal notes\n"
    assert git(repo, "ls-files", "--error-unmatch", existing, check=False).returncode != 0


@pytest.mark.parametrize("procedure", ["single-issue.md", "review-threads.md"])
def test_documented_add_does_not_match_existing_untracked_file(tmp_path, capsys, procedure):
    repo = make_repo(tmp_path)
    write(repo, "notes/a.txt", "personal notes\n")
    ready_file = write(tmp_path, "ready.json", json.dumps({"untracked_paths": ["notes/a.txt"]}))
    write(repo, "notes/[a].txt", "fix\n")
    code, out = run(capsys, *changes_args(repo, tmp_path, head_of(repo), "main", ["notes/[a].txt"]),
                    "--ready-file", str(ready_file))
    assert code == 0
    reference = REPO_ROOT / "plugins/cai/skills/fix/references" / procedure
    command = next(line for line in reference.read_text(encoding="utf-8").splitlines()
                   if line.startswith("git ") and "--pathspec-from-file=" in line)
    argv = [word.replace("PATHSPEC", str(tmp_path / "paths.bin"))
            for word in shlex.split(command.replace("<pathspec file>", "PATHSPEC"))]
    git(repo, *argv[1:])
    assert git(repo, "diff", "--cached", "--name-only").stdout.splitlines() == ["notes/[a].txt"]


def test_pushable_nothing_to_push(tmp_path, capsys):
    repo = make_repo(tmp_path)
    git(repo, "switch", "-q", "-c", "fix/2-y", "--no-track", "origin/main")
    assert pushable(capsys, repo) == (3, "not-pushable nothing-to-push\n")


def test_pushable_held_path_lists_each_path_once(tmp_path, capsys):
    repo = make_repo(tmp_path)
    branch_with(repo, files={"package.json": "{}", "ok.txt": "1"})
    write(repo, "package.json", "{ }")
    commit_all(repo)
    code, out = pushable(capsys, repo)
    assert code == 3
    assert out.splitlines() == ["not-pushable held-path", "held package.json"]


def test_pushable_catches_a_held_path_added_then_deleted(tmp_path, capsys):
    repo = make_repo(tmp_path)
    branch_with(repo, files={".github/workflows/x.yml": "on: push\n"})
    git(repo, "rm", "-q", ".github/workflows/x.yml")
    git(repo, "commit", "-q", "-m", "remove it again")
    assert git(repo, "diff", "--name-only", "origin/main..HEAD").stdout == ""
    code, out = pushable(capsys, repo)
    assert code == 3 and "held .github/workflows/x.yml" in out.splitlines()


def test_pushable_unknown_base_is_a_git_failure(tmp_path, capsys):
    repo = make_repo(tmp_path)
    branch_with(repo)
    code, out = pushable(capsys, repo, "origin/missing")
    assert code == 2 and out.startswith("stopped ")


# ---------------------------------------------------------------------------
# report (I8)
# ---------------------------------------------------------------------------

WORDS = ["pr-opened", "replied-fixed", "replied-not-fixed", "cannot-reproduce",
         "needs-decision", "too-large", "failed-three-attempts", "waiting-for-pr",
         "held-path", "dependency-not-fixed", "dependency-cycle",
         "committed-not-pushed", "pushed-no-pr", "replied-not-resolved",
         "pushed-not-replied", "paths-mismatch", "not-selected", "has-open-pr",
         "dependency-not-selected", "local-branch-kept", "claimed-elsewhere"]
FILL = {"url": "https://github.com/o/r/pull/9", "branch": "fix/1-x", "detail": "abc1234",
        "paths": ["a.py"]}


def item(id_, outcome, **fields):
    row = {"id": id_, "outcome": outcome, "url": None, "branch": None,
           "detail": None, "paths": [], "notes": []}
    for key in ft.REQUIRED.get(outcome, ()):
        row[key] = FILL[key]
    row.update(fields)
    return row


def results(*items, kind="issue-list"):
    return {"kind": kind, "items": list(items)}


def test_outcomes_are_the_twenty_one_words_with_english_sentences():
    assert sorted(ft.OUTCOMES) == sorted(WORDS) and len(ft.OUTCOMES) == 21
    for sentence in ft.OUTCOMES.values():
        assert sentence.endswith(".") and sentence.isascii()
    assert "/cai:track <url>" in ft.OUTCOMES["too-large"]


def test_required_fields_match_the_design():
    assert ft.REQUIRED["pr-opened"] == ("url", "branch", "paths")
    assert ft.REQUIRED["held-path"] == ("branch", "paths")
    assert ft.REQUIRED["too-large"] == ("url",)
    assert ft.REQUIRED["replied-fixed"] == ("detail",)
    assert ft.REQUIRED["claimed-elsewhere"] == ("url", "detail")
    assert ft.REQUIRED.get("cannot-reproduce", ()) == ()


@pytest.mark.parametrize("word", WORDS)
def test_check_results_accepts_every_word_with_its_required_fields(word):
    assert ft.check_results(results(item("#1", word)), None) == []


@pytest.mark.parametrize("word", [w for w in WORDS if ft.REQUIRED.get(w)])
def test_check_results_names_each_missing_required_field(word):
    for field in ft.REQUIRED[word]:
        row = item("#1", word)
        row[field] = [] if field == "paths" else None
        problems = ft.check_results(results(row), None)
        assert len(problems) == 1 and "#1" in problems[0] and field in problems[0]


def test_check_results_rejects_an_unknown_word():
    problems = ft.check_results(results(item("#1", "done")), None)
    assert len(problems) == 1 and "#1" in problems[0] and "done" in problems[0]


def test_check_results_rejects_a_duplicate_id():
    problems = ft.check_results(results(item("#1", "not-selected"),
                                        item("#1", "has-open-pr", url="u")), None)
    assert len(problems) == 1 and "duplicate" in problems[0]


def test_check_results_compares_against_the_expected_ids():
    res = results(item("#1", "not-selected"), item("#3", "not-selected"))
    problems = ft.check_results(res, ["#1", "#2"])
    assert any("#2" in p and "missing" in p for p in problems)
    assert any("#3" in p and "not expected" in p for p in problems)
    assert ft.check_results(res, ["#3", "#1"]) == []


def test_check_results_takes_numeric_ids_and_rejects_a_bad_shape():
    assert ft.check_results(results(item(4711, "not-selected")), ["4711"]) == []
    assert ft.check_results([], None)
    assert ft.check_results({"kind": "issue", "items": "x"}, None)
    assert ft.check_results(results("nope"), None)
    assert ft.check_results(results(item("", "not-selected")), None)


def test_render_report_lines_and_the_fixed_sentence():
    lines = ft.render_report(results(
        item("#1", "pr-opened", paths=["a.py"], notes=["claimed by someone"]),
        item("#2", "not-selected")))
    assert lines[0] == "#1 pr-opened https://github.com/o/r/pull/9 checks not waited for"
    assert "  " + ft.OUTCOMES["pr-opened"] in lines
    assert "  claimed by someone" in lines
    assert "#2 not-selected" in lines
    assert "local branches kept:" not in lines
    assert "same file touched by:" not in lines


def test_render_report_lists_local_branches_kept():
    lines = ft.render_report(results(
        item("#1", "held-path"), item("#2", "pr-opened"), item("#3", "paths-mismatch")))
    at = lines.index("local branches kept:")
    assert lines[at + 1:at + 3] == ["  #1 fix/1-x", "  #3 fix/1-x"]


def test_render_report_flags_a_file_two_pull_requests_touch():
    lines = ft.render_report(results(
        item("#1", "pr-opened", paths=["a.py", "only1.py"]),
        item("#2", "pr-opened", paths=["a.py"]),
        item("#3", "pr-opened", paths=["only3.py"]),
        item("#4", "held-path", paths=["a.py"])))
    at = lines.index("same file touched by:")
    assert lines[at + 1:] == ["  a.py: #1, #2"]


def test_render_report_escapes_text_that_is_not_ours():
    lines = ft.render_report(results(item("#1", "needs-decision",
                                          notes=["x\n#9 pr-opened https://forged"])))
    assert not any(line.startswith("#9") for line in lines)
    assert any("x\\x0a#9 pr-opened" in line for line in lines)


def test_render_report_shows_the_detail_that_the_outcome_requires():
    lines = ft.render_report(results(item("#5", "replied-fixed")))
    assert "  detail: abc1234" in lines


def test_render_report_of_nothing_says_so():
    assert ft.render_report(results()) == ["no items"]


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def test_report_command_prints_the_report(tmp_path, capsys):
    res = write_json(tmp_path / "r.json", results(item("#1", "not-selected")))
    expect = tmp_path / "e.txt"
    expect.write_text("#1\n\n", encoding="utf-8")
    code, out = run(capsys, "report", "--results-file", res, "--expect-file", str(expect))
    assert code == 0 and out.splitlines()[0] == "#1 not-selected"


@pytest.mark.parametrize("kind,url,detail", [
    ("issue", "https://github.com/o/r/issues/1",
     "claude 6f1c-session 2026-10-13T08:00:00.123Z"),
    ("jira", "https://jira.example.com/browse/PROJ-12",
     "codex thread-123 2026-10-13T08:00:00.456Z"),
])
def test_report_claimed_elsewhere_keeps_url_and_raw_detail(
        tmp_path, capsys, kind, url, detail):
    res = write_json(tmp_path / "r.json", results(
        item("#1", "claimed-elsewhere", url=url, detail=detail), kind=kind))
    code, out = run(capsys, "report", "--results-file", res)
    assert code == 0
    assert out.splitlines() == [
        "#1 claimed-elsewhere " + url,
        "  Another session on this machine is working on it; once that session "
        "has ended, /cai:fix-unclaim with this URL and the detail's values clears "
        "its claim.",
        "  detail: " + detail,
    ]


@pytest.mark.parametrize("field", ["url", "detail"])
def test_report_claimed_elsewhere_requires_url_and_detail(tmp_path, capsys, field):
    row = item("#1", "claimed-elsewhere", url="https://github.com/o/r/issues/1",
               detail="claude 6f1c-session 2026-10-13T08:00:00.123Z")
    del row[field]
    res = results(row)
    problem = "#1: outcome claimed-elsewhere needs " + field
    assert ft.check_results(res, None) == [problem]
    path = write_json(tmp_path / "r.json", res)
    code, out = run(capsys, "report", "--results-file", path)
    assert code == 2 and out.splitlines() == ["stopped results-invalid: " + problem]


def test_report_command_stops_on_an_invalid_results_file(tmp_path, capsys):
    res = write_json(tmp_path / "r.json", results(item("#1", "done")))
    code, out = run(capsys, "report", "--results-file", res)
    assert code == 2 and out.startswith("stopped results-invalid: ")
    assert "#1" in out.splitlines()[0]


def test_report_command_stops_on_an_expected_id_that_is_missing(tmp_path, capsys):
    res = write_json(tmp_path / "r.json", results(item("#1", "not-selected")))
    expect = tmp_path / "e.txt"
    expect.write_text("#1\n#2\n", encoding="utf-8")
    code, out = run(capsys, "report", "--results-file", res, "--expect-file", str(expect))
    assert code == 2 and out.startswith("stopped results-invalid: ")


def test_report_command_stops_on_a_file_that_is_not_json(tmp_path, capsys):
    bad = tmp_path / "r.json"
    bad.write_text("{nope", encoding="utf-8")
    code, out = run(capsys, "report", "--results-file", str(bad))
    assert code == 2 and out.startswith("stopped results-invalid: ")
    code, out = run(capsys, "report", "--results-file", str(tmp_path / "absent.json"))
    assert code == 2 and out.startswith("stopped results-invalid: ")
