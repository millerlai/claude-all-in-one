"""viewer.py's ### state-file, ### http (skeleton) and ### launcher
components -- unit 1 covers everything except the poller (unit 5), so
GET /api/rows is checked only for its always-empty shape here.
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

import viewer


# --- state-file --------------------------------------------------------

def test_state_path_is_under_the_temp_dir():
    import tempfile
    path = viewer.state_path()
    assert os.path.dirname(path) == os.path.normpath(tempfile.gettempdir())
    assert path.endswith(".json")
    assert os.path.basename(path).startswith("cai-viewer")


def test_write_then_read_state_roundtrips(tmp_path):
    path = str(tmp_path / "state.json")
    state = {"format": 1, "pid": 4242, "procStart": "123456", "port": 7788,
             "token": "a" * 64, "startedAt": 1700000000000}
    viewer.write_state(path, state)
    got = viewer.read_state(path)
    assert got == state


def test_read_state_of_absent_file_is_none(tmp_path):
    assert viewer.read_state(str(tmp_path / "nope.json")) is None


def test_read_state_missing_proc_start_is_none(tmp_path):
    path = str(tmp_path / "state.json")
    viewer.write_state(path, {"format": 1, "pid": 1, "port": 2, "token": "t"})
    got = viewer.read_state(path)
    assert got["procStart"] is None


def test_read_state_corrupt_json_retries_then_none(tmp_path):
    path = str(tmp_path / "state.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    before = time.time()
    assert viewer.read_state(path) is None
    assert time.time() - before >= 0.09  # the one 100ms retry actually slept


def test_read_state_rejects_wrong_types(tmp_path):
    path = str(tmp_path / "state.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"format": 1, "pid": "not-an-int", "port": 1, "token": "t"}, fh)
    assert viewer.read_state(path) is None


def test_write_state_file_mode_is_owner_only(tmp_path):
    if os.name == "nt":
        pytest.skip("POSIX file mode bits do not apply on Windows")
    path = str(tmp_path / "state.json")
    viewer.write_state(path, {"format": 1, "pid": 1, "port": 2, "token": "t"})
    assert (os.stat(path).st_mode & 0o777) == 0o600


def test_remove_state_only_removes_matching_pid(tmp_path):
    path = str(tmp_path / "state.json")
    viewer.write_state(path, {"format": 1, "pid": 111, "port": 2, "token": "t"})
    viewer.remove_state(path, 999)
    assert os.path.isfile(path)

    viewer.remove_state(path, 111)
    assert not os.path.isfile(path)


def test_remove_state_of_absent_file_does_not_raise(tmp_path):
    viewer.remove_state(str(tmp_path / "gone.json"), 111)  # must not raise


# --- http skeleton -------------------------------------------------------

def test_host_ok():
    assert viewer.host_ok("127.0.0.1:7788", 7788)
    assert viewer.host_ok("LOCALHOST:7788", 7788)
    assert viewer.host_ok("localhost:7788", 7788)
    assert not viewer.host_ok("127.0.0.1:7789", 7788)
    assert not viewer.host_ok("evil.example:7788", 7788)
    assert not viewer.host_ok(None, 7788)
    assert not viewer.host_ok("", 7788)


@pytest.fixture
def live_server():
    server = viewer.ViewerServer(("127.0.0.1", 0), viewer.Handler)
    server.token = "test-token-value"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield server, port
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _get(port, path, token=None, host=None):
    headers = {}
    if token is not None:
        headers[viewer.TOKEN_HEADER] = token
    req = urllib.request.Request(
        "http://127.0.0.1:%d%s" % (port, path), headers=headers)
    if host is not None:
        req.host = host
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def test_get_root_is_html_placeholder(live_server):
    _server, port = live_server
    status, headers, body = _get(port, "/")
    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert b"<html" in body.lower()
    assert "Content-Security-Policy" in headers


def test_api_rows_is_always_empty_for_unit_1(live_server):
    _server, port = live_server
    status, headers, body = _get(port, "/api/rows")
    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    payload = json.loads(body)
    assert payload["format"] == 1
    assert payload["rows"] == []
    assert payload["problems"] == []
    assert isinstance(payload["generatedAt"], int)


def test_identity_requires_the_right_token(live_server):
    server, port = live_server
    status, _headers, body = _get(port, "/identity", token=server.token)
    assert status == 200
    payload = json.loads(body)
    assert payload == {"app": "cai-viewer", "format": 1,
                       "pid": os.getpid(), "port": port}

    status, _headers, _body = _get(port, "/identity", token="wrong")
    assert status == 403

    status, _headers, _body = _get(port, "/identity")
    assert status == 403


def test_unknown_path_is_404(live_server):
    _server, port = live_server
    status, _headers, _body = _get(port, "/nope")
    assert status == 404


def test_security_headers_present_on_every_response(live_server):
    server, port = live_server
    for path, token in (("/", None), ("/api/rows", None),
                        ("/identity", server.token), ("/nope", None)):
        _status, headers, _body = _get(port, path, token=token)
        assert headers.get("Cache-Control") == "no-store"
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("Referrer-Policy") == "no-referrer"
        assert not any(h.lower().startswith("access-control-allow")
                       for h in headers)


def test_shutdown_requires_token_then_stops_the_server(live_server):
    server, port = live_server

    req = urllib.request.Request(
        "http://127.0.0.1:%d/shutdown" % port, method="POST", data=b"")
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "expected 403 without a token"
    except urllib.error.HTTPError as exc:
        assert exc.code == 403

    req = urllib.request.Request(
        "http://127.0.0.1:%d/shutdown" % port, method="POST", data=b"",
        headers={viewer.TOKEN_HEADER: server.token})
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 202


def test_host_check_runs_before_token_check(live_server):
    """A wrong Host header is rejected even with a valid token, and the
    server never leaks past the host gate."""
    server, port = live_server
    conn_req = urllib.request.Request(
        "http://127.0.0.1:%d/identity" % port,
        headers={viewer.TOKEN_HEADER: server.token, "Host": "evil.example:%d" % port})
    try:
        urllib.request.urlopen(conn_req, timeout=5)
        assert False, "expected 403 for a forbidden Host header"
    except urllib.error.HTTPError as exc:
        assert exc.code == 403
        assert exc.read() == b"forbidden host"


# --- launcher: full start/stop lifecycle against a real subprocess -------

VIEWER_PY = os.path.abspath(viewer.__file__)


def run_launcher(*args, env=None):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run([sys.executable, VIEWER_PY, *args],
                          capture_output=True, text=True, encoding="utf-8",
                          env=full_env, timeout=20)


@pytest.fixture
def isolated_state(tmp_path):
    """A private temp dir passed to the launcher subprocess's environment,
    so state_path() (computed there, in a fresh process) never touches a
    real running viewer on the developer's machine."""
    fake_tmp = tmp_path / "viewer-tmp"
    fake_tmp.mkdir()
    yield str(fake_tmp)


def test_start_then_start_again_then_stop(isolated_state):
    env = {"TMP": isolated_state, "TEMP": isolated_state, "TMPDIR": isolated_state}
    try:
        first = run_launcher("start", env=env)
        assert first.returncode == 0, first.stdout + first.stderr
        lines = first.stdout.strip().splitlines()
        assert lines[0].startswith("Agent Viewer: http://127.0.0.1:")
        assert lines[1].startswith("started (pid ")

        second = run_launcher("start", env=env)
        assert second.returncode == 0, second.stdout + second.stderr
        assert second.stdout.strip().splitlines()[1].startswith("already running (pid ")

        stop = run_launcher("stop", env=env)
        assert stop.returncode == 0, stop.stdout + stop.stderr
        assert "stopped (pid " in stop.stdout

        again = run_launcher("stop", env=env)
        assert again.returncode == 0
        assert again.stdout.strip() == "not running"
    finally:
        run_launcher("stop", env=env)


def test_stop_with_no_server_running(isolated_state):
    env = {"TMP": isolated_state, "TEMP": isolated_state, "TMPDIR": isolated_state}
    result = run_launcher("stop", env=env)
    assert result.returncode == 0
    assert result.stdout.strip() == "not running"
