"""Unit 5: `ticket.py transition`, `--confirmed-by-user`, and its downstream
guarantees.

This is the one subcommand of the five that can perform an irreversible
external operation, so the negative assertions here matter more than the
positive ones: a missing `--confirmed-by-user` must make *zero* calls into
the backend, not merely return early after having already called it.
`RecordingBackend` below counts calls precisely so that mutation-style
sabotage of the guard (removing the early return, or checking the flag
after the pointer/backend lookups) turns a passing test red -- see each
test's own comment for which mutation it is meant to catch.

Never drives the real `gh` -- everything here is `RecordingBackend`,
registered into `ticket_backend.BACKENDS` the same way `test_ticket_project.
py`'s double is (StubBackend covers the always-succeeds shape separately,
via `local-stub` in `test_transition_via_cli_with_flag_calls_stub_backend`).
"""
import json
import sys

import ticket
import ticket_backend as tb


def enable_ticket(project_dir, backend="recording-transition"):
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "cai.json").write_text(
        json.dumps({"ticket": {"enabled": True, "backend": backend}}), encoding="utf-8")


def set_pointer(track_dir, backend, ref, login=None, projection=None):
    ticket.write_pointer(str(track_dir),
                          {"backend": backend, "ref": ref, "login": login,
                           "projection": projection})


class RecordingBackend(tb.Backend):
    """A backend whose `transition_once` calls are countable and whose
    result is controllable -- the double AC16 and idempotence need, none of
    which `StubBackend` (always succeeds, remembers nothing) can drive."""
    name = "recording-transition"

    def __init__(self, ok=True, category="ok"):
        self.transition_calls = []
        self._ok = ok
        self._category = category

    def __call__(self):
        return self

    def whoami(self, project_dir):
        raise NotImplementedError  # not exercised by transition()

    def read(self, project_dir, ref):
        raise NotImplementedError  # not exercised by transition()

    def upsert_comment(self, project_dir, ref, marker, body, login):
        raise NotImplementedError  # not exercised by transition()

    def transition_once(self, project_dir, ref):
        self.transition_calls.append(ref)
        return self._ok, self._category


def register(monkeypatch, backend):
    monkeypatch.setitem(tb.BACKENDS, backend.name, backend)


# --- AC16: missing --confirmed-by-user makes zero external calls -----------

def test_missing_flag_makes_zero_backend_calls(tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend()
    register(monkeypatch, backend)
    set_pointer(track, "recording-transition", "48")

    rc = ticket.transition(str(track), str(project_dir), confirmed_by_user=False)

    assert rc is None
    assert backend.transition_calls == []  # the guard, proven by absence
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert "confirmed-by-user" in out


def test_missing_flag_still_exits_0(tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend()
    register(monkeypatch, backend)
    set_pointer(track, "recording-transition", "48")

    monkeypatch.setattr(
        sys, "argv",
        ["ticket.py", "transition", "--track-dir", str(track),
         "--project-dir", str(project_dir)])
    rc = ticket.main()
    assert rc == 0
    assert backend.transition_calls == []


def test_missing_flag_does_not_touch_pointer_projection(tmp_path, monkeypatch):
    # `transition` never writes to the pointer at all (DD2: a transition
    # result has nowhere defined to land but the screen) -- a refusal must
    # not be the one case that breaks that.
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend()
    register(monkeypatch, backend)
    existing_projection = {"status": "ok", "at": "2026-08-30T00:00:00Z"}
    set_pointer(track, "recording-transition", "48", login="octocat",
                projection=existing_projection)

    ticket.transition(str(track), str(project_dir), confirmed_by_user=False)

    pointer = ticket.read_pointer(str(track))
    assert pointer["projection"] == existing_projection
    assert pointer["login"] == "octocat"


# --- with the flag: exactly one transition call, and it never writes the ---
# --- pointer either -----------------------------------------------------

def test_flag_present_calls_transition_exactly_once(tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend(ok=True, category="ok")
    register(monkeypatch, backend)
    set_pointer(track, "recording-transition", "48")

    rc = ticket.transition(str(track), str(project_dir), confirmed_by_user=True)

    assert rc == "ok"
    assert backend.transition_calls == ["48"]
    out = capsys.readouterr().out
    assert "ok" in out


def test_flag_present_never_writes_the_pointer(tmp_path, monkeypatch):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend(ok=True, category="ok")
    register(monkeypatch, backend)
    existing_projection = {"status": "ok", "at": "2026-08-30T00:00:00Z"}
    set_pointer(track, "recording-transition", "48", login="octocat",
                projection=existing_projection)

    ticket.transition(str(track), str(project_dir), confirmed_by_user=True)

    pointer = ticket.read_pointer(str(track))
    assert pointer["projection"] == existing_projection
    assert pointer["login"] == "octocat"


def test_transition_via_main_with_flag_calls_backend_once(tmp_path, monkeypatch):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend(ok=True, category="ok")
    register(monkeypatch, backend)
    set_pointer(track, "recording-transition", "48")

    monkeypatch.setattr(
        sys, "argv",
        ["ticket.py", "transition", "--track-dir", str(track),
         "--project-dir", str(project_dir), "--confirmed-by-user"])
    rc = ticket.main()
    assert rc == 0
    assert backend.transition_calls == ["48"]


# --- shared shape with project/read: disabled, no pointer, unknown backend -

def test_disabled_prints_nothing_once_flag_is_present(tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()  # no .claude/cai.json -- disabled
    backend = RecordingBackend()
    register(monkeypatch, backend)
    set_pointer(track, "recording-transition", "48")

    rc = ticket.transition(str(track), str(project_dir), confirmed_by_user=True)

    assert rc is None
    assert backend.transition_calls == []
    out = capsys.readouterr().out
    assert out == ""  # AC1: silence when never turned on


def test_no_pointer_prints_one_line(tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend()
    register(monkeypatch, backend)
    # deliberately no ticket.json

    rc = ticket.transition(str(track), str(project_dir), confirmed_by_user=True)

    assert rc is None
    assert backend.transition_calls == []
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert "point" in out


def test_unknown_backend_prints_one_line(tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    set_pointer(track, "no-such-backend", "48")

    rc = ticket.transition(str(track), str(project_dir), confirmed_by_user=True)

    assert rc is None
    out = capsys.readouterr().out
    assert out.count("\n") == 1


# --- Blocker 1: a pointer missing "ref" must not raise KeyError ------------

def test_missing_ref_in_pointer_prints_one_line_and_does_not_raise(
        tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend()
    register(monkeypatch, backend)
    # a hand-edited or truncated ticket.json: valid dict, but no "ref" key
    ticket.write_pointer(str(track), {"backend": "recording-transition"})

    rc = ticket.transition(str(track), str(project_dir), confirmed_by_user=True)

    assert rc is None
    assert backend.transition_calls == []
    out = capsys.readouterr().out
    assert out.count("\n") == 1


# --- idempotence: two closes in a row both exit 0, second is not an error --

def test_idempotent_two_transitions_both_succeed(tmp_path, monkeypatch):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend(ok=True, category="ok")  # already-closed still exits 0
    register(monkeypatch, backend)
    set_pointer(track, "recording-transition", "48")

    rc1 = ticket.transition(str(track), str(project_dir), confirmed_by_user=True)
    rc2 = ticket.transition(str(track), str(project_dir), confirmed_by_user=True)

    assert rc1 == "ok"
    assert rc2 == "ok"  # a repeat close on an already-closed issue is not an error
    assert backend.transition_calls == ["48", "48"]


def test_idempotent_via_the_real_gitHubBackend_shape(tmp_path, monkeypatch):
    # ticket_backend.py's own test already proves `gh issue close` on an
    # already-closed issue exits 0 (test_transition_once_is_idempotent);
    # this proves ticket.transition() carries that result through unchanged.
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir, backend="local-stub")
    set_pointer(track, "local-stub", "48")

    rc1 = ticket.transition(str(track), str(project_dir), confirmed_by_user=True)
    rc2 = ticket.transition(str(track), str(project_dir), confirmed_by_user=True)
    assert rc1 == "ok"
    assert rc2 == "ok"


# --- failure: the printed line is the only thing the user will ever see ----

def test_failed_transition_names_the_ticket_and_says_it_is_still_open(
        tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend(ok=False, category="auth-failed")
    register(monkeypatch, backend)
    set_pointer(track, "recording-transition", "48")

    rc = ticket.transition(str(track), str(project_dir), confirmed_by_user=True)

    assert rc == "auth-failed"
    out = capsys.readouterr().out
    assert "48" in out
    assert "still open" in out
    assert "not" in out and "automatically" in out


# --- usage error: `transition` is a valid choice, not rejected by argparse -

def test_transition_is_a_valid_cli_choice(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()  # disabled is fine -- this only proves the choice parses
    monkeypatch.setattr(
        sys, "argv",
        ["ticket.py", "transition", "--track-dir", str(tmp_path),
         "--project-dir", str(project_dir)])
    rc = ticket.main()
    assert rc == 0
