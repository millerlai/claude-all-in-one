"""codex_review.py: run `codex exec review` only inside a read-only sandbox.

A fake `codex` stands in for the real one. Its output follows what unit 0
measured with codex-cli 0.164.0 (.cai/track/.../unit0-c17.md): the banner and
transcript on stderr with a `sandbox:` line, only the final review on stdout.
The fake is a Windows `codex.bat` or, on POSIX, a file named `codex` with a
`#!/bin/sh` line and mode 0o755 (#219); both hand over to one Python script
whose behaviour FAKE_MODE picks, so the assertions are the same on both.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import codex_review as cr
import local_run
from test_local_run_tree import _pid_alive, _until

FAKE_SCRIPT = '''\
import json, os, sys, time

def banner(mode):
    sys.stderr.write("OpenAI Codex v0.164.0\\n--------\\nworkdir: x\\nmodel: m\\n"
                     "provider: openai\\napproval: never\\nsandbox: " + mode + "\\n"
                     "reasoning effort: high\\n--------\\n")
    sys.stderr.flush()

def hang():
    time.sleep(60)

mode = os.environ["FAKE_MODE"]
if os.environ.get("FAKE_PIDFILE"):  # before any output: the test waits on this file
    with open(os.environ["FAKE_PIDFILE"], "w") as fh:
        fh.write(str(os.getpid()))
if mode == "crash":
    sys.stderr.write("error: unexpected argument\\n")
    sys.exit(1)
elif mode == "nobanner":
    hang()
elif mode == "nobanner0":
    sys.stdout.write("a review\\n")
elif mode == "workspace":
    banner("workspace-write")
    hang()
elif mode == "workspace0":  # a finished, non-empty review from the wrong sandbox
    banner("workspace-write")
    sys.stdout.write("a review\\n")
elif mode == "hang":
    banner("read-only")
    hang()
elif mode == "empty":
    banner("read-only")
elif mode == "ansi-banner":
    sys.stderr.write("\\x1b[2msandbox: read-only\\x1b[0m\\n")
    sys.stderr.flush()
    sys.stdout.write("colour ok\\n")
elif mode == "env":
    banner("read-only")
    sys.stdout.write(json.dumps({
        "argv": sys.argv[1:], "codex_home": os.environ.get("CODEX_HOME"),
        "guard": os.environ.get("CAI_PLATFORM_REVIEW"), "has_path": bool(os.environ.get("PATH")),
        "extra": os.environ.get("EXTRA_FROM_PARENT")}))
else:
    banner("read-only")
    # Bytes: the review is UTF-8 whatever the console's code page, and no \\r\\n.
    sys.stdout.buffer.write("one finding \\u2014 \\u65b0\\u589e\\u7684\\u8def\\u5f91\\n\\nReview comment:\\n- [P2] t\\n".encode("utf-8"))
'''


def make_fake_codex(directory):
    """The fake `codex` and the argv that runs it. Returns its path."""
    directory.mkdir(exist_ok=True)
    script = directory / "fake_codex.py"
    script.write_text(FAKE_SCRIPT, encoding="utf-8")
    if os.name == "nt":
        path = directory / "codex.bat"
        path.write_text('@echo off\r\n"%s" "%s" %%*\r\n' % (sys.executable, script))
    else:
        path = directory / "codex"
        path.write_text('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, script))
        path.chmod(0o755)
    return path


def call_for(fake, home="/home/me/.codex"):
    return {"format": 1, "platform": "codex", "status": "run", "reason": None,
            "base": "main", "lines": 3, "docs_only": False, "notes": [],
            "argv": [str(fake), "exec", "review", "--base", "main", "-c", "sandbox_mode=read-only"],
            "env": {"CODEX_HOME": home},
            "call": "codex exec review --base main -c sandbox_mode=read-only"}


@pytest.fixture
def fake(tmp_path):
    return make_fake_codex(tmp_path / "bin")


@pytest.fixture
def top(tmp_path):
    d = tmp_path / "top"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv(cr.GUARD_ENV, raising=False)
    monkeypatch.setenv("FAKE_MODE", "ok")


def go(fake, top, mode="ok", **kw):
    kw.setdefault("environ", {**os.environ, "FAKE_MODE": mode})
    return cr.run(call_for(fake), str(top), **kw)


def capture_files(top):
    d = Path(top) / ".cai" / "platform-review"
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


# --- run: success ---------------------------------------------------------

def test_read_only_runs_to_the_end(fake, top):
    r = go(fake, top)
    assert r["status"] == "ran" and r["reason"] is None
    assert r["sandbox"] == "read-only"
    assert r["review"].startswith("one finding — 新增")
    assert r["left_running"] == [] and isinstance(r["seconds"], int)
    assert r["call"] == "codex exec review --base main -c sandbox_mode=read-only"
    assert r["format"] == 1


def test_capture_files_are_deleted(fake, top):
    go(fake, top)
    assert capture_files(top) == []
    go(fake, top, "crash")
    assert capture_files(top) == []


def test_stderr_is_never_in_the_result(fake, top):
    r = go(fake, top)
    assert "OpenAI Codex" not in json.dumps(r)


@pytest.mark.parametrize("mode,leak", [("crash", "unexpected argument"),
                                       ("workspace", "OpenAI Codex"),
                                       ("empty", "OpenAI Codex")])
def test_stderr_is_never_in_a_fallback_result_either(fake, top, mode, leak):
    r = go(fake, top, mode)
    assert r["status"] == "fallback"
    assert leak not in json.dumps(r)


def test_child_gets_inherited_env_plus_keys_and_guard(fake, top, monkeypatch):
    monkeypatch.setenv("EXTRA_FROM_PARENT", "kept")
    r = go(fake, top, "env", environ={**os.environ, "FAKE_MODE": "env"})
    seen = json.loads(r["review"])
    assert seen["codex_home"] == "/home/me/.codex"
    assert seen["guard"] == "1"
    assert seen["has_path"] is True       # the fake `codex` could start a Python at all
    assert seen["extra"] == "kept"
    assert seen["argv"][:2] == ["exec", "review"] and "sandbox_mode=read-only" in seen["argv"]


def test_ansi_around_the_sandbox_word_is_stripped(fake, top):
    r = go(fake, top, "ansi-banner")
    assert r["status"] == "ran" and r["sandbox"] == "read-only"


# --- run: fallbacks -------------------------------------------------------

def test_workspace_write_is_stopped(fake, top):
    r = go(fake, top, "workspace")
    assert r["status"] == "fallback" and r["reason"] == "sandbox was workspace-write"
    assert r["sandbox"] == "workspace-write" and r["review"] is None
    assert r["seconds"] < 30  # stopped, not waited out
    assert r["left_running"] == []


def test_no_banner_is_stopped_after_the_banner_time(fake, top):
    r = go(fake, top, "nobanner", banner_s=2)
    assert r["status"] == "fallback" and r["reason"] == "no sandbox line from codex"
    assert r["sandbox"] is None and r["seconds"] < 30


def test_exit_without_banner_reports_the_exit_code_first(fake, top):
    r = go(fake, top, "crash")
    assert r["status"] == "fallback" and r["reason"] == "codex exec review exited 1"


def test_exit_zero_without_banner(fake, top):
    r = go(fake, top, "nobanner0")
    assert r["status"] == "fallback" and r["reason"] == "no sandbox line from codex"


def test_exit_zero_under_a_wider_sandbox_is_not_a_review(fake, top, monkeypatch):
    # The child exits before the loop's second look, so the exit branch decides,
    # not the "still running" one; a slow first poll makes that certain.
    monkeypatch.setattr(cr, "POLL_SECONDS", 1.5)
    r = go(fake, top, "workspace0")
    assert r["status"] == "fallback" and r["reason"] == "sandbox was workspace-write"
    assert r["review"] is None


def test_timeout(fake, top):
    r = go(fake, top, "hang", timeout_s=4)
    assert r["status"] == "fallback" and r["reason"] == "timed out after 4 s"
    assert r["sandbox"] == "read-only" and r["seconds"] < 30


@pytest.mark.parametrize("mode,kw", [("workspace", {}), ("hang", {"timeout_s": 3})])
def test_a_stopped_review_leaves_no_process_behind(fake, top, tmp_path, mode, kw):
    pidfile = tmp_path / "pid.txt"
    environ = {**os.environ, "FAKE_MODE": mode, "FAKE_PIDFILE": str(pidfile)}
    r = cr.run(call_for(fake), str(top), environ=environ, **kw)
    assert r["status"] == "fallback" and r["left_running"] == []
    pid = int(pidfile.read_text())
    assert _until(lambda: not _pid_alive(pid)), "the fake codex is still alive"


def test_an_exception_in_the_wait_loop_still_stops_the_child(fake, top, tmp_path, monkeypatch):
    pidfile = tmp_path / "pid.txt"
    real = cr._sandbox

    def boom(text):
        if not pidfile.exists():  # let the child start before failing
            return real(text)
        raise RuntimeError("wait loop failed")
    monkeypatch.setattr(cr, "_sandbox", boom)
    environ = {**os.environ, "FAKE_MODE": "hang", "FAKE_PIDFILE": str(pidfile)}
    live_before = list(local_run._LIVE)
    with pytest.raises(RuntimeError, match="wait loop failed"):
        cr.run(call_for(fake), str(top), environ=environ)
    assert _until(lambda: not _pid_alive(int(pidfile.read_text()))), "the fake codex is still alive"
    assert capture_files(top) == []
    assert local_run._LIVE == live_before


def test_empty_stdout(fake, top):
    r = go(fake, top, "empty")
    assert r["status"] == "fallback" and r["reason"] == "no review text"


def test_guard_env_already_set_starts_nothing(fake, top):
    r = cr.run(call_for(fake), str(top), environ={**os.environ, cr.GUARD_ENV: "1"})
    assert r["status"] == "fallback" and r["reason"] == "already inside a platform review"
    assert not (top / ".cai").exists()  # nothing was started or written


def test_decide_fallback_reason_is_kept(top):
    call = {"status": "fallback", "reason": "codex not found in a trusted PATH entry",
            "call": None, "notes": ["n"]}
    r = cr.run(call, str(top))
    assert r["status"] == "fallback" and r["reason"] == call["reason"]
    assert r["notes"] == ["n"] and r["call"] is None


def test_safety_net_failure(fake, top, monkeypatch):
    def boom():
        raise OSError("no job")
    monkeypatch.setattr(local_run, "install_safety_net", boom)
    r = go(fake, top)
    assert r["status"] == "fallback" and r["reason"] == "cannot guarantee the review's processes stop"


def test_codex_that_cannot_start(top, tmp_path):
    r = cr.run(call_for(tmp_path / "missing" / "codex"), str(top))
    assert r["status"] == "fallback" and r["reason"] == "codex could not be started"


def test_survivor_is_reported(fake, top, monkeypatch):
    real = local_run.stop_tree
    monkeypatch.setattr(local_run, "stop_tree", lambda tree, **kw: real(tree, **kw) + [4242])
    r = go(fake, top, "workspace")
    assert r["left_running"] == [4242]


def test_delete_failure_is_swallowed_into_notes(fake, top, monkeypatch):
    def refuse(path):
        raise PermissionError(path)
    monkeypatch.setattr(cr.os, "remove", refuse)
    r = go(fake, top)
    assert r["status"] == "ran"
    assert sorted(r["notes"]) == ["could not delete stderr.txt", "could not delete stdout.txt"]


# --- main -----------------------------------------------------------------

def _git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "a.py").write_text("x = 1\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "init")
    (r / "a.py").write_text("x = 1\ny = 2\n")  # tracked, uncommitted
    return r


@pytest.fixture
def codex_on_path(fake, monkeypatch):
    monkeypatch.setenv("PATH", str(fake.parent) + os.pathsep + os.environ["PATH"])


def test_main_ran_writes_the_platform_review_file(repo, codex_on_path, tmp_path, capsys):
    out = tmp_path / "ev" / "platform-review.md"
    code = cr.main(["--base", "main", "--out", str(out), "--project-dir", str(repo)])
    printed = json.loads(capsys.readouterr().out)
    assert code == cr.EXIT_RAN and printed["status"] == "ran"
    head, _, body = out.read_bytes().decode("utf-8").partition("\n---\n")
    assert head == ("# platform review\ncall: codex exec review --base main "
                    "-c sandbox_mode=read-only\nstatus: ran\nreading: pending\nreason: -")
    assert body == printed["review"]


def test_main_without_out_writes_no_file(repo, codex_on_path, capsys):
    assert cr.main(["--base", "main", "--project-dir", str(repo)]) == cr.EXIT_RAN
    capsys.readouterr()
    assert not list(repo.rglob("platform-review.md"))


def test_main_fallback_exit_3_writes_no_file(repo, codex_on_path, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FAKE_MODE", "crash")
    out = tmp_path / "pr.md"
    code = cr.main(["--base", "main", "--out", str(out), "--project-dir", str(repo)])
    printed = json.loads(capsys.readouterr().out)
    assert code == cr.EXIT_FALLBACK and printed["reason"] == "codex exec review exited 1"
    assert not out.exists()


def test_main_codex_missing_is_a_fallback(repo, monkeypatch, capsys):
    real = cr.rrc.tool_path.resolve

    def resolve(name, cwd=None):
        if name == "codex":
            raise FileNotFoundError(name)
        return real(name, cwd=cwd)
    monkeypatch.setattr(cr.rrc.tool_path, "resolve", resolve)
    code = cr.main(["--base", "main", "--project-dir", str(repo)])
    assert code == cr.EXIT_FALLBACK
    assert "codex not found" in json.loads(capsys.readouterr().out)["reason"]


def test_main_empty_diff_is_invalid(repo, codex_on_path, capsys):
    _git(repo, "checkout", "-q", "--", "a.py")
    code = cr.main(["--base", "main", "--project-dir", str(repo)])
    printed = json.loads(capsys.readouterr().out)
    assert code == cr.EXIT_INVALID and "empty diff" in printed["reason"]


def test_main_bad_project_dir_is_invalid(tmp_path, capsys):
    code = cr.main(["--base", "main", "--project-dir", str(tmp_path / "nope")])
    assert code == cr.EXIT_INVALID
    assert json.loads(capsys.readouterr().out)["status"] == "fallback"


def test_main_survivor_writes_no_file(repo, codex_on_path, monkeypatch, tmp_path, capsys):
    # Exit 6 is a fallback to the caller, which writes the fallback file itself.
    real = local_run.stop_tree
    monkeypatch.setattr(local_run, "stop_tree", lambda tree, **kw: real(tree, **kw) + [4242])
    out = tmp_path / "pr.md"
    code = cr.main(["--base", "main", "--out", str(out), "--project-dir", str(repo)])
    capsys.readouterr()
    assert code == cr.EXIT_LEFT_RUNNING
    assert not out.exists()


def test_main_survivor_exits_6_and_still_prints(repo, codex_on_path, monkeypatch, capsys):
    real = local_run.stop_tree
    monkeypatch.setattr(local_run, "stop_tree", lambda tree, **kw: real(tree, **kw) + [4242])
    code = cr.main(["--base", "main", "--project-dir", str(repo)])
    assert code == cr.EXIT_LEFT_RUNNING
    assert json.loads(capsys.readouterr().out)["left_running"] == [4242]
