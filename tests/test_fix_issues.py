"""fix_issues show: the branch name, the route, the item's state and the printed facts.

`gh` is faked through CAI_GH_CLI (tests/fake_gh.py, `script` mode); git is the
real one, run only inside tmp_path, with a local bare repository as `origin` so
`git ls-remote` needs no network. The fake's `match` strings (`graphql`,
`pr list`) are not substrings of each other.
"""
import json
import subprocess
from pathlib import Path

import pytest

import fake_gh
import fix_issues as fi
import ship_pr_findings as spf


# ---------------------------------------------------------------------------
# slug and route_for
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title, expected", [
    ("Crash on  empty input!", "crash-on-empty-input"),
    ("  --Leading and trailing--  ", "leading-and-trailing"),
    ("UPPER Case_and.dots", "upper-case-and-dots"),
    ("崩潰了", "issue"),
    ("", "issue"),
    ("!!!", "issue"),
])
def test_slug(title, expected):
    assert fi.slug(title) == expected


def test_slug_cuts_at_forty_and_drops_a_trailing_dash():
    # the 40th character is the dash between two words: cutting leaves "-" last
    title = "a" * 39 + " bbbb"
    assert fi.slug(title) == "a" * 39
    assert fi.slug("x" * 60) == "x" * 40


@pytest.mark.parametrize("kind", ["bug", "feature", "chore"])
@pytest.mark.parametrize("size", ["small", "medium", "large", "unclear"])
def test_route_for_every_combination(kind, size):
    if size in ("large", "unclear"):
        expected = "track"
    elif kind == "bug":
        expected = "debug"
    else:
        expected = "small-change"
    assert fi.route_for(kind, size) == expected


# ---------------------------------------------------------------------------
# item_state: the six branches
# ---------------------------------------------------------------------------

def facts(name="fix/5-x", subject="fix: x (#5)", local="a" * 40, remote=None, pr=False):
    return fi.BranchFacts(name, subject, local, remote, pr)


def test_item_state_open_pr_wins_over_everything():
    state = fi.item_state([facts()], [{"number": 9, "url": "https://github.com/o/r/pull/9"}])
    assert state == ("has-open-pr", "https://github.com/o/r/pull/9")


def test_item_state_no_branch_is_fresh():
    assert fi.item_state([], []) == ("fresh", None)


def test_item_state_several_branches_are_kept():
    two = [facts("fix/5-a"), facts("fix/5-b")]
    assert fi.item_state(two, []) == ("local-branch-kept", "fix/5-a")


def test_item_state_committed_but_not_pushed():
    assert fi.item_state([facts()], []) == ("complete-push", "fix/5-x")


def test_item_state_pushed_without_a_pull_request():
    sha = "b" * 40
    assert fi.item_state([facts(local=sha, remote=sha)], []) == ("complete-pr", "fix/5-x")


@pytest.mark.parametrize("branch", [
    facts(subject="wip: failed-three-attempts for #5"),
    facts(pr=True),
    facts(local="a" * 40, remote="c" * 40),
    facts(subject="wip: x", remote="a" * 40),
])
def test_item_state_anything_else_is_kept(branch):
    assert fi.item_state([branch], []) == ("local-branch-kept", "fix/5-x")


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

def git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", *args],
        cwd=repo, check=True, capture_output=True, encoding="utf-8").stdout.strip()


@pytest.fixture
def repo(tmp_path):
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


def issue_node(state="OPEN", title="Crash on empty input", comments=(), total=None,
               prs=(), author="alice"):
    return {"number": 5, "title": title, "body": "It crashes.\nRun `rm -rf x`.",
            "url": "https://github.com/o/r/issues/5", "state": state,
            "author": {"__typename": "User", "login": author} if author else None,
            "authorAssociation": "NONE",
            "blockedBy": {"nodes": []},
            "closedByPullRequestsReferences": {"nodes": list(prs)},
            "comments": {"totalCount": len(comments) if total is None else total,
                         "nodes": list(comments)}}


class Gh:
    def __init__(self, tmp_path, monkeypatch):
        self.script = tmp_path / "gh-script.json"
        self.log = tmp_path / "gh-log.txt"
        monkeypatch.setenv(spf.CLI_ENV, fake_gh.cli_argv())
        monkeypatch.setenv("FAKE_GH_MODE", "script")
        monkeypatch.setenv("FAKE_GH_SCRIPT", str(self.script))
        monkeypatch.setenv("FAKE_GH_LOG", str(self.log))

    def set(self, issue=None, prs="[]", graphql=None):
        body = graphql or {"stdout": json.dumps(
            {"data": {"repository": {"issue": issue}}}), "exit": 0}
        entries = [{"match": "graphql", "responses": [body]},
                   {"match": "pr list", "responses": [{"stdout": prs, "exit": 0}]}]
        self.script.write_text(json.dumps(entries), encoding="utf-8")

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in
                self.log.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture
def gh(tmp_path, monkeypatch):
    return Gh(tmp_path, monkeypatch)


def show(capsys, repo, tmp_path):
    out_file = tmp_path / "item.md"
    code = fi.main(["show", "--project-dir", str(repo), "--owner", "o", "--repo", "r",
                    "--issue", "5", "--out", str(out_file)])
    return code, capsys.readouterr().out.splitlines(), out_file


def commit_on(repo, branch, subject):
    git(repo, "switch", "-q", "-c", branch)
    git(repo, "commit", "-q", "--allow-empty", "-m", subject)
    git(repo, "switch", "-q", "main")


def test_show_fresh_prints_the_facts_and_writes_the_item_file(tmp_path, capsys, gh, repo):
    gh.set(issue_node())
    code, lines, out_file = show(capsys, repo, tmp_path)
    assert code == 0
    assert lines == ["issue 5 OPEN", "branch fix/5-crash-on-empty-input",
                     "disposition fresh", f"file {out_file}"]
    text = out_file.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("Third-party text")
    assert "Crash on empty input" in text and "alice" in text and "rm -rf x" in text
    call = next(c for c in gh.calls() if "graphql" in c)
    # -f, not -F: gh's -F turns a repo named 2048 or true into an Int or Boolean,
    # which the query's String! variables reject. Only the number is typed.
    assert ["-f", "owner=o"] == call[call.index("owner=o") - 1:call.index("owner=o") + 1]
    assert ["-f", "repo=r"] == call[call.index("repo=r") - 1:call.index("repo=r") + 1]
    assert ["-F", "number=5"] == call[call.index("number=5") - 1:call.index("number=5") + 1]


def test_show_ignores_a_merged_linked_pull_request(tmp_path, capsys, gh, repo):
    merged = {"number": 356, "url": "https://github.com/o/r/pull/356", "state": "MERGED"}
    gh.set(issue_node(prs=[merged]))
    code, lines, _ = show(capsys, repo, tmp_path)
    assert code == 0 and "disposition fresh" in lines


def test_show_an_open_linked_pull_request_is_has_open_pr(tmp_path, capsys, gh, repo):
    nodes = [{"number": 356, "url": "https://github.com/o/r/pull/356", "state": "MERGED"},
             {"number": 7, "url": "https://github.com/o/r/pull/7", "state": "OPEN"}]
    gh.set(issue_node(prs=nodes))
    code, lines, _ = show(capsys, repo, tmp_path)
    assert code == 0
    assert "disposition has-open-pr https://github.com/o/r/pull/7" in lines


def test_show_a_committed_local_branch_is_complete_push(tmp_path, capsys, gh, repo):
    commit_on(repo, "fix/5-old-title", "fix: stop the crash (#5)")
    gh.set(issue_node())
    code, lines, _ = show(capsys, repo, tmp_path)
    assert code == 0
    assert "branch fix/5-old-title" in lines
    assert "disposition complete-push fix/5-old-title" in lines
    assert any("pr list" in " ".join(c) and "fix/5-old-title" in c for c in gh.calls())


def test_show_a_pushed_branch_without_a_pull_request_is_complete_pr(tmp_path, capsys, gh, repo):
    commit_on(repo, "fix/5-x", "fix: stop the crash (#5)")
    git(repo, "push", "-q", "origin", "fix/5-x")
    gh.set(issue_node())
    code, lines, _ = show(capsys, repo, tmp_path)
    assert code == 0 and "disposition complete-pr fix/5-x" in lines


def test_show_a_branch_that_already_has_a_pull_request_is_kept(tmp_path, capsys, gh, repo):
    commit_on(repo, "fix/5-x", "fix: stop the crash (#5)")
    gh.set(issue_node(), prs='[{"number": 3}]')
    code, lines, _ = show(capsys, repo, tmp_path)
    assert code == 0 and "disposition local-branch-kept fix/5-x" in lines


def test_show_does_not_mistake_issue_55_for_issue_5(tmp_path, capsys, gh, repo):
    commit_on(repo, "fix/55-other", "fix: other (#55)")
    gh.set(issue_node())
    code, lines, _ = show(capsys, repo, tmp_path)
    assert code == 0 and "disposition fresh" in lines


def test_show_prints_each_claim(tmp_path, capsys, gh, repo):
    comments = [{"body": "[cai track: fix-crash]\nupdated 2026-10-01T10:00:00Z\nstage: build",
                 "author": {"login": "bob"}},
                {"body": "unrelated talk", "author": {"login": "carol"}}]
    gh.set(issue_node(comments=comments))
    code, lines, _ = show(capsys, repo, tmp_path)
    assert code == 0
    assert "claim fix-crash by bob updated 2026-10-01T10:00:00Z" in lines
    assert not any(line.startswith("claim ") and "carol" in line for line in lines)


def test_show_more_than_a_hundred_comments_makes_the_claims_unreadable(
        tmp_path, capsys, gh, repo):
    comments = [{"body": "[cai track: t]", "author": {"login": "bob"}}]
    gh.set(issue_node(comments=comments, total=101))
    code, lines, _ = show(capsys, repo, tmp_path)
    assert code == 0
    assert "claims unreadable" in lines
    assert not any(line.startswith("claim ") for line in lines)


def test_show_escapes_control_characters_in_what_it_prints(tmp_path, capsys, gh, repo):
    comments = [{"body": "[cai track: t]", "author": {"login": "bo\nb"}}]
    gh.set(issue_node(comments=comments))
    code, lines, _ = show(capsys, repo, tmp_path)
    assert code == 0 and "claim t by bo\\x0ab updated unknown" in lines


def test_show_a_closed_issue_stops(tmp_path, capsys, gh, repo):
    gh.set(issue_node(state="CLOSED"))
    code, lines, out_file = show(capsys, repo, tmp_path)
    assert code == 2
    assert lines[0].startswith("stopped issue-not-open:")
    assert not out_file.exists()


def test_show_a_missing_issue_stops(tmp_path, capsys, gh, repo):
    gh.set(None)
    code, lines, _ = show(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped issue-not-found:")


def test_show_gh_exit_1_on_the_query_is_issue_not_found(tmp_path, capsys, gh, repo):
    gh.set(graphql={"stdout": "", "stderr": "Could not resolve to an Issue", "exit": 1})
    code, lines, _ = show(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped issue-not-found:")


def test_show_a_gh_failure_is_named_by_its_class(tmp_path, capsys, gh, repo):
    gh.set(graphql={"stdout": "", "stderr": "HTTP 401", "exit": 1})
    code, lines, _ = show(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped not-authenticated:")


def test_show_an_unreadable_answer_stops(tmp_path, capsys, gh, repo):
    gh.set(graphql={"stdout": "not json", "exit": 0})
    code, lines, _ = show(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped unreadable:")


def test_show_a_deleted_author_is_not_a_crash(tmp_path, capsys, gh, repo):
    gh.set(issue_node(author=None))
    code, lines, out_file = show(capsys, repo, tmp_path)
    assert code == 0 and "ghost" in out_file.read_text(encoding="utf-8")


def test_show_writes_only_the_out_file(tmp_path, capsys, gh, repo):
    gh.set(issue_node())
    show(capsys, repo, tmp_path)
    assert git(repo, "status", "--porcelain") == ""


def test_show_needs_its_flags():
    with pytest.raises(SystemExit) as exc:
        fi.main(["show", "--project-dir", "."])
    assert exc.value.code == 1


def test_script_text_has_no_write_subcommand():
    text = Path(fi.__file__).read_text(encoding="utf-8")
    for word in ('"push"', '"commit"', '"merge"'):
        assert word not in text


# ---------------------------------------------------------------------------
# list, default_ticked, plan, parse_answer, render_screen, screen, select
# ---------------------------------------------------------------------------

def lnode(number, title="Some title", assoc="OWNER", state="OPEN", typename="Issue",
          blocked=(), prs=(), comments=(), total=None, author="alice", **extra):
    node = {"__typename": typename, "number": number, "title": title, "body": "",
            "url": f"https://github.com/acme/widgets/issues/{number}", "state": state,
            "author": {"__typename": "User", "login": author} if author else None,
            "authorAssociation": assoc,
            "blockedBy": {"nodes": [{"number": n, "state": s} for n, s in blocked]},
            "closedByPullRequestsReferences": {"nodes": list(prs)},
            "comments": {"totalCount": len(comments) if total is None else total,
                         "nodes": list(comments)}}
    node.update(extra)
    return node


def page(nodes, cursor=None):
    block = {"pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor},
             "nodes": nodes}
    return {"stdout": json.dumps({"data": {"repository": {"issues": block}}}), "exit": 0}


def script_pages(gh, responses, prs="[]"):
    entries = [{"match": "graphql", "responses": responses},
               {"match": "pr list", "responses": [{"stdout": prs, "exit": 0}]}]
    gh.script.write_text(json.dumps(entries), encoding="utf-8")


def run_list(capsys, repo, tmp_path):
    out_file = tmp_path / "list.json"
    code = fi.main(["list", "--project-dir", str(repo), "--owner", "acme", "--repo",
                    "widgets", "--out", str(out_file)])
    return code, capsys.readouterr().out.splitlines(), out_file


def test_list_reads_every_page_and_keeps_only_open_issues_once_ascending(
        tmp_path, capsys, gh, repo):
    first = [lnode(n) for n in range(200, 100, -1)]  # 100 nodes, descending
    second = [lnode(5), lnode(3), lnode(300, typename="PullRequest"),
              lnode(7, state="CLOSED"), lnode(150), lnode(5, title="a duplicate")]
    script_pages(gh, [page(first, cursor="c1"), page(second)])
    code, lines, out_file = run_list(capsys, repo, tmp_path)
    assert code == 0
    assert lines == ["issues 102", f"file {out_file}"]
    listed = json.loads(out_file.read_text(encoding="utf-8"))
    numbers = [i["number"] for i in listed]
    assert numbers == sorted(numbers) and len(numbers) == 102
    assert numbers[:2] == [3, 5] and 300 not in numbers and 7 not in numbers
    assert next(i for i in listed if i["number"] == 5)["title"] == "Some title"
    graphql = [c for c in gh.calls() if "graphql" in c]
    assert len(graphql) == 2
    assert not any(a.startswith("endCursor=") for a in graphql[0])
    assert "endCursor=c1" in graphql[1]
    assert "owner=acme" in graphql[0] and "repo=widgets" in graphql[0]
    # -f keeps a cursor, owner or repo that looks like a number a String
    assert graphql[1][graphql[1].index("endCursor=c1") - 1] == "-f"
    for call in graphql:
        for value in ("owner=acme", "repo=widgets"):
            assert call[call.index(value) - 1] == "-f"


def test_list_of_zero_issues_is_not_an_error(tmp_path, capsys, gh, repo):
    script_pages(gh, [page([])])
    code, lines, out_file = run_list(capsys, repo, tmp_path)
    assert code == 0 and lines == ["issues 0", f"file {out_file}"]
    assert json.loads(out_file.read_text(encoding="utf-8")) == []


def test_list_failing_mid_way_prints_no_list(tmp_path, capsys, gh, repo):
    script_pages(gh, [page([lnode(1)], cursor="c1"),
                      {"stdout": "", "stderr": "HTTP 502", "exit": 1}])
    code, lines, out_file = run_list(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped list-incomplete:")
    assert not any(line.startswith("issues ") for line in lines)
    assert not out_file.exists()


def test_list_an_unreadable_later_page_is_incomplete_too(tmp_path, capsys, gh, repo):
    script_pages(gh, [page([lnode(1)], cursor="c1"), {"stdout": "not json", "exit": 0}])
    code, lines, out_file = run_list(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped list-incomplete:")
    assert not out_file.exists()


def test_list_past_the_deadline_stops_before_asking(tmp_path, capsys, gh, repo, monkeypatch):
    script_pages(gh, [page([lnode(1)])])
    monkeypatch.setattr(fi, "LIST_DEADLINE_SECONDS", -1)
    code, lines, out_file = run_list(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped list-incomplete:")
    assert not out_file.exists() and gh.calls() == []


def test_list_a_failure_on_the_first_page_is_named_by_its_class(tmp_path, capsys, gh, repo):
    script_pages(gh, [{"stdout": "", "stderr": "HTTP 401", "exit": 1}])
    code, lines, _ = run_list(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped not-authenticated:")


def test_list_an_unreadable_first_page_stops(tmp_path, capsys, gh, repo):
    script_pages(gh, [{"stdout": json.dumps({"data": {"repository": None}}), "exit": 0}])
    code, lines, _ = run_list(capsys, repo, tmp_path)
    assert code == 2 and lines[0].startswith("stopped unreadable:")


def test_list_attaches_a_disposition_and_asks_the_remote_only_about_local_branches(
        tmp_path, capsys, gh, repo):
    commit_on(repo, "fix/5-x", "fix: stop the crash (#5)")
    pr = {"number": 9, "url": "https://github.com/acme/widgets/pull/9", "state": "OPEN"}
    script_pages(gh, [page([lnode(5), lnode(6), lnode(7, prs=[pr])])])
    code, _, out_file = run_list(capsys, repo, tmp_path)
    assert code == 0
    by_number = {i["number"]: i for i in json.loads(out_file.read_text(encoding="utf-8"))}
    assert (by_number[5]["disposition"], by_number[5]["disposition_detail"]) == (
        "complete-push", "fix/5-x")
    assert by_number[6]["disposition"] == "fresh"
    assert by_number[7]["disposition"] == "has-open-pr"
    pr_calls = [c for c in gh.calls() if "pr" in c and "list" in c]
    assert len(pr_calls) == 1 and "fix/5-x" in pr_calls[0]


def test_list_needs_its_flags():
    with pytest.raises(SystemExit) as exc:
        fi.main(["list", "--project-dir", "."])
    assert exc.value.code == 1


# default_ticked -------------------------------------------------------------

@pytest.mark.parametrize("assoc, expected", [
    ("OWNER", True), ("MEMBER", True), ("COLLABORATOR", True),
    ("CONTRIBUTOR", False), ("FIRST_TIMER", False), ("FIRST_TIME_CONTRIBUTOR", False),
    ("MANNEQUIN", False), ("NONE", False), (None, False), ("SOMETHING_NEW", False),
])
def test_default_ticked_follows_the_author_association(assoc, expected):
    assert fi.default_ticked(lnode(1, assoc=assoc)) is expected


def test_default_ticked_an_open_linked_pull_request_blocks_it():
    pr = {"number": 9, "url": "u", "state": "OPEN"}
    assert fi.default_ticked(lnode(1, prs=[pr])) is False
    merged = {"number": 8, "url": "u", "state": "MERGED"}
    assert fi.default_ticked(lnode(1, prs=[merged])) is True


def test_default_ticked_a_claim_blocks_it():
    claim = {"body": "[cai track: t]\nupdated 2026-10-01T10:00:00Z",
             "author": {"login": "bob"}}
    chat = {"body": "any news?", "author": {"login": "bob"}}
    assert fi.default_ticked(lnode(1, comments=[claim])) is False
    assert fi.default_ticked(lnode(1, comments=[chat])) is True


def test_default_ticked_unreadable_claims_follow_the_association():
    comments = [{"body": "[cai track: t]", "author": {"login": "bob"}}]
    assert fi.default_ticked(lnode(1, comments=comments, total=101)) is True
    assert fi.default_ticked(lnode(1, assoc="NONE", comments=comments, total=101)) is False


# plan -----------------------------------------------------------------------

def entry(kind="bug", size="small", deps=()):
    return {"kind": kind, "size": size, "depends_on": list(deps)}


def disposed(node, state, detail=None):
    node["disposition"], node["disposition_detail"] = state, detail
    return node


def plan_of(issues, analysis, selected):
    return {d.number: (d.action, d.detail) for d in fi.plan(issues, analysis, frozenset(selected))}


def test_plan_names_every_action():
    pr = {"number": 160, "url": "https://github.com/acme/widgets/pull/160", "state": "OPEN"}
    issues = [
        lnode(1, prs=[pr]),
        disposed(lnode(2), "complete-push", "fix/2-x"),
        disposed(lnode(3), "complete-pr", "fix/3-x"),
        disposed(lnode(4), "local-branch-kept", "fix/4-x"),
        lnode(5), lnode(6), lnode(7),                    # 5 is large; 6 and 7 form a cycle
        lnode(8), lnode(9, prs=[pr]),                    # 8 waits for 9's pull request
        lnode(10), lnode(11),                            # 10 needs 11, which is not selected
        lnode(12), lnode(13),                            # 12 comes after 13
        lnode(14), lnode(15, typename="Issue"),          # 14 is a plain fix; 15 is not selected
    ]
    analysis = {n: entry() for n in range(1, 16)}
    analysis[5] = entry(size="large")
    analysis[6] = entry(deps=[7])
    analysis[7] = entry(deps=[6])
    analysis[8] = entry(deps=[9])
    analysis[10] = entry(deps=[11])
    analysis[12] = entry(deps=[13])
    analysis[14] = entry(kind="feature")
    got = plan_of(issues, analysis, set(range(1, 15)) - {11})
    assert got[1] == ("has-open-pr", "https://github.com/acme/widgets/pull/160")
    assert got[2] == ("complete-push", "fix/2-x")
    assert got[3] == ("complete-pr", "fix/3-x")
    assert got[4] == ("local-branch-kept", "fix/4-x")
    assert got[5] == ("too-large", "https://github.com/acme/widgets/issues/5")
    assert got[6] == ("dependency-cycle", "6 7") and got[7] == ("dependency-cycle", "6 7")
    assert got[8] == ("waiting-for-pr", "https://github.com/acme/widgets/pull/160")
    assert got[10] == ("dependency-not-selected", "11")
    assert got[11] == ("not-selected", "")
    assert got[12] == ("after", "13") and got[13] == ("fix", "debug")
    assert got[14] == ("fix", "small-change")
    assert got[15] == ("not-selected", "")


def test_plan_an_unselected_dependency_is_never_queued():
    issues = [lnode(1), lnode(2)]
    result = fi.plan(issues, {1: entry(), 2: entry(deps=[1])}, frozenset({2}))
    assert [(d.number, d.action) for d in result] == [(1, "not-selected"),
                                                      (2, "dependency-not-selected")]
    assert not [d for d in result if d.action in fi.WORKING_ACTIONS]


def test_plan_puts_dependencies_first_then_numbers():
    issues = [lnode(n) for n in (10, 11, 12, 13, 14)]
    analysis = {10: entry(deps=[14]), 11: entry(), 12: entry(deps=[11]), 13: entry(),
                14: entry()}
    order = [d.number for d in fi.plan(issues, analysis, frozenset({10, 11, 12, 13, 14}))]
    assert order == [11, 13, 14, 10, 12]


def test_plan_dependencies_are_blocked_by_open_issues_and_depends_on_listed_ones_only():
    issues = [lnode(30, blocked=[(31, "OPEN"), (32, "CLOSED")]), lnode(31), lnode(32),
              lnode(33)]
    analysis = {30: entry(deps=[33, 999, 30]), 31: entry(), 32: entry(), 33: entry()}
    got = plan_of(issues, analysis, {30, 31, 32, 33})
    assert got[30] == ("after", "31 33")


def test_plan_a_selected_dependency_that_is_not_selectable_still_queues_the_dependent():
    issues = [lnode(1), lnode(2)]
    analysis = {1: entry(size="large"), 2: entry(deps=[1])}
    got = plan_of(issues, analysis, {1, 2})
    assert got[1][0] == "too-large" and got[2] == ("after", "1")


# parse_answer ---------------------------------------------------------------

LISTED = frozenset({142, 145, 150, 163})
DEFAULT = frozenset({142, 145, 150})


@pytest.mark.parametrize("text, numbers", [
    ("Fix the default: #142 #145 #150 (Recommended)", DEFAULT),
    ("  Fix the default: 3 issues, as listed above (Recommended) ", DEFAULT),
    ("Fix none", frozenset()),
    ("142 145", frozenset({142, 145})),
    ("#142, #163", frozenset({142, 163})),
    ("142,145,  150", frozenset({142, 145, 150})),
    ("+163", DEFAULT | {163}),
    ("-145 +163", frozenset({142, 150, 163})),
    ("-#145", frozenset({142, 150})),
])
def test_parse_answer_understood(text, numbers):
    assert fi.parse_answer(text, LISTED, DEFAULT) == fi.Selection(numbers, None)


@pytest.mark.parametrize("text, problem", [
    ("", "(nothing)"),
    ("  ,  ", "(nothing)"),
    ("142 +145", "+145"),
    ("+142 145", "145"),
    ("142 abc", "abc"),
    ("abc", "abc"),
    ("142 999", "999"),
    ("+999", "+999"),
    ("-142 -777", "-777"),
    ("Fix everything", "Fix"),
    ("fix none", "fix"),
])
def test_parse_answer_not_understood(text, problem):
    assert fi.parse_answer(text, LISTED, DEFAULT) == fi.Selection(None, problem)


# render_screen --------------------------------------------------------------

def claim_comment(name, login, updated):
    return {"body": f"[cai track: {name}]\nupdated {updated}", "author": {"login": login}}


def sample_issues():
    pr = {"number": 160, "url": "https://github.com/acme/widgets/pull/160", "state": "OPEN"}
    return [
        lnode(142, "Export to CSV garbles non-ASCII columns", "OWNER", author="alice"),
        lnode(145, "Retry after timeout charges twice", "COLLABORATOR", author="bob"),
        lnode(147, "Settings page hides a button on mobile", "OWNER", author="alice",
              comments=[claim_comment("mobile-settings", "bob", "2026-10-07T08:00:00Z")]),
        lnode(150, "Reconciliation report is off after a retry", "MEMBER", author="carol"),
        lnode(151, "README install command lacks a flag", "NONE", author="dave"),
        lnode(153, "Weekly dependency check failed", "NONE", author="github-actions[bot]"),
        disposed(lnode(156, "Session survives logout", "OWNER", author="alice", prs=[pr]),
                 "has-open-pr", pr["url"]),
        lnode(163, "Rewrite the permission model", "OWNER", author="alice"),
    ]


def sample_analysis():
    return {142: entry(), 145: entry(size="medium"), 147: entry(), 150: entry(deps=[145]),
            151: entry(), 153: entry("chore"), 156: entry(size="medium"),
            163: entry("feature", "large")}


# The fictional screen of the detail design, one line per element.
SAMPLE_SCREEN = [
    "acme/widgets: 8 open issues.",
    "",
    "Worked on if you take the default (2)",
    "  #142  bug · small · alice (OWNER)               Export to CSV garbles non-ASCII columns",
    "  #145  bug · medium · bob (COLLABORATOR)         Retry after timeout charges twice",
    "",
    "Ticked by default, but not worked on this round (2)",
    "  #150  bug · small · carol (MEMBER)              Reconciliation report is off after a retry",
    "        - depends on #145: waits for its pull request to merge",
    "  #163  feature · large · alice (OWNER)           Rewrite the permission model",
    "        - too large: only listed as needing a track",
    "",
    "Not ticked by default (4)",
    "  #147  bug · small · alice (OWNER)               Settings page hides a button on mobile",
    '        - claimed by track "mobile-settings" (bob, updated 2026-10-07T08:00:00Z)',
    "  #151  bug · small · dave (NONE)                 README install command lacks a flag",
    "  #153  chore · small · github-actions[bot] (NONE)  Weekly dependency check failed",
    "  #156  bug · medium · alice (OWNER)              Session survives logout",
    "        - has open pull request #160: selecting it opens no second one",
    "",
    "default: #142 #145 #150 #163",
    "option 1: Fix the default: #142 #145 #150 #163 (Recommended)",
    "option 2: Fix none",
]


def test_render_screen_equals_the_designed_sample_line_for_line():
    assert fi.render_screen(sample_issues(), sample_analysis()) == SAMPLE_SCREEN


def test_render_screen_column_fits_the_longest_description_up_to_forty():
    short = fi.render_screen([lnode(1, "T", author="al")], {1: entry()})
    assert "  #1  bug · small · al (OWNER)  T" in short
    long_login = "x" * 60
    long_row = fi.render_screen([lnode(1, "T", author=long_login), lnode(2, "U", author="al")],
                                {1: entry(), 2: entry()})
    row_two = next(line for line in long_row if line.startswith("  #2"))
    assert row_two == "  #2  " + "bug · small · al (OWNER)".ljust(40) + "  U"


def test_render_screen_with_many_ticked_counts_instead_of_listing():
    issues = [lnode(n) for n in range(1, 8)]
    lines = fi.render_screen(issues, {n: entry() for n in range(1, 8)})
    assert lines[-2:] == ["option 1: Fix the default: 7 issues, as listed above (Recommended)",
                          "option 2: Fix none"]
    assert "default: #1 #2 #3 #4 #5 #6 #7" in lines


def test_render_screen_six_ticked_are_still_listed():
    issues = [lnode(n) for n in range(1, 7)]
    lines = fi.render_screen(issues, {n: entry() for n in range(1, 7)})
    assert lines[-2] == "option 1: Fix the default: #1 #2 #3 #4 #5 #6 (Recommended)"


def test_render_screen_with_nothing_ticked_recommends_nothing():
    issues = [lnode(1, assoc="NONE"), lnode(2, assoc="NONE")]
    lines = fi.render_screen(issues, {1: entry(), 2: entry()})
    assert lines[-3:] == ["default: none", "option 1: Fix the default: none ticked",
                          "option 2: Fix none"]
    assert "Worked on if you take the default" not in "\n".join(lines)


def test_render_screen_notes_for_half_done_kept_branch_cycle_and_unclear():
    issues = [disposed(lnode(1), "complete-push", "fix/1-x"),
              disposed(lnode(2), "local-branch-kept", "fix/2-x"),
              lnode(3), lnode(4), lnode(5),
              disposed(lnode(6, assoc="NONE"), "complete-pr", "fix/6-x")]
    analysis = {n: entry() for n in range(1, 7)}
    analysis[3] = entry(deps=[4])
    analysis[4] = entry(deps=[3])
    analysis[5] = entry(size="unclear")
    text = "\n".join(fi.render_screen(issues, analysis))
    half = "earlier run left this half-done: selecting it completes the missing step"
    assert text.count(half) == 2
    assert "- a local branch from an earlier run is kept: fix/2-x" in text
    assert "- dependency cycle with #3, #4: not worked on" in text
    assert "- too unclear: only listed as needing a track" in text


def _not_ticked_block(lines):
    """The lines of the "Not ticked by default" section, header excluded."""
    start = next(i for i, line in enumerate(lines) if line.startswith("Not ticked by default"))
    end = next((i for i in range(start + 1, len(lines)) if lines[i] == ""), len(lines))
    # column padding depends on the longest row, so compare with runs of spaces squeezed
    return [" ".join(line.split()) for line in lines[start + 1:end]]


def test_render_screen_an_unticked_row_shows_what_waiting_on_a_ticked_issue_would_do():
    issues = [lnode(145), lnode(151, assoc="NONE")]
    lines = fi.render_screen(issues, {145: entry(), 151: entry(deps=[145])})
    assert _not_ticked_block(lines) == [
        "#151 bug · small · alice (NONE) Some title",
        "- depends on #145: waits for its pull request to merge"]
    assert lines[-3:] == ["default: #145", "option 1: Fix the default: #145 (Recommended)",
                          "option 2: Fix none"]


def test_render_screen_an_unticked_row_behind_an_unticked_dependency_says_it_waits():
    issues = [lnode(1, assoc="NONE"), lnode(2, assoc="NONE")]
    lines = fi.render_screen(issues, {1: entry(), 2: entry(deps=[1])})
    assert _not_ticked_block(lines) == [
        "#1 bug · small · alice (NONE) Some title",
        "#2 bug · small · alice (NONE) Some title",
        "- depends on #1: it is not ticked, so this waits"]


def test_render_screen_an_unticked_row_behind_an_open_pull_request_says_it_waits():
    pr = {"number": 9, "url": "https://github.com/acme/widgets/pull/9", "state": "OPEN"}
    issues = [lnode(1, prs=[pr]), lnode(2, assoc="NONE")]
    lines = fi.render_screen(issues, {1: entry(), 2: entry(deps=[1])})
    assert "- depends on #1: waits for its pull request to merge" in _not_ticked_block(lines)


def test_render_screen_an_unticked_large_or_unclear_row_says_it_needs_a_track():
    issues = [lnode(1, assoc="NONE"), lnode(2, assoc="NONE")]
    lines = fi.render_screen(issues, {1: entry(size="large"), 2: entry(size="unclear")})
    assert _not_ticked_block(lines) == [
        "#1 bug · large · alice (NONE) Some title",
        "- too large: only listed as needing a track",
        "#2 bug · unclear · alice (NONE) Some title",
        "- too unclear: only listed as needing a track"]


def test_render_screen_an_unticked_cycle_member_is_marked():
    issues = [lnode(3, assoc="NONE"), lnode(4, assoc="NONE"), lnode(5, assoc="NONE")]
    analysis = {3: entry(deps=[4]), 4: entry(deps=[3]), 5: entry()}
    block = _not_ticked_block(fi.render_screen(issues, analysis))
    assert block == [
        "#3 bug · small · alice (NONE) Some title",
        "- dependency cycle with #3, #4: not worked on",
        "#4 bug · small · alice (NONE) Some title",
        "- dependency cycle with #3, #4: not worked on",
        "#5 bug · small · alice (NONE) Some title"]


def test_render_screen_an_unticked_row_with_a_pull_request_or_kept_state_is_not_noted_twice():
    pr = {"number": 160, "url": "https://github.com/acme/widgets/pull/160", "state": "OPEN"}
    issues = [lnode(1), lnode(2, prs=[pr]), disposed(lnode(3, assoc="NONE"), "complete-push", "f")]
    analysis = {1: entry(), 2: entry(deps=[1]), 3: entry(deps=[1])}
    notes = [line for line in _not_ticked_block(fi.render_screen(issues, analysis))
             if line.startswith("- ")]
    assert notes == ["- has open pull request #160: selecting it opens no second one",
                     "- earlier run left this half-done: selecting it completes the missing step"]


def test_render_screen_notes_on_unticked_rows_leave_ticked_rows_and_choices_as_they_were():
    issues = [lnode(1), lnode(2), lnode(3, assoc="NONE"), lnode(4, assoc="NONE")]
    base = {1: entry(), 2: entry(deps=[1]), 3: entry(), 4: entry()}
    noted = dict(base)
    noted[3], noted[4] = entry(deps=[1]), entry(size="large")
    plain, with_notes = fi.render_screen(issues, base), fi.render_screen(issues, noted)
    assert plain[:plain.index("Not ticked by default (2)")] == \
        with_notes[:with_notes.index("Not ticked by default (2)")]
    assert plain[-3:] == with_notes[-3:] == [
        "default: #1 #2", "option 1: Fix the default: #1 #2 (Recommended)", "option 2: Fix none"]
    assert len(with_notes) == len(plain) + 2


def test_render_screen_escapes_what_others_wrote():
    lines = fi.render_screen([lnode(1, title="bad\x1b[31mtitle", author="al\nice")],
                             {1: entry()})
    assert not any("\x1b" in line or "\n" in line for line in lines)


# screen and select ----------------------------------------------------------

def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def files(tmp_path, issues=None, analysis=None, answer=None):
    listed = write_json(tmp_path / "list.json", issues if issues is not None else sample_issues())
    pairs = sample_analysis() if analysis is None else analysis
    analysis_file = write_json(tmp_path / "analysis.json",
                               [dict(number=n, **v) for n, v in pairs.items()]
                               if isinstance(pairs, dict) else pairs)
    answer_file = tmp_path / "answer.txt"
    if answer is not None:
        answer_file.write_text(answer, encoding="utf-8")
    return listed, analysis_file, answer_file


def test_screen_prints_the_sample(tmp_path, capsys):
    listed, analysis_file, _ = files(tmp_path)
    code = fi.main(["screen", "--list-file", str(listed), "--analysis-file", str(analysis_file)])
    assert code == 0
    assert capsys.readouterr().out.splitlines() == SAMPLE_SCREEN


@pytest.mark.parametrize("mutate, needle", [
    (lambda a: [e for e in a if e["number"] != 142], "#142"),
    (lambda a: a + [dict(number=999, **entry())], "#999"),
    (lambda a: a + [dict(a[0])], "#142"),
    (lambda a: [dict(e, size="huge") if e["number"] == 145 else e for e in a], "#145"),
    (lambda a: [dict(e, kind="docs") if e["number"] == 145 else e for e in a], "#145"),
    (lambda a: [dict(e, depends_on="145") if e["number"] == 150 else e for e in a], "#150"),
    (lambda a: [dict(e, depends_on=[True]) if e["number"] == 150 else e for e in a], "#150"),
    (lambda a: [{k: v for k, v in e.items() if k != "size"} if e["number"] == 145 else e
                for e in a], "#145"),
    (lambda a: {"not": "a list"}, "array"),
])
@pytest.mark.parametrize("command", ["screen", "select"])
def test_a_bad_analysis_stops_screen_and_select(tmp_path, capsys, command, mutate, needle):
    listed, analysis_file, answer_file = files(tmp_path, answer="142")
    good = json.loads(analysis_file.read_text(encoding="utf-8"))
    write_json(analysis_file, mutate(good))
    argv = [command, "--list-file", str(listed), "--analysis-file", str(analysis_file)]
    if command == "select":
        argv += ["--answer-file", str(answer_file)]
    code = fi.main(argv)
    out = capsys.readouterr().out.splitlines()
    assert code == 2 and out[0].startswith("stopped analysis-invalid:") and needle in out[0]


def run_select(capsys, tmp_path, answer, **kwargs):
    listed, analysis_file, answer_file = files(tmp_path, answer=answer, **kwargs)
    code = fi.main(["select", "--list-file", str(listed), "--analysis-file",
                    str(analysis_file), "--answer-file", str(answer_file)])
    return code, capsys.readouterr().out.splitlines()


def test_select_the_default_prints_the_order_and_every_selected_item(tmp_path, capsys):
    code, out = run_select(capsys, tmp_path, "Fix the default: #142 #145 #150 #163 (Recommended)")
    assert code == 0
    assert out == ["order: #142 -> #145",
                   "item 142 fix debug", "item 145 fix debug",
                   "item 163 too-large https://github.com/acme/widgets/issues/163",
                   "item 150 after 145"]


def test_select_free_text_chooses_exactly_those(tmp_path, capsys):
    code, out = run_select(capsys, tmp_path, "#151, 142")
    assert code == 0
    assert out == ["order: #142 -> #151", "item 142 fix debug", "item 151 fix debug"]


def test_select_an_answer_it_cannot_read_is_exit_3(tmp_path, capsys):
    code, out = run_select(capsys, tmp_path, "142 and 145")
    assert code == 3
    assert out[0] == "selection not understood: and"
    assert len(out) > 1 and not any(line.startswith("order:") for line in out)


def test_select_nothing_is_exit_4(tmp_path, capsys):
    code, out = run_select(capsys, tmp_path, "Fix none")
    assert code == 4 and not any(line.startswith("order:") for line in out)


def test_select_only_things_that_cannot_be_worked_on_is_exit_4(tmp_path, capsys):
    code, out = run_select(capsys, tmp_path, "163 156")
    assert code == 4
    assert "item 156 has-open-pr https://github.com/acme/widgets/pull/160" in out
    assert not any(line.startswith("order:") for line in out)


def test_select_a_number_not_on_the_list_is_exit_3(tmp_path, capsys):
    code, out = run_select(capsys, tmp_path, "999")
    assert code == 3 and out[0] == "selection not understood: 999"


def test_screen_and_select_are_read_only_and_repeatable(tmp_path, capsys):
    first = run_select(capsys, tmp_path, "142 145")
    second = run_select(capsys, tmp_path, "142 145")
    assert first == second


def test_screen_and_select_need_their_flags():
    for argv in (["screen", "--list-file", "x"], ["select", "--list-file", "x"]):
        with pytest.raises(SystemExit) as exc:
            fi.main(argv)
        assert exc.value.code == 1


def test_an_unreadable_list_file_stops(tmp_path, capsys):
    bad = tmp_path / "list.json"
    bad.write_text("not json", encoding="utf-8")
    analysis_file = write_json(tmp_path / "a.json", [])
    code = fi.main(["screen", "--list-file", str(bad), "--analysis-file", str(analysis_file)])
    assert code == 2 and capsys.readouterr().out.startswith("stopped unreadable:")
    missing = tmp_path / "absent.json"
    code = fi.main(["screen", "--list-file", str(missing), "--analysis-file", str(analysis_file)])
    assert code == 2 and capsys.readouterr().out.startswith("stopped unreadable:")
