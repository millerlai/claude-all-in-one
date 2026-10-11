"""fix_threads list and reply: which threads are listed in what state, and when a reply may be sent.

`gh` is faked through CAI_GH_CLI (tests/fake_gh.py, `script` mode); git is the
real one, run only inside tmp_path, with a local bare repository as `origin` so
`git ls-remote` needs no network, and HEAD on `main`, never on the PR branch.
The fake's `match` strings (`reviewThreads`, `pr view`,
`addPullRequestReviewThreadReply`, `resolveReviewThread`) are not substrings of
each other.
"""
import json
import subprocess
from types import SimpleNamespace

import pytest

import fake_gh
import fix_target
import fix_threads as ft
import ship_pr_findings as spf

FIXED_TITLE = "fix: address review thread 11 on PR #7"


# ---------------------------------------------------------------------------
# pure functions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("last_login, last_body, branch_commit, expected", [
    ("me", "Fixed in abc1234.", None, ("complete-resolve", "abc1234")),
    ("me", "Fixed in " + "A" * 40 + ".\n\nWhy.", "c" * 40, ("complete-resolve", "A" * 40)),
    ("me", "Fixed in abc123.", None, ("skip-own-reply", None)),
    ("me", "Not fixed: needs-decision", "c" * 40, ("skip-own-reply", None)),
    ("someone", "Fixed in abc1234.", "c" * 40, ("committed", "c" * 40)),
    (None, "", None, ("pending", None)),
    ("someone", "please fix", None, ("pending", None)),
])
def test_thread_state(last_login, last_body, branch_commit, expected):
    assert ft.thread_state(last_login, last_body, "me", branch_commit) == expected


@pytest.mark.parametrize("pr_head, local_head, ancestor, expected", [
    ("a" * 40, "a" * 40, True, True),
    ("a" * 40, "b" * 40, True, False),
    ("a" * 40, "a" * 40, False, False),
    ("", "", True, False),
])
def test_may_reply_fixed(pr_head, local_head, ancestor, expected):
    assert ft.may_reply_fixed(pr_head, local_head, ancestor) is expected


# ---------------------------------------------------------------------------
# a temporary repository and a scripted gh
# ---------------------------------------------------------------------------

def git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", *args],
        cwd=repo, check=True, capture_output=True, encoding="utf-8").stdout.strip()


def commit(repo, subject):
    git(repo, "commit", "-q", "--allow-empty", "-m", subject)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    """main with one commit, and a pushed branch `feature`; HEAD is on main."""
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
    git(work, "push", "-q", "origin", "main")
    git(work, "switch", "-q", "-c", "feature")
    oid = commit(work, "feature work")
    git(work, "push", "-q", "origin", "feature")
    git(work, "switch", "-q", "main")
    return SimpleNamespace(path=work, oid=oid, main=git(work, "rev-parse", "main"))


class Gh:
    def __init__(self, tmp_path, monkeypatch):
        self.script = tmp_path / "gh-script.json"
        self.log = tmp_path / "gh-log.txt"
        monkeypatch.setenv(spf.CLI_ENV, fake_gh.cli_argv())
        monkeypatch.setenv("FAKE_GH_MODE", "script")
        monkeypatch.setenv("FAKE_GH_SCRIPT", str(self.script))
        monkeypatch.setenv("FAKE_GH_LOG", str(self.log))

    def set(self, **by_match):
        entries = [{"match": match, "responses": responses}
                   for match, responses in by_match.items()]
        self.script.write_text(json.dumps(entries), encoding="utf-8")

    def calls(self, needle=None):
        if not self.log.exists():
            return []
        rows = [json.loads(line) for line in
                self.log.read_text(encoding="utf-8").splitlines() if line]
        return [r for r in rows if needle is None or needle in " ".join(r)]


@pytest.fixture
def gh(tmp_path, monkeypatch):
    return Gh(tmp_path, monkeypatch)


def resp(stdout="", stderr="", exit=0):
    return {"stdout": stdout, "stderr": stderr, "exit": exit}


def comment(login="rev", body="please fix", dbid=11, typename="User"):
    return {"databaseId": dbid, "author": {"__typename": typename, "login": login},
            "body": body, "url": "https://github.com/o/r/pull/7#discussion_r%d" % dbid}


def thread(tid="PRRT_1", dbid=11, resolved=False, outdated=False, path="a.py", line=3,
           can_reply=True, can_resolve=True, comments=None):
    comments = comments or [comment(dbid=dbid)]
    last = comments[-1]
    return {"id": tid, "isResolved": resolved, "isOutdated": outdated, "path": path,
            "line": line, "viewerCanReply": can_reply, "viewerCanResolve": can_resolve,
            "comments": {"totalCount": len(comments), "nodes": comments},
            "last": {"nodes": [{"author": last["author"], "body": last["body"]}]}}


def page(oid, *nodes, has_next=False, cursor=None, **pr):
    facts = {"state": "OPEN", "headRefName": "feature", "headRefOid": oid,
             "baseRefName": "main", "isCrossRepository": False,
             "url": "https://github.com/o/r/pull/7"}
    facts.update(pr)
    facts["reviewThreads"] = {"pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                              "nodes": list(nodes)}
    return resp(json.dumps({"data": {"repository": {"pullRequest": facts}}}))


def run_list(capsys, repo, tmp_path, *extra):
    out_dir = tmp_path / "items"
    code = ft.main(["list", "--project-dir", str(repo.path), "--owner", "o", "--repo", "r",
                    "--login", "me", "--out-dir", str(out_dir), *extra])
    return code, capsys.readouterr().out.splitlines(), out_dir


def head_branch(repo):
    return git(repo.path, "symbolic-ref", "--short", "HEAD")


# ---------------------------------------------------------------------------
# list: what is printed
# ---------------------------------------------------------------------------

def test_list_prints_the_facts_and_one_line_per_unresolved_thread(tmp_path, capsys, gh, repo):
    gh.set(reviewThreads=[page(repo.oid, thread(), thread("PRRT_2", 12, resolved=True))])
    code, lines, out_dir = run_list(capsys, repo, tmp_path, "--number", "7")
    assert code == 0
    assert lines == [
        "pr 7 https://github.com/o/r/pull/7 OPEN",
        f"head feature {repo.oid}",
        "base main",
        "sync same",
        "threads 1 pending 1",
        f"thread 11 PRRT_1 a.py:3 bot=no outdated=no state=pending file={out_dir / 'thread-11.md'}",
    ]
    assert head_branch(repo) == "main"
    assert git(repo.path, "status", "--porcelain") == ""


def test_list_item_file_is_marked_third_party_and_holds_every_comment(tmp_path, capsys, gh, repo):
    comments = [comment("rev", "please rename x", 11), comment("me", "why?", 15)]
    gh.set(reviewThreads=[page(repo.oid, thread(comments=comments))])
    code, _, out_dir = run_list(capsys, repo, tmp_path, "--number", "7")
    assert code == 0
    text = (out_dir / "thread-11.md").read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("Third-party text")
    for wanted in ("a.py", "line 3", "please rename x", "why?", "rev", "me"):
        assert wanted in text


def test_list_an_outdated_thread_prints_no_line_number(tmp_path, capsys, gh, repo):
    # GitHub gives an outdated thread a null line; a stale number is dropped too
    for line in (None, 3):
        gh.set(reviewThreads=[page(repo.oid, thread(outdated=True, line=line))])
        code, lines, out_dir = run_list(capsys, repo, tmp_path, "--number", "7")
        assert code == 0
        assert lines[-1] == (f"thread 11 PRRT_1 a.py bot=no outdated=yes state=pending "
                             f"file={out_dir / 'thread-11.md'}")
        text = (out_dir / "thread-11.md").read_text(encoding="utf-8")
        assert "line 3" not in text and "Outdated: yes" in text


def test_list_a_bot_thread_is_marked_by_typename_not_login(tmp_path, capsys, gh, repo):
    bot = comment("github-advanced-security", "alert", 11, typename="Bot")
    gh.set(reviewThreads=[page(repo.oid, thread(comments=[bot]))])
    code, lines, _ = run_list(capsys, repo, tmp_path, "--number", "7")
    assert code == 0 and " bot=yes " in lines[-1]


def test_list_reads_every_page_and_passes_the_cursor(tmp_path, capsys, gh, repo):
    first = page(repo.oid, thread("PRRT_1", 11), has_next=True, cursor="CUR1")
    second = page(repo.oid, thread("PRRT_2", 12), thread("PRRT_3", 13))
    gh.set(reviewThreads=[first, second])
    code, lines, _ = run_list(capsys, repo, tmp_path, "--number", "7")
    assert code == 0
    assert "threads 3 pending 3" in lines
    assert [line.split()[1] for line in lines if line.startswith("thread ")] == ["11", "12", "13"]
    queries = gh.calls("reviewThreads")
    assert len(queries) == 2
    assert "endCursor=CUR1" not in " ".join(queries[0])
    assert "endCursor=CUR1" in queries[1]


def test_list_without_a_number_asks_gh_for_the_current_branchs_pull_request(
        tmp_path, capsys, gh, repo):
    gh.set(**{"pr view": [resp('{"number": 7}')],
              "reviewThreads": [page(repo.oid, thread())]})
    code, lines, _ = run_list(capsys, repo, tmp_path)
    assert code == 0 and lines[0].startswith("pr 7 ")
    assert "number=7" in gh.calls("reviewThreads")[0]


def test_list_gives_the_four_thread_states(tmp_path, capsys, gh, repo):
    git(repo.path, "switch", "-q", "feature")
    sha = commit(repo.path, "fix: address review thread 14 on PR #7")
    git(repo.path, "switch", "-q", "main")
    mine = [comment("rev", "x", 12), comment("me", "Fixed in abcdef1.", 99)]
    own = [comment("rev", "y", 13), comment("me", "Not fixed: needs-decision", 98)]
    gh.set(reviewThreads=[page(
        repo.oid, thread("PRRT_1", 11), thread("PRRT_2", 12, comments=mine),
        thread("PRRT_3", 13, comments=own), thread("PRRT_4", 14))])
    code, lines, _ = run_list(capsys, repo, tmp_path, "--number", "7")
    assert code == 0
    states = {line.split()[1]: line.split("state=")[1].split(" file=")[0]
              for line in lines if line.startswith("thread ")}
    assert states == {"11": "pending", "12": "complete-resolve abcdef1",
                      "13": "skip-own-reply", "14": f"committed {sha}"}
    assert "sync ahead-own" in lines and "threads 4 pending 1" in lines


# ---------------------------------------------------------------------------
# list: the four sync states, computed with HEAD on main
# ---------------------------------------------------------------------------

def sync_line(capsys, repo, tmp_path, gh):
    gh.set(reviewThreads=[page(repo.oid, thread())])
    code, lines, _ = run_list(capsys, repo, tmp_path, "--number", "7")
    return code, lines


def test_sync_same(tmp_path, capsys, gh, repo):
    code, lines = sync_line(capsys, repo, tmp_path, gh)
    assert code == 0 and "sync same" in lines


def test_sync_absent_when_there_is_no_local_branch(tmp_path, capsys, gh, repo):
    git(repo.path, "branch", "-D", "feature")
    code, lines = sync_line(capsys, repo, tmp_path, gh)
    assert code == 0 and "sync absent" in lines


def test_sync_absent_finds_the_fix_commit_on_the_remote_branch(tmp_path, capsys, gh, repo):
    git(repo.path, "switch", "-q", "feature")
    sha = commit(repo.path, FIXED_TITLE)
    git(repo.path, "push", "-q", "origin", "feature")
    git(repo.path, "switch", "-q", "main")
    git(repo.path, "branch", "-D", "feature")
    gh.set(reviewThreads=[page(sha, thread())])
    code, lines, _ = run_list(capsys, repo, tmp_path, "--number", "7")
    assert code == 0 and "sync absent" in lines and f"state=committed {sha}" in lines[-1]


def test_sync_behind_when_the_local_branch_is_an_ancestor(tmp_path, capsys, gh, repo):
    git(repo.path, "branch", "-f", "feature", "main")
    code, lines = sync_line(capsys, repo, tmp_path, gh)
    assert code == 0 and "sync behind" in lines


def test_sync_ahead_own_when_only_fix_commits_lead(tmp_path, capsys, gh, repo):
    git(repo.path, "switch", "-q", "feature")
    commit(repo.path, FIXED_TITLE)
    git(repo.path, "switch", "-q", "main")
    code, lines = sync_line(capsys, repo, tmp_path, gh)
    assert code == 0 and "sync ahead-own" in lines


def test_sync_stops_when_a_foreign_commit_leads(tmp_path, capsys, gh, repo):
    git(repo.path, "switch", "-q", "feature")
    commit(repo.path, "my own experiment")
    git(repo.path, "switch", "-q", "main")
    code, lines = sync_line(capsys, repo, tmp_path, gh)
    assert code == 2 and lines[0].startswith("stopped branch-not-in-sync:")


def test_sync_stops_when_the_branches_diverged(tmp_path, capsys, gh, repo):
    git(repo.path, "branch", "-f", "feature", "main")
    git(repo.path, "switch", "-q", "feature")
    commit(repo.path, FIXED_TITLE)
    git(repo.path, "switch", "-q", "main")
    code, lines = sync_line(capsys, repo, tmp_path, gh)
    assert code == 2 and lines[0].startswith("stopped branch-not-in-sync:")


def test_sync_a_commit_title_for_another_pull_request_is_foreign(tmp_path, capsys, gh, repo):
    git(repo.path, "switch", "-q", "feature")
    commit(repo.path, "fix: address review thread 11 on PR #70")
    git(repo.path, "switch", "-q", "main")
    code, lines = sync_line(capsys, repo, tmp_path, gh)
    assert code == 2 and lines[0].startswith("stopped branch-not-in-sync:")


# ---------------------------------------------------------------------------
# list: every stop reason
# ---------------------------------------------------------------------------

def stopped(capsys, repo, tmp_path, reason):
    code, lines, out_dir = run_list(capsys, repo, tmp_path, "--number", "7")
    assert code == 2 and lines[0].startswith(f"stopped {reason}:"), lines
    assert len(lines) == 1
    assert not out_dir.exists()


def test_stop_no_pull_request_from_gh_pr_view(tmp_path, capsys, gh, repo):
    gh.set(**{"pr view": [resp(stderr="no pull requests found for branch", exit=1)]})
    code, lines, _ = run_list(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped no-pull-request:")


def test_stop_no_pull_request_when_the_query_finds_none(tmp_path, capsys, gh, repo):
    gh.set(reviewThreads=[resp(json.dumps({"data": {"repository": {"pullRequest": None}}}))])
    stopped(capsys, repo, tmp_path, "no-pull-request")


def test_stop_no_pull_request_when_graphql_says_so(tmp_path, capsys, gh, repo):
    gh.set(reviewThreads=[resp(stderr="Could not resolve to a PullRequest", exit=1)])
    stopped(capsys, repo, tmp_path, "no-pull-request")


@pytest.mark.parametrize("state", ["MERGED", "CLOSED"])
def test_stop_pr_not_open(tmp_path, capsys, gh, repo, state):
    gh.set(reviewThreads=[page(repo.oid, thread(), state=state)])
    stopped(capsys, repo, tmp_path, "pr-not-open")


def test_stop_pr_from_fork_flag(tmp_path, capsys, gh, repo):
    gh.set(reviewThreads=[page(repo.oid, thread(), isCrossRepository=True)])
    stopped(capsys, repo, tmp_path, "pr-from-fork")


def test_stop_pr_from_fork_when_origin_has_no_such_branch(tmp_path, capsys, gh, repo):
    gh.set(reviewThreads=[page(repo.oid, thread(), headRefName="elsewhere")])
    stopped(capsys, repo, tmp_path, "pr-from-fork")


def test_stop_pr_from_fork_when_origins_branch_is_not_the_pr_head(tmp_path, capsys, gh, repo):
    gh.set(reviewThreads=[page("e" * 40, thread())])
    stopped(capsys, repo, tmp_path, "pr-from-fork")


@pytest.mark.parametrize("field, name", [
    ("headRefName", "fix$(id>x)"), ("headRefName", "a;b"), ("headRefName", "-x"),
    ("headRefName", "a b"), ("headRefName", "it's"), ("baseRefName", "main&x"),
    ("baseRefName", "--output=x")])
def test_stop_unsafe_branch_name(tmp_path, capsys, gh, repo, field, name):
    # The skill puts the head name on git command lines; a name a stranger chose
    # with a shell character or a leading '-' must stop the run before any does.
    gh.set(reviewThreads=[page(repo.oid, thread(), **{field: name})])
    stopped(capsys, repo, tmp_path, "unsafe-branch-name")


@pytest.mark.parametrize("flags", [{"can_reply": False}, {"can_resolve": False}])
def test_stop_cannot_write_threads(tmp_path, capsys, gh, repo, flags):
    gh.set(reviewThreads=[page(repo.oid, thread(), thread("PRRT_2", 12, **flags))])
    stopped(capsys, repo, tmp_path, "cannot-write-threads")


def test_a_resolved_thread_nobody_can_write_to_does_not_stop_the_run(tmp_path, capsys, gh, repo):
    gh.set(reviewThreads=[page(repo.oid, thread(), thread(
        "PRRT_2", 12, resolved=True, can_reply=False, can_resolve=False))])
    code, _, _ = run_list(capsys, repo, tmp_path, "--number", "7")
    assert code == 0


@pytest.mark.parametrize("stderr, exit, reason", [
    ("HTTP 401", 1, "not-authenticated"),
    ("Could not resolve to a repository", 1, "no-github-repo"),
    ("dial tcp: lookup", 1, "unreachable"),
    ("boom", 4, "exit-4"),
])
def test_stop_names_the_gh_failure_class(tmp_path, capsys, gh, repo, stderr, exit, reason):
    gh.set(reviewThreads=[resp(stderr=stderr, exit=exit)])
    stopped(capsys, repo, tmp_path, reason)


@pytest.mark.parametrize("stdout", [
    "not json",
    json.dumps({"data": {"repository": {"pullRequest": {"state": "OPEN"}}}}),
    json.dumps({"data": {}}),
])
def test_stop_unreadable(tmp_path, capsys, gh, repo, stdout):
    gh.set(reviewThreads=[resp(stdout)])
    stopped(capsys, repo, tmp_path, "unreadable")


def test_stop_unreadable_when_a_thread_has_no_comment(tmp_path, capsys, gh, repo):
    bad = thread()
    bad["comments"]["nodes"] = []
    gh.set(reviewThreads=[page(repo.oid, bad)])
    stopped(capsys, repo, tmp_path, "unreadable")


def test_list_writes_only_into_the_out_dir(tmp_path, capsys, gh, repo):
    gh.set(reviewThreads=[page(repo.oid, thread())])
    run_list(capsys, repo, tmp_path, "--number", "7")
    assert git(repo.path, "status", "--porcelain", "--ignored") == ""


def test_list_escapes_control_characters_in_what_it_prints(tmp_path, capsys, gh, repo):
    gh.set(reviewThreads=[page(repo.oid, thread(path="a\nb.py"))])
    code, lines, _ = run_list(capsys, repo, tmp_path, "--number", "7")
    assert code == 0 and " a\\x0ab.py:3 " in lines[-1]


def test_list_needs_its_flags():
    with pytest.raises(SystemExit) as exc:
        ft.main(["list", "--project-dir", "."])
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# reply
# ---------------------------------------------------------------------------

REPLY = "addPullRequestReviewThreadReply"
RESOLVE = "resolveReviewThread"
OK = resp('{"data": {}}')
SENTENCES = fix_target.OUTCOMES


def reply(capsys, repo, *extra, outcome="fixed", commit="HEAD", thread_id="PRRT_1"):
    argv = ["reply", "--project-dir", str(repo.path), "--owner", "o", "--repo", "r",
            "--number", "7", "--thread-id", thread_id, "--outcome", outcome]
    if commit:
        argv += ["--commit", repo.main if commit == "HEAD" else commit]
    code = ft.main(argv + list(extra))
    return code, capsys.readouterr().out.splitlines()


def script(gh, repo, head=None, reply_resp=OK, resolve_resp=OK):
    gh.set(**{"pr view": [resp(json.dumps({"headRefOid": head or repo.main}))],
              REPLY: [reply_resp], RESOLVE: [resolve_resp]})


def mutations(gh):
    return gh.calls(REPLY) + gh.calls(RESOLVE)


def test_reply_fixed_replies_then_resolves(tmp_path, capsys, gh, repo):
    script(gh, repo)
    note = tmp_path / "note.txt"
    note.write_text("Renamed x to y.\n", encoding="utf-8")
    code, lines = reply(capsys, repo, "--body-file", str(note))
    assert code == 0 and lines == ["replied-fixed"]
    first, second = gh.calls(REPLY)[0], gh.calls(RESOLVE)[0]
    assert "body=Fixed in %s.\n\nRenamed x to y." % repo.main in first
    assert "threadId=PRRT_1" in first and "threadId=PRRT_1" in second
    assert first[first.index("threadId=PRRT_1") - 1] == "-F"
    assert gh.calls().index(first) < gh.calls().index(second)
    assert not any("body=" in a for a in second)
    assert repo.main not in "\n".join(lines) and "Renamed" not in "\n".join(lines)
    assert head_branch(repo) == "main"


def test_reply_fixed_without_a_body_file_is_just_the_first_line(capsys, gh, repo):
    script(gh, repo)
    code, _ = reply(capsys, repo)
    assert code == 0
    assert "body=Fixed in %s." % repo.main in gh.calls(REPLY)[0]


def test_reply_fixed_reads_the_pull_request_head_first(capsys, gh, repo):
    script(gh, repo)
    reply(capsys, repo)
    calls = gh.calls()
    assert "pr view" in " ".join(calls[0]) and "7" in calls[0] and "headRefOid" in calls[0]
    assert len(calls) == 3


def test_reply_refuses_when_the_pull_request_head_differs_from_local_head(capsys, gh, repo):
    script(gh, repo, head="f" * 40)
    code, lines = reply(capsys, repo)
    assert code == 3 and lines[0] == "refused head-mismatch"
    assert mutations(gh) == []


def test_reply_refuses_when_the_commit_is_not_an_ancestor_of_head(capsys, gh, repo):
    script(gh, repo)
    code, lines = reply(capsys, repo, commit=repo.oid)
    assert code == 3 and lines[0] == "refused head-mismatch"
    assert mutations(gh) == []


def test_reply_refuses_an_unknown_commit(capsys, gh, repo):
    script(gh, repo)
    code, lines = reply(capsys, repo, commit="1" * 40)
    assert code == 3 and mutations(gh) == []


def test_reply_resolve_failing_is_exit_4_after_the_reply(capsys, gh, repo):
    script(gh, repo, resolve_resp=resp(stderr="boom", exit=1))
    code, lines = reply(capsys, repo)
    assert code == 4 and lines[0] == "replied-not-resolved"
    assert len(gh.calls(REPLY)) == 1


def test_reply_failing_is_exit_5_and_never_resolves(capsys, gh, repo):
    script(gh, repo, reply_resp=resp(stderr="HTTP 401", exit=1))
    code, lines = reply(capsys, repo)
    assert code == 5 and lines[0] == "reply-failed not-authenticated"
    assert gh.calls(RESOLVE) == []


def test_reply_a_graphql_error_in_a_successful_call_counts_as_failed(capsys, gh, repo):
    script(gh, repo, reply_resp=resp('{"errors": [{"message": "nope"}]}'))
    code, lines = reply(capsys, repo)
    assert code == 5 and lines[0] == "reply-failed unreadable"
    assert gh.calls(RESOLVE) == []


def test_reply_stops_when_the_pull_request_head_cannot_be_read(capsys, gh, repo):
    gh.set(**{"pr view": [resp(stderr="HTTP 401", exit=1)]})
    code, lines = reply(capsys, repo)
    assert code == 2 and lines[0].startswith("stopped not-authenticated:")
    assert mutations(gh) == []


def test_reply_stops_when_the_pull_request_head_is_unreadable(capsys, gh, repo):
    gh.set(**{"pr view": [resp("not json")]})
    code, lines = reply(capsys, repo)
    assert code == 2 and lines[0].startswith("stopped unreadable:")
    assert mutations(gh) == []


def test_reply_stops_when_git_cannot_read_head(tmp_path, capsys, gh, repo):
    script(gh, repo)
    elsewhere = SimpleNamespace(path=tmp_path, main=repo.main)
    code, lines = reply(capsys, elsewhere)
    assert code == 2 and lines[0].startswith("stopped git-failed:")
    assert mutations(gh) == []


@pytest.mark.parametrize("word", ["cannot-reproduce", "needs-decision", "too-large",
                                  "failed-three-attempts", "paths-mismatch"])
def test_reply_not_fixed_never_resolves_and_never_reads_the_head(tmp_path, capsys, gh, repo, word):
    script(gh, repo)
    note = tmp_path / "note.txt"
    note.write_text("Because.\n", encoding="utf-8")
    code, lines = reply(capsys, repo, "--body-file", str(note), outcome=word, commit=None)
    assert code == 0 and lines == ["replied-not-fixed"]
    assert gh.calls(RESOLVE) == [] and gh.calls("pr view") == []
    assert "body=Not fixed: %s\n\nBecause." % SENTENCES[word] in gh.calls(REPLY)[0]


def test_reply_not_fixed_failing_is_exit_5(capsys, gh, repo):
    script(gh, repo, reply_resp=resp(stderr="boom", exit=1))
    code, lines = reply(capsys, repo, outcome="needs-decision", commit=None)
    assert code == 5 and lines[0] == "reply-failed exit-1"
    assert gh.calls(RESOLVE) == []


def test_resolve_only_never_replies(capsys, gh, repo):
    script(gh, repo)
    code, lines = reply(capsys, repo, "--resolve-only")
    assert code == 0 and lines == ["replied-fixed"]
    assert gh.calls(REPLY) == [] and len(gh.calls(RESOLVE)) == 1


def test_resolve_only_is_gated_like_a_reply(capsys, gh, repo):
    script(gh, repo, head="f" * 40)
    code, lines = reply(capsys, repo, "--resolve-only")
    assert code == 3 and lines[0] == "refused head-mismatch"
    assert mutations(gh) == []


def test_resolve_only_failing_is_exit_4(capsys, gh, repo):
    script(gh, repo, resolve_resp=resp(stderr="boom", exit=1))
    code, lines = reply(capsys, repo, "--resolve-only")
    assert code == 4 and lines[0] == "replied-not-resolved"


@pytest.mark.parametrize("kwargs, extra", [
    ({"commit": None}, []),
    ({"commit": "not-a-sha"}, []),
    ({"outcome": "needs-decision", "commit": None}, ["--resolve-only"]),
    ({"outcome": "replied-fixed", "commit": None}, []),
    ({"thread_id": "@file"}, []),
    ({}, ["--body-file", "missing-file.txt"]),
])
def test_reply_usage_errors_write_nothing(capsys, gh, repo, kwargs, extra):
    script(gh, repo)
    if kwargs.get("outcome") == "replied-fixed":
        with pytest.raises(SystemExit) as exc:
            reply(capsys, repo, *extra, **kwargs)
        assert exc.value.code == 1
    else:
        code, _ = reply(capsys, repo, *extra, **kwargs)
        assert code == 1
    assert gh.calls() == []


def test_reply_needs_its_flags():
    with pytest.raises(SystemExit) as exc:
        ft.main(["reply", "--project-dir", "."])
    assert exc.value.code == 1
