"""ship_pr_findings: wait for a PR's checks, read its two finding sources.

Every `gh` call goes to tests/fake_gh.py in `script` mode through CAI_GH_CLI,
and the clock is a fake whose sleep() only advances it, so nothing here waits
90 or 30 real seconds. The log file the fake writes is also the evidence for
AC6 (the script only reads) and for "the re-look lists check runs once more,
not twice".
"""
import json
import types

import pytest

import fake_gh
import ship_pr_findings as spf

SHA = "a" * 40
URL = "https://github.com/o/r/pull/281"
START = 1_000_000


class Clock:
    """now()/sleep() with no real waiting; `slept` records every sleep."""

    def __init__(self, t=START):
        self.t = t
        self.slept = []

    def time(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds


def pr_json(state="OPEN", head=SHA):
    return json.dumps({"number": 281, "url": URL, "headRefOid": head,
                       "state": state})


def runs_json(*runs):
    """One /check-runs page: runs are (id, name, status[, conclusion])."""
    rows = []
    for run_ in runs:
        row = {"id": run_[0], "name": run_[1], "status": run_[2]}
        if len(run_) > 3:
            row["conclusion"] = run_[3]
        rows.append(row)
    return json.dumps([{"total_count": len(rows), "check_runs": rows}])


def annotations_json(*anns):
    return json.dumps([list(anns)])


def thread(path="x.py", line=42, body="msg", login="bot", resolved=False,
           outdated=False, url="https://github.com/o/r/pull/281#r1",
           total=None, bodies=None, kind="Bot"):
    # kind is GraphQL's author __typename ("Bot" for the scan bot, whose login
    # has no "[bot]" suffix); None is a deleted account, whose author is null.
    author = {"__typename": kind, "login": login} if kind else None
    comments = [{"author": author, "body": body, "url": url}]
    for extra in bodies or []:
        comments.append({"author": author, "body": extra, "url": url})
    return {"isResolved": resolved, "isOutdated": outdated, "path": path,
            "line": line,
            "comments": {"totalCount": total or len(comments),
                         "nodes": comments}}


def threads_json(*nodes, has_next=False, cursor=None):
    return json.dumps({"data": {"repository": {"pullRequest": {
        "reviewThreads": {"pageInfo": {"hasNextPage": has_next,
                                       "endCursor": cursor},
                          "nodes": list(nodes)}}}}})


def resp(stdout="", stderr="", exit=0, sleep=0):
    return {"stdout": stdout, "stderr": stderr, "exit": exit, "sleep": sleep}


class Gh:
    """Writes FAKE_GH_SCRIPT, points the seam at it, reads FAKE_GH_LOG back."""

    def __init__(self, tmp_path, monkeypatch):
        self.script = tmp_path / "script.json"
        self.log = tmp_path / "log.txt"
        monkeypatch.setenv(spf.CLI_ENV, fake_gh.cli_argv())
        monkeypatch.setenv("FAKE_GH_MODE", "script")
        monkeypatch.setenv("FAKE_GH_SCRIPT", str(self.script))
        monkeypatch.setenv("FAKE_GH_LOG", str(self.log))

    def set(self, pr=None, checks=None, annotations=None, threads=None):
        entries = []
        for match, responses in (("pr view", pr), ("/commits/", checks),
                                 ("/annotations", annotations),
                                 ("graphql", threads)):
            if responses is not None:
                entries.append({"match": match, "responses": responses})
        self.script.write_text(json.dumps(entries), encoding="utf-8")

    def calls(self, needle=None):
        if not self.log.exists():
            return []
        rows = [json.loads(line) for line in
                self.log.read_text(encoding="utf-8").splitlines() if line]
        return [r for r in rows if needle is None or needle in " ".join(r)]


@pytest.fixture
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(spf, "time",
                        types.SimpleNamespace(time=fake.time,
                                              sleep=fake.sleep))
    return fake


@pytest.fixture
def track(tmp_path):
    d = tmp_path / "track"
    d.mkdir()
    return d


@pytest.fixture
def gh(tmp_path, monkeypatch):
    return Gh(tmp_path, monkeypatch)


def run(track, capsys, *extra):
    code = spf.main(["--track-dir", str(track), "--sha", SHA, *extra])
    return code, capsys.readouterr().out


def lines(out):
    return out.splitlines()


def happy(gh, checks=None, annotations=None, threads=None):
    gh.set(pr=[resp(pr_json())],
           checks=checks or [resp(runs_json((1, "bandit", "completed")))],
           annotations=annotations or [resp(annotations_json())],
           threads=threads or [resp(threads_json())])


# --- the two sources, de-duplicated ----------------------------------------

def test_same_text_on_both_sides_keeps_the_thread_and_drops_the_annotation(
        gh, clock, track, capsys):
    msg = "Consider possible security implications."
    happy(gh,
          annotations=[resp(annotations_json(
              {"path": "x.py", "start_line": 42, "message": " " + msg + "\n",
               "title": "t", "annotation_level": "warning"}))],
          threads=[resp(threads_json(thread(body=msg)))])
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert "source review_thread ok 1" in lines(out)
    assert "source check_annotation ok 1" in lines(out)
    assert "findings 1 after de-duplication, 1 dropped" in lines(out)
    assert sum(1 for ln in lines(out) if ln.startswith("finding ")) == 1
    assert "finding 1 review_thread x.py:42 outdated=no url=" in out


def ghas_body(msg, n=1):
    """The shape code scanning really posts: a heading, the message, a link."""
    return ("## Bandit / \n\n%s\n\n[Show more details]"
            "(https://github.com/o/r/security/code-scanning/%d)" % (msg, n))


def ann(path, line, message):
    return {"path": path, "start_line": line, "message": message,
            "title": "t", "annotation_level": "warning"}


def test_annotation_inside_the_threads_first_comment_is_dropped(
        gh, clock, track, capsys):
    # Six pairs as on PR #270; lines 52 holds two different findings.
    pairs = [("a.py", 10, "Use of assert detected."),
             ("b.py", 20, "Possible hardcoded password."),
             ("c.py", 30, "Try, Except, Pass detected."),
             ("resolve.py", 52,
              "Starting a process with a partial executable path"),
             ("resolve.py", 52,
              "subprocess call - check for execution of untrusted input."),
             ("d.py", 7, "Consider possible security implications.")]
    happy(gh,
          annotations=[resp(annotations_json(
              *[ann(p, ln, m) for p, ln, m in pairs]))],
          threads=[resp(threads_json(
              *[thread(path=p, line=ln, body=ghas_body(m, i))
                for i, (p, ln, m) in enumerate(pairs)]))])
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert "findings 6 after de-duplication, 6 dropped" in lines(out)
    assert sum(1 for ln in lines(out) if ln.startswith("finding ")) == 6


def test_each_annotation_removes_only_the_thread_that_holds_its_message(
        gh, clock, track, capsys):
    a = "Starting a process with a partial executable path"
    b = "subprocess call - check for execution of untrusted input."
    happy(gh,
          annotations=[resp(annotations_json(ann("r.py", 52, a)))],
          threads=[resp(threads_json(
              thread(path="r.py", line=52, body=ghas_body(a, 1)),
              thread(path="r.py", line=52, body=ghas_body(b, 2))))])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "findings 2 after de-duplication, 1 dropped" in lines(out)


def test_annotation_not_in_any_thread_on_that_line_is_kept(
        gh, clock, track, capsys):
    happy(gh,
          annotations=[resp(annotations_json(
              ann("x.py", 42, "Something else entirely"),
              ann("x.py", 43, "msg")))],
          threads=[resp(threads_json(thread(body=ghas_body("msg"))))])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "findings 3 after de-duplication, 0 dropped" in lines(out)


def test_human_thread_never_removes_an_annotation(gh, clock, track, capsys):
    # Even when the human quotes the annotation's exact text.
    happy(gh,
          annotations=[resp(annotations_json(ann("x.py", 42, "use shlex")))],
          threads=[resp(threads_json(
              thread(body="use shlex", login="me", kind="User")))])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "findings 2 after de-duplication, 0 dropped" in lines(out)
    assert "finding 1 review_thread x.py:42" in out
    assert "finding 2 check_annotation x.py:42" in out


def test_thread_with_a_deleted_author_is_not_a_bot(gh, clock, track, capsys):
    happy(gh,
          annotations=[resp(annotations_json(ann("x.py", 42, "msg")))],
          threads=[resp(threads_json(thread(body="msg", kind=None)))])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "findings 2 after de-duplication, 0 dropped" in lines(out)


def test_bot_is_decided_by_the_author_type_not_the_login(
        gh, clock, track, capsys):
    # A human whose login ends in [bot] is still a User; the real scan bot
    # is typed Bot with a plain login.
    happy(gh,
          annotations=[resp(annotations_json(ann("x.py", 42, "msg")))],
          threads=[resp(threads_json(
              thread(body="msg", login="fake[bot]", kind="User")))])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "findings 2 after de-duplication, 0 dropped" in lines(out)


def test_graphql_query_asks_for_the_author_type():
    assert "author{__typename login}" in spf._QUERY


def test_same_line_different_text_keeps_both(gh, clock, track, capsys):
    happy(gh,
          annotations=[resp(annotations_json(
              {"path": "x.py", "start_line": 42, "message": "other",
               "title": "t", "annotation_level": "warning"}))],
          threads=[resp(threads_json(thread(body="msg")))])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "findings 2 after de-duplication, 0 dropped" in lines(out)


def test_resolved_threads_are_left_out(gh, clock, track, capsys):
    happy(gh, threads=[resp(threads_json(thread(resolved=True),
                                         thread(body="open one")))])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "source review_thread ok 1" in lines(out)
    assert "open one" in out


def test_each_finding_shows_path_line_source_and_text(gh, clock, track,
                                                      capsys):
    happy(gh,
          annotations=[resp(annotations_json(
              {"path": ".github", "start_line": 1, "message": "Node 20",
               "title": "t", "annotation_level": "warning"}))])
    _, out = run(track, capsys, "--started-at", str(START))
    assert 'finding 1 check_annotation .github:1 check="bandit" ' \
           "level=warning" in lines(out)
    assert "    Node 20" in lines(out)


def test_multiline_text_is_indented_and_control_chars_escaped(
        gh, clock, track, capsys):
    forged = "finding 9 review_thread evil.py:1"
    happy(gh, threads=[resp(threads_json(
        thread(body="first\x1b[31m\n" + forged)))])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "\x1b" not in out
    assert "\\x1b[31m" in out
    # The forged line is there, but only as indented body text.
    assert "    " + forged in lines(out)
    assert forged not in lines(out)
    assert not any(ln.startswith("finding 9") for ln in lines(out))


def test_thread_without_a_line_prints_only_the_path(gh, clock, track, capsys):
    happy(gh, threads=[resp(threads_json(thread(line=None, outdated=True)))])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "finding 1 review_thread x.py outdated=yes" in out


def test_comments_beyond_the_first_hundred_are_counted_not_dropped_silently(
        gh, clock, track, capsys):
    happy(gh, threads=[resp(threads_json(thread(total=105)))])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "5 more comments not listed" in out


def test_threads_are_paged_with_a_cursor(gh, clock, track, capsys):
    happy(gh, threads=[
        resp(threads_json(thread(body="one"), has_next=True, cursor="CUR1")),
        resp(threads_json(thread(body="two")))])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "source review_thread ok 2" in lines(out)
    calls = gh.calls("graphql")
    assert len(calls) == 2
    assert "endCursor=CUR1" in calls[1]
    assert not any(a.startswith("endCursor") for a in calls[0])


# --- 0 findings, and the re-look -------------------------------------------

def test_zero_findings_prints_both_sources_as_ok_0(gh, clock, track, capsys):
    happy(gh)
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert "source review_thread ok 0" in lines(out)
    assert "source check_annotation ok 0" in lines(out)
    assert "findings 0 after de-duplication, 0 dropped" in lines(out)


def test_no_check_runs_after_the_relook_says_so_and_still_fetches(
        gh, clock, track, capsys):
    gh.set(pr=[resp(pr_json())],
           checks=[resp(runs_json()), resp(runs_json())],
           threads=[resp(threads_json())])
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert clock.slept == [spf.SETTLE_SECONDS] == [30]
    assert len(gh.calls("/commits/")) == 2
    # The fake clock only moves by the sleep, so waited is exactly 30 here.
    assert ("checks 0 completed, 0 running, waited 30 s of 600: "
            "still no check runs after a 30 s re-look") in lines(out)
    assert "source review_thread ok 0" in lines(out)
    assert "source check_annotation ok 0" in lines(out)
    assert "unchecked" not in out


def test_relook_that_finds_running_checks_waits_like_any_other(
        gh, clock, track, capsys):
    gh.set(pr=[resp(pr_json())],
           checks=[resp(runs_json()),
                   resp(runs_json((1, "a", "in_progress"),
                                  (2, "b", "in_progress")))])
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 8
    assert "still no check runs" not in out
    assert any(ln.startswith("waiting 2 of 2 checks running") for ln in
               lines(out))
    assert not gh.calls("graphql")


def test_first_poll_with_checks_never_relooks(gh, clock, track, capsys):
    happy(gh)
    run(track, capsys, "--started-at", str(START))
    assert 30 not in clock.slept
    assert len(gh.calls("/commits/")) == 1


def test_relook_that_fails_reports_unknown_and_still_reads_threads(
        gh, clock, track, capsys):
    gh.set(pr=[resp(pr_json())],
           checks=[resp(runs_json()), resp(stderr="boom", exit=1)],
           threads=[resp(threads_json(thread(body="t")))])
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert "checks unknown exit-1" in lines(out)
    assert "source check_annotation unchecked exit-1" in lines(out)
    assert "source review_thread ok 1" in lines(out)
    assert len(gh.calls("/commits/")) == 2


# --- waiting in slices -------------------------------------------------------

def test_running_check_gives_waiting_exit_8_and_prints_the_start(
        gh, clock, track, capsys):
    gh.set(pr=[resp(pr_json())],
           checks=[resp(runs_json((1, "a", "completed"),
                                  (2, "bandit", "in_progress")))])
    code = spf.main(["--track-dir", str(track), "--sha", SHA])
    out = capsys.readouterr().out
    assert code == 8
    assert "wait_started_at %d" % START in lines(out)
    waiting = [ln for ln in lines(out) if ln.startswith("waiting ")]
    assert waiting and waiting[0].startswith(
        "waiting 1 of 2 checks running after ")
    assert '"bandit"' in waiting[0]
    assert not gh.calls("graphql")
    # One call never sleeps past its slice.
    assert sum(clock.slept) <= spf.WAIT_SLICE_SECONDS


def test_started_at_given_is_not_printed_again(gh, clock, track, capsys):
    gh.set(pr=[resp(pr_json())],
           checks=[resp(runs_json((2, "bandit", "in_progress")))])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "wait_started_at" not in out


def test_checks_finishing_during_the_call_still_wait_for_the_next_call(
        gh, clock, track, capsys):
    gh.set(pr=[resp(pr_json())],
           checks=[resp(runs_json((1, "a", "in_progress"))),
                   resp(runs_json((1, "a", "completed")))])
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 8
    assert "waiting 0 of 1 checks running" in out
    assert not gh.calls("graphql")


def test_all_completed_on_the_first_poll_fetches(gh, clock, track, capsys):
    happy(gh, checks=[resp(runs_json((1, "a", "completed"),
                                     (2, "b", "completed")))])
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert 'checks 2 completed, 0 running, waited 0 s of 600: "a", "b"' \
        in lines(out)
    assert len(gh.calls("/annotations")) == 2
    assert len(gh.calls("graphql")) == 1


def test_a_check_still_running_after_600_seconds_is_unchecked(
        gh, clock, track, capsys):
    happy(gh, checks=[resp(runs_json((1, "a", "completed"),
                                     (2, "CodeQL", "in_progress")))])
    code, out = run(track, capsys, "--started-at", str(START - 601))
    assert code == 0
    assert 'unchecked check "CodeQL" still running after 600 s' in lines(out)
    assert "source review_thread ok 0" in lines(out)
    assert len(gh.calls("/annotations")) == 1


@pytest.mark.parametrize("conclusion", [
    "timed_out", "cancelled", "startup_failure", "action_required", "stale"])
def test_a_completed_check_with_no_result_is_unchecked(
        gh, clock, track, capsys, conclusion):
    happy(gh, checks=[resp(runs_json((1, "a", "completed", "success"),
                                     (2, "Code\nQL", "completed",
                                      conclusion)))])
    code, out = run(track, capsys, "--started-at", str(START))
    ls = lines(out)
    assert code == 0
    # Still counted as completed; the name is escaped like the running case.
    assert any(ln.startswith("checks 2 completed, 0 running") for ln in ls)
    assert 'unchecked check "Code\\x0aQL" concluded %s' % conclusion in ls
    assert not any(ln.startswith("unchecked") and '"a"' in ln for ln in ls)


@pytest.mark.parametrize("conclusion", [
    "success", "failure", "neutral", "skipped"])
def test_other_conclusions_stay_clean(gh, clock, track, capsys, conclusion):
    happy(gh, checks=[resp(runs_json((1, "a", "completed", conclusion)))])
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert not any(ln.startswith("unchecked") for ln in lines(out))


def test_concluded_unchecked_lines_follow_running_ones_before_findings(
        gh, clock, track, capsys):
    happy(gh, checks=[resp(runs_json((1, "a", "completed", "cancelled"),
                                     (2, "b", "in_progress")))],
          threads=[resp(threads_json(thread()))])
    _, out = run(track, capsys, "--started-at", str(START - 601))
    ls = lines(out)
    running = ls.index('unchecked check "b" still running after 600 s')
    concluded = ls.index('unchecked check "a" concluded cancelled')
    assert ls.index("source check_annotation ok 0") < running < concluded
    assert concluded < ls.index("findings 1 after de-duplication, 0 dropped")


def test_fetching_stops_at_the_deadline_and_says_timed_out(
        gh, clock, track, capsys, monkeypatch):
    happy(gh)
    # The annotation fetch runs first; push the clock past the deadline
    # inside it, so the thread fetch finds the deadline already gone.
    real_ann = spf.check_annotations

    def slow_ann(run_, cwd):
        out = real_ann(run_, cwd)
        clock.t += spf.FETCH_DEADLINE_SECONDS + 1
        return out

    monkeypatch.setattr(spf, "check_annotations", slow_ann)
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert "source review_thread unchecked timed-out" in lines(out)
    assert not gh.calls("graphql")


# --- failures are a category word, never gh's own text ----------------------

@pytest.mark.parametrize("stderr,exit_code,word", [
    ("HTTP 401: Bad credentials secret-token-xyz", 1, "not-authenticated"),
    ("could not resolve to a repository secret-token-xyz", 1,
     "no-github-repo"),
    ("error connecting to api.github.com secret-token-xyz", 1,
     "unreachable"),
    ("no pull requests found for branch x secret-token-xyz", 1,
     "no-pull-request"),
    ("something odd secret-token-xyz", 4, "exit-4"),
])
def test_pull_request_failure_becomes_a_category(
        gh, clock, track, capsys, stderr, exit_code, word):
    gh.set(pr=[resp(stderr=stderr, exit=exit_code)])
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert "source review_thread unchecked " + word in lines(out)
    assert "source check_annotation unchecked " + word in lines(out)
    assert "secret-token-xyz" not in out


def test_unparseable_pr_output_is_unreadable(gh, clock, track, capsys):
    gh.set(pr=[resp(stdout="<html>secret-token-xyz")])
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert "source review_thread unchecked unreadable" in lines(out)
    assert "secret-token-xyz" not in out


def test_missing_gh_is_not_found(clock, track, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv(spf.CLI_ENV, str(tmp_path / "no-such-gh"))
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert "source review_thread unchecked not-found" in lines(out)
    assert "source check_annotation unchecked not-found" in lines(out)


def test_a_hung_gh_is_timed_out(gh, clock, track, capsys, monkeypatch):
    # Long enough that a loaded machine's interpreter start-up is not the
    # thing that times out; only the scripted sleep is.
    monkeypatch.setattr(spf, "TIMEOUT_SECONDS", 3)
    gh.set(pr=[resp(pr_json())],
           checks=[resp(runs_json((1, "a", "completed")))],
           annotations=[resp(annotations_json())],
           threads=[resp(threads_json(), sleep=10)])
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert "source review_thread unchecked timed-out" in lines(out)
    assert "source check_annotation ok 0" in lines(out)


def test_one_failed_annotation_read_marks_the_source_but_keeps_the_rest(
        gh, clock, track, capsys):
    gh.set(pr=[resp(pr_json())],
           checks=[resp(runs_json((1, "a", "completed"),
                                  (2, "b", "completed")))],
           annotations=[resp(annotations_json(
               {"path": "x.py", "start_line": 3, "message": "kept",
                "title": "t", "annotation_level": "warning"})),
               resp(stderr="HTTP 401 secret-token-xyz", exit=1)],
           threads=[resp(threads_json())])
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert "source check_annotation unchecked not-authenticated" in lines(out)
    assert "    kept" in lines(out)
    assert "secret-token-xyz" not in out


def test_check_listing_failure_still_reads_threads(gh, clock, track, capsys):
    gh.set(pr=[resp(pr_json())],
           checks=[resp(stderr="HTTP 401", exit=1)],
           threads=[resp(threads_json(thread(body="t")))])
    code, out = run(track, capsys, "--started-at", str(START))
    assert code == 0
    assert "checks unknown not-authenticated" in lines(out)
    assert "source check_annotation unchecked not-authenticated" in lines(out)
    assert "source review_thread ok 1" in lines(out)
    assert len(gh.calls("/commits/")) == 1


def test_unreadable_check_runs_output(gh, clock, track, capsys):
    gh.set(pr=[resp(pr_json())], checks=[resp(stdout="not json")],
           threads=[resp(threads_json())])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "checks unknown unreadable" in lines(out)


# --- the PR and the SHA ------------------------------------------------------

def test_sha_defaults_to_the_pr_head_and_a_mismatch_is_printed(
        gh, clock, track, capsys):
    head = "b" * 40
    gh.set(pr=[resp(pr_json(head=head))],
           checks=[resp(runs_json((1, "a", "completed")))],
           annotations=[resp(annotations_json())],
           threads=[resp(threads_json())])
    _, out = run(track, capsys, "--started-at", str(START))
    assert "sha %s pr-head %s" % (SHA, head) in lines(out)
    assert "pr 281 %s OPEN" % URL in lines(out)
    assert any(SHA in " ".join(c) for c in gh.calls("/commits/"))

    code = spf.main(["--track-dir", str(track), "--started-at", str(START)])
    out = capsys.readouterr().out
    assert code == 0
    assert "sha %s pr-head %s" % (head, head) in lines(out)


# --- rounds ------------------------------------------------------------------

def write_ledger(track, rows):
    (track / "ledger.jsonl").write_text(
        "\n".join(json.dumps({"stage": s, "outcome": o}) for s, o in rows)
        + "\n", encoding="utf-8")


def test_fix_rounds_counts_verifies_after_the_first_ship_passed(track):
    write_ledger(track, [
        ("verify", "passed"), ("ship", "passed"),
        ("verify", "passed"), ("ship", "passed"),
        ("verify", "failed"), ("verify", "blocked"),
        ("verify", "unavailable"), ("verify", "skipped"),
        ("build", "passed")])
    assert spf.fix_rounds(str(track)) == 3


def test_fix_rounds_is_zero_without_a_ledger_or_a_ship_passed(track):
    assert spf.fix_rounds(str(track)) == 0
    write_ledger(track, [("verify", "passed"), ("ship", "failed")])
    assert spf.fix_rounds(str(track)) == 0


def test_fix_rounds_ignores_a_torn_last_line(track):
    write_ledger(track, [("ship", "passed"), ("verify", "passed")])
    with open(track / "ledger.jsonl", "a", encoding="utf-8") as fh:
        fh.write('{"stage": "verify", "outc')
    assert spf.fix_rounds(str(track)) == 1


def test_the_report_names_the_round_against_the_cap(gh, clock, track, capsys):
    write_ledger(track, [("ship", "passed"), ("verify", "passed"),
                         ("verify", "passed")])
    happy(gh)
    _, out = run(track, capsys, "--started-at", str(START))
    assert "fix_rounds 2 of 2" in lines(out)


# --- read only (AC6) ---------------------------------------------------------

def test_every_call_is_a_read(gh, clock, track, capsys):
    happy(gh, checks=[resp(runs_json((1, "a", "completed")))],
          annotations=[resp(annotations_json())],
          threads=[resp(threads_json(has_next=True, cursor="C")),
                   resp(threads_json())])
    run(track, capsys, "--started-at", str(START))
    calls = gh.calls()
    assert calls
    for argv in calls:
        assert "-X" not in argv and "--method" not in argv
        assert "mutation" not in " ".join(argv).lower()
        if argv[0] == "api":
            assert "-f" not in argv or argv[0:2] == ["api", "graphql"]
        else:
            assert argv[:2] == ["pr", "view"]


# --- command line ------------------------------------------------------------

def test_a_missing_track_dir_is_a_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        spf.main(["--track-dir", str(tmp_path / "nope")])
    assert exc.value.code == 1


@pytest.mark.parametrize("bad", [
    ["--sha", "xyz"], ["--sha", "a" * 39],
    ["--started-at", "-1"], ["--started-at", "soon"]])
def test_bad_flag_values_exit_1(track, bad):
    with pytest.raises(SystemExit) as exc:
        spf.main(["--track-dir", str(track), *bad])
    assert exc.value.code == 1


# --- small pure helpers ------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("", ["gh"]), ("/x/gh", ["/x/gh"]), ('["py", "f.py"]', ["py", "f.py"]),
    ("[broken", ["gh"])])
def test_gh_prefix(monkeypatch, raw, expected):
    monkeypatch.setenv(spf.CLI_ENV, raw)
    assert spf.gh_prefix() == expected


@pytest.mark.parametrize("exc,code,stderr,word", [
    (FileNotFoundError(), 0, "", "not-found"),
    (None, 0, "", "ok"),
    (None, 1, "gh auth login", "not-authenticated"),
    (None, 1, "none of the git remotes", "no-github-repo"),
    (None, 1, "dial tcp", "unreachable"),
    (None, 7, "", "exit-7")])
def test_classify(exc, code, stderr, word):
    assert spf.classify(exc, code, stderr) == word


def test_classify_timeout():
    import subprocess
    assert spf.classify(subprocess.TimeoutExpired("gh", 1), 0, "") == \
        "timed-out"
