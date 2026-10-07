"""Unit 5: local_run.run / main against real processes (AC3 a-d, AC8 a-b).

The app under test is tests/fake_app.py (answers 200 "ok" to any GET and
spawns a grandchild) or a few inline stand-ins. Ports always come from
local_run.free_port(). Every wait is bounded and every test kills what it
started in a fixture teardown, so a failing run leaves nothing behind.
"""
import hashlib
import http.client
import http.server
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import types
import urllib.error

import pytest

import local_run

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE_APP = os.path.join(HERE, "fake_app.py")
SCRIPT = local_run.__file__
WIN = sys.platform == "win32"
WAIT = 30

BIG_APP = """
import http.server, sys
BODY = b"x" * 5000 + b"NEEDLE" + b"y" * 5000
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)
    def log_message(self, *a):
        pass
http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
"""


# ---- helpers ---------------------------------------------------------------

def _pid_alive(pid):
    if WIN:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = wintypes.DWORD()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # an unreaped zombie is dead for our purposes
        with open("/proc/%d/stat" % pid) as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return True


def _until(pred, timeout=WAIT):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.1)
    return pred()


def _read_int(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _kill_pid(pid):
    if pid and _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM if WIN else signal.SIGKILL)
        except OSError:
            pass


@pytest.fixture
def env(tmp_path, monkeypatch):
    """track dir, project dir, pid dir; kills anything the test left running."""
    for name in ("BASH_DEFAULT_TIMEOUT_MS", "BASH_MAX_TIMEOUT_MS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(local_run, "READY_POLL", 0.1)
    track, proj, pids = tmp_path / "track", tmp_path / "proj", tmp_path / "pids"
    for d in (track, proj, pids):
        d.mkdir()
    yield {"track": str(track), "proj": str(proj), "pids": str(pids), "tmp": tmp_path}
    for key in ("app", "grandchild", "e2e"):
        _kill_pid(_read_int(os.path.join(str(pids), key + ".txt")))
    local_run.stop_all()


def _write_intake(track, rows):
    """rows: [(ac, level, check)]; every AC also gets a body line, as the parser requires."""
    body = "\n".join("- %s: something" % ac for ac, _, _ in rows)
    table = "\n".join("| %s | %s | %s |" % r for r in rows)
    text = ("# Intake\n\n## Acceptance criteria\n%s\n\n## Verification levels\n"
            "| AC | level | check |\n|---|---|---|\n%s\n" % (body, table))
    with open(os.path.join(track, "intake.md"), "w", encoding="utf-8") as f:
        f.write(text)


def _write_run(proj, decl):
    os.makedirs(os.path.join(proj, ".claude"), exist_ok=True)
    with open(os.path.join(proj, ".claude", "cai.json"), "w", encoding="utf-8") as f:
        json.dump({"run": decl}, f)


def _fake_app_decl(env, e2e=None):
    decl = {"start": [sys.executable, FAKE_APP, "--port", "{port}", "--pid-dir", env["pids"]],
            "ready": "http://127.0.0.1:{port}/"}
    if e2e:
        decl["e2e"] = e2e
    return decl


def _go(env, rows, decl, stage="verify", unit=None, only=None):
    _write_intake(env["track"], rows)
    if decl is not None:
        _write_run(env["proj"], decl)
    return local_run.run(env["track"], env["proj"], stage, unit, only)


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _record(env, out):
    last = out.strip().splitlines()[-1]
    assert last.startswith("run record: ")
    path = last[len("run record: "):]
    with open(path, encoding="utf-8") as f:
        return json.load(f), os.path.dirname(path)


def _no_evidence(env):
    return not os.path.exists(os.path.join(env["track"], "evidence"))


def _marker_decl(env, name="marker.txt"):
    """A start that would leave a file behind if it were ever started."""
    marker = os.path.join(env["tmp"], name)
    code = "open(%r, 'w').write('x')" % marker
    return marker, code


# ---- AC3 (a): stdout lines, evidence file, sha256 --------------------------

def test_ac3a_pass_lines_evidence_and_sha(env, capsys):
    code, d = _go(env, [("AC3", "local-run", 'GET /health 200 "ok"')], _fake_app_decl(env))
    out = capsys.readouterr().out
    assert code == local_run.EXIT_PASS, out
    lines = out.strip().splitlines()
    m = re.fullmatch(r"AC3 PASS (evidence/verify/\d{8}T\d{6}Z(?:-\d+)?/AC3\.txt) "
                     r"sha256=([0-9a-f]{64})", lines[0])
    assert m, lines[0]
    evidence = os.path.join(env["track"], *m.group(1).split("/"))
    assert _sha(evidence) == m.group(2)
    with open(evidence, "rb") as f:
        text = f.read()
    assert text.startswith(b"GET http://127.0.0.1:") and b"/health" in text.split(b"\n")[0]
    assert b"200 OK" in text and text.endswith(b"\n\nok")
    rec, run_dir = _record(env, out)
    assert lines[-1] == "run record: " + os.path.join(run_dir, "run.json")
    assert rec["format"] == 1 and rec["stage"] == "verify" and rec["unit"] is None
    assert rec["platform"] == sys.platform
    assert rec["budget"] == {"total": 540, "ready": 120, "check": 120}
    s = rec["start"]
    assert s["outcome"] == "ready" and s["log"] == "start.log"
    assert s["ready"] == "http://127.0.0.1:%d/" % s["port"]
    assert s["log_sha256"] == _sha(os.path.join(run_dir, "start.log"))
    assert rec["survivors"] == []
    c = rec["checks"][0]
    assert (c["ac"], c["check"], c["outcome"], c["reason"], c["evidence"]) == \
        ("AC3", 'GET /health 200 "ok"', "PASS", None, "AC3.txt")
    assert c["sha256"] == m.group(2) and c["bytes_seen"] == 2 and c["truncated"] is False
    assert d["checks"] == rec["checks"]


# ---- AC3 (b): a failing check ----------------------------------------------

@pytest.mark.parametrize("check", ["GET /x 201", 'GET /x 200 "nope"'])
def test_ac3b_failing_check_fails(env, capsys, check):
    code, _ = _go(env, [("AC3", "local-run", check)], _fake_app_decl(env))
    out = capsys.readouterr().out
    assert code == local_run.EXIT_FAILED
    assert "AC3 FAIL" in out and "AC3 PASS" not in out
    rec, _ = _record(env, out)
    assert rec["checks"][0]["outcome"] == "FAIL" and rec["checks"][0]["reason"]


def test_non_ascii_check_path_is_requested_not_a_crash(env, capsys):
    # verify_plan.parse_check accepts any path that starts with "/", so a Chinese
    # intake can plan this check; the runner must send it (percent-encoded), not
    # die with UnicodeEncodeError before run.json is written.
    code, _ = _go(env, [("AC3", "local-run", "GET /健康 200")], _fake_app_decl(env))
    out = capsys.readouterr().out
    assert code == local_run.EXIT_PASS, out
    rec, _ = _record(env, out)
    assert rec["checks"][0]["outcome"] == "PASS"


def test_the_declared_http_method_is_the_one_sent(env, capsys):
    # fake_app answers GET with 200 and has no do_POST, so the stdlib handler
    # answers a POST with 501: "POST / 501" passes only when POST was really sent.
    code, _ = _go(env, [("AC3", "local-run", "POST / 501")], _fake_app_decl(env))
    out = capsys.readouterr().out
    assert code == local_run.EXIT_PASS, out
    assert "AC3 PASS" in out


def test_http_check_that_never_answers_is_a_timeout(tmp_path):
    # AC3: a check that hangs is TIMEOUT with evidence, not a FAIL and not a hang.
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)  # accepts at the OS level and never replies
    try:
        parsed = {"method": "GET", "path": "/", "status": 200, "text": None}
        evidence = tmp_path / "AC3.txt"
        res = local_run._do_http("http://127.0.0.1:%d/" % server.getsockname()[1],
                                 parsed, str(evidence), 1)
    finally:
        server.close()
    assert res["outcome"] == "TIMEOUT" and "timeout" in res["reason"]
    assert evidence.is_file()


def test_connect_failure_is_fail_with_evidence(env, capsys, monkeypatch):
    # The app answers readiness, then the check hits a port nothing listens on.
    real = local_run._http_url
    dead = local_run.free_port()
    monkeypatch.setattr(local_run, "_http_url", lambda base, path: real(
        "http://127.0.0.1:%d" % dead, path))
    code, _ = _go(env, [("AC3", "local-run", "GET / 200")], _fake_app_decl(env))
    out = capsys.readouterr().out
    assert code == local_run.EXIT_FAILED
    rec, run_dir = _record(env, out)
    assert rec["checks"][0]["outcome"] == "FAIL"
    assert os.path.isfile(os.path.join(run_dir, "AC3.txt"))


# ---- AC3 (c): readiness never answers --------------------------------------

def test_ac3c_ready_timeout_never_passes(env, capsys, monkeypatch):
    monkeypatch.setattr(local_run, "READY_WAIT", 1.5)
    decl = {"start": [sys.executable, "-c", "import time; time.sleep(60)", "{port}"],
            "ready": "http://127.0.0.1:{port}/"}
    code, _ = _go(env, [("AC3", "local-run", "GET / 200"), ("AC4", "local-run", "GET /a 200")],
                  decl)
    out = capsys.readouterr().out
    assert code == local_run.EXIT_FAILED
    assert "PASS" not in out
    rec, _ = _record(env, out)
    assert rec["start"]["outcome"] == "timeout"
    assert [c["outcome"] for c in rec["checks"]] == ["TIMEOUT", "TIMEOUT"]
    assert local_run.survivors() == []


# ---- AC3 (d): the whole tree is gone, the port is free ---------------------

def test_ac3d_tree_gone_and_port_rebindable(env, capsys):
    code, _ = _go(env, [("AC3", "local-run", "GET / 200")], _fake_app_decl(env))
    out = capsys.readouterr().out
    assert code == local_run.EXIT_PASS, out
    rec, _ = _record(env, out)
    app = _read_int(os.path.join(env["pids"], "app.txt"))
    grandchild = _read_int(os.path.join(env["pids"], "grandchild.txt"))
    assert app and grandchild
    assert _until(lambda: not _pid_alive(app)), "fake app still alive"
    assert _until(lambda: not _pid_alive(grandchild)), "grandchild still alive"
    srv = http.server.HTTPServer(("127.0.0.1", rec["start"]["port"]),
                                 http.server.BaseHTTPRequestHandler)
    srv.server_close()


# ---- AC8 (a)(b): nothing runnable ------------------------------------------

def test_ac8a_undeclared_start_starts_nothing(env, capsys):
    code, d = _go(env, [("AC3", "local-run", "GET / 200")], None)
    out = capsys.readouterr().out
    assert code == local_run.EXIT_NOTHING_RUN
    assert "no-start-declaration" in out
    assert _no_evidence(env)
    assert not os.listdir(env["pids"])


def test_ac8b_undeclared_e2e_name_is_not_run(env, capsys):
    code, _ = _go(env, [("AC3", "local-run", "GET / 200"), ("AC4", "local-run", "e2e nope")],
                  _fake_app_decl(env))
    out = capsys.readouterr().out
    assert code == local_run.EXIT_PASS, out
    rec, _ = _record(env, out)
    assert [c["ac"] for c in rec["checks"]] == ["AC3"]


def test_ac8b_only_undeclared_e2e_runs_nothing(env, capsys):
    code, _ = _go(env, [("AC4", "local-run", "e2e nope")], _fake_app_decl(env))
    out = capsys.readouterr().out
    assert code == local_run.EXIT_NOTHING_RUN
    assert "e2e" in out or "no-runnable-ac" in out
    assert _no_evidence(env) and not os.listdir(env["pids"])


def test_no_local_run_ac_runs_nothing(env, capsys):
    code, _ = _go(env, [("AC1", "test", "pytest")], _fake_app_decl(env))
    assert code == local_run.EXIT_NOTHING_RUN
    assert _no_evidence(env)


def test_invalid_intake_is_exit_5(env, capsys):
    _write_intake(env["track"], [("AC3", "local-run", "GET / 200")])
    path = os.path.join(env["track"], "intake.md")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    with open(path, "w", encoding="utf-8") as f:  # an AC in the body with no table row
        f.write(text.replace("- AC3: something\n", "- AC3: something\n- AC9: no row\n"))
    code, _ =local_run.run(env["track"], env["proj"], "verify", None, None)
    cap = capsys.readouterr()
    assert code == local_run.EXIT_INVALID
    assert "AC9" in cap.out + cap.err
    assert _no_evidence(env)


# ---- --ac and stage layout -------------------------------------------------

def test_only_names_a_non_local_run_id(env, capsys):
    marker, code = _marker_decl(env)
    decl = {"start": [sys.executable, "-c", code, "{port}"],
            "ready": "http://127.0.0.1:{port}/"}
    rows = [("AC3", "local-run", "GET / 200"), ("AC4", "test", "pytest")]
    for only in (["AC4"], ["AC3", "AC9"]):
        code_, _ = _go(env, rows, decl, only=only)
        cap = capsys.readouterr()
        assert code_ == local_run.EXIT_INVALID
        assert only[-1] in cap.out + cap.err
    assert not os.path.exists(marker) and _no_evidence(env)


def test_only_selects_a_subset(env, capsys):
    rows = [("AC3", "local-run", "GET / 200"), ("AC4", "local-run", "GET /b 200")]
    code, _ = _go(env, rows, _fake_app_decl(env), only=["AC4"])
    rec, _ = _record(env, capsys.readouterr().out)
    assert code == 0 and [c["ac"] for c in rec["checks"]] == ["AC4"]


def test_build_stage_layout(env, capsys):
    code, _ = _go(env, [("AC3", "local-run", "GET / 200")], _fake_app_decl(env),
                  stage="build", unit=3)
    out = capsys.readouterr().out
    assert code == 0, out
    assert re.match(r"AC3 PASS evidence/build/unit-3/\d{8}T\d{6}Z/AC3\.txt sha256=", out)
    rec, _ = _record(env, out)
    assert rec["stage"] == "build" and rec["unit"] == 3


def test_build_stage_needs_a_unit(env, capsys):
    code, _ = _go(env, [("AC3", "local-run", "GET / 200")], _fake_app_decl(env), stage="build")
    capsys.readouterr()
    assert code == local_run.EXIT_INVALID and _no_evidence(env)


def test_same_second_dirs_get_a_suffix(env, capsys, monkeypatch):
    monkeypatch.setattr(local_run, "_utc_stamp", lambda: "20261006T101500Z")
    rows = [("AC3", "local-run", "GET / 200")]
    for _ in range(3):
        assert _go(env, rows, _fake_app_decl(env))[0] == 0
    capsys.readouterr()
    base = os.path.join(env["track"], "evidence", "verify")
    assert sorted(os.listdir(base)) == ["20261006T101500Z", "20261006T101500Z-2",
                                        "20261006T101500Z-3"]


# ---- start variants --------------------------------------------------------

def test_start_exited_before_ready(env, capsys):
    decl = {"start": [sys.executable, "-c", "import sys; sys.exit(7)", "{port}"],
            "ready": "http://127.0.0.1:{port}/"}
    code, _ = _go(env, [("AC3", "local-run", "GET / 200")], decl)
    out = capsys.readouterr().out
    assert code == local_run.EXIT_FAILED and "PASS" not in out
    rec, _ = _record(env, out)
    c = rec["checks"][0]
    assert c["outcome"] == "FAIL" and c["reason"].startswith("start-exited") and "7" in c["reason"]
    assert rec["start"]["outcome"] == "exited"


def test_fixed_port_in_use_starts_nothing(env, capsys):
    marker, code = _marker_decl(env)
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        decl = {"start": [sys.executable, "-c", code], "ready": "http://127.0.0.1:%d/" % port}
        rc, _ = _go(env, [("AC3", "local-run", "GET / 200")], decl)
    out = capsys.readouterr().out
    assert rc == local_run.EXIT_NOTHING_RUN
    assert not os.path.exists(marker)
    rec, _ = _record(env, out)
    assert rec["start"]["outcome"] == "port-in-use" and rec["start"]["port"] == port
    assert rec["checks"][0]["outcome"] == "NOT-RUN" and rec["checks"][0]["reason"] == "port-in-use"


def test_fixed_port_free_runs(env, capsys):
    port = local_run.free_port()
    decl = {"start": [sys.executable, FAKE_APP, "--port", str(port), "--pid-dir", env["pids"]],
            "ready": "http://127.0.0.1:%d/" % port}
    code, _ = _go(env, [("AC3", "local-run", "GET / 200")], decl)
    out = capsys.readouterr().out
    assert code == 0, out
    assert _record(env, out)[0]["start"]["port"] == port


# ---- truncation ------------------------------------------------------------

def _big_decl(env):
    script = os.path.join(env["tmp"], "big_app.py")
    with open(script, "w") as f:
        f.write(BIG_APP)
    return {"start": [sys.executable, script, "{port}"], "ready": "http://127.0.0.1:{port}/"}


@pytest.mark.parametrize("chunk", [local_run.CHUNK, 7])
def test_truncation_keeps_head_and_tail_and_verdict(env, capsys, monkeypatch, chunk):
    monkeypatch.setattr(local_run, "EVIDENCE_LIMIT", 1000)
    monkeypatch.setattr(local_run, "CHUNK", chunk)
    code, _ = _go(env, [("AC3", "local-run", 'GET / 200 "NEEDLE"'),
                        ("AC4", "local-run", 'GET / 200 "ABSENT"')], _big_decl(env))
    out = capsys.readouterr().out
    rec, run_dir = _record(env, out)
    ac3, ac4 = rec["checks"]
    assert ac3["outcome"] == "PASS" and ac3["truncated"] is True and ac3["bytes_seen"] == 10006
    assert ac4["outcome"] == "FAIL"  # absent text is still absent after truncation
    with open(os.path.join(run_dir, "AC3.txt"), "rb") as f:
        body = f.read().split(b"\n\n", 1)[1]
    assert body.startswith(b"x" * 500 + b"\n[... 9006 bytes cut ...]\n") and body.endswith(b"y" * 500)
    assert len(body) == 500 + len("\n[... 9006 bytes cut ...]\n") + 500


def test_capture_matches_across_chunk_edges_and_cuts_exactly():
    cap = local_run._Capture(b"NEEDLE")
    data = b"a" * 50 + b"NEEDLE" + b"b" * 50
    for i in range(0, len(data), 5):
        cap.feed(data[i:i + 5])
    assert cap.found and cap.total == 106
    # exactly at the limit: nothing cut; one byte over: one byte cut
    at = local_run._Capture()
    at.feed(b"z" * local_run.EVIDENCE_LIMIT)
    assert at.render() == (b"z" * local_run.EVIDENCE_LIMIT, False)
    over = local_run._Capture()
    over.feed(b"z" * (local_run.EVIDENCE_LIMIT + 1))
    data, truncated = over.render()
    assert truncated and b"[... 1 bytes cut ...]" in data
    assert len(data) == local_run.EVIDENCE_LIMIT + len(b"\n[... 1 bytes cut ...]\n")


def test_start_log_is_capped(env, capsys, monkeypatch):
    monkeypatch.setattr(local_run, "EVIDENCE_LIMIT", 1000)
    code_ = "import sys,time; sys.stdout.write('L' * 5000); sys.stdout.flush(); time.sleep(60)"
    decl = {"start": [sys.executable, "-c", code_, "{port}"],
            "ready": "http://127.0.0.1:{port}/"}
    monkeypatch.setattr(local_run, "READY_WAIT", 1.5)
    _go(env, [("AC3", "local-run", "GET / 200")], decl)
    rec, run_dir = _record(env, capsys.readouterr().out)
    with open(os.path.join(run_dir, "start.log"), "rb") as f:
        data = f.read()
    assert b"bytes cut" in data and len(data) < 1100
    assert rec["start"]["log_sha256"] == hashlib.sha256(data).hexdigest()


# ---- e2e -------------------------------------------------------------------

def test_e2e_pass_fail_timeout(env, capsys, monkeypatch):
    monkeypatch.setattr(local_run, "CHECK_WAIT", 2)
    slow_pid = os.path.join(env["pids"], "e2e.txt")
    e2e = {"ok": [sys.executable, "-c", "import sys; print('hi', sys.argv[1])", "{port}"],
           "bad": [sys.executable, "-c", "import sys; print('boom'); sys.exit(2)"],
           "slow": [sys.executable, "-c",
                    "import os, time; open(%r, 'w').write(str(os.getpid())); time.sleep(60)"
                    % slow_pid]}
    rows = [("AC3", "local-run", "e2e ok"), ("AC4", "local-run", "e2e bad"),
            ("AC5", "local-run", "e2e slow"), ("AC6", "local-run", "GET / 200")]
    code, _ = _go(env, rows, _fake_app_decl(env, e2e))
    out = capsys.readouterr().out
    assert code == local_run.EXIT_FAILED, out
    rec, run_dir = _record(env, out)
    outcomes = {c["ac"]: c["outcome"] for c in rec["checks"]}
    assert outcomes == {"AC3": "PASS", "AC4": "FAIL", "AC5": "TIMEOUT", "AC6": "PASS"}
    with open(os.path.join(run_dir, "AC3.txt"), encoding="utf-8") as f:
        text = f.read()
    port = rec["start"]["port"]
    assert "exit code: 0" in text and "hi %d" % port in text and "seconds:" in text
    assert "argv: " in text.splitlines()[0]
    assert "exit code: 2" in open(os.path.join(run_dir, "AC4.txt"), encoding="utf-8").read()
    # the slow check's tree was ended, and ending it did not take the app down
    # (AC6 still got its 200 afterwards)
    assert _until(lambda: _read_int(slow_pid) is not None)
    assert _until(lambda: not _pid_alive(_read_int(slow_pid)))


# ---- budget ----------------------------------------------------------------

def test_total_budget_follows_the_bash_cap(monkeypatch):
    for name in ("BASH_DEFAULT_TIMEOUT_MS", "BASH_MAX_TIMEOUT_MS"):
        monkeypatch.delenv(name, raising=False)
    assert local_run.total_budget({}) == 540                       # 600000 assumed
    assert local_run.total_budget({"BASH_MAX_TIMEOUT_MS": "300000"}) == 240
    assert local_run.total_budget({"BASH_MAX_TIMEOUT_MS": "3600000"}) == 540
    # the larger of the two is the cap
    assert local_run.total_budget({"BASH_DEFAULT_TIMEOUT_MS": "300000",
                                   "BASH_MAX_TIMEOUT_MS": "200000"}) == 240
    assert local_run.total_budget({"BASH_DEFAULT_TIMEOUT_MS": "120000"}) == 60
    assert local_run.total_budget({"BASH_MAX_TIMEOUT_MS": "30000"}) == 0
    assert local_run.total_budget({"BASH_MAX_TIMEOUT_MS": "junk"}) == 540


def test_budget_recorded_from_env(env, capsys, monkeypatch):
    monkeypatch.setenv("BASH_MAX_TIMEOUT_MS", "300000")
    _go(env, [("AC3", "local-run", "GET / 200")], _fake_app_decl(env))
    rec, _ = _record(env, capsys.readouterr().out)
    assert rec["budget"]["total"] == 240


def test_budget_exhausted_midway(env, capsys, monkeypatch):
    offset = [0]
    real_now, real_e2e = local_run._now, local_run._run_e2e
    monkeypatch.setattr(local_run, "_now", lambda: real_now() + offset[0])

    def e2e_then_time_passes(*a, **k):
        try:
            return real_e2e(*a, **k)
        finally:
            offset[0] += 10000
    monkeypatch.setattr(local_run, "_run_e2e", e2e_then_time_passes)
    ok = [sys.executable, "-c", "print('hi')"]
    code, _ = _go(env, [("AC3", "local-run", "e2e ok"), ("AC4", "local-run", "e2e ok"),
                        ("AC5", "local-run", "GET / 200")], _fake_app_decl(env, {"ok": ok}))
    out = capsys.readouterr().out
    assert code == local_run.EXIT_FAILED
    rec, _ = _record(env, out)
    assert [(c["outcome"], c["reason"]) for c in rec["checks"]] == [
        ("PASS", None), ("NOT-RUN", "time-budget-exhausted"),
        ("NOT-RUN", "time-budget-exhausted")]
    assert local_run.survivors() == []


def test_budget_exhausted_before_start_starts_nothing(env, capsys, monkeypatch):
    marker, code = _marker_decl(env)
    monkeypatch.setattr(local_run, "RESERVE", 10 ** 6)
    decl = {"start": [sys.executable, "-c", code, "{port}"],
            "ready": "http://127.0.0.1:{port}/"}
    rc, _ = _go(env, [("AC3", "local-run", "GET / 200")], decl)
    rec, _ = _record(env, capsys.readouterr().out)
    assert rc == local_run.EXIT_FAILED and not os.path.exists(marker)
    assert rec["start"]["outcome"] == "not-started"
    assert rec["checks"][0]["reason"] == "time-budget-exhausted"


# ---- survivors, readiness, main, interrupt ---------------------------------

def test_survivors_after_stop_is_exit_6(env, capsys, monkeypatch):
    monkeypatch.setattr(local_run, "survivors", lambda: [4242])
    code, _ = _go(env, [("AC3", "local-run", "GET / 200")], _fake_app_decl(env))
    out = capsys.readouterr().out
    assert code == local_run.EXIT_TREE_LEFT and "4242" in out
    rec, _ = _record(env, out)
    assert rec["survivors"] == [4242]


@pytest.mark.parametrize("status,ready", [(302, True), (404, True), (503, False)])
def test_ready_status_below_500_counts(status, ready):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Location", "http://127.0.0.1:1/never")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        url = "http://127.0.0.1:%d/" % srv.server_address[1]
        assert local_run._answers_ready(url, 5) is ready
    finally:
        srv.shutdown()
        srv.server_close()


def test_main_runs_and_reports_exit_code(env, capsys, monkeypatch):
    monkeypatch.setattr(local_run, "install_safety_net", lambda: None)
    _write_intake(env["track"], [("AC3", "local-run", "GET / 200")])
    _write_run(env["proj"], _fake_app_decl(env))
    rc = local_run.main(["--track-dir", env["track"], "--stage", "build", "--unit", "2",
                         "--ac", "AC3", "--project-dir", env["proj"]])
    out = capsys.readouterr().out
    assert rc == 0 and "evidence/build/unit-2/" in out


def test_main_hard_fails_when_the_safety_net_cannot_be_installed(env, capsys, monkeypatch):
    def refuse():
        raise OSError("nesting forbidden")
    monkeypatch.setattr(local_run, "install_safety_net", refuse)
    _write_intake(env["track"], [("AC3", "local-run", "GET / 200")])
    _write_run(env["proj"], _fake_app_decl(env))
    rc = local_run.main(["--track-dir", env["track"], "--stage", "verify",
                         "--project-dir", env["proj"]])
    cap = capsys.readouterr()
    assert rc == local_run.EXIT_INVALID and "nesting forbidden" in cap.out + cap.err
    assert _no_evidence(env) and not os.listdir(env["pids"])


def test_interrupt_stops_trees_and_writes_the_record(env):
    flag = os.path.join(env["pids"], "e2e.txt")
    e2e = {"hang": [sys.executable, "-c",
                    "import os, time; open(%r, 'w').write(str(os.getpid())); time.sleep(60)"
                    % flag]}
    _write_intake(env["track"], [("AC3", "local-run", "e2e hang"),
                                 ("AC4", "local-run", "GET / 200")])
    _write_run(env["proj"], _fake_app_decl(env, e2e))
    out_path = str(env["tmp"] / "runner.out")
    kwargs = {}
    if WIN:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    with open(out_path, "w") as out:
        p = subprocess.Popen(
            [sys.executable, SCRIPT, "--track-dir", env["track"], "--stage", "verify",
             "--project-dir", env["proj"]], stdout=out, stderr=subprocess.STDOUT, **kwargs)
    try:
        assert _until(lambda: _read_int(flag) is not None), open(out_path).read()
        app = _read_int(os.path.join(env["pids"], "app.txt"))
        grandchild = _read_int(os.path.join(env["pids"], "grandchild.txt"))
        p.send_signal(signal.CTRL_BREAK_EVENT if WIN else signal.SIGTERM)
        assert p.wait(WAIT) == local_run.EXIT_FAILED, open(out_path).read()
        out_text = open(out_path).read()
        rec, _ = _record(env, out_text)
        assert [(c["outcome"], c["reason"]) for c in rec["checks"]] == [
            ("NOT-RUN", "interrupted"), ("NOT-RUN", "interrupted")]
        assert rec["survivors"] == []
        for pid in (app, grandchild, _read_int(flag)):
            assert _until(lambda: not _pid_alive(pid)), "pid %s still alive" % pid
    finally:
        if p.poll() is None:
            p.kill()


# ---- failure paths the real-process tests above cannot reach ---------------
# Each one needs the operating system or the network to misbehave on cue, so the
# misbehaviour is injected at the one call that would see it.

def test_group_we_may_not_signal_still_counts_as_populated(monkeypatch):
    def denied(pgid, sig):
        raise PermissionError(1, "not permitted")
    monkeypatch.setattr(os, "killpg", denied, raising=False)  # Windows has no killpg
    assert local_run._group_populated(4242) is True

    def gone(pgid, sig):
        raise ProcessLookupError(3, "no such process")
    monkeypatch.setattr(os, "killpg", gone, raising=False)
    assert local_run._group_populated(4242) is False


def test_wait_group_empty_gives_up_when_the_group_stays_populated(monkeypatch):
    monkeypatch.setattr(local_run, "_group_populated", lambda pgid: True)
    tree = local_run.Tree(types.SimpleNamespace(poll=lambda: None), 4242)
    assert local_run._wait_group_empty(tree, 0) is False


@pytest.mark.skipif(WIN, reason="the POSIX branch of stop_tree; Windows ends a job object")
def test_stop_tree_reports_a_group_that_outlives_both_signals(monkeypatch):
    sent = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: sent.append((pgid, sig)))
    monkeypatch.setattr(local_run, "_wait_group_empty", lambda tree, seconds: False)
    tree = local_run.Tree(types.SimpleNamespace(poll=lambda: None), 4242)
    assert local_run.stop_tree(tree) == [4242]
    assert sent == [(4242, signal.SIGTERM), (4242, signal.SIGKILL)]


@pytest.mark.skipif(WIN, reason="on Windows this would put the test process in a job")
def test_install_job_does_nothing_off_windows():
    assert local_run.install_job() is None
    assert local_run._J0 is None


def _serve(body):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


_GET_ROOT = {"method": "GET", "path": "/", "status": 200, "text": None}


def test_http_check_still_reading_past_its_limit_is_a_timeout(tmp_path, monkeypatch):
    calls = []

    def now():  # the first reading sets the deadline; every later one is long past it
        calls.append(None)
        return 0 if len(calls) == 1 else 10 ** 6
    monkeypatch.setattr(local_run, "_now", now)
    srv = _serve(b"ok")
    evidence = tmp_path / "AC3.txt"
    try:
        res = local_run._do_http("http://127.0.0.1:%d/" % srv.server_address[1],
                                 _GET_ROOT, str(evidence), 5)
    finally:
        srv.shutdown()
        srv.server_close()
    assert res["outcome"] == "TIMEOUT" and res["reason"] == "timeout: check ran past 5 s"
    assert res["wrote"] is True and b"200 OK" in evidence.read_bytes()


def test_http_connect_timeout_is_a_timeout_not_a_failure(tmp_path, monkeypatch):
    def slow(*args, **kwargs):
        raise urllib.error.URLError(socket.timeout("timed out"))
    monkeypatch.setattr(local_run._LOOPBACK, "open", slow)
    evidence = tmp_path / "AC3.txt"
    res = local_run._do_http("http://127.0.0.1:1/", _GET_ROOT, str(evidence), 1)
    assert (res["outcome"], res["reason"]) == ("TIMEOUT", "timeout: timed out")
    assert b"error: timeout: timed out" in evidence.read_bytes()


@pytest.mark.parametrize("error, reason", [
    (ConnectionResetError("reset by peer"), "request failed: reset by peer"),
    (http.client.BadStatusLine("junk"), "request failed: junk"),
])
def test_http_check_broken_mid_request_is_a_fail_with_evidence(tmp_path, monkeypatch, error,
                                                               reason):
    def broken(*args, **kwargs):
        raise error
    monkeypatch.setattr(local_run._LOOPBACK, "open", broken)
    evidence = tmp_path / "AC3.txt"
    res = local_run._do_http("http://127.0.0.1:1/", _GET_ROOT, str(evidence), 1)
    assert (res["outcome"], res["reason"]) == ("FAIL", reason)
    assert ("error: " + reason).encode() in evidence.read_bytes()


def test_e2e_whose_program_cannot_be_found_is_a_fail_and_leaves_no_temp_file(tmp_path):
    evidence = tmp_path / "AC3.txt"
    res = local_run._do_e2e(["cai-no-such-program-xyz"], str(tmp_path), str(evidence), 5)
    assert res["outcome"] == "FAIL" and res["reason"].startswith("e2e-not-started: ")
    assert res["wrote"] is False and res["bytes_seen"] is None
    assert not evidence.exists() and not (tmp_path / "AC3.txt.out").exists()


def test_an_interrupt_that_arrived_while_an_e2e_tree_stopped_is_replayed_after(monkeypatch):
    state = {"stopping": False, "defer": 0, "pending": signal.SIGINT}
    monkeypatch.setattr(local_run, "_SIG", state)
    monkeypatch.setattr(local_run, "stop_tree", lambda tree, sweep=True: [])
    with pytest.raises(local_run._Interrupted):
        local_run._stop_e2e_tree(object())
    assert state == {"stopping": False, "defer": 0, "pending": None}


def test_interrupt_handler_ignores_defers_or_raises_by_state(monkeypatch):
    state = {"stopping": True, "defer": 0, "pending": None}
    monkeypatch.setattr(local_run, "_SIG", state)
    restore = local_run._install_interrupt()
    try:
        handler = signal.getsignal(signal.SIGINT)
        handler(signal.SIGINT, None)  # already stopping: nothing to do, nothing raised
        assert state["pending"] is None
        state.update(stopping=False, defer=1)
        handler(signal.SIGINT, None)  # an e2e tree is being stopped: remember it
        assert state["pending"] == signal.SIGINT
        state.update(defer=0, pending=None)
        with pytest.raises(local_run._Interrupted):
            handler(signal.SIGINT, None)
    finally:
        restore()


def test_install_interrupt_off_the_main_thread_leaves_the_handlers_alone():
    before = signal.getsignal(signal.SIGINT)
    seen = {}

    def work():
        restore = local_run._install_interrupt()  # signal.signal refuses outside the main thread
        restore()
        seen["after"] = signal.getsignal(signal.SIGINT)
    thread = threading.Thread(target=work)
    thread.start()
    thread.join(WAIT)
    assert seen == {"after": before}


def test_start_that_cannot_be_launched_fails_every_check(env, capsys, monkeypatch):
    def refuse(argv, cwd, out_path):
        raise OSError("exec format error")
    monkeypatch.setattr(local_run, "start_tree", refuse)
    code, _ = _go(env, [("AC3", "local-run", "GET / 200"), ("AC4", "local-run", "GET /a 200")],
                  _fake_app_decl(env))
    out = capsys.readouterr().out
    assert code == local_run.EXIT_FAILED and "PASS" not in out
    rec, _ = _record(env, out)
    assert [(c["outcome"], c["reason"]) for c in rec["checks"]] == [
        ("FAIL", "start-failed: exec format error")] * 2
    assert rec["start"]["outcome"] == "not-started"


def test_invalid_start_declaration_prints_its_problem(env, capsys):
    decl = {"start": "node server.js", "ready": "http://127.0.0.1:8000/"}  # start must be a list
    code, _ = _go(env, [("AC3", "local-run", "GET / 200")], decl)
    lines = capsys.readouterr().out.splitlines()
    assert code == local_run.EXIT_NOTHING_RUN
    assert lines[0] == "nothing to run: runtime skipped (invalid-start-declaration)"
    assert "run.start must be a non-empty list" in lines[1]
    assert _no_evidence(env)
