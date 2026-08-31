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
    never implements `read()` at all."""
    name = "fake-read"

    def __init__(self, value=None, category="ok"):
        self._value = value
        self._category = category
        self.read_calls = []

    def __call__(self):
        return self

    def whoami(self, project_dir):
        raise NotImplementedError

    def read(self, project_dir, ref):
        self.read_calls.append(ref)
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
