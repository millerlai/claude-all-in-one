"""Unit 2: read_config, read_pointer, write_pointer, plus AC21/22/23.

No `gh`, no network -- ticket.py and ticket_backend.py's StubBackend are
both purely local, which this file spends most of its lines proving rather
than assuming.
"""
import ast
import json
import os
import sys

import ticket
import ticket_backend as tb

import fake_gh

SCRIPTS_DIR = os.path.dirname(os.path.abspath(ticket.__file__))


def _top_level_imports(path):
    """Every module name a `import x` / `import x.y` / `from x import y`
    statement at any depth of `path` names -- just the top-level package,
    since that is what decides whether it is stdlib or a third-party dep."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:  # ignore relative imports
                names.add(node.module.split(".")[0])
    return names


# --- AC22: zero deps beyond stdlib + the sibling preflight module ----------

def test_ticket_py_imports_only_stdlib_and_siblings():
    """AC22 is about third-party dependencies, not about module count.

    `ticket_backend` is this feature's other half, living in the same
    directory and -- proven by the next test -- importing nothing but the
    standard library itself. Allowing it keeps the chain ticket.py ->
    ticket_backend -> stdlib free of any installed package, which is the
    guarantee AC22 exists for. Unit 2 wrote this list before unit 3 wired
    the two halves together, so the original spelling admitted only
    `preflight` and would have forced either a broken projection or an
    importlib trick that games this very assertion."""
    allowed = set(sys.stdlib_module_names) | {"preflight", "ticket_backend"}
    found = _top_level_imports(os.path.join(SCRIPTS_DIR, "ticket.py"))
    assert found <= allowed, found - allowed


def test_ticket_backend_py_imports_only_stdlib():
    allowed = set(sys.stdlib_module_names)
    found = _top_level_imports(os.path.join(SCRIPTS_DIR, "ticket_backend.py"))
    assert found <= allowed, found - allowed


# --- AC23: Backend's exact shape, StubBackend calls no external process ----

def test_backend_exposes_exactly_the_four_methods():
    declared = {name for name, value in vars(tb.Backend).items()
                if callable(value) and not name.startswith("__")}
    assert declared == {"whoami", "read", "upsert_comment", "transition_once"}


def test_stub_backend_invokes_no_external_process(tmp_path, monkeypatch):
    # Point the CLI at a fake that always fails -- if StubBackend ever shells
    # out to it, every call below would come back a failing category instead
    # of "ok", which is what makes this an assertion and not a hope.
    monkeypatch.setenv(tb.CLI_ENV, fake_gh.cli_argv())
    monkeypatch.setenv("FAKE_GH_MODE", "fail")

    stub = tb.get("local-stub")
    assert stub.name == "local-stub"

    login, cat1 = stub.whoami(str(tmp_path))
    assert cat1 == "ok" and login

    value, cat2 = stub.read(str(tmp_path), "1")
    assert cat2 == "ok" and value["number"] == "1"

    url, cat3 = stub.upsert_comment(str(tmp_path), "1", "[cai track: x]", "body", "someone")
    assert cat3 == "ok" and url

    ok, cat4 = stub.transition_once(str(tmp_path), "1")
    assert ok is True and cat4 == "ok"


def test_stub_backend_never_calls_subprocess_run(tmp_path, monkeypatch):
    import subprocess

    def boom(*args, **kwargs):
        raise AssertionError("StubBackend must never invoke subprocess.run")

    monkeypatch.setattr(subprocess, "run", boom)
    stub = tb.get("local-stub")
    stub.whoami(str(tmp_path))
    stub.read(str(tmp_path), "1")
    stub.upsert_comment(str(tmp_path), "1", "[cai track: x]", "body", "someone")
    stub.transition_once(str(tmp_path), "1")


# --- read_config -------------------------------------------------------------

def test_read_config_missing_file_is_disabled_and_silent():
    result = ticket.read_config("does-not-exist")
    assert result == {"enabled": False, "backend": "", "problem": None}


def _write_cai_json(project_dir, content):
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "cai.json").write_text(content, encoding="utf-8")


def test_read_config_malformed_json_is_disabled_with_a_problem(tmp_path):
    _write_cai_json(tmp_path, "{not valid json")
    result = ticket.read_config(str(tmp_path))
    assert result["enabled"] is False
    assert result["backend"] == ""
    assert result["problem"]
    assert "not valid json" not in result["problem"]  # never the file's own content


def test_read_config_wrong_type_is_disabled_with_a_problem(tmp_path):
    _write_cai_json(tmp_path, json.dumps({"ticket": {"enabled": "yes", "backend": "github"}}))
    result = ticket.read_config(str(tmp_path))
    assert result["enabled"] is False
    assert result["problem"]


def test_read_config_missing_ticket_key_is_disabled_with_a_problem(tmp_path):
    _write_cai_json(tmp_path, json.dumps({"something_else": True}))
    result = ticket.read_config(str(tmp_path))
    assert result["enabled"] is False
    assert result["problem"]


def test_read_config_problem_never_contains_the_files_raw_content(tmp_path):
    secret = "sk-super-secret-token-marker"
    _write_cai_json(tmp_path, "{ this is garbage -- %s" % secret)
    result = ticket.read_config(str(tmp_path))
    assert result["problem"] is not None
    assert secret not in result["problem"]


def test_read_config_success_reports_enabled_and_backend(tmp_path):
    _write_cai_json(tmp_path, json.dumps({"ticket": {"enabled": True, "backend": "github"}}))
    result = ticket.read_config(str(tmp_path))
    assert result == {"enabled": True, "backend": "github", "problem": None}


# --- AC21: two projects' configs never see each other ----------------------

def test_ac21_two_projects_dont_affect_each_other(tmp_path, capsys):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    _write_cai_json(project_a, json.dumps({"ticket": {"enabled": True, "backend": "github"}}))
    project_b.mkdir()  # no .claude/cai.json at all -- disabled

    result_a = ticket.read_config(str(project_a))
    assert result_a["enabled"] is True

    captured_before = capsys.readouterr()
    result_b = ticket.read_config(str(project_b))
    captured_after = capsys.readouterr()
    assert result_b == {"enabled": False, "backend": "", "problem": None}
    # AC1: not enabled means not one character printed
    assert captured_after.out == "" and captured_after.err == ""
    assert captured_before.out == "" and captured_before.err == ""


# --- read_pointer / write_pointer -------------------------------------------

def test_read_pointer_missing_file_returns_none(tmp_path):
    assert ticket.read_pointer(str(tmp_path)) is None


def test_write_pointer_then_read_pointer_round_trips(tmp_path):
    pointer = {"backend": "github", "ref": "48", "login": "octocat",
               "projection": {"status": "ok", "at": "2026-08-31T00:00:00Z"}}
    ticket.write_pointer(str(tmp_path), pointer)
    assert ticket.read_pointer(str(tmp_path)) == pointer


def test_write_pointer_swallows_oserror_and_prints_one_line(capsys, tmp_path):
    unwritable_track_dir = str(tmp_path / "no-such-parent" / "track")
    ticket.write_pointer(unwritable_track_dir, {"backend": "github", "ref": "1",
                                                 "login": None, "projection": None})
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert out.strip() != ""


def test_read_pointer_malformed_json_returns_none(tmp_path):
    (tmp_path / ticket.POINTER_NAME).write_text("{not json", encoding="utf-8")
    assert ticket.read_pointer(str(tmp_path)) is None
