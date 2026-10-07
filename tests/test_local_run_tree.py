"""Unit 1 probes P1-P4 for local_run's process-tree mechanics (I5).

Real processes throughout: tests/local_run_probe.py starts tests/fake_app.py
(which spawns one grandchild) through local_run.start_tree, and the tests
then end the probe in different ways and look for the two pids afterwards.
P5 (cut off by the Bash tool) and P6 (environment variables) are manual and
live in the design doc, not here.

Every wait is bounded and every test kills what it started in a `finally`, so
a failing run leaves no process behind.
"""
import http.server
import os
import signal
import socket
import subprocess
import sys
import time

import pytest

import local_run

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "local_run_probe.py")
WAIT = 20  # seconds; generous for a loaded CI box, never an unbounded wait
WIN = sys.platform == "win32"


def _pid_alive(pid):
    if WIN:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = wintypes.DWORD()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # a zombie nobody reaped is dead for our purposes
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


def _ids(pid_dir):
    return {k: _read_int(os.path.join(pid_dir, k + ".txt"))
            for k in ("app", "grandchild", "port")}


def _ready(pid_dir):
    return all(v is not None for v in _ids(pid_dir).values())


def _kill_leftovers(pid_dir):
    for key in ("app", "grandchild"):
        pid = _read_int(os.path.join(pid_dir, key + ".txt"))
        if pid and _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGTERM if WIN else signal.SIGKILL)
            except OSError:
                pass


def _start_driver(pid_dir, tmp_path, mode):
    cmd = [sys.executable, PROBE, "--pid-dir", pid_dir, "--sleep", "60",
           "--mode", mode]
    with open(str(tmp_path / "driver.out"), "w") as out:
        return subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT)


def _start_nested(pid_dir, tmp_path, mode):
    code = ("import subprocess, sys, local_run\n"
            "local_run.install_job()\n"
            "pid_dir = sys.argv[1]\n"
            "p = subprocess.Popen([sys.executable, %r, '--pid-dir', pid_dir,"
            " '--sleep', '60', '--mode', sys.argv[2]])\n"
            "open(pid_dir + '/driver.pid', 'w').write(str(p.pid))\n"
            "sys.exit(p.wait())\n" % PROBE)
    out = open(str(tmp_path / "wrapper.out"), "w")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.dirname(local_run.__file__), env.get("PYTHONPATH", "")])
    try:
        return subprocess.Popen([sys.executable, "-c", code, pid_dir, mode],
                                stdout=out, stderr=subprocess.STDOUT, env=env)
    finally:
        out.close()


def _assert_gone_and_port_free(pid_dir):
    ids = _ids(pid_dir)
    assert _until(lambda: not _pid_alive(ids["app"])), "fake app still alive"
    assert _until(lambda: not _pid_alive(ids["grandchild"])), "grandchild still alive"
    srv = http.server.HTTPServer(("127.0.0.1", ids["port"]),
                                 http.server.BaseHTTPRequestHandler)
    srv.server_close()


def _text(tmp_path, name):
    p = tmp_path / name
    return p.read_text() if p.exists() else "<no output file>"


def test_free_port_is_bindable():
    port = local_run.free_port()
    with socket.socket() as s:
        s.bind(("127.0.0.1", port))


def test_exit_codes_are_the_documented_values():
    assert (local_run.EXIT_PASS, local_run.EXIT_FAILED, local_run.EXIT_NOTHING_RUN,
            local_run.EXIT_INVALID, local_run.EXIT_TREE_LEFT) == (0, 3, 4, 5, 6)


def test_p1_normal_stop(tmp_path):
    pid_dir = str(tmp_path)
    p = _start_driver(pid_dir, tmp_path, "stop")
    try:
        assert p.wait(WAIT * 2) == 0, _text(tmp_path, "driver.out")
        assert _ready(pid_dir), _text(tmp_path, "driver.out")
        _assert_gone_and_port_free(pid_dir)
    finally:
        p.kill()
        _kill_leftovers(pid_dir)


@pytest.mark.skipif(WIN, reason="no interceptable external termination on Windows (P2 n/a)")
@pytest.mark.parametrize("sig", ["SIGTERM", "SIGINT", "SIGHUP"])
def test_p2_interceptable_signal(tmp_path, sig):
    pid_dir = str(tmp_path)
    p = _start_driver(pid_dir, tmp_path, "wait")
    try:
        assert _until(lambda: _ready(pid_dir)), _text(tmp_path, "driver.out")
        os.kill(p.pid, getattr(signal, sig))
        p.wait(WAIT * 2)
        _assert_gone_and_port_free(pid_dir)
    finally:
        p.kill()
        _kill_leftovers(pid_dir)


@pytest.mark.xfail(not WIN, strict=True,
                   reason="POSIX: SIGKILL cannot be handled, so the tree is left (C4)")
def test_p3_hard_kill_of_driver(tmp_path):
    pid_dir = str(tmp_path)
    p = _start_driver(pid_dir, tmp_path, "wait")
    try:
        assert _until(lambda: _ready(pid_dir)), _text(tmp_path, "driver.out")
        p.kill()
        p.wait(WAIT)
        _assert_gone_and_port_free(pid_dir)  # Windows: J0 closed with the driver
    finally:
        p.kill()
        _kill_leftovers(pid_dir)  # POSIX leftovers are expected; do not leak them


@pytest.mark.skipif(not WIN, reason="job objects are Windows only")
@pytest.mark.parametrize("mode", ["stop", "kill"])
def test_p4_nested_job(tmp_path, mode):
    """The driver's J0 is created inside another job (the wrapper's, on top of
    whatever job pytest's own launcher uses); both the normal stop and a hard
    kill of the driver must still leave nothing behind."""
    pid_dir = str(tmp_path)
    w = _start_nested(pid_dir, tmp_path, "stop" if mode == "stop" else "wait")
    try:
        if mode == "stop":
            assert w.wait(WAIT * 2) == 0, _text(tmp_path, "wrapper.out")
            assert "J0 installed" in _text(tmp_path, "wrapper.out")
        else:
            assert _until(lambda: _ready(pid_dir) and
                          _read_int(os.path.join(pid_dir, "driver.pid")) is not None), \
                _text(tmp_path, "wrapper.out")
            assert "J0 installed" in _text(tmp_path, "wrapper.out")
            os.kill(_read_int(os.path.join(pid_dir, "driver.pid")), signal.SIGTERM)
        _assert_gone_and_port_free(pid_dir)
    finally:
        w.kill()
        _kill_leftovers(pid_dir)
