"""open_items.py publish: the GitHub writes a record has queued (AC6, AC7).

`tests/fake_gh.py` answers through CAI_TICKET_CLI's JSON argv form, so no real
`gh` runs, and its FAKE_GH_LOG holds one argv line per call. fake_gh does not
keep a body file, which `ticket_backend.run()`'s caller deletes straight
afterwards, so a wrapper around `ticket_backend.run` reads it first. `publish()`
is called in-process throughout: the timeout case lowers TIMEOUT_SECONDS with
monkeypatch, which a subprocess would not see.
"""
import json
import os
import subprocess
import sys

import pytest

import fake_gh
import ledger
import open_items
import ticket_backend

SCRIPT = os.path.join(os.path.dirname(open_items.__file__), "open_items.py")
ISSUE = "https://github.com/o/r/issues/%d"
COMMENT = "https://github.com/o/r/pull/7#issuecomment-%d"


@pytest.fixture
def track(tmp_path):
    d = tmp_path / "feat"
    d.mkdir()
    return d


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    return p


def _item(n, state="queued-issue", stage="verify", kind="unfixed-minor",
          where="src/a.py:3", what=None, why="left unfixed", at="stop",
          url=None, target=None, source="report", quoted=None):
    picked = {"date": "2026-10-13", "pick": "file", "at": at} if state.startswith("queued") else None
    return {"id": "open-%d" % n, "state": state, "stage": stage, "kind": kind,
            "where": where, "what": what or "Minor %d" % n, "why": why,
            "picked": picked, "url": url, "target": target, "source": source,
            "quoted": quoted}


def _imported(n, what, **kw):
    kw.setdefault("where", None)
    return _item(n, stage="build", kind="imported", what=what, source="state.md",
                 why=open_items.IMPORT_WHY, **kw)


def _note(n, **kw):
    return _item(n, state="queued-note", **kw)


def _record(track, *items, branch="track/x"):
    open_items.write_atomic(
        str(track / "open-items.md"),
        open_items.render({"branch": branch, "applied": [], "items": list(items)}))


def _shipped(track, note="PR #7"):
    ledger.append(str(track), "ship", "passed", note=note)


def _by_id(track):
    return {i["id"]: i for i in open_items.load(str(track))["items"]}


class Gh:
    """The fake CLI wired in: argv log, captured bodies, and the record's
    state at the moment of each call."""

    def __init__(self, tmp_path, monkeypatch, track, entries):
        self.log = tmp_path / "gh.log"
        script = tmp_path / "script.json"
        script.write_text(json.dumps(entries), encoding="utf-8")
        monkeypatch.setenv(ticket_backend.CLI_ENV, fake_gh.cli_argv())
        monkeypatch.setenv("FAKE_GH_MODE", "script")
        monkeypatch.setenv("FAKE_GH_SCRIPT", str(script))
        monkeypatch.setenv("FAKE_GH_LOG", str(self.log))
        self.bodies = []
        self.during = []
        real = ticket_backend.run

        def run(args, cwd=None):
            if "--body-file" in args:
                with open(args[args.index("--body-file") + 1], encoding="utf-8") as fh:
                    self.bodies.append(fh.read())
            self.during.append({k: (v["state"], v["target"])
                                for k, v in _by_id(track).items()})
            return real(args, cwd)

        monkeypatch.setattr(ticket_backend, "run", run)

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(ln) for ln in self.log.read_text(encoding="utf-8").splitlines()
                if ln.strip()]


def _gh(tmp_path, monkeypatch, track, issue=None, comment=None):
    issue = issue or [{"stdout": ISSUE % n + "\n"} for n in range(11, 20)]
    comment = comment or [{"stdout": COMMENT % 90 + "\n"}]
    return Gh(tmp_path, monkeypatch, track,
              [{"match": "issue create", "responses": issue},
               {"match": "pr comment", "responses": comment}])


def _publish(track, project, at="done", **kw):
    return open_items.publish(str(track), str(project), at, **kw)


# ---- issues -----------------------------------------------------------------

def test_one_issue_per_item_title_is_one_argument_and_body_carries_the_fields(
        tmp_path, monkeypatch, track, project):
    what = "The sha-line wording reads as two rules"
    _record(track, _item(1, what=what, why="Minor; left unfixed"),
            _item(2, what="Second minor", where=None, stage="build", kind="deviation"))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN", ticket=41)
    assert out == ["open-1 filed " + ISSUE % 11, "open-2 filed " + ISSUE % 12]
    first, second = gh.calls()
    assert first[:3] == ["issue", "create", "--title"]
    assert first[3] == what and first[4] == "--body-file" and len(first) == 6
    assert "--label" not in first
    assert gh.bodies[0] == "\n".join([
        what, "", "- Where: `src/a.py:3`", "- Found by: the verify stage",
        "- Why it was left: Minor; left unfixed", "- Pull request: #7", "",
        "Refs #41"]) + "\n"
    assert "Where" not in gh.bodies[1] and "Found by: the build stage" in gh.bodies[1]
    assert second[3] == "Second minor"
    item = _by_id(track)["open-1"]
    assert (item["state"], item["url"], item["target"]) == ("filed", ISSUE % 11, "issue")


def test_no_refs_line_without_a_ticket(tmp_path, monkeypatch, track, project):
    _record(track, _item(1))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert "Refs" not in gh.bodies[0]


def test_item_is_filing_with_its_target_before_the_call(tmp_path, monkeypatch, track, project):
    _record(track, _item(1), _note(2), _note(3))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    issue_call, note_call = gh.during
    assert issue_call["open-1"] == ("filing", "issue")
    assert note_call["open-2"] == note_call["open-3"] == ("filing", "note-1")
    assert note_call["open-1"][0] == "filed"


def test_title_is_cut_and_the_full_text_is_in_the_body_for_an_imported_item(
        tmp_path, monkeypatch, track, project):
    what = "word " * 60
    _record(track, _imported(1, what.strip(), state="queued-issue"))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert out == ["open-1 filed " + ISSUE % 11]
    title = gh.calls()[0][3]
    assert title == what.strip()[:200] + "\u2026"
    assert gh.bodies[0].startswith(what.strip() + "\n")


@pytest.mark.parametrize("text,rule", [
    ("token=abcd1234efgh5678 was printed", "credential"),
    ("see C:\\Users\\x\\f.py for it", "local-path"),
    ("Traceback (most recent call last)", "raw-output"),
    ("run it with --a --b --c", "argument-vector"),
])
def test_each_forbidden_kind_refuses_with_no_call(
        tmp_path, monkeypatch, track, project, text, rule):
    # An imported item, so add's own check did not already refuse it.
    _record(track, _imported(1, text, state="queued-issue"))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert out == ["open-1 undecided again: forbidden text (%s)" % rule]
    assert gh.calls() == []
    assert _by_id(track)["open-1"]["state"] == "undecided"


def test_a_closing_keyword_refuses_with_no_call(tmp_path, monkeypatch, track, project):
    _record(track, _imported(1, "This fixes #3 for good", state="queued-issue"))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert out == ["open-1 undecided again: closing keyword"]
    assert gh.calls() == [] and _by_id(track)["open-1"]["state"] == "undecided"


def test_flags_spread_across_fields_do_not_add_up_for_an_issue(
        tmp_path, monkeypatch, track, project):
    _record(track, _item(1, what="Pass --a and --b together", why="Also takes --c"))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert out == ["open-1 filed " + ISSUE % 11] and len(gh.calls()) == 1


def test_quoted_text_never_reaches_a_body(tmp_path, monkeypatch, track, project):
    secret = "reviewer said: rewrite everything"
    _record(track, _item(1, quoted=secret), _note(2, quoted=secret))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert len(gh.bodies) == 2
    assert not any("rewrite everything" in b for b in gh.bodies)


# ---- notes ------------------------------------------------------------------

@pytest.mark.parametrize("text,rule", [
    ("token=abcd1234efgh5678 was printed", "credential"),
    ("see C:\\Users\\x\\f.py for it", "local-path"),
    ("Traceback (most recent call last)", "raw-output"),
    ("run it with --a --b --c", "argument-vector"),
])
def test_each_forbidden_kind_refuses_a_note_with_no_call(
        tmp_path, monkeypatch, track, project, text, rule):
    # AC7: the comment carries none of what AC6 excludes.
    _record(track, _imported(1, text, state="queued-note"))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert out == ["open-1 undecided again: forbidden text (%s)" % rule]
    assert gh.calls() == []
    assert _by_id(track)["open-1"]["state"] == "undecided"


def test_a_closing_keyword_refuses_a_note_with_no_call(
        tmp_path, monkeypatch, track, project):
    _record(track, _imported(1, "This fixes #3 for good", state="queued-note"))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert out == ["open-1 undecided again: closing keyword"]
    assert gh.calls() == [] and _by_id(track)["open-1"]["state"] == "undecided"


def test_a_refused_note_leaves_the_others_to_be_posted(
        tmp_path, monkeypatch, track, project):
    _record(track, _note(1, what="token=abcd1234efgh5678 was printed"),
            _note(2, what="A clean note"))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert out == ["open-1 undecided again: forbidden text (credential)",
                   "open-2 noted " + COMMENT % 90]
    assert len(gh.calls()) == 1 and gh.bodies[0].startswith("1. A clean note\n")
    assert "abcd1234" not in gh.bodies[0]
    assert _by_id(track)["open-1"]["state"] == "undecided"


def test_three_notes_are_one_pr_comment_and_flags_do_not_add_up(
        tmp_path, monkeypatch, track, project):
    _record(track, _note(1, what="Uses --one here"), _note(2, what="Uses --two here"),
            _note(3, what="Uses --three here"))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN", ticket=41)
    assert out == ["open-%d noted %s" % (n, COMMENT % 90) for n in (1, 2, 3)]
    calls = gh.calls()
    assert len(calls) == 1 and calls[0][:3] == ["pr", "comment", "7"]
    assert calls[0][3] == "--body-file" and len(calls[0]) == 5
    body = gh.bodies[0]
    for n, what in ((1, "Uses --one here"), (2, "Uses --two here"), (3, "Uses --three here")):
        assert "%d. %s" % (n, what) in body
    assert body.count("- Pull request: #7") == 3 and body.endswith("Refs #41\n")
    for item in _by_id(track).values():
        assert (item["state"], item["url"], item["target"]) == (
            "noted", COMMENT % 90, "note-1")


def test_next_note_gets_the_next_k(tmp_path, monkeypatch, track, project):
    _record(track, _item(1, state="noted", url=COMMENT % 5, target="note-3"), _note(2))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert gh.during[0]["open-2"] == ("filing", "note-4")


@pytest.mark.parametrize("state", ["MERGED", "CLOSED"])
def test_notes_return_to_undecided_when_the_pr_is_not_open(
        tmp_path, monkeypatch, track, project, state):
    _record(track, _note(1), _note(2))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    out = _publish(track, project, at="done", pr=7, pr_state=state)
    assert out == ["open-1 undecided again: PR is %s" % state,
                   "open-2 undecided again: PR is %s" % state]
    assert gh.calls() == []
    assert {i["state"] for i in _by_id(track).values()} == {"undecided"}


def test_unknown_state_returns_notes_at_done_and_keeps_them_at_ship(
        tmp_path, monkeypatch, track, project):
    _record(track, _note(1))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    assert _publish(track, project, at="ship") == []
    assert _by_id(track)["open-1"]["state"] == "queued-note"
    assert _publish(track, project, at="done") == ["open-1 undecided again: PR is unknown"]
    assert gh.calls() == []


def test_a_pr_number_other_than_the_recorded_one_counts_as_unknown(
        tmp_path, monkeypatch, track, project):
    _record(track, _note(1))
    _shipped(track, note="PR #7")
    gh = _gh(tmp_path, monkeypatch, track)
    assert _publish(track, project, at="done", pr=8, pr_state="OPEN") == [
        "open-1 undecided again: PR is unknown"]
    assert gh.calls() == []


# ---- no PR recorded ---------------------------------------------------------

def test_no_pr_at_done_with_the_branch_on_origin_files_naming_the_branch(
        tmp_path, monkeypatch, track, project):
    _record(track, _item(1, at="done"), branch="track/x")
    monkeypatch.setattr(open_items, "branch_on_remote", lambda p, b: b == "track/x")
    gh = _gh(tmp_path, monkeypatch, track)
    out = _publish(track, project, at="done")
    assert out == ["open-1 filed " + ISSUE % 11]
    assert "- Branch: `track/x`" in gh.bodies[0] and "Pull request" not in gh.bodies[0]


def test_no_pr_at_done_with_the_branch_not_found_is_undecided_again(
        tmp_path, monkeypatch, track, project):
    _record(track, _item(1, at="done"))
    monkeypatch.setattr(open_items, "branch_on_remote", lambda p, b: False)
    gh = _gh(tmp_path, monkeypatch, track)
    assert _publish(track, project, at="done") == [
        "open-1 undecided again: branch not on origin"]
    assert gh.calls() == [] and _by_id(track)["open-1"]["state"] == "undecided"


def test_an_item_picked_at_the_stop_with_no_pr_is_undecided_again_at_done(
        tmp_path, monkeypatch, track, project):
    _record(track, _item(1, at="stop"), _note(2, at="stop"))
    monkeypatch.setattr(open_items, "branch_on_remote", lambda p, b: True)
    gh = _gh(tmp_path, monkeypatch, track)
    assert _publish(track, project, at="done") == [
        "open-1 undecided again: no PR recorded", "open-2 undecided again: no PR recorded"]
    assert gh.calls() == []


def test_pr_unknown_takes_the_branch_path(tmp_path, monkeypatch, track, project):
    _record(track, _item(1, at="done"), branch="track/x")
    _shipped(track, note="a note that names no number")
    monkeypatch.setattr(open_items, "branch_on_remote", lambda p, b: True)
    gh = _gh(tmp_path, monkeypatch, track)
    assert _publish(track, project, at="done", pr=7, pr_state="OPEN") == [
        "open-1 filed " + ISSUE % 11]
    assert "- Branch: `track/x`" in gh.bodies[0]


# ---- results never retried --------------------------------------------------

def test_a_timeout_leaves_filing_with_one_call_and_a_second_publish_makes_none(
        tmp_path, monkeypatch, track, project):
    _record(track, _item(1))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track, issue=[{"stdout": ISSUE % 11, "sleep": 5}])
    monkeypatch.setattr(ticket_backend, "TIMEOUT_SECONDS", 0.5)
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert out == ["open-1 filing: result unknown, check GitHub (unreachable)"]
    assert _by_id(track)["open-1"]["state"] == "filing"
    assert len(gh.calls()) == 1
    assert _publish(track, project, at="ship", pr=7, pr_state="OPEN") == []
    assert len(gh.calls()) == 1 and _by_id(track)["open-1"]["state"] == "filing"


def test_auth_failed_without_a_url_returns_the_item_to_undecided(
        tmp_path, monkeypatch, track, project):
    _record(track, _item(1))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track,
             issue=[{"exit": 1, "stderr": "HTTP 401: Bad credentials"}])
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert out == ["open-1 undecided again: auth-failed"]
    item = _by_id(track)["open-1"]
    assert item["state"] == "undecided" and item["picked"] is None
    assert len(gh.calls()) == 1


def test_any_other_failure_without_a_url_stays_filing_and_names_only_the_category(
        tmp_path, monkeypatch, track, project):
    _record(track, _item(1))
    _shipped(track)
    _gh(tmp_path, monkeypatch, track,
        issue=[{"exit": 1, "stderr": "secret-looking stderr text"}])
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert out == ["open-1 filing: result unknown, check GitHub (unclassified)"]
    assert "secret-looking" not in open_items.render(open_items.load(str(track)))


def test_a_nonzero_exit_that_printed_a_url_is_filed_with_the_category(
        tmp_path, monkeypatch, track, project):
    _record(track, _item(1), _note(2))
    _shipped(track)
    _gh(tmp_path, monkeypatch, track,
        issue=[{"exit": 1, "stdout": "warning\n" + ISSUE % 12 + "\n", "stderr": "partial"}],
        comment=[{"exit": 1, "stdout": COMMENT % 8 + "\n", "stderr": "partial"}])
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert out == ["open-1 filed %s (unclassified)" % (ISSUE % 12),
                   "open-2 noted %s (unclassified)" % (COMMENT % 8)]
    assert _by_id(track)["open-1"]["state"] == "filed"


def test_a_stdout_line_that_is_not_exactly_a_url_is_no_url(
        tmp_path, monkeypatch, track, project):
    _record(track, _item(1))
    _shipped(track)
    _gh(tmp_path, monkeypatch, track,
        issue=[{"stdout": "created " + ISSUE % 12 + "\n"}])
    out = _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert out == ["open-1 filing: result unknown, check GitHub (ok)"]


# ---- record and command line ------------------------------------------------

def test_a_second_publish_leaves_filed_items_alone(tmp_path, monkeypatch, track, project):
    _record(track, _item(1))
    _shipped(track)
    gh = _gh(tmp_path, monkeypatch, track)
    _publish(track, project, at="ship", pr=7, pr_state="OPEN")
    assert _publish(track, project, at="ship", pr=7, pr_state="OPEN") == []
    assert len(gh.calls()) == 1


def test_command_line_prints_the_lines_and_exits_0(tmp_path, track, project):
    _record(track, _item(1), _imported(2, "token=abcd1234efgh5678", state="queued-issue"))
    _shipped(track)
    script = tmp_path / "script.json"
    script.write_text(json.dumps([{"match": "issue create",
                                   "responses": [{"stdout": ISSUE % 31 + "\n"}]}]),
                      encoding="utf-8")
    env = dict(os.environ, FAKE_GH_MODE="script", FAKE_GH_SCRIPT=str(script),
               FAKE_GH_LOG=str(tmp_path / "gh.log"),
               **{ticket_backend.CLI_ENV: fake_gh.cli_argv()})
    done = subprocess.run(
        [sys.executable, SCRIPT, "publish", "--track-dir", str(track), "--project-dir",
         str(project), "--at", "ship", "--pr", "7", "--pr-state", "OPEN",
         "--ticket", "41"], capture_output=True, text=True, encoding="utf-8", env=env)
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert "open-1 filed " + ISSUE % 31 in lines
    assert "open-2 undecided again: forbidden text (credential)" in lines


def test_an_unreadable_record_exits_2_and_calls_nothing(tmp_path, track, project):
    (track / "open-items.md").write_text("not a record\n", encoding="utf-8")
    done = subprocess.run(
        [sys.executable, SCRIPT, "publish", "--track-dir", str(track), "--project-dir",
         str(project), "--at", "ship"], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 2 and done.stdout == ""
    assert "open-items.md" in done.stderr


def test_a_missing_record_is_created_and_publish_prints_nothing(
        tmp_path, monkeypatch, track, project):
    (track / "state.md").write_text("# f\n", encoding="utf-8")
    gh = _gh(tmp_path, monkeypatch, track)
    assert _publish(track, project, at="ship") == []
    assert (track / "open-items.md").exists() and gh.calls() == []
