"""Unit 3: `ticket.py project` wiring, `point`, `show`, and the CLI frame.

Everything here drives `ticket.py` through either a controllable in-process
fake backend (`RecordingBackend` below, registered into `ticket_backend.
BACKENDS` the same way `StubBackend` is) or through `CAI_TICKET_CLI` pointed
at `tests/fake_gh.py` / a throwaway script -- never the real `gh`, never the
network. The three rules this unit exists to prove:

1. `ticket.py` never exits 2 and never fails a stage -- exit 0 on every path
   except a usage error (exit 1), and it never touches `ledger.py` (asserted
   both structurally, via the import list, and behaviourally, via
   `ledger.records()`).
2. A projection failure is recorded in `ticket.json`'s `projection` field,
   never in the ledger (DD2).
3. A projection never overwrites a cached `login` -- only `point` may clear
   or set it.
"""
import ast
import json
import os
import sys

import pytest

import ledger
import ticket
import ticket_backend as tb

import fake_gh

SCRIPTS_DIR = os.path.dirname(os.path.abspath(ticket.__file__))

STAGE_IDS = ["intake", "discover", "design", "build", "verify", "ship"]

SIX_ROWS = [
    ("intake", "done", "docs/design/x-intake.md", "signed off"),
    ("discover", "skipped", "—", "reason: closed at the program layer"),
    ("design", "done", "docs/design/x-detail.md", "HLD and detail both signed off"),
    ("build", "passed", "—", ""),
    ("verify", "", "", ""),
    ("ship", "", "", ""),
]


def make_state_md(track_dir, rows=SIX_ROWS):
    lines = ["# fixture", "", "branch: feat/fixture", "started: 2026-08-29", "",
             "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track_dir / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def enable_ticket(project_dir, backend="recording-stub"):
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "cai.json").write_text(
        json.dumps({"ticket": {"enabled": True, "backend": backend}}), encoding="utf-8")


def set_pointer(track_dir, backend, ref, login=None, projection=None):
    ticket.write_pointer(str(track_dir),
                          {"backend": backend, "ref": ref, "login": login,
                           "projection": projection})


def ledger_path(track_dir):
    return os.path.join(str(track_dir), "ledger.jsonl")


def assert_ledger_untouched(track_dir):
    assert not os.path.exists(ledger_path(track_dir))
    assert ledger.records(str(track_dir)) == []


def assert_ticket_py_never_imports_ledger():
    with open(os.path.join(SCRIPTS_DIR, "ticket.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    assert "ledger" not in names


# --- a controllable in-process backend, the "StubBackend" the brief means --

class RecordingBackend(tb.Backend):
    """A backend whose calls and state are inspectable from the test that
    registers it -- the controllable double for AC5a/AC5b/AC12/idempotence/
    login-caching, none of which StubBackend itself can drive (it always
    succeeds and remembers nothing).

    Registered into `ticket_backend.BACKENDS` as a singleton that answers its
    own `__call__` with itself, matching `get()`'s `cls()` -- `BACKENDS`'
    values only need to be callables that return a `Backend`, not literally
    classes."""
    name = "recording-stub"

    def __init__(self, whoami_category="ok", login="octocat", write_category="ok"):
        self.whoami_calls = 0
        self.write_calls = []
        self.comments = []  # [{"body": str, "login": str}]
        self._whoami_category = whoami_category
        self._login = login
        self._write_category = write_category

    def __call__(self):
        return self

    def whoami(self, project_dir):
        self.whoami_calls += 1
        if self._whoami_category != "ok":
            return None, self._whoami_category
        return self._login, "ok"

    def read(self, project_dir, ref):
        raise NotImplementedError  # not exercised by this unit

    def upsert_comment(self, project_dir, ref, marker, body, login):
        self.write_calls.append((ref, marker, login))
        if self._write_category != "ok":
            return None, self._write_category
        match = next((c for c in self.comments
                      if marker in c["body"] and c["login"] == login), None)
        if match is not None:
            match["body"] = body
        else:
            self.comments.append({"body": body, "login": login})
        return "recording-stub://%s/comment" % ref, "ok"

    def transition_once(self, project_dir, ref):
        raise NotImplementedError  # unit 5's job


def register(monkeypatch, backend):
    monkeypatch.setitem(tb.BACKENDS, backend.name, backend)


# --- AC12: zero write calls when a projection should not be attempted ------

def test_ac12_disabled_feature_makes_zero_write_calls(tmp_path, monkeypatch):
    track = tmp_path / "track"
    track.mkdir()
    make_state_md(track)
    project_dir = tmp_path / "proj"
    project_dir.mkdir()  # no .claude/cai.json at all -- disabled
    backend = RecordingBackend()
    register(monkeypatch, backend)
    set_pointer(track, "recording-stub", "48")  # a pointer exists, but disabled wins

    rc = ticket.project(str(track), str(project_dir))
    assert rc is None
    assert backend.write_calls == []


def test_ac12_no_pointer_makes_zero_write_calls(tmp_path, monkeypatch):
    track = tmp_path / "track"
    track.mkdir()
    make_state_md(track)
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend()
    register(monkeypatch, backend)
    # deliberately no ticket.json in track -- read_pointer() returns None

    rc = ticket.project(str(track), str(project_dir))
    assert rc is None
    assert backend.write_calls == []


def test_ac12_render_comment_none_makes_zero_write_calls(tmp_path, monkeypatch):
    track = tmp_path / "track"
    track.mkdir()
    # deliberately no state.md -- render_comment() returns None
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend()
    register(monkeypatch, backend)
    set_pointer(track, "recording-stub", "48")

    rc = ticket.project(str(track), str(project_dir))
    assert rc is None
    assert backend.write_calls == []


# --- Blocker 1: a pointer missing "ref" must not raise KeyError ------------

def test_missing_ref_in_pointer_prints_one_line_and_does_not_raise(
        tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    make_state_md(track)
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend()
    register(monkeypatch, backend)
    # a hand-edited or truncated ticket.json: valid dict, but no "ref" key
    ticket.write_pointer(str(track), {"backend": "recording-stub"})

    rc = ticket.project(str(track), str(project_dir))

    assert rc is None
    assert backend.write_calls == []
    out = capsys.readouterr().out
    assert out.count("\n") == 1


# --- Major 1: the unknown-backend guard, exercised through project() itself,
# --- not only through read()/transition() -----------------------------------

def test_unknown_backend_prints_one_line_and_does_not_raise(
        tmp_path, monkeypatch, capsys):
    track = tmp_path / "track"
    track.mkdir()
    make_state_md(track)
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    ticket.write_pointer(str(track),
                          {"backend": "no-such-backend", "ref": "48",
                           "login": None, "projection": None})

    rc = ticket.project(str(track), str(project_dir))

    assert rc is None
    out = capsys.readouterr().out
    assert out.count("\n") == 1


# --- AC5a: a fake CLI failing every time never blocks or fails the stage ---

def test_ac5a_always_failing_cli_never_blocks_six_times(tmp_path, monkeypatch):
    track = tmp_path / "track"
    track.mkdir()
    make_state_md(track)
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir, backend="github")
    set_pointer(track, "github", "48")

    monkeypatch.setenv(tb.CLI_ENV, fake_gh.cli_argv())
    monkeypatch.setenv("FAKE_GH_MODE", "fail")

    for _ in range(6):
        rc = ticket.project(str(track), str(project_dir))
        assert rc in tb.CATEGORIES
        assert rc != "ok"

    assert_ledger_untouched(track)
    assert_ticket_py_never_imports_ledger()
    pointer = ticket.read_pointer(str(track))
    assert pointer["projection"]["status"] in tb.CATEGORIES
    assert pointer["login"] is None  # whoami always failed too -- never cached


# --- AC5b: read succeeds, write always fails -- category lands in ticket.json,
#     the ledger stays untouched, and nothing raises the exit code ----------

def _read_ok_write_fails_script(log_path):
    return (
        "import sys\n"
        "argv = sys.argv[1:]\n"
        "with open(%r, 'a', encoding='utf-8') as fh:\n"
        "    fh.write(' '.join(argv) + '\\n')\n"
        "if argv[:2] == ['api', 'user']:\n"
        "    print('octocat')\n"
        "elif argv[:2] == ['issue', 'view']:\n"
        "    print('{\"comments\": []}')\n"
        "else:\n"
        "    sys.stderr.write('boom')\n"
        "    sys.exit(1)\n"
    ) % str(log_path)


def test_ac5b_write_always_fails_records_category_in_pointer_not_ledger(tmp_path, monkeypatch):
    track = tmp_path / "track"
    track.mkdir()
    make_state_md(track)
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir, backend="github")
    set_pointer(track, "github", "48")

    log = tmp_path / "calls.log"
    script = tmp_path / "fake_gh.py"
    script.write_text(_read_ok_write_fails_script(log), encoding="utf-8")
    monkeypatch.setenv(tb.CLI_ENV, json.dumps([sys.executable, str(script)]))

    rc = ticket.project(str(track), str(project_dir))
    assert rc == "unclassified"  # "boom" matches none of classify()'s wordings

    pointer = ticket.read_pointer(str(track))
    assert pointer["projection"]["status"] == "unclassified"
    assert pointer["projection"]["at"]
    assert pointer["login"] == "octocat"  # whoami succeeded and got cached

    assert_ledger_untouched(track)

    calls = log.read_text(encoding="utf-8").splitlines()
    assert any(c.startswith("api user") for c in calls)
    assert any(c.startswith("issue view") for c in calls)


# --- AC7: CAI_TICKET_CLI pointing at a path that does not exist at all -----

def test_ac7_missing_cli_executable_still_holds_ac5a_and_ac5b_assertions(tmp_path, monkeypatch):
    track = tmp_path / "track"
    track.mkdir()
    make_state_md(track)
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir, backend="github")
    set_pointer(track, "github", "48")

    monkeypatch.setenv(tb.CLI_ENV, str(tmp_path / "does-not-exist.exe"))

    for _ in range(6):
        rc = ticket.project(str(track), str(project_dir))
        assert rc == "unreachable"

    assert_ledger_untouched(track)
    pointer = ticket.read_pointer(str(track))
    assert pointer["projection"] == {"status": "unreachable", "at": pointer["projection"]["at"]}
    assert pointer["login"] is None


# --- idempotence: two runs of a working backend never create a second ------
# --- comment, and a cache-hit costs zero extra whoami calls ---------------

def test_project_is_idempotent_and_caches_login_after_the_first_run(tmp_path, monkeypatch):
    track = tmp_path / "track"
    track.mkdir()
    make_state_md(track)
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    set_pointer(track, "recording-stub", "48")
    backend = RecordingBackend()
    register(monkeypatch, backend)

    rc1 = ticket.project(str(track), str(project_dir))
    assert rc1 == "ok"
    assert len(backend.comments) == 1
    assert backend.whoami_calls == 1

    rc2 = ticket.project(str(track), str(project_dir))
    assert rc2 == "ok"
    assert len(backend.comments) == 1  # still one comment, updated in place
    assert backend.whoami_calls == 1  # cache hit -- no second whoami

    pointer = ticket.read_pointer(str(track))
    assert pointer["login"] == "octocat"


# --- point clears the cached login; the next projection fetches it again ---

def test_point_clears_cached_login_and_project_refetches_it(tmp_path, monkeypatch):
    track = tmp_path / "track"
    track.mkdir()
    make_state_md(track)
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend()
    register(monkeypatch, backend)
    set_pointer(track, "recording-stub", "48")

    ticket.project(str(track), str(project_dir))
    assert backend.whoami_calls == 1
    assert ticket.read_pointer(str(track))["login"] == "octocat"

    ticket.point(str(track), "48", None)  # no cache to compare against after this
    pointer = ticket.read_pointer(str(track))
    assert pointer["login"] is None
    assert pointer["projection"] is None
    assert pointer["backend"] == "recording-stub"  # kept from the existing pointer

    ticket.project(str(track), str(project_dir))
    assert backend.whoami_calls == 2  # re-fetched, not reused


def test_point_never_overwrites_login_during_a_projection(tmp_path, monkeypatch):
    # The inverse of the test above: a projection itself must never touch
    # pointer["login"] once it is cached, even across many runs.
    track = tmp_path / "track"
    track.mkdir()
    make_state_md(track)
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    backend = RecordingBackend()
    register(monkeypatch, backend)
    set_pointer(track, "recording-stub", "48")

    for _ in range(3):
        ticket.project(str(track), str(project_dir))
    assert backend.whoami_calls == 1
    assert ticket.read_pointer(str(track))["login"] == "octocat"


# --- show ---------------------------------------------------------------

def test_show_prints_ref_login_and_last_projection(tmp_path, capsys):
    track = tmp_path / "track"
    track.mkdir()
    set_pointer(track, "github", "48", login="octocat",
                projection={"status": "ok", "at": "2026-08-31T00:00:00Z"})

    ticket.show(str(track), dry_run=False)
    out = capsys.readouterr().out
    assert "48" in out
    assert "octocat" in out
    assert "ok" in out
    assert "2026-08-31T00:00:00Z" in out


def test_show_no_pointer_prints_one_line(tmp_path, capsys):
    track = tmp_path / "track"
    track.mkdir()
    ticket.show(str(track), dry_run=False)
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert "point" in out


def test_show_dry_run_prints_body_and_makes_zero_external_calls(tmp_path, capsys, monkeypatch):
    track = tmp_path / "track"
    track.mkdir()
    make_state_md(track)
    set_pointer(track, "github", "48", login="octocat")

    def boom(name):
        raise AssertionError("show() must never resolve a backend")
    monkeypatch.setattr(tb, "get", boom)

    ticket.show(str(track), dry_run=True)
    out = capsys.readouterr().out
    assert "[cai track: track]" in out  # the marker line, from render_comment
    assert "updated " in out


# --- CLI frame: exit codes ------------------------------------------------

def test_usage_error_missing_track_dir_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["ticket.py", "show"])
    with pytest.raises(SystemExit) as exc:
        ticket.main()
    assert exc.value.code == 1


def test_usage_error_point_without_ref_exits_1(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["ticket.py", "point", "--track-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        ticket.main()
    assert exc.value.code == 1


def test_usage_error_unknown_command_exits_1(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["ticket.py", "bogus", "--track-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        ticket.main()
    assert exc.value.code == 1


def test_project_command_via_main_exits_0_when_disabled(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()  # disabled: no .claude/cai.json
    monkeypatch.setattr(sys, "argv",
                        ["ticket.py", "project", "--track-dir", str(tmp_path),
                         "--project-dir", str(project_dir)])
    rc = ticket.main()
    assert rc == 0


def test_point_command_via_main_exits_0_and_writes_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["ticket.py", "point", "--track-dir", str(tmp_path),
                         "--ref", "48", "--backend", "github"])
    rc = ticket.main()
    assert rc == 0
    pointer = ticket.read_pointer(str(tmp_path))
    assert pointer == {"backend": "github", "ref": "48", "login": None, "projection": None}


def test_project_command_via_main_exits_0_even_when_the_backend_fails(tmp_path, monkeypatch):
    # The CLI-level version of the "never exit 2" rule: preflight.py uses 2
    # for "blocked", and ticket.py must never produce that exit code no
    # matter how badly the backend fails.
    track = tmp_path / "track"
    track.mkdir()
    make_state_md(track)
    project_dir = tmp_path / "proj"
    enable_ticket(project_dir)
    set_pointer(track, "recording-stub", "48")
    backend = RecordingBackend(write_category="unreachable")
    register(monkeypatch, backend)

    monkeypatch.setattr(sys, "argv",
                        ["ticket.py", "project", "--track-dir", str(track),
                         "--project-dir", str(project_dir)])
    rc = ticket.main()
    assert rc == 0
    pointer = ticket.read_pointer(str(track))
    assert pointer["projection"]["status"] == "unreachable"


def test_show_command_via_main_exits_0(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ticket.py", "show", "--track-dir", str(tmp_path)])
    rc = ticket.main()
    assert rc == 0
