"""fix_jira read: the ticket, the site proof, the branch name and what it never does.

`acli` is faked through CAI_ACLI_CLI: the value is a JSON argv that runs a small
Python script planted in tmp_path, the same way tests/fake_gh.py is reached
through CAI_GH_CLI, so the same file works on Windows and POSIX (no `.bat` or
`#!/bin/sh` file is needed). `gh` is faked through CAI_GH_CLI; git is the real
one, run only inside tmp_path.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import fake_gh
import fix_jira as fj
import ship_pr_findings as spf

SCRIPT = Path(fj.__file__)
HOST = "site.example.net"

FAKE_ACLI = '''\
import json, os, sys
with open(os.environ["FAKE_ACLI_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
if os.environ.get("FAKE_ACLI_MODE") == "fail":
    sys.stderr.write("SECRET-STDERR-TEXT")
    sys.exit(1)
sys.stdout.write(os.environ.get("FAKE_ACLI_STDOUT", ""))
'''


# ---------------------------------------------------------------------------
# site_matches
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", ["url", "self", "browseUrl", "webUrl"])
def test_site_matches_reads_every_candidate_key_at_the_top(key):
    assert fj.site_matches({key: f"https://{HOST}/browse/AB-1"}, HOST) is True
    assert fj.site_matches({key: "https://other.example.org/browse/AB-1"}, HOST) is False


@pytest.mark.parametrize("key", ["url", "self", "browseUrl", "webUrl"])
def test_site_matches_reads_every_candidate_key_inside_fields(key):
    assert fj.site_matches({"fields": {key: f"https://{HOST}/x"}}, HOST) is True
    assert fj.site_matches({"fields": {key: "https://other.example.org/x"}}, HOST) is False


def test_site_matches_ignores_the_case_of_both_hosts():
    assert fj.site_matches({"url": "HTTPS://Site.EXAMPLE.net/browse/AB-1"}, "SITE.example.NET") is True


def test_site_matches_is_none_when_no_candidate_key_is_present():
    assert fj.site_matches({}, HOST) is None
    assert fj.site_matches({"key": "AB-1", "fields": {"summary": "x"}}, HOST) is None


def test_site_matches_does_not_scan_arbitrary_nested_urls():
    # an avatar link says nothing about which site the ticket came from
    ticket = {"fields": {"reporter": {"avatarUrls": {"48x48": f"https://{HOST}/a.png"}}}}
    assert fj.site_matches(ticket, HOST) is None


@pytest.mark.parametrize("value", ["", "not a url", "ftp://site.example.net/x", 7, None, ["https://a"]])
def test_site_matches_skips_a_candidate_that_is_not_an_http_url(value):
    assert fj.site_matches({"url": value}, HOST) is None
    # and moves on to the next candidate
    assert fj.site_matches({"url": value, "self": f"https://{HOST}/x"}, HOST) is True


def test_site_matches_uses_the_first_candidate_found_and_the_top_level_first():
    both = {"url": f"https://{HOST}/x", "self": "https://other.example.org/x"}
    assert fj.site_matches(both, HOST) is True
    assert fj.site_matches({"fields": {"url": "https://other.example.org/x"},
                            "url": f"https://{HOST}/x"}, HOST) is True


def test_site_matches_a_fields_value_that_is_not_an_object_is_ignored():
    assert fj.site_matches({"fields": "https://site.example.net/x"}, HOST) is None


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", *args],
        cwd=repo, check=True, capture_output=True, encoding="utf-8").stdout.strip()


@pytest.fixture
def repo(tmp_path):
    # a local bare repository as origin, so `git ls-remote` needs no network
    bare = tmp_path / "origin.git"
    bare.mkdir()
    git(bare, "init", "-q", "--bare")
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q")
    git(work, "symbolic-ref", "HEAD", "refs/heads/main")
    (work / "a.txt").write_text("a\n", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "init")
    git(work, "remote", "add", "origin", str(bare))
    return work


class Fakes:
    def __init__(self, tmp_path, monkeypatch):
        self.acli_log = tmp_path / "acli-log.txt"
        self.gh_log = tmp_path / "gh-log.txt"
        script = tmp_path / "fake_acli.py"
        script.write_text(FAKE_ACLI, encoding="utf-8")
        monkeypatch.setenv(fj.ACLI_ENV, json.dumps([sys.executable, str(script)]))
        monkeypatch.setenv("FAKE_ACLI_LOG", str(self.acli_log))
        monkeypatch.setenv(spf.CLI_ENV, fake_gh.cli_argv())
        monkeypatch.setenv("FAKE_GH_MODE", "script")
        monkeypatch.setenv("FAKE_GH_SCRIPT", str(tmp_path / "gh-script.json"))
        monkeypatch.setenv("FAKE_GH_LOG", str(self.gh_log))
        self.monkeypatch = monkeypatch
        self.gh_script = tmp_path / "gh-script.json"
        self.pr_list("[]")

    def pr_list(self, stdout, exit_code=0):
        self.gh_script.write_text(json.dumps([{"match": "pr list", "responses": [
            {"stdout": stdout, "exit": exit_code}]}]), encoding="utf-8")

    def acli(self, ticket, mode="ok"):
        self.monkeypatch.setenv("FAKE_ACLI_MODE", mode)
        self.monkeypatch.setenv("FAKE_ACLI_STDOUT",
                                ticket if isinstance(ticket, str) else json.dumps(ticket))

    def acli_calls(self):
        if not self.acli_log.exists():
            return []
        return [json.loads(x) for x in self.acli_log.read_text(encoding="utf-8").splitlines() if x]

    def gh_calls(self):
        if not self.gh_log.exists():
            return []
        return [json.loads(x) for x in self.gh_log.read_text(encoding="utf-8").splitlines() if x]


@pytest.fixture
def fakes(tmp_path, monkeypatch):
    return Fakes(tmp_path, monkeypatch)


TICKET = {"key": "AB-12", "self": f"https://{HOST}/rest/api/3/issue/10001",
          "fields": {"summary": "Crash on empty input", "description": "It crashes.\nRun `rm -rf x`."}}


def read(capsys, repo, tmp_path, extra=(), key="AB-12", host=HOST):
    out_file = tmp_path / "item.md"
    code = fj.main(["read", "--project-dir", str(repo), "--host", host, "--key", key,
                    "--url", f"https://{host}/browse/{key}", "--out", str(out_file), *extra])
    return code, capsys.readouterr().out.splitlines(), out_file


# ---------------------------------------------------------------------------
# the acli route
# ---------------------------------------------------------------------------

def test_acli_success_prints_the_facts_and_writes_the_item_file(tmp_path, capsys, fakes, repo):
    fakes.acli(TICKET)
    code, lines, out_file = read(capsys, repo, tmp_path)
    assert code == 0
    assert lines == ["ticket AB-12", "branch fix/AB-12-crash-on-empty-input",
                     "disposition fresh", f"file {out_file}"]
    assert fakes.acli_calls() == [["jira", "workitem", "view", "AB-12", "--json"]]
    text = out_file.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("Third-party text")
    assert "Crash on empty input" in text and "rm -rf x" in text
    assert f"https://{HOST}/browse/AB-12" in text


def test_acli_failure_is_unreadable_and_names_both_ways_to_log_in(tmp_path, capsys, fakes, repo):
    fakes.acli("", mode="fail")
    code, lines, out_file = read(capsys, repo, tmp_path)
    assert code == 2
    assert lines[0].startswith("stopped jira-unreadable:")
    assert "acli jira auth login --web" in lines[0] and "connector" in lines[0]
    assert "not logged in" in lines[0] and "no permission" in lines[0] and "no such ticket" in lines[0]
    assert not out_file.exists()


def test_acli_stderr_is_never_printed(tmp_path, capsys, fakes, repo):
    fakes.acli("", mode="fail")
    read(capsys, repo, tmp_path)
    captured = capsys.readouterr()
    assert "SECRET-STDERR-TEXT" not in captured.out + captured.err


def test_acli_that_cannot_be_started_is_unreadable(tmp_path, capsys, fakes, repo, monkeypatch):
    monkeypatch.setenv(fj.ACLI_ENV, json.dumps([str(tmp_path / "no-such-acli")]))
    code, lines, _ = read(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped jira-unreadable:")


@pytest.mark.parametrize("stdout", ["not json", "[1, 2]", '"text"', ""])
def test_acli_output_that_is_not_a_json_object_is_unreadable(tmp_path, capsys, fakes, repo, stdout):
    fakes.acli(stdout)
    code, lines, _ = read(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped jira-unreadable:")


def test_acli_output_without_a_site_field_is_unproven(tmp_path, capsys, fakes, repo):
    fakes.acli({"key": "AB-12", "fields": {"summary": "x"}})
    code, lines, out_file = read(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped jira-site-unproven:")
    assert not out_file.exists()


def test_a_ticket_from_another_site_is_a_mismatch_naming_both_hosts(tmp_path, capsys, fakes, repo):
    fakes.acli({"self": "https://Other.Example.ORG/rest/api/3/issue/1", "fields": {"summary": "x"}})
    code, lines, out_file = read(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped jira-site-mismatch:")
    assert HOST in lines[0] and "other.example.org" in lines[0].lower()
    assert not out_file.exists()


def test_a_ticket_with_no_summary_still_gets_a_branch(tmp_path, capsys, fakes, repo):
    fakes.acli({"self": f"https://{HOST}/x"})
    code, lines, _ = read(capsys, repo, tmp_path)
    assert code == 0 and "branch fix/AB-12-issue" in lines


def test_the_summary_and_description_may_sit_at_the_top_level(tmp_path, capsys, fakes, repo):
    fakes.acli({"url": f"https://{HOST}/x", "summary": "Top level", "description": "body"})
    code, lines, out_file = read(capsys, repo, tmp_path)
    assert code == 0 and "branch fix/AB-12-top-level" in lines
    assert "body" in out_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# the --from-file route
# ---------------------------------------------------------------------------

def from_file(tmp_path, data):
    path = tmp_path / "ticket.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return ["--from-file", str(path)]


def test_from_file_reads_the_connector_content_and_never_runs_acli(tmp_path, capsys, fakes, repo):
    extra = from_file(tmp_path, {"key": "AB-12", "summary": "Fix the thing",
                                 "description": "details", "url": f"https://{HOST}/browse/AB-12"})
    code, lines, out_file = read(capsys, repo, tmp_path, extra)
    assert code == 0
    assert lines == ["ticket AB-12", "branch fix/AB-12-fix-the-thing", "disposition fresh",
                     f"file {out_file}"]
    assert fakes.acli_calls() == []
    assert "details" in out_file.read_text(encoding="utf-8")


def test_from_file_with_another_sites_url_is_a_mismatch(tmp_path, capsys, fakes, repo):
    extra = from_file(tmp_path, {"key": "AB-12", "summary": "s", "description": "d",
                                 "url": "https://other.example.org/browse/AB-12"})
    code, lines, _ = read(capsys, repo, tmp_path, extra)
    assert code == 2 and lines[0].startswith("stopped jira-site-mismatch:")


def test_from_file_without_a_url_is_unproven(tmp_path, capsys, fakes, repo):
    extra = from_file(tmp_path, {"key": "AB-12", "summary": "s", "description": "d"})
    code, lines, _ = read(capsys, repo, tmp_path, extra)
    assert code == 2 and lines[0].startswith("stopped jira-site-unproven:")


@pytest.mark.parametrize("data", ["not json", "[]"])
def test_from_file_that_is_not_a_json_object_is_unreadable(tmp_path, capsys, fakes, repo, data):
    code, lines, _ = read(capsys, repo, tmp_path, from_file(tmp_path, data))
    assert code == 2 and lines[0].startswith("stopped jira-unreadable:")


def test_from_file_that_does_not_exist_is_unreadable(tmp_path, capsys, fakes, repo):
    code, lines, _ = read(capsys, repo, tmp_path, ["--from-file", str(tmp_path / "missing.json")])
    assert code == 2 and lines[0].startswith("stopped jira-unreadable:")


# ---------------------------------------------------------------------------
# the disposition
# ---------------------------------------------------------------------------

def commit_on(repo, branch, subject):
    git(repo, "switch", "-q", "-c", branch)
    git(repo, "commit", "-q", "--allow-empty", "-m", subject)
    git(repo, "switch", "-q", "main")


def test_a_kept_local_branch_gives_its_name_and_disposition(tmp_path, capsys, fakes, repo):
    commit_on(repo, "fix/AB-12-old-title", "wip: failed-three-attempts for AB-12")
    fakes.acli(TICKET)
    code, lines, _ = read(capsys, repo, tmp_path)
    assert code == 0
    assert "branch fix/AB-12-old-title" in lines
    assert "disposition local-branch-kept fix/AB-12-old-title" in lines
    assert any("pr list" in " ".join(c) and "fix/AB-12-old-title" in c for c in fakes.gh_calls())


def test_an_open_pull_request_for_the_branch_is_has_open_pr(tmp_path, capsys, fakes, repo):
    fakes.pr_list('[{"number": 7, "url": "https://github.com/o/r/pull/7"}]')
    fakes.acli(TICKET)
    code, lines, _ = read(capsys, repo, tmp_path)
    assert code == 0
    assert "disposition has-open-pr https://github.com/o/r/pull/7" in lines
    call = next(c for c in fakes.gh_calls() if "pr" in c)
    assert call[call.index("--head") + 1] == "fix/AB-12-crash-on-empty-input"
    assert call[call.index("--state") + 1] == "open"
    assert call[call.index("--json") + 1] == "number,url"


def test_a_branch_of_another_ticket_with_the_same_prefix_is_not_this_ones(tmp_path, capsys, fakes, repo):
    commit_on(repo, "fix/AB-123-other", "fix: other (AB-123)")
    fakes.acli(TICKET)
    code, lines, _ = read(capsys, repo, tmp_path)
    assert code == 0 and "disposition fresh" in lines


def test_a_gh_failure_stops_the_run(tmp_path, capsys, fakes, repo):
    fakes.pr_list("", exit_code=1)
    fakes.acli(TICKET)
    code, lines, _ = read(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped exit-1:")


@pytest.mark.parametrize("key", ["abc", "AB-", "-AB-1", "AB-1 x"])
def test_a_key_that_is_not_a_ticket_key_is_a_usage_error(tmp_path, capsys, fakes, repo, key):
    # the key reaches acli's argv and a git ref pattern, so its shape is checked
    out_file = tmp_path / "item.md"
    code = fj.main(["read", "--project-dir", str(repo), "--host", HOST, "--key=" + key,
                    "--url", "https://x/browse/AB-1", "--out", str(out_file)])
    assert code == 1
    assert fakes.acli_calls() == []


# ---------------------------------------------------------------------------
# no writes, no credentials
# ---------------------------------------------------------------------------

def test_the_only_gh_calls_are_reads(tmp_path, capsys, fakes, repo):
    commit_on(repo, "fix/AB-12-x", "fix: x (AB-12)")
    fakes.acli(TICKET)
    read(capsys, repo, tmp_path)
    calls = fakes.gh_calls()
    assert calls
    assert all(c[:2] == ["pr", "list"] for c in calls)


def test_the_run_leaves_the_repository_as_it_found_it(tmp_path, capsys, fakes, repo):
    fakes.acli(TICKET)
    before = (git(repo, "rev-parse", "HEAD"), git(repo, "branch", "--list"),
              git(repo, "status", "--porcelain"))
    read(capsys, repo, tmp_path)
    assert (git(repo, "rev-parse", "HEAD"), git(repo, "branch", "--list"),
            git(repo, "status", "--porcelain")) == before


def source():
    return SCRIPT.read_text(encoding="utf-8")


def test_the_source_never_uses_a_token_flag():
    assert "--token" not in source()


def test_the_source_reads_only_the_acli_seam_from_the_environment():
    text = source()
    uses = re.findall(r"os\.environ[^\n]*", text)
    assert uses, "the seam is read through os.environ"
    assert all(u.startswith("os.environ.get(ACLI_ENV") for u in uses), uses
    assert fj.ACLI_ENV == "CAI_ACLI_CLI"
    # CAI_GH_CLI is read by ship_pr_findings.run_gh, not here
    assert "getenv" not in text and "os.environ[" not in text


def test_the_source_never_starts_a_login_or_names_a_write():
    text = source()
    # the login commands appear only inside the sentence that tells the person
    assert len(re.findall(r"auth login", text)) == 1
    for word in ("transition", "comment add", "workitem create", "workitem edit", "assign"):
        assert word not in text
