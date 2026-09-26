"""Unit 4: `ticket.py read`, plus the `ticket-mirror.md` reference file it
backs (references/ticket-mirror.md).

`read` shares its shape with `project`/`show`: disabled or unreachable never
raises and never exits anything but 0, and a failure prints exactly one
line. A fake in-process backend (`FakeReadBackend`) drives the success and
failure paths the same way `test_ticket_project.py`'s `RecordingBackend`
does for `project` -- registered into `ticket_backend.BACKENDS`, never the
real `gh`.
"""
import json
import os

import pytest

import ticket
import ticket_backend as tb


def make_state_md(track_dir):
    lines = ["# fixture", "", "branch: feat/fixture", "started: 2026-08-29", "",
             "| stage | status | artifact | note |", "|---|---|---|---|"]
    (track_dir / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def enable_ticket(project_dir, backend="fake-read"):
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "cai.json").write_text(
        json.dumps({"ticket": {"enabled": True, "backend": backend}}), encoding="utf-8")


def set_pointer(track_dir, backend, ref):
    ticket.write_pointer(str(track_dir),
                          {"backend": backend, "ref": ref, "login": None,
                           "projection": None})


class FakeReadBackend(tb.Backend):
    """A backend whose `read()` answer and category are set by the test --
    the controllable double this unit needs, since `StubBackend` always
    succeeds with a fixed value and `RecordingBackend` (test_ticket_project.py)
    never implements `read()` at all.

    `comments` is only merged into the returned value when the caller asks
    for `with_comments=True` -- a test that never sets `comments` and never
    asks for them behaves exactly as it did before this unit."""
    name = "fake-read"

    def __init__(self, value=None, category="ok", comments=None):
        self._value = value
        self._category = category
        self._comments = comments if comments is not None else []
        self.read_calls = []
        self.with_comments_calls = []

    def __call__(self):
        return self

    def whoami(self, project_dir):
        raise NotImplementedError

    def read(self, project_dir, ref, with_comments=False):
        self.read_calls.append(ref)
        self.with_comments_calls.append(with_comments)
        if with_comments and self._value is not None:
            value = dict(self._value)
            value["comments"] = self._comments
            return value, self._category
        return self._value, self._category

    def upsert_comment(self, project_dir, ref, marker, body, login):
        raise NotImplementedError

    def transition_once(self, project_dir, ref):
        raise NotImplementedError


def register(monkeypatch, backend):
    monkeypatch.setitem(tb.BACKENDS, backend.name, backend)


# --- AC1: disabled means not one character printed, same as every other ---
# --- subcommand ------------------------------------------------------------

def test_read_disabled_prints_nothing(tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()  # no .claude/cai.json at all -- disabled
    backend = FakeReadBackend(value={"number": "48", "title": "t", "body": "b"})
    register(monkeypatch, backend)
    set_pointer(track, "fake-read", "48")

    rc = ticket.read(str(track), str(project_dir))
    out = capsys.readouterr().out
    assert rc is None
    assert out == ""
    assert backend.read_calls == []  # never even reached the backend


def test_read_no_pointer_prints_one_line(tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = FakeReadBackend(value={"number": "48", "title": "t", "body": "b"})
    register(monkeypatch, backend)
    # deliberately no ticket.json -- read_pointer() returns None

    rc = ticket.read(str(track), str(project_dir))
    out = capsys.readouterr().out
    assert rc is None
    assert out.count("\n") == 1
    assert "point" in out


def test_read_unknown_backend_prints_one_line(tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    set_pointer(track, "no-such-backend", "48")

    rc = ticket.read(str(track), str(project_dir))
    out = capsys.readouterr().out
    assert rc is None
    assert out.count("\n") == 1


def test_read_backend_failure_prints_one_line_and_returns_category(
        tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = FakeReadBackend(value=None, category="unreachable")
    register(monkeypatch, backend)
    set_pointer(track, "fake-read", "48")

    rc = ticket.read(str(track), str(project_dir))
    out = capsys.readouterr().out
    assert rc == "unreachable"
    assert out.count("\n") == 1
    assert "unreachable" in out


def test_read_success_prints_number_title_and_body(tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = FakeReadBackend(
        value={"number": "48", "title": "Fix the thing", "body": "line one\nline two"})
    register(monkeypatch, backend)
    set_pointer(track, "fake-read", "48")

    rc = ticket.read(str(track), str(project_dir))
    out = capsys.readouterr().out
    assert rc == "ok"
    assert "48" in out
    assert "Fix the thing" in out
    assert "line one" in out
    assert "line two" in out
    assert backend.read_calls == ["48"]


# --- Blocker 1: a pointer missing "ref" must not raise KeyError ------------

def test_read_missing_ref_in_pointer_prints_one_line_and_does_not_raise(
        tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = FakeReadBackend(value={"number": "48", "title": "t", "body": "b"})
    register(monkeypatch, backend)
    # a hand-edited or truncated ticket.json: valid dict, but no "ref" key
    ticket.write_pointer(str(track), {"backend": "fake-read"})

    rc = ticket.read(str(track), str(project_dir))

    assert rc is None
    assert backend.read_calls == []
    out = capsys.readouterr().out
    assert out.count("\n") == 1


# --- CLI frame: `read` is wired into main(), exits 0 on every path --------

def test_read_command_via_main_exits_0_when_disabled(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()  # disabled
    monkeypatch.setattr(
        "sys.argv",
        ["ticket.py", "read", "--track-dir", str(tmp_path),
         "--project-dir", str(project_dir)])
    rc = ticket.main()
    assert rc == 0


def test_read_command_via_main_exits_0_on_success(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = FakeReadBackend(value={"number": "1", "title": "t", "body": "b"})
    register(monkeypatch, backend)
    set_pointer(tmp_path, "fake-read", "1")

    monkeypatch.setattr(
        "sys.argv",
        ["ticket.py", "read", "--track-dir", str(tmp_path),
         "--project-dir", str(project_dir)])
    rc = ticket.main()
    assert rc == 0


# --- read --ref: a ticket nothing points at yet ----------------------------
#
# `/cai:track <issue ref>` needs the ticket's title before it can name the
# directory a pointer would live in. Without this, the only way to see what a
# ticket says was to commit a track to it first -- binding "look at this" to
# "start work on this", which are not the same decision.

def test_read_with_ref_needs_no_pointer_and_no_track(tmp_path, monkeypatch, capsys):
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = FakeReadBackend(value={"number": "91", "title": "gates by hook",
                                     "body": "the body"})
    register(monkeypatch, backend)

    # No track directory is created, and no pointer is written anywhere.
    rc = ticket.read(None, str(project_dir), ref="91")
    out = capsys.readouterr().out
    assert rc == "ok"
    assert backend.read_calls == ["91"]
    assert "number: 91" in out
    assert "title: gates by hook" in out


def test_read_with_ref_takes_the_backend_from_the_project_config(
        tmp_path, monkeypatch, capsys):
    """There is no pointer to carry a backend name, so the project's own
    config is the only thing left to read it from."""
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir, backend="fake-read")
    backend = FakeReadBackend(value={"number": "7", "title": "t", "body": "b"})
    register(monkeypatch, backend)

    assert ticket.read(None, str(project_dir), ref="7") == "ok"
    assert backend.read_calls == ["7"]


def test_read_with_ref_reports_an_unknown_backend_in_one_line(
        tmp_path, monkeypatch, capsys):
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir, backend="no-such-backend")

    rc = ticket.read(None, str(project_dir), ref="7")
    out = capsys.readouterr().out
    assert rc is None
    assert out.count("\n") == 1
    assert "no-such-backend" in out


def test_read_with_ref_stays_silent_when_mirroring_is_off(
        tmp_path, monkeypatch, capsys):
    """AC1 holds on this path too: a project that never turned the feature on
    prints nothing, so `/cai:track <url>` can tell "off" from "unreachable"."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()  # no .claude/cai.json at all
    backend = FakeReadBackend(value={"number": "1", "title": "t", "body": "b"})
    register(monkeypatch, backend)

    assert ticket.read(None, str(project_dir), ref="1") is None
    assert capsys.readouterr().out == ""
    assert backend.read_calls == []


def test_read_via_main_with_ref_and_no_track_dir_exits_0(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = FakeReadBackend(value={"number": "91", "title": "t", "body": "b"})
    register(monkeypatch, backend)

    monkeypatch.setattr(
        "sys.argv",
        ["ticket.py", "read", "--ref", "91", "--project-dir", str(project_dir)])
    assert ticket.main() == 0


def test_read_via_main_with_neither_track_dir_nor_ref_exits_1(monkeypatch):
    monkeypatch.setattr("sys.argv", ["ticket.py", "read"])
    with pytest.raises(SystemExit) as exc:
        ticket.main()
    assert exc.value.code == 1


def test_the_other_subcommands_still_require_a_track_dir(monkeypatch):
    """Making --track-dir optional for `read` must not make it optional for
    the four subcommands that cannot work without one."""
    for command in ("project", "point", "show", "transition"):
        monkeypatch.setattr("sys.argv", ["ticket.py", command])
        with pytest.raises(SystemExit) as exc:
            ticket.main()
        assert exc.value.code == 1, command


# --- Claim listing -----------------------------------------------------------
#
# `list_claims` turns raw `{"body", "login"}` comment pairs into the claim
# lines `read --ref` prints; `local_claim_state` says whether this tree's own
# ticket.json (or its done/ counterpart) matches one of those claims.

def _claim_comment(name, login="someone", updated="2026-09-26T12:45:17Z"):
    lines = [ticket.marker_for(name), "此留言由 cai 就地覆寫，請勿手動編輯"]
    if updated is not None:
        lines.append("updated %s" % updated)
    return {"body": "\n".join(lines), "login": login}


def test_list_claims_empty_when_no_comments():
    assert ticket.list_claims([]) == []


def test_list_claims_parses_name_login_updated():
    comments = [_claim_comment("track-issue-status-sync", login="millerlai",
                                updated="2026-09-26T12:45:17Z")]
    claims = ticket.list_claims(comments)
    assert claims == [{"name": "track-issue-status-sync", "login": "millerlai",
                        "updated": "2026-09-26T12:45:17Z"}]


def test_list_claims_ignores_marker_not_on_first_line():
    body = "just a comment\n" + ticket.marker_for("sneaky")
    claims = ticket.list_claims([{"body": body, "login": "someone"}])
    assert claims == []


def test_list_claims_ignores_empty_body():
    claims = ticket.list_claims([{"body": "", "login": "someone"},
                                  {"login": "someone"}])
    assert claims == []


def test_list_claims_missing_login_is_unknown():
    comment = _claim_comment("a-name", updated="2026-09-25T00:00:00Z")
    del comment["login"]
    claims = ticket.list_claims([comment])
    assert claims[0]["login"] == "unknown"


def test_list_claims_missing_updated_line_is_unknown():
    comment = _claim_comment("a-name", updated=None)
    claims = ticket.list_claims([comment])
    assert claims[0]["updated"] == "unknown"


def test_list_claims_sorts_newest_first_unknown_last():
    older = _claim_comment("older", login="a", updated="2026-09-01T00:00:00Z")
    newer = _claim_comment("newer", login="b", updated="2026-09-25T00:00:00Z")
    unknown = _claim_comment("nodate", login="c", updated=None)
    claims = ticket.list_claims([older, unknown, newer])
    assert [c["name"] for c in claims] == ["newer", "older", "nodate"]


def test_issue_number_from_plain_digits():
    assert ticket._issue_number("170") == "170"
    assert ticket._issue_number(" 170 ") == "170"


def test_issue_number_from_url():
    url = "https://github.com/owner/repo/issues/170"
    assert ticket._issue_number(url) == "170"
    assert ticket._issue_number(url + "#issuecomment-1") == "170"


def test_issue_number_none_for_garbage():
    assert ticket._issue_number("not-a-ref") is None
    assert ticket._issue_number("") is None


def test_local_claim_state_empty_number_is_not_local():
    assert ticket.local_claim_state("proj", "some-track", "octocat", "") == ""


def test_local_claim_state_invalid_name_is_not_local(tmp_path):
    project_dir = str(tmp_path)
    for bad_name in ("current", "done", "../x", "a name with space"):
        assert ticket.local_claim_state(project_dir, bad_name, "octocat", "170") == ""


def test_local_claim_state_resumable(tmp_path):
    track_dir = tmp_path / ".claude" / "track" / "track-issue-status-sync"
    track_dir.mkdir(parents=True)
    ticket.write_pointer(str(track_dir),
                          {"backend": "github", "ref": "170", "login": "octocat",
                           "projection": None})
    state = ticket.local_claim_state(str(tmp_path), "track-issue-status-sync",
                                      "octocat", "170")
    assert state == "resumable"


def test_local_claim_state_finished(tmp_path):
    done_dir = tmp_path / ".claude" / "track" / "done" / "track-issue-status-sync"
    done_dir.mkdir(parents=True)
    ticket.write_pointer(str(done_dir),
                          {"backend": "github", "ref": "170", "login": "octocat",
                           "projection": None})
    state = ticket.local_claim_state(str(tmp_path), "track-issue-status-sync",
                                      "octocat", "170")
    assert state == "finished"


def test_local_claim_state_wrong_login_or_issue_is_not_local(tmp_path):
    track_dir = tmp_path / ".claude" / "track" / "track-issue-status-sync"
    track_dir.mkdir(parents=True)
    ticket.write_pointer(str(track_dir),
                          {"backend": "github", "ref": "170", "login": "octocat",
                           "projection": None})
    assert ticket.local_claim_state(str(tmp_path), "track-issue-status-sync",
                                     "someone-else", "170") == ""
    assert ticket.local_claim_state(str(tmp_path), "track-issue-status-sync",
                                     "octocat", "999") == ""


def test_local_claim_state_unreadable_pointer_is_not_local(tmp_path):
    track_dir = tmp_path / ".claude" / "track" / "track-issue-status-sync"
    track_dir.mkdir(parents=True)
    (track_dir / "ticket.json").write_text("{not json", encoding="utf-8")
    assert ticket.local_claim_state(str(tmp_path), "track-issue-status-sync",
                                     "octocat", "170") == ""


def test_local_claim_state_missing_login_is_not_local(tmp_path):
    """A cached login of "" or None can never equal a claim's login, so a
    pointer without one is never resumable -- the failure mode the design
    calls out for a deleted claim author."""
    track_dir = tmp_path / ".claude" / "track" / "track-issue-status-sync"
    track_dir.mkdir(parents=True)
    ticket.write_pointer(str(track_dir),
                          {"backend": "github", "ref": "170", "login": None,
                           "projection": None})
    assert ticket.local_claim_state(str(tmp_path), "track-issue-status-sync",
                                     "unknown", "170") == ""


# --- `read --ref` with claims -------------------------------------------

def test_read_ref_prints_claims_zero_on_success(tmp_path, monkeypatch, capsys):
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = FakeReadBackend(value={"number": "170", "title": "t", "body": "b"},
                               comments=[])
    register(monkeypatch, backend)

    rc = ticket.read(None, str(project_dir), ref="170")
    out = capsys.readouterr().out
    assert rc == "ok"
    assert "claims: 0" in out
    assert backend.with_comments_calls == [True]
    # claims block sits between title and body
    lines = out.splitlines()
    assert lines[1] == "title: t"
    assert lines[2] == "claims: 0"
    assert lines[3] == "b"


def test_read_ref_prints_claim_lines_with_local_suffixes(tmp_path, monkeypatch, capsys):
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    track_dir = project_dir / ".claude" / "track" / "track-issue-status-sync"
    track_dir.mkdir(parents=True)
    ticket.write_pointer(str(track_dir),
                          {"backend": "github", "ref": "170", "login": "millerlai",
                           "projection": None})

    mine = _claim_comment("track-issue-status-sync", login="millerlai",
                           updated="2026-09-26T12:45:17Z")
    other = _claim_comment("issue-status-claims", login="octocat",
                            updated="2026-09-25T08:10:00Z")
    backend = FakeReadBackend(value={"number": "170", "title": "t", "body": "b"},
                               comments=[other, mine])
    register(monkeypatch, backend)

    rc = ticket.read(None, str(project_dir), ref="170")
    out = capsys.readouterr().out
    assert rc == "ok"
    assert "claims: 2" in out
    assert ("- track-issue-status-sync by millerlai, updated "
            "2026-09-26T12:45:17Z, local: resumable") in out
    assert ("- issue-status-claims by octocat, updated 2026-09-25T08:10:00Z"
            in out)
    # the other claim gets no local: suffix
    for line in out.splitlines():
        if line.startswith("- issue-status-claims"):
            assert "local:" not in line


def test_read_pointer_path_never_prints_claims(tmp_path, monkeypatch, capsys):
    """The `--track-dir` pointer path stays `with_claims=False` per the
    design's D3 refinement -- claims present in the fake backend's data must
    not leak into that call's output."""
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = FakeReadBackend(value={"number": "48", "title": "t", "body": "b"},
                               comments=[_claim_comment("someone-elses-track")])
    register(monkeypatch, backend)
    set_pointer(track, "fake-read", "48")

    rc = ticket.read(str(track), str(project_dir))
    out = capsys.readouterr().out
    assert rc == "ok"
    assert "claims:" not in out
    assert backend.with_comments_calls == [False]
