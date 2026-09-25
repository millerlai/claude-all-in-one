"""viewer.py's ### poller component and the finished ### http wiring
(GET / now serves PAGE_HTML, GET /api/rows now serves poller.snapshot()).

build_snapshot()'s sub-calls (claude_rows/codex_rows/find_track) are already
covered by units 2-4's own test files; this file monkeypatches them rather
than touching the filesystem, so it only exercises unit 5's own assembly and
orchestration logic.
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


# =========================================================== build_snapshot

def test_build_snapshot_assembles_rows_and_problems(monkeypatch):
    # summary/recent/subagents are now unit 2/3's own job (claude_rows()/
    # codex_rows() -- see their test files' D2 sections); build_snapshot()
    # must pass them through unchanged, not derive or clobber them, so the
    # stub rows below carry them like any other pre-set field.
    claude_row = {"key": "claude:1:2", "platform": "claude", "cwd": "/proj/a",
                 "sessionId": "sess-1", "summary": "做完了", "recent": [],
                 "subagents": []}
    codex_row = {"key": "codex:abc", "platform": "codex", "cwd": "/proj/b",
                "sessionId": "thread-1", "summary": None, "recent": [],
                "subagents": ["reviewer"]}

    monkeypatch.setattr(viewer, "claude_rows",
                        lambda config_root, now_ms: ([claude_row], ["claude problem"]))
    monkeypatch.setattr(viewer, "count_processes", lambda name: 3)
    monkeypatch.setattr(viewer, "codex_rows",
                        lambda codex_home, now_ms, k: ([codex_row], ["codex problem"]))
    monkeypatch.setattr(viewer, "branch_for_cwd", lambda cwd: None)

    seen_find_track = []

    def fake_find_track(cwd, session_id):
        seen_find_track.append((cwd, session_id))
        return {"name": "t", "certainty": "confirmed", "stages": [],
               "current": None, "gateWaiting": None}

    monkeypatch.setattr(viewer, "find_track", fake_find_track)

    snap = viewer.build_snapshot("/config", "/codex-home", 123456)

    assert snap["format"] == 1
    assert snap["generatedAt"] == 123456
    assert snap["problems"] == ["claude problem", "codex problem"]
    assert [r["key"] for r in snap["rows"]] == ["claude:1:2", "codex:abc"]
    for row in snap["rows"]:
        assert row["track"]["name"] == "t"
    assert snap["rows"][0]["summary"] == "做完了"
    assert snap["rows"][1]["subagents"] == ["reviewer"]

    # Claude rows are matched by their real sessionId; Codex rows never pass
    # their thread id as though it were a Claude ledger session_id.
    assert seen_find_track == [("/proj/a", "sess-1"), ("/proj/b", None)]


def test_build_snapshot_track_is_none_when_cwd_missing(monkeypatch):
    row = {"key": "claude:1:2", "platform": "claude", "cwd": None, "sessionId": "s"}
    monkeypatch.setattr(viewer, "claude_rows", lambda config_root, now_ms: ([row], []))
    monkeypatch.setattr(viewer, "count_processes", lambda name: 0)
    monkeypatch.setattr(viewer, "codex_rows", lambda codex_home, now_ms, k: ([], []))

    def boom(*a, **k):
        raise AssertionError("find_track must not be called for a cwd-less row")

    monkeypatch.setattr(viewer, "find_track", boom)

    snap = viewer.build_snapshot("/config", "/codex-home", 1)
    assert snap["rows"][0]["track"] is None


def test_branch_for_cwd_plain_ref(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/feat/thing\n", encoding="utf-8")
    assert viewer.branch_for_cwd(str(tmp_path)) == "feat/thing"


def test_branch_for_cwd_detached_head_is_none(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n", encoding="utf-8")
    assert viewer.branch_for_cwd(str(tmp_path)) is None


def test_branch_for_cwd_worktree_gitdir_pointer(tmp_path):
    real_git_dir = tmp_path / "real-git"
    real_git_dir.mkdir()
    (real_git_dir / "HEAD").write_text("ref: refs/heads/worktree-branch\n", encoding="utf-8")

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: " + str(real_git_dir) + "\n", encoding="utf-8")

    assert viewer.branch_for_cwd(str(worktree)) == "worktree-branch"


def test_branch_for_cwd_no_git_is_none(tmp_path):
    assert viewer.branch_for_cwd(str(tmp_path)) is None


def test_branch_for_cwd_none_cwd_is_none():
    assert viewer.branch_for_cwd(None) is None


# ================================================================== Poller

def _state(pid, port=1, token="t", proc_start="1"):
    return {"format": 1, "pid": pid, "procStart": proc_start, "port": port,
           "token": token, "startedAt": 0}


def test_self_check_absent_state_calls_superseded(monkeypatch):
    monkeypatch.setattr(viewer, "read_state", lambda path: None)
    calls = []
    poller = viewer.Poller("/config", "/codex", "/state.json", 111,
                           lambda: calls.append("superseded"))
    assert poller._self_check() is False
    assert calls == ["superseded"]


def test_self_check_same_pid_is_a_noop(monkeypatch):
    monkeypatch.setattr(viewer, "read_state", lambda path: _state(111))

    def boom_write(*a, **k):
        raise AssertionError("write_state must not be called for a matching pid")

    monkeypatch.setattr(viewer, "write_state", boom_write)
    calls = []
    poller = viewer.Poller("/config", "/codex", "/state.json", 111,
                           lambda: calls.append("superseded"))
    assert poller._self_check() is True
    assert calls == []


def test_self_check_other_pid_alive_calls_superseded(monkeypatch):
    monkeypatch.setattr(viewer, "read_state", lambda path: _state(222))
    monkeypatch.setattr(viewer, "check_alive", lambda pid, start, exact: "alive")
    calls = []
    poller = viewer.Poller("/config", "/codex", "/state.json", 111,
                           lambda: calls.append("superseded"))
    assert poller._self_check() is False
    assert calls == ["superseded"]


def test_self_check_other_pid_gone_reclaims(monkeypatch):
    monkeypatch.setattr(viewer, "read_state", lambda path: _state(222, port=9, token="old"))
    monkeypatch.setattr(viewer, "check_alive", lambda pid, start, exact: "gone")
    monkeypatch.setattr(viewer, "process_start", lambda pid: "own-start")
    written = []
    monkeypatch.setattr(viewer, "write_state", lambda path, state: written.append((path, state)))
    calls = []
    poller = viewer.Poller("/config", "/codex", "/state.json", 111,
                           lambda: calls.append("superseded"),
                           own_port=7788, own_token="mine")
    assert poller._self_check() is True
    assert calls == []
    assert len(written) == 1
    path, state = written[0]
    assert path == "/state.json"
    assert state["pid"] == 111
    assert state["procStart"] == "own-start"
    assert state["port"] == 7788
    assert state["token"] == "mine"


def test_run_keeps_previous_snapshot_on_unexpected_exception(monkeypatch):
    monkeypatch.setattr(viewer, "read_state", lambda path: _state(111))

    calls = {"n": 0}

    def flaky_build_snapshot(config_root, codex_home, now_ms):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"format": 1, "generatedAt": now_ms, "rows": [{"key": "a"}], "problems": []}
        raise RuntimeError("boom")

    monkeypatch.setattr(viewer, "build_snapshot", flaky_build_snapshot)

    poller = viewer.Poller("/config", "/codex", "/state.json", 111, lambda: None)
    # Drive two iterations of the loop body directly, without sleeping.
    assert poller._self_check() is True
    snap1 = viewer.build_snapshot("/config", "/codex", 1)
    poller._snapshot_bytes = json.dumps(snap1).encode("utf-8")

    assert poller._self_check() is True
    try:
        viewer.build_snapshot("/config", "/codex", 2)
        assert False, "expected the second call to raise"
    except RuntimeError:
        pass

    # Simulate what run() does on that exception: keep the previous snapshot's
    # rows, replace `problems` with just this cycle's error (not accumulated
    # on top of what was already there -- see
    # test_run_does_not_accumulate_problems_across_repeated_failures).
    with poller._lock:
        prev = json.loads(poller._snapshot_bytes.decode("utf-8"))
    prev["problems"] = ["poller error: boom"]
    with poller._lock:
        poller._snapshot_bytes = json.dumps(prev).encode("utf-8")

    final = json.loads(poller.snapshot().decode("utf-8"))
    assert final["rows"] == [{"key": "a"}]
    assert final["problems"] == ["poller error: boom"]


def test_run_does_not_accumulate_problems_across_repeated_failures(monkeypatch):
    """An end-to-end run of the real thread body: a sustained build_snapshot
    failure must not grow `problems` without bound cycle over cycle -- each
    poll should report only the current cycle's failure, not every prior
    cycle's concatenated on top (run()'s except branch used to do
    `prev["problems"] + [...]` against whatever was already there, so N
    consecutive failures produced a list N entries long)."""
    monkeypatch.setattr(viewer, "read_state", lambda path: _state(111))
    monkeypatch.setattr(viewer, "SERVER_POLL_INTERVAL_S", 0.01)

    def always_boom(config_root, codex_home, now_ms):
        raise RuntimeError("boom")

    monkeypatch.setattr(viewer, "build_snapshot", always_boom)

    poller = viewer.Poller("/config", "/codex", "/state.json", 111, lambda: None)
    poller.start()
    try:
        time.sleep(0.3)  # many poll cycles at the patched 0.01s interval
    finally:
        poller.stop()
        poller.join(timeout=5)

    final = json.loads(poller.snapshot().decode("utf-8"))
    assert final["problems"] == ["poller error: boom"]


def test_run_thread_self_check_absent_state_stops_the_loop(monkeypatch):
    """An end-to-end run of the real thread body (not the manual drive
    above): the state file is absent from the first tick, so run() must
    call on_superseded exactly once and return without looping forever."""
    monkeypatch.setattr(viewer, "read_state", lambda path: None)
    event = threading.Event()
    poller = viewer.Poller("/config", "/codex", "/state.json", 111, event.set)
    poller.start()
    assert event.wait(timeout=5)
    poller.join(timeout=5)
    assert not poller.is_alive()


# ============================================================ cmd_serve wiring

VIEWER_PY = os.path.abspath(viewer.__file__)


def run_launcher(*args, env=None, timeout=20):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run([sys.executable, VIEWER_PY, *args],
                          capture_output=True, text=True, encoding="utf-8",
                          env=full_env, timeout=timeout)


@pytest.fixture
def isolated_state(tmp_path):
    fake_tmp = tmp_path / "viewer-tmp"
    fake_tmp.mkdir()
    yield str(fake_tmp)


def test_cmd_serve_writes_state_before_starting_the_poller(monkeypatch, tmp_path):
    written_before_start = {}

    real_write_state = viewer.write_state

    def spy_write_state(path, state):
        real_write_state(path, state)
        written_before_start["state_on_disk"] = viewer.read_state(path) is not None

    monkeypatch.setattr(viewer, "write_state", spy_write_state)
    monkeypatch.setattr(viewer, "state_path", lambda: str(tmp_path / "state.json"))

    started = {"poller_saw_state": None}

    # Poller.start() is monkeypatched to record whether the state file was
    # already on disk, then immediately trigger cmd_serve's own shutdown
    # path (the same one on_superseded would call) instead of actually
    # starting the polling thread.
    def spy_start(self):
        started["poller_saw_state"] = viewer.read_state(str(tmp_path / "state.json")) is not None
        threading.Thread(target=self.on_superseded, daemon=True).start()

    monkeypatch.setattr(viewer.Poller, "start", spy_start)

    result = viewer.cmd_serve(0)  # port 0: bind to an OS-assigned free port

    assert written_before_start.get("state_on_disk") is True
    assert started["poller_saw_state"] is True
    assert result == 0


# --- two real instances converge to one -----------------------------------

def test_two_instances_converge_to_one(isolated_state):
    # cmd_serve records the *requested* candidate port as the bound port
    # (true whenever that candidate actually binds, which a fixed base port
    # picked for this test does) -- "--port 0" would defeat that, since the
    # OS-assigned actual port would differ from the recorded "0".
    base_port = 18899
    env = {"TMP": isolated_state, "TEMP": isolated_state, "TMPDIR": isolated_state}
    procs = []
    try:
        for _ in range(2):
            p = subprocess.Popen(
                [sys.executable, VIEWER_PY, "serve", "--port", str(base_port)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=dict(list(os.environ.items()) + list(env.items())))
            procs.append(p)
            time.sleep(0.3)  # stagger so the second one sees the first's state file

        # Give the pollers a few self-check cycles (2s interval) to converge.
        deadline = time.time() + 12
        state = None
        while time.time() < deadline:
            state = viewer.read_state(
                os.path.join(isolated_state, "cai-viewer.json")
                if os.name == "nt" else
                os.path.join(isolated_state, "cai-viewer-%d.json" % os.getuid()))
            if state is not None:
                break
            time.sleep(0.3)
        assert state is not None

        survivor_pid = state["pid"]
        other_pid = [p.pid for p in procs if p.pid != survivor_pid]

        deadline = time.time() + 12
        converged = False
        while time.time() < deadline:
            identity = viewer._get_identity(state["port"], state["token"], 1.0)
            if identity is not None and identity.get("pid") == survivor_pid:
                converged = True
                break
            time.sleep(0.3)
        assert converged
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=5)


# ==================================================================== V3 ===
# Host/token/CORS/CSP checks, and /api/rows serving real (monkeypatched)
# snapshot content instead of unit 1's hardcoded empty payload.

class _FakePoller:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def snapshot(self):
        return self._body


@pytest.fixture
def live_server():
    server = viewer.ViewerServer(("127.0.0.1", 0), viewer.Handler)
    server.token = "test-token-value"
    server.poller = _FakePoller(
        {"format": 1, "generatedAt": 42, "rows": [{"key": "x"}], "problems": ["p"]})
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


def test_api_rows_serves_the_real_poller_snapshot(live_server):
    _server, port = live_server
    status, headers, body = _get(port, "/api/rows")
    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    payload = json.loads(body)
    assert payload == {"format": 1, "generatedAt": 42, "rows": [{"key": "x"}], "problems": ["p"]}


def test_get_root_serves_page_html_with_port_substituted(live_server):
    _server, port = live_server
    status, headers, body = _get(port, "/")
    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert "Content-Security-Policy" in headers
    text = body.decode("utf-8")
    assert "__PORT__" not in text
    assert ("127.0.0.1:%d" % port) in text


def test_host_check_runs_before_token_check(live_server):
    server, port = live_server
    conn_req = urllib.request.Request(
        "http://127.0.0.1:%d/identity" % port,
        headers={viewer.TOKEN_HEADER: server.token, "Host": "evil.example:%d" % port})
    try:
        urllib.request.urlopen(conn_req, timeout=5)
        assert False, "expected 403 for a forbidden Host header"
    except urllib.error.HTTPError as exc:
        assert exc.code == 403


def test_identity_and_shutdown_require_token(live_server):
    server, port = live_server
    status, _h, _b = _get(port, "/identity", token="wrong")
    assert status == 403
    status, _h, _b = _get(port, "/identity")
    assert status == 403

    req = urllib.request.Request(
        "http://127.0.0.1:%d/shutdown" % port, method="POST", data=b"")
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "expected 403 without a token"
    except urllib.error.HTTPError as exc:
        assert exc.code == 403


def test_no_cors_header_ever(live_server):
    server, port = live_server
    for path, token in (("/", None), ("/api/rows", None), ("/identity", server.token)):
        _status, headers, _body = _get(port, path, token=token)
        assert not any(h.lower().startswith("access-control-allow") for h in headers)


def test_csp_header_on_html_response(live_server):
    _server, port = live_server
    _status, headers, _body = _get(port, "/")
    assert "unsafe-inline" in headers["Content-Security-Policy"]
