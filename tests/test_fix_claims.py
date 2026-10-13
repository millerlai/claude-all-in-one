"""Session claim registry: signed unit 2 contract, including real process locks."""
import builtins
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

import fix_claims
import fix_target


SCRIPT = Path(__file__).resolve().parents[1] / "plugins/cai/scripts/fix_claims.py"
KEY = "acme/app#142"
URL = "https://github.com/acme/app/issues/142"
START = "2026-10-13T08:00:00.123Z"
NEXT = "2026-10-13T08:00:01.124Z"


def stamp(now):
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)


def entry(**changes):
    row = {"platform": "claude", "session_id": "other", "started": stamp(datetime.now(timezone.utc)),
           "status": "in-progress", "branch": "fix/142"}
    row.update(changes)
    return row


def write(data):
    path = Path(fix_claims.registry_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    Path(str(path) + ".lock").touch()
    return path


def register(*extra):
    return fix_claims.main(["register", "--owner", "Acme", "--repo", "APP", "--issue", "142",
                            "--branch", "fix/142", *extra])


def release(started):
    return fix_claims.main(["release", "--owner", "acme", "--repo", "app", "--issue", "142",
                            "--started", started])


def clear(platform="claude", session="other", started=START, url=URL):
    return fix_claims.main(["clear", "--project-dir", ".", "--platform", platform,
                            "--session", session, "--started", started, url])


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setattr(fix_target, "origin_remote", lambda cwd: fix_target.Remote("github.com", "acme", "app"))


def test_register_update_release_and_exact_shape(tmp_path, monkeypatch, capsys):
    assert Path(fix_claims.registry_path()) == tmp_path / "cai/fix-claims.json"
    assert fix_claims.item_key("Acme", "APP", 142) == KEY
    assert fix_claims.jira_key("JIRA.Example.com", "PROJ-12") == "jira.example.com/proj-12"
    monkeypatch.setenv(fix_claims.SESSION_ID_ENV, "mine")
    times = iter([START, NEXT])
    monkeypatch.setattr(fix_claims.ledger, "_now_ms", lambda: next(times))
    assert register() == 0
    assert capsys.readouterr().out == f"registry held {KEY} {START}\n"
    data = json.loads(Path(fix_claims.registry_path()).read_text(encoding="utf-8"))
    assert data == {"claims": {KEY: {"platform": "claude", "session_id": "mine", "started": START,
                                     "status": "in-progress", "branch": "fix/142"}}}
    assert register() == 0
    assert capsys.readouterr().out == f"registry held {KEY} {NEXT}\n"
    assert release(START) == 0
    assert capsys.readouterr().out == f"registry not-held {KEY}\n"
    assert release(NEXT) == 0
    assert capsys.readouterr().out == f"registry released {KEY}\n"
    assert json.loads(Path(fix_claims.registry_path()).read_text()) == {"claims": {}}
    assert release(NEXT) == 0
    assert capsys.readouterr().out == f"registry not-held {KEY}\n"


def test_foreign_claim_blocks_without_any_write(monkeypatch, capsys):
    monkeypatch.setenv(fix_claims.SESSION_ID_ENV, "mine")
    row = entry(platform="future-platform", status="future-status", branch=42)
    path = write({"claims": {KEY: row}, "future": [1]})
    before = path.read_bytes()
    assert register() == 3
    assert capsys.readouterr().out == f"registry elsewhere future-platform other {row['started']}\n"
    assert path.read_bytes() == before
    assert fix_claims.others_by_key([KEY, "missing"]) == {
        KEY: [{k: row[k] for k in ("platform", "session_id", "started")}], "missing": []}


@pytest.mark.parametrize("session", [None, "", "white space", "bad\nline", "unknown"])
def test_unknown_sessions_block_each_other_but_release_matches_start(session, monkeypatch, capsys):
    if session is not None:
        monkeypatch.setenv(fix_claims.SESSION_ID_ENV, session)
    assert fix_claims.current_session() is None
    assert register() == 0
    lines = capsys.readouterr().out.splitlines()
    started = lines[0].split()[3]
    assert lines[1] == (f"registry note session unknown: {fix_claims.SESSION_ID_ENV} is not set or not usable, "
                        "so this claim names no session")
    assert register() == 3
    assert capsys.readouterr().out.splitlines()[0] == f"registry elsewhere claude unknown {started}"
    assert fix_claims.others_by_key([KEY])[KEY][0]["session_id"] is None
    assert release("2000-01-01T00:00:00.000Z") == 0
    assert KEY in json.loads(Path(fix_claims.registry_path()).read_text())["claims"]
    assert release(started) == 0
    assert KEY not in json.loads(Path(fix_claims.registry_path()).read_text())["claims"]


def test_reserved_unknown_env_claim_can_be_cleared_from_copied_detail(remote, monkeypatch, capsys):
    monkeypatch.setenv(fix_claims.SESSION_ID_ENV, "unknown")
    assert register() == 0
    lines = capsys.readouterr().out.splitlines()
    path = Path(fix_claims.registry_path())
    assert json.loads(path.read_text())["claims"][KEY]["session_id"] is None
    assert lines[1] == (f"registry note session unknown: {fix_claims.SESSION_ID_ENV} is not set or not usable, "
                        "so this claim names no session")
    monkeypatch.setenv(fix_claims.SESSION_ID_ENV, "blocked")
    assert register() == 3
    _, _, platform, session, started = capsys.readouterr().out.splitlines()[0].split()
    assert session == "unknown"
    assert clear(platform, session, started) == 0
    assert capsys.readouterr().out == f"registry cleared {KEY}\n"
    assert json.loads(path.read_text())["claims"] == {}


def test_legacy_string_unknown_is_unreadable_and_replaced(monkeypatch, capsys):
    monkeypatch.setenv(fix_claims.SESSION_ID_ENV, "mine")
    path = write({"claims": {KEY: entry(session_id="unknown", extension=[1])}})
    before = path.read_bytes()
    assert fix_claims.others_by_key([KEY]) == {KEY: []}
    assert path.read_bytes() == before
    assert register() == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith(f"registry held {KEY} ")
    assert lines[1] == "registry note replaced an unreadable entry for this item"
    row = json.loads(path.read_text())["claims"][KEY]
    assert row["session_id"] == "mine"
    assert row["extension"] == [1]


def test_same_session_other_platform_is_not_own(monkeypatch, capsys):
    monkeypatch.setenv(fix_claims.SESSION_ID_ENV, "mine")
    path = write({"claims": {KEY: entry(platform="codex", session_id="mine")}})
    before = path.read_bytes()
    assert register() == 3
    assert release(json.loads(before)["claims"][KEY]["started"]) == 0
    assert path.read_bytes() == before
    assert fix_claims.others_by_key([KEY])[KEY][0]["platform"] == "codex"


def test_stale_takeover_boundary_and_utc(monkeypatch, capsys):
    now = datetime(2026, 10, 13, 8, 0, 0, 123000, timezone.utc)
    assert fix_claims.is_expired(stamp(now - timedelta(seconds=1800)), now) is True
    assert fix_claims.is_expired(stamp(now - timedelta(seconds=1799, milliseconds=999)), now) is False
    assert fix_claims.is_expired(stamp(now + timedelta(days=1)), now) is False
    monkeypatch.setenv(fix_claims.SESSION_ID_ENV, "mine")
    old = entry(started=stamp(datetime.now(timezone.utc) - timedelta(minutes=31)))
    write({"claims": {KEY: old}})
    assert register() == 0
    assert capsys.readouterr().out.splitlines()[1] == (
        f"registry note took over an expired claim by claude session other started {old['started']}")
    assert fix_claims.others_by_key([KEY]) == {KEY: []}


@pytest.mark.parametrize("started", [None, 23, "2026-10-13T08:00:00Z", "2026-10-13T08:00:00.1Z",
                                     "2026-13-45T08:00:00.123Z", "2026-10-13T08:00:00.123Z\n"])
def test_unreadable_start(started):
    assert fix_claims.is_expired(started, datetime.now(timezone.utc)) is None


@pytest.mark.parametrize("bad", [None, [], {"platform": "Bad"}, entry(platform="bad platform"),
                                 entry(session_id=[]), entry(session_id=""), entry(started=123),
                                 entry(started="2026-13-45T08:00:00.123Z")])
def test_unreadable_item_is_replaced_with_note(bad, monkeypatch, capsys):
    monkeypatch.setenv(fix_claims.SESSION_ID_ENV, "mine")
    write({"claims": {KEY: bad}})
    assert fix_claims.others_by_key([KEY]) == {KEY: []}
    assert register() == 0
    assert "registry note replaced an unreadable entry for this item\n" in capsys.readouterr().out
    assert json.loads(Path(fix_claims.registry_path()).read_text())["claims"][KEY]["session_id"] == "mine"


def test_preserves_unknown_fields_and_other_items(monkeypatch):
    monkeypatch.setenv(fix_claims.SESSION_ID_ENV, "mine")
    other = {"unrecognised": [1, 2]}
    write({"claims": {KEY: entry(session_id="mine", extension={"x": 1}), "elsewhere": other},
           "extension": [42]})
    assert register() == 0
    data = json.loads(Path(fix_claims.registry_path()).read_text())
    assert data["extension"] == [42]
    assert data["claims"]["elsewhere"] == other
    assert data["claims"][KEY]["extension"] == {"x": 1}


@pytest.mark.parametrize("raw", [b"{", b"\xff", b"[]", b"{}", b'{"claims": []}', b'{"claims": null}'])
def test_corrupt_registry_is_readonly_until_repaired(raw, monkeypatch, capsys):
    monkeypatch.setenv(fix_claims.SESSION_ID_ENV, "mine")
    path = write({"claims": {}})
    path.write_bytes(raw)
    backup = Path(str(path) + ".bak")
    backup.write_bytes(b"older backup")
    assert fix_claims.load(str(path), repair=False) == (None, [])
    assert fix_claims.others_by_key([KEY]) is None
    assert path.read_bytes() == raw
    assert backup.read_bytes() == b"older backup"
    assert register() == 0
    assert backup.read_bytes() == raw
    assert capsys.readouterr().out.splitlines()[1] == (
        f"registry note the registry could not be parsed and was moved to {backup}")


def test_absent_lock_and_registry_do_not_create_files(tmp_path, capsys):
    assert fix_claims.load(fix_claims.registry_path(), repair=False) == ({"claims": {}}, [])
    assert fix_claims.others_by_key([KEY]) == {KEY: []}
    assert release(START) == 0
    assert capsys.readouterr().out == f"registry not-held {KEY}\n"
    assert not (tmp_path / "cai").exists()


@pytest.mark.parametrize("failure", ["mkdir", "open", "read", "replace", "backup"])
def test_registry_io_failure_is_unavailable_and_cleans_temp(failure, monkeypatch, capsys):
    path = write({"claims": {}})
    before = path.read_bytes()
    if failure == "backup":
        path.write_bytes(b"{")
        before = b"{"
    def denied(*args, **kwargs):
        raise PermissionError("denied\n" + "x" * 250)
    if failure == "mkdir":
        monkeypatch.setattr(fix_claims.os, "makedirs", denied)
    elif failure == "open":
        monkeypatch.setattr(fix_claims.os, "open", denied)
    elif failure == "read":
        original = builtins.open
        def read_denied(name, *args, **kwargs):
            if str(name) == str(path):
                return denied()
            return original(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "open", read_denied)
    else:
        monkeypatch.setattr(fix_claims.os, "replace", denied)
    assert register() == 0
    output = capsys.readouterr().out.splitlines()
    assert output[0].startswith("registry unavailable PermissionError:")
    assert "held" not in output[0]
    assert len(output[0]) < 250
    assert not list(path.parent.glob("*.tmp"))
    if failure != "read":
        assert path.read_bytes() == before


def test_release_and_clear_io_failures_and_snapshot_unavailable(remote, monkeypatch, capsys):
    row = entry(session_id=None, started=START)
    path = write({"claims": {KEY: row}})
    def denied(*args, **kwargs):
        raise PermissionError("denied")
    monkeypatch.setattr(fix_claims.os, "replace", denied)
    assert release(START) == 0
    assert capsys.readouterr().out.startswith("registry unavailable PermissionError:")
    assert clear(session="unknown") == 3
    assert capsys.readouterr().out.startswith("registry unavailable PermissionError:")
    assert json.loads(path.read_text())["claims"][KEY] == row
    monkeypatch.setattr(fix_claims.os, "open", denied)
    assert fix_claims.others_by_key([KEY]) is None
    assert release(START) == 0
    assert clear(session="unknown") == 3


def test_missing_temp_on_save_is_unavailable_not_absent(remote, monkeypatch, capsys):
    write({"claims": {KEY: entry(session_id=None, started=START)}})
    def missing(*args):
        raise FileNotFoundError(2, "temporary file missing", args[0])
    monkeypatch.setattr(fix_claims.os, "replace", missing)
    assert release(START) == 0
    assert capsys.readouterr().out.startswith("registry unavailable FileNotFoundError:")
    assert clear(session="unknown") == 3
    assert capsys.readouterr().out.startswith("registry unavailable FileNotFoundError:")


@pytest.mark.parametrize("manual", [False, True])
@pytest.mark.parametrize("operation", ["load", "backup", "save"])
def test_file_disappearing_after_existing_lock_is_unavailable(operation, manual, remote, monkeypatch, capsys):
    path = write({"claims": {KEY: entry(session_id=None, started=START)}})
    if operation == "backup":
        path.write_bytes(b"{")
    def missing(*args, **kwargs):
        raise FileNotFoundError(2, "registry file disappeared", str(path))
    if operation == "backup":
        monkeypatch.setattr(fix_claims.os, "replace", missing)
    else:
        monkeypatch.setattr(fix_claims, operation, missing)
    assert (clear(session="unknown") if manual else release(START)) == (3 if manual else 0)
    assert capsys.readouterr().out.startswith("registry unavailable FileNotFoundError:")
    assert path.exists()


def test_snapshot_missing_read_after_existing_lock_is_unavailable(monkeypatch):
    path = write({"claims": {}})
    def missing(*args, **kwargs):
        raise FileNotFoundError(2, "registry file disappeared", str(path))
    monkeypatch.setattr(fix_claims, "load", missing)
    assert fix_claims.others_by_key([KEY]) is None


@pytest.mark.parametrize("manual", [False, True])
def test_mutating_removal_repairs_corrupt_registry(remote, manual, capsys):
    path = write({"claims": {}})
    path.write_bytes(b"\xff")
    assert (clear() if manual else release(START)) == (3 if manual else 0)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "registry %s %s" % ("not-found" if manual else "not-held", KEY)
    assert lines[1].startswith("registry note the registry could not be parsed and was moved to ")
    assert Path(str(path) + ".bak").read_bytes() == b"\xff"


def test_write_failure_cleans_partial_temp(monkeypatch, capsys):
    path = write({"claims": {}})
    before = path.read_bytes()
    def interrupted(*args, **kwargs):
        args[1].write("partial")
        raise OSError("interrupted write")
    monkeypatch.setattr(fix_claims.json, "dump", interrupted)
    assert register() == 0
    assert capsys.readouterr().out.startswith("registry unavailable OSError:")
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.tmp"))


def test_lock_released_when_body_raises(tmp_path):
    write({"claims": {}})
    with pytest.raises(RuntimeError):
        with fix_claims.hold_lock(create=False) as held:
            assert held
            raise RuntimeError("body failed")
    with fix_claims.hold_lock(create=False, readonly=True, attempts=1) as held:
        assert held


def test_clear_copied_detail_matches_only_exact_fingerprint(remote, monkeypatch, capsys):
    monkeypatch.setenv(fix_claims.SESSION_ID_ENV, "holder")
    assert register() == 0
    capsys.readouterr()
    monkeypatch.setenv(fix_claims.SESSION_ID_ENV, "blocked")
    assert register() == 3
    _, _, platform, session, started = capsys.readouterr().out.splitlines()[0].split()
    for p, s, t, url in [("codex", session, started, URL), (platform, "wrong", started, URL),
                          (platform, session, START, URL), (platform, session, started, URL + "0")]:
        assert clear(p, s, t, url) == 3
        lines = capsys.readouterr().out.splitlines()
        assert lines[0].startswith("registry not-found ")
        if url == URL:
            assert lines[1] == f"registry entry {platform} {session} {started}"
    assert clear(platform, session, started) == 0
    assert capsys.readouterr().out == f"registry cleared {KEY}\n"
    assert clear(platform, session, started) == 3


def test_jira_register_release_and_unknown_clear(remote, capsys):
    args = ["--host", "jira.EXAMPLE.com", "--key", "PROJ-12"]
    assert fix_claims.main(["register", *args, "--branch", "fix/proj"]) == 0
    started = capsys.readouterr().out.splitlines()[0].split()[3]
    assert clear(session="unknown", started=started, url="https://jira.example.com/browse/PROJ-12") == 0
    assert capsys.readouterr().out == "registry cleared jira.example.com/proj-12\n"
    assert fix_claims.main(["release", *args, "--started", started]) == 0


@pytest.mark.parametrize("kwargs,reason", [({"platform": "bad platform"}, "unrecognised"),
                                          ({"session": "bad session"}, "unrecognised"),
                                          ({"started": "2026-13-01T00:00:00.000Z"}, "unrecognised"),
                                          ({"url": "https://github.com/other/app/issues/142"}, "other-repository"),
                                          ({"url": "https://github.com/acme/app/pull/142"}, "unrecognised"),
                                          ({"url": "https://github.com/acme/app/issues"}, "unrecognised"),
                                          ({"url": "bad"}, "unrecognised")])
def test_clear_rejects_before_lock_or_registry(remote, kwargs, reason, monkeypatch, capsys, tmp_path):
    def unexpected(*args, **kwargs):
        pytest.fail("rejected input must not open the registry lock")
    monkeypatch.setattr(fix_claims, "hold_lock", unexpected)
    assert clear(**kwargs) == 2
    assert capsys.readouterr().out.startswith(f"rejected {reason}:")
    assert not (tmp_path / "cai").exists()


def test_clear_no_remote_and_absent_lock(remote, monkeypatch, capsys):
    assert clear() == 3
    assert capsys.readouterr().out == f"registry not-found {KEY}\n"
    monkeypatch.setattr(fix_target, "origin_remote", lambda cwd: None)
    assert clear() == 2
    assert capsys.readouterr().out.startswith("rejected no-remote:")


@pytest.mark.parametrize("argv", [[], ["wrong"], ["register"], ["register", "--owner", "acme", "--branch", "b"],
                                  ["register", "--host", "h", "--key", "K-1", "--issue", "1", "--branch", "b"],
                                  ["release", "--owner", "o", "--repo", "r", "--issue", "bad", "--started", START],
                                  ["clear", URL]])
def test_malformed_cli_exits_one(argv):
    with pytest.raises(SystemExit) as error:
        fix_claims.main(argv)
    assert error.value.code == 1


def test_snapshot_ignores_own_and_expired_but_retains_unknown(monkeypatch):
    monkeypatch.setenv(fix_claims.SESSION_ID_ENV, "mine")
    write({"claims": {KEY: entry(session_id="mine"), "expired": entry(started="2000-01-01T00:00:00.000Z"),
                       "unknown": entry(session_id=None), "broken": entry(session_id=3)}})
    result = fix_claims.others_by_key([KEY, "expired", "unknown", "broken"])
    assert result[KEY] == result["expired"] == result["broken"] == []
    assert result["unknown"][0]["session_id"] is None


def process_env(root, session):
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(root), PYTHONPATH=str(SCRIPT.parent))
    env.pop("CODEX_THREAD_ID", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    if session is not None:
        env["CLAUDE_CODE_SESSION_ID"] = session
    return env


@pytest.mark.parametrize("mode", ["fresh", "stale", "unknown"])
def test_integration_eight_processes_have_exactly_one_holder(mode, tmp_path):
    if mode == "stale":
        write({"claims": {KEY: entry(started="2000-01-01T00:00:00.000Z")}})
    # A shared start time makes all eight processes enter the registry together.
    start = time.time() + 1.5
    code = ("import sys,time,fix_claims; time.sleep(max(0,float(sys.argv[1])-time.time())); "
            "sys.exit(fix_claims.main(sys.argv[2:]))")
    args = ["register", "--owner", "acme", "--repo", "app", "--issue", "142", "--branch", "fix/142"]
    processes = [subprocess.Popen([sys.executable, "-c", code, str(start), *args],
                                  env=process_env(tmp_path, None if mode == "unknown" else f"session-{n}"),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
                 for n in range(8)]
    outputs = [p.communicate(timeout=15) for p in processes]
    assert sorted(p.returncode for p in processes) == [0] + [3] * 7, outputs
    assert sum(out.startswith("registry held ") for out, _ in outputs) == 1, outputs
    assert sum(out.startswith("registry elsewhere ") for out, _ in outputs) == 7, outputs
    data = json.loads(Path(fix_claims.registry_path()).read_text())
    assert list(data["claims"]) == [KEY]
    if mode == "unknown":
        assert data["claims"][KEY]["session_id"] is None
    if mode == "stale":
        assert sum("took over an expired claim" in out for out, _ in outputs) == 1


@contextlib.contextmanager
def held_by_process(root):
    code = ("import sys,fix_claims; "
            "exec('with fix_claims.hold_lock(create=True) as held:\\n"
            " print(held, flush=True)\\n sys.stdin.readline()')")
    process = subprocess.Popen([sys.executable, "-c", code], env=process_env(root, "locker"),
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8")
    try:
        assert process.stdout.readline().strip() == "True"
        yield
    finally:
        process.communicate("stop\n", timeout=10)
        assert process.returncode == 0


def test_integration_readonly_snapshot_lock_missing_free_busy(tmp_path):
    assert fix_claims.others_by_key([KEY]) == {KEY: []}
    row = entry()
    path = write({"claims": {KEY: row}})
    before = path.read_bytes()
    lock = Path(str(path) + ".lock")
    lock_before = lock.stat()
    assert fix_claims.others_by_key([KEY])[KEY][0]["session_id"] == "other"
    assert lock.stat().st_mtime_ns == lock_before.st_mtime_ns
    assert lock.read_bytes() == b""
    with held_by_process(tmp_path):
        start = time.monotonic()
        assert fix_claims.others_by_key([KEY]) is None
        assert time.monotonic() - start < 1
    assert path.read_bytes() == before
    assert fix_claims.others_by_key([KEY])[KEY]


def test_snapshot_opens_lock_readonly_once_and_does_not_sleep(monkeypatch):
    write({"claims": {KEY: entry()}})
    original = fix_claims.os.open
    calls = []
    def record(path, flags, mode):
        calls.append((path, flags))
        return original(path, flags, mode)
    def unexpected_sleep(*args):
        pytest.fail("one-attempt snapshot must not wait")
    monkeypatch.setattr(fix_claims.os, "open", record)
    monkeypatch.setattr(fix_claims.time, "sleep", unexpected_sleep)
    assert fix_claims.others_by_key([KEY])[KEY]
    assert calls == [(fix_claims.registry_path() + ".lock", os.O_RDONLY)]


def test_integration_lock_timeout_within_budget(tmp_path, remote, capsys):
    path = write({"claims": {}})
    with held_by_process(tmp_path):
        for call, expected in [(register, 0), (lambda: release(START), 0), (clear, 3)]:
            start = time.monotonic()
            assert call() == expected
            elapsed = time.monotonic() - start
            assert elapsed < fix_claims.LOCK_WAIT_SECONDS + 1
            assert elapsed >= fix_claims.LOCK_WAIT_SECONDS - 0.1
            assert capsys.readouterr().out.splitlines()[0] == "registry unavailable lock-busy"
    assert json.loads(path.read_text()) == {"claims": {}}
