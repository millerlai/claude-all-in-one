"""ledger.py's central-ledger write path: D6's write order (`_fit` first,
then central, then `synced`, then per-track), D7's fit target (the central
candidate, not the per-track shape), and D10's import-day marker.

The design is docs/design/2026-08-30-track-usage-accounting-detail.md, the
D6/D7/D10/D14 decisions and the `ledger.append`/`_fit` sections; this is
unit 3 of the work breakdown. Each test names the Verification-table row it
stands for.
"""
import datetime
import json
import os
import subprocess
import sys
import time

import ledger
import usage_collector

LONG_MODEL = "claude-haiku-4-5-2025100%d"
MAX_TOKENS = {key: 999999 for key in usage_collector.TOKEN_KEYS}


def _worst_case_models(n):
    """`n` distinct model ids, each at the maximum five-key token count --
    same shape as tests/test_ledger_usage.py's helper, kept local because
    that file is off limits to import from (standalone scripts, no
    package)."""
    return {(LONG_MODEL % i) + ("x" * 16): dict(MAX_TOKENS) for i in range(n)}


def _read_lines(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh.read().splitlines() if line]


# --- R1 write side: central ledger unwritable -> per-track still lands -----

def test_unwritable_central_location_marks_unsynced_but_still_writes_per_track(
        tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)

    # A regular file sitting where the central ledger's directory needs to
    # be makes that location impossible to create, on both Windows and
    # POSIX -- no permission-bit dance required.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("CAI_USAGE_LEDGER", str(blocker / "cai" / "usage.jsonl"))
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)

    record = ledger.append(track, "build", "failed", note="cannot reach central")

    assert record["synced"] is False
    assert record["sync_error"]
    assert "project" not in record and "track" not in record

    on_disk = _read_lines(os.path.join(track, "ledger.jsonl"))
    assert len(on_disk) == 1
    assert on_disk[0]["synced"] is False
    assert on_disk[0]["sync_error"]


def test_unwritable_central_location_cli_exits_zero(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("CAI_USAGE_LEDGER", str(blocker / "cai" / "usage.jsonl"))

    ledger_py = os.path.join(os.path.dirname(ledger.__file__), "ledger.py")
    env = dict(os.environ)
    env["CAI_USAGE_LEDGER"] = str(blocker / "cai" / "usage.jsonl")
    done = subprocess.run(
        [sys.executable, ledger_py, "append", "--track-dir", track,
         "--stage", "build", "--outcome", "failed", "--note", "cli path"],
        capture_output=True, text=True, encoding="utf-8", env=env)

    assert done.returncode == 0, done.stderr
    record = json.loads(done.stdout)
    assert record["synced"] is False
    assert record["sync_error"]


# --- Blocker: the window's lower bound is scoped to the session, not to
# (session, track) -- a session that moves from one track to another in the
# same conversation must not re-count usage the first track already booked -

def test_window_since_is_scoped_to_session_not_track(tmp_path, monkeypatch):
    track_a = str(tmp_path / "track-a")
    track_b = str(tmp_path / "track-b")
    os.makedirs(track_a)
    os.makedirs(track_b)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-cross-track")

    calls = []

    def fake_collect(session_id, cwd, since, until, projects_root=None):
        calls.append((since, until))
        return {}, {}, []

    monkeypatch.setattr(ledger.usage_collector, "collect", fake_collect)

    record_a = ledger.append(track_a, "build", "passed", note="first track")
    ledger.append(track_b, "design", "passed", note="second track, same session")

    assert len(calls) == 2
    # trackB has never seen this session in its own ledger.jsonl -- the old,
    # (session, track)-scoped lookup would fall back to the import-day
    # floor here and re-scan everything trackA's window already covered.
    assert calls[1][0] == record_a["window_end"]


# --- timing: 500ms tripwire on a ~4MB central ledger (Blocker's fix scans
# the whole file every call, same budget line as usage_collector's 500ms) --

def test_window_since_scan_under_500ms_on_4mb_central_ledger(tmp_path, monkeypatch):
    central_path = tmp_path / "central" / "usage.jsonl"
    os.makedirs(os.path.dirname(str(central_path)), exist_ok=True)
    monkeypatch.setenv("CAI_USAGE_LEDGER", str(central_path))

    # Worst case for a full scan: none of these records belong to the
    # session being looked up, so nothing short-circuits it -- every line
    # has to be parsed and checked.
    line_template = (
        '{"ts":"2026-08-30T00:00:00Z","stage":"build","outcome":"passed",'
        '"artifact":null,"sha256":null,"gate":"auto","note":"",'
        '"orchestration":{},"agents":{},"usage_problems":[],'
        '"window_end":"2026-08-30T00:00:00.000Z","session_id":"sess-%d",'
        '"project":"C:\\\\some\\\\project","track":"track-%d"}\n')
    written = 0
    n = 0
    with open(str(central_path), "w", encoding="utf-8") as fh:
        while written < 4 * 1024 * 1024:
            line = line_template % (n, n % 20)
            fh.write(line)
            written += len(line)
            n += 1
    assert written > 3.5 * 1024 * 1024

    start = time.perf_counter()
    ledger._window_since("sess-not-present")
    elapsed = time.perf_counter() - start

    assert elapsed < 0.5
    print("\n_window_since scan: %.1f ms for %d bytes, %d lines"
         % (elapsed * 1000, written, n))


# --- R3: a session's first attempt on a track never counts usage from
# before the day the central ledger was first created ----------------------

def test_no_backfill_before_the_import_day(tmp_path, monkeypatch):
    config_root = tmp_path / "config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_root))
    monkeypatch.delenv("CAI_USAGE_LEDGER", raising=False)

    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    os.makedirs(config_root / "cai", exist_ok=True)
    with open(usage_collector.data_start_path(), "w", encoding="utf-8") as fh:
        fh.write(today + "\n")

    session_id = "sess-r3"
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", session_id)
    cwd = os.getcwd()
    encoded = usage_collector.encoded_project_dir(cwd)
    proj_dir = os.path.join(str(config_root), "projects", encoded)
    os.makedirs(proj_dir, exist_ok=True)

    def _line(request_id, ts, input_tokens):
        return json.dumps({
            "type": "assistant", "timestamp": ts, "requestId": request_id,
            "message": {"model": "claude-opus-5", "usage": {
                "input_tokens": input_tokens, "output_tokens": 3,
                "cache_read_input_tokens": 0,
                "cache_creation": {"ephemeral_1h_input_tokens": 0,
                                   "ephemeral_5m_input_tokens": 0}}}})

    yesterday_line = _line("req-yesterday", yesterday + "T12:00:00.000Z", 999)
    today_line = _line("req-today", today + "T00:00:00.500Z", 7)
    with open(os.path.join(proj_dir, session_id + ".jsonl"), "w", encoding="utf-8") as fh:
        fh.write(yesterday_line + "\n" + today_line + "\n")

    track = str(tmp_path / "track")
    os.makedirs(track)
    record = ledger.append(track, "build", "passed", note="r3")

    assert record["orchestration"] == {"claude-opus-5": {
        "input_tokens": 7, "output_tokens": 3, "cache_read_input_tokens": 0,
        "ephemeral_1h_input_tokens": 0, "ephemeral_5m_input_tokens": 0}}


# --- R5: both writes stay inside one atomic write's size -------------------

def test_worst_case_record_both_writes_stay_under_max_record(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-worst-case")

    orchestration = _worst_case_models(20)
    agents = _worst_case_models(20)

    def fake_collect(session_id, cwd, since, until, projects_root=None):
        return dict(orchestration), dict(agents), []

    monkeypatch.setattr(ledger.usage_collector, "collect", fake_collect)

    record = ledger.append(track, "build", "failed", note="n" * 3800)

    central_path = usage_collector.central_ledger_path()
    central_lines = [line for line in open(central_path, "rb").read().split(b"\n") if line]
    per_track_lines = [
        line for line in open(os.path.join(track, "ledger.jsonl"), "rb").read().split(b"\n")
        if line]

    assert len(central_lines) == 1
    assert len(per_track_lines) == 1
    assert len(central_lines[0]) + 1 <= ledger.MAX_RECORD
    assert len(per_track_lines[0]) + 1 <= ledger.MAX_RECORD

    central = json.loads(central_lines[0])
    assert central["project"] == os.getcwd()
    assert central["track"] == os.path.basename(os.path.normpath(track))
    assert "synced" not in central and "sync_error" not in central
    assert record.get("usage_collapsed") is True


# --- R5: concurrent writers to one central ledger neither tear nor clobber -

WORKER = '''
import sys
sys.path.insert(0, %r)
import ledger

track, tag, count = sys.argv[1], sys.argv[2], int(sys.argv[3])
for n in range(count):
    ledger.append(track, "build", "failed", note="%%s-%%04d-%%s" %% (tag, n, "x" * 100))
''' % os.path.dirname(ledger.__file__)

WRITERS = 8
PER_WRITER = 50


def test_concurrent_writers_share_one_central_ledger_without_loss(tmp_path, monkeypatch):
    central_path = tmp_path / "central" / "usage.jsonl"
    monkeypatch.setenv("CAI_USAGE_LEDGER", str(central_path))
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)

    worker = tmp_path / "worker.py"
    worker.write_text(WORKER, encoding="utf-8")

    env = dict(os.environ)
    running = []
    for index in range(WRITERS):
        track = tmp_path / ("track-%d" % index)
        os.makedirs(track, exist_ok=True)
        running.append(subprocess.Popen(
            [sys.executable, str(worker), str(track), "w%d" % index, str(PER_WRITER)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env))
    for process in running:
        _, err = process.communicate()
        assert process.returncode == 0, err.decode("utf-8", "replace")

    with open(str(central_path), "rb") as fh:
        lines = [line for line in fh.read().split(b"\n") if line]

    torn = 0
    notes = set()
    for line in lines:
        try:
            row = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            torn += 1
            continue
        note = row["note"]
        notes.add(note.split("-")[0] + "-" + note.split("-")[1])

    expected = WRITERS * PER_WRITER
    assert (len(lines), torn) == (expected, 0)
    assert len(notes) == expected


# --- deep project path: collapse fires earlier, both writes stay in bounds -

def test_deep_project_path_triggers_collapse_and_stays_in_bounds(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-deep-path")

    # Near the Windows MAX_PATH ceiling, eating heavily into the central
    # candidate's 3840-byte budget (D7).
    deep_cwd = "C:\\" + "\\".join(["deep-directory-name-segment"] * 8)
    monkeypatch.setattr(os, "getcwd", lambda: deep_cwd)

    orchestration = _worst_case_models(20)
    agents = _worst_case_models(20)

    def fake_collect(session_id, cwd, since, until, projects_root=None):
        return dict(orchestration), dict(agents), []

    monkeypatch.setattr(ledger.usage_collector, "collect", fake_collect)

    record = ledger.append(track, "build", "passed", note="short")

    assert record.get("usage_collapsed") is True

    central_path = usage_collector.central_ledger_path()
    central_lines = [line for line in open(central_path, "rb").read().split(b"\n") if line]
    per_track_lines = [
        line for line in open(os.path.join(track, "ledger.jsonl"), "rb").read().split(b"\n")
        if line]
    assert len(central_lines[0]) + 1 <= ledger.MAX_RECORD
    assert len(per_track_lines[0]) + 1 <= ledger.MAX_RECORD

    central = json.loads(central_lines[0])
    assert central["project"] == deep_cwd


# --- `_fit` refusing to shrink leaves neither file written ------------------

def test_fit_returning_none_leaves_no_orphan(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-refused")
    monkeypatch.setattr(ledger, "CENTRAL_FIT_LIMIT", 10)

    monkeypatch.setattr(ledger.usage_collector, "collect",
                        lambda *a, **k: ({}, {}, []))

    central_path = usage_collector.central_ledger_path()
    try:
        ledger.append(track, "build", "failed", note="too small to ever fit")
        assert False, "expected LedgerError"
    except ledger.LedgerError:
        pass

    assert not os.path.exists(central_path)
    assert not os.path.exists(os.path.join(track, "ledger.jsonl"))


# --- Major-2: sync_error can still blow the per-track record past
# MAX_RECORD -- SYNC_RESERVE is a fixed budget, but json.dumps doubles every
# backslash, and a Windows OSError message is mostly backslash-heavy paths --

def test_sync_error_overflow_is_shrunk_to_keep_per_track_under_max_record(
        tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-sync-overflow")
    monkeypatch.setattr(os, "getcwd", lambda: "C:\\a")

    orchestration = _worst_case_models(9)

    def fake_collect(session_id, cwd, since, until, projects_root=None):
        return dict(orchestration), {}, []

    monkeypatch.setattr(ledger.usage_collector, "collect", fake_collect)

    central_path = usage_collector.central_ledger_path()
    real_write_line = ledger._write_line
    # An OSError whose message is almost entirely backslashes -- exactly
    # what a Windows path-not-found error looks like -- so json.dumps
    # doubles nearly every character of it.
    long_error = "\\" * 200

    def fake_write_line(path, line):
        if path == central_path:
            raise OSError(long_error)
        return real_write_line(path, line)

    monkeypatch.setattr(ledger, "_write_line", fake_write_line)

    ledger.append(track, "build", "failed", note="n" * 3800)

    per_track_lines = [
        line for line in open(os.path.join(track, "ledger.jsonl"), "rb").read().split(b"\n")
        if line]
    assert len(per_track_lines) == 1
    assert len(per_track_lines[0]) + 1 <= ledger.MAX_RECORD
