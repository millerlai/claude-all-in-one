"""usage_collector.py: reads transcripts, dedupes by requestId, aggregates
per-model token usage for one session's time window.

The design is docs/design/2026-08-30-track-usage-accounting-detail.md, the
`usage_collector` section; each test names the Verification-table row it
stands for so a failure says what broke, not just where.
"""
import datetime
import json
import os
import time

import usage_collector

TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
             "ephemeral_1h_input_tokens", "ephemeral_5m_input_tokens")


def _usage(n):
    """Four distinct non-zero token counts, offset by n so fixtures with
    several rows do not accidentally share a value. The combined cache-write
    figure is split across the two TTL buckets the way real transcripts do:
    nested under `cache_creation`, not as a flat `cache_creation_input_tokens`
    key (that key no longer exists in TOKEN_KEYS -- see usage_collector.py)."""
    return {"input_tokens": 100 + n, "output_tokens": 10 + n,
            "cache_read_input_tokens": 500 + n,
            "cache_creation": {"ephemeral_1h_input_tokens": 600 + n,
                                "ephemeral_5m_input_tokens": 400 + n}}


def _expected(usage_n):
    """The five TOKEN_KEYS totals `_usage(n)` resolves to, for asserting
    against collector output (which never carries the nested shape)."""
    creation = usage_n["cache_creation"]
    return {"input_tokens": usage_n["input_tokens"],
            "output_tokens": usage_n["output_tokens"],
            "cache_read_input_tokens": usage_n["cache_read_input_tokens"],
            "ephemeral_1h_input_tokens": creation["ephemeral_1h_input_tokens"],
            "ephemeral_5m_input_tokens": creation["ephemeral_5m_input_tokens"]}


def _assistant_line(request_id, model, usage, ts):
    return json.dumps({
        "type": "assistant",
        "timestamp": ts,
        "requestId": request_id,
        "message": {"model": model, "usage": usage},
    })


def _write_session(root, cwd, session_id, lines):
    encoded = usage_collector.encoded_project_dir(cwd)
    proj_dir = os.path.join(root, encoded)
    os.makedirs(proj_dir, exist_ok=True)
    path = os.path.join(proj_dir, session_id + ".jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


# --- UC1: per-model, five token types, three match message.usage verbatim,
# two are message.usage.cache_creation's ephemeral_1h/5m split -------------

def test_two_models_five_nonzero_token_types_keys_match_source(tmp_path):
    root = str(tmp_path / "projects")
    cwd = str(tmp_path / "proj")
    session_id = "sess-uc1"
    usage_a = _usage(1)
    usage_b = _usage(2)
    lines = [
        _assistant_line("req-a", "claude-opus-5", usage_a, "2026-08-30T00:00:01.000Z"),
        _assistant_line("req-b", "claude-sonnet-5", usage_b, "2026-08-30T00:00:02.000Z"),
    ]
    _write_session(root, cwd, session_id, lines)

    orchestration, agents, problems = usage_collector.collect(
        session_id, cwd, None, "2026-08-30T00:10:00.000Z", projects_root=root)

    assert problems == []
    assert agents == {}
    assert set(orchestration.keys()) == {"claude-opus-5", "claude-sonnet-5"}
    assert set(orchestration["claude-opus-5"].keys()) == set(TOKEN_KEYS)
    assert orchestration["claude-opus-5"] == _expected(usage_a)
    assert orchestration["claude-sonnet-5"] == _expected(usage_b)


# --- D4: the window is left-open, right-closed -- `since` itself belongs to
# the window before, `until` itself belongs to this one (Major-3 guard) ----

def test_window_excludes_since_and_includes_until(tmp_path):
    root = str(tmp_path / "projects")
    cwd = str(tmp_path / "proj")
    session_id = "sess-boundary"
    since = "2026-08-30T00:00:01.000Z"
    until = "2026-08-30T00:00:02.000Z"
    usage_at_since = _usage(1)
    usage_at_until = _usage(2)
    lines = [
        _assistant_line("req-since", "claude-opus-5", usage_at_since, since),
        _assistant_line("req-until", "claude-opus-5", usage_at_until, until),
    ]
    _write_session(root, cwd, session_id, lines)

    orchestration, agents, problems = usage_collector.collect(
        session_id, cwd, since, until, projects_root=root)

    assert problems == []
    assert agents == {}
    # Only the line at `until` counts -- the one at `since` belongs to the
    # window that ended there, not this one, so its tokens must be absent.
    assert orchestration == {"claude-opus-5": _expected(usage_at_until)}


# --- UC2: same source twice is identical; 25 lines / 5 requestId dedup -----

def test_rerun_is_byte_identical(tmp_path):
    root = str(tmp_path / "projects")
    cwd = str(tmp_path / "proj")
    session_id = "sess-uc2a"
    lines = [
        _assistant_line("req-a", "claude-opus-5", _usage(1), "2026-08-30T00:00:01.000Z"),
        _assistant_line("req-b", "claude-sonnet-5", _usage(2), "2026-08-30T00:00:02.000Z"),
    ]
    _write_session(root, cwd, session_id, lines)

    first = usage_collector.collect(session_id, cwd, None, "2026-08-30T00:10:00.000Z", projects_root=root)
    second = usage_collector.collect(session_id, cwd, None, "2026-08-30T00:10:00.000Z", projects_root=root)
    assert first == second


def test_25_lines_5_request_ids_dedup_to_5(tmp_path):
    root = str(tmp_path / "projects")
    cwd = str(tmp_path / "proj")
    session_id = "sess-uc2b"
    usage = _usage(7)
    lines = []
    for req_number in range(5):
        request_id = "req-%d" % req_number
        for repeat in range(5):
            ts = "2026-08-30T00:00:%02d.000Z" % (req_number * 5 + repeat)
            lines.append(_assistant_line(request_id, "claude-opus-5", usage, ts))
    _write_session(root, cwd, session_id, lines)

    orchestration, agents, problems = usage_collector.collect(
        session_id, cwd, None, "2026-08-30T00:10:00.000Z", projects_root=root)

    assert problems == []
    counted = orchestration["claude-opus-5"]
    expected = _expected(usage)
    for key in TOKEN_KEYS:
        assert counted[key] == expected[key] * 5


# --- R1: unrecognisable content leaves both columns dict, empty, flagged ---

def test_unrecognisable_transcript_stays_dict_empty_and_flagged(tmp_path):
    root = str(tmp_path / "projects")
    cwd = str(tmp_path / "proj")
    session_id = "sess-r1"
    encoded = usage_collector.encoded_project_dir(cwd)
    proj_dir = os.path.join(root, encoded)
    os.makedirs(proj_dir, exist_ok=True)
    path = os.path.join(proj_dir, session_id + ".jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("this is not json\nneither is this line{{{\n")

    orchestration, agents, problems = usage_collector.collect(
        session_id, cwd, None, "2026-08-30T00:10:00.000Z", projects_root=root)

    assert isinstance(orchestration, dict)
    assert isinstance(agents, dict)
    assert orchestration == {}
    assert agents == {}
    assert problems != []
    # No fabricated zero anywhere -- an empty dict has no entries to fake.
    assert orchestration == {} and agents == {}


def test_missing_session_transcript_stays_dict_and_flagged(tmp_path):
    root = str(tmp_path / "projects")
    cwd = str(tmp_path / "proj")
    orchestration, agents, problems = usage_collector.collect(
        "no-such-session", cwd, None, "2026-08-30T00:10:00.000Z", projects_root=root)
    assert orchestration == {}
    assert agents == {}
    assert problems != []


# --- Major-1: a subagent line inside the window must not be dropped because
# the file's mtime landed after the window's upper bound -- mtime and the
# line's own `timestamp` are two different clocks -------------------------

def test_subagent_line_inside_window_survives_a_late_file_mtime(tmp_path):
    root = str(tmp_path / "projects")
    cwd = str(tmp_path / "proj")
    session_id = "sess-major1"
    encoded = usage_collector.encoded_project_dir(cwd)
    sub_dir = os.path.join(root, encoded, session_id, "subagents")
    os.makedirs(sub_dir, exist_ok=True)
    path = os.path.join(sub_dir, "agent-1.jsonl")
    usage = _usage(1)
    line = _assistant_line("req-a", "claude-opus-5", usage, "2026-08-30T10:00:03.000Z")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(line + "\n")

    # The line's own timestamp (10:00:03) is inside (since, until], but disk
    # flush / antivirus / a synced home directory can make the file's mtime
    # land after `until` (10:00:05) even though nothing in it does.
    until_epoch = datetime.datetime(
        2026, 8, 30, 10, 0, 5, tzinfo=datetime.timezone.utc).timestamp()
    late_mtime = until_epoch + 0.5
    os.utime(path, (late_mtime, late_mtime))

    orchestration, agents, problems = usage_collector.collect(
        session_id, cwd, "2026-08-30T10:00:00.000Z", "2026-08-30T10:00:05.000Z",
        projects_root=root)

    assert agents == {"claude-opus-5": _expected(usage)}


# --- N2a addendum: cache_creation missing but the combined total is
# nonzero -- must not guess a TTL and must not silently drop it -------------

def test_missing_cache_creation_with_nonzero_total_is_flagged_not_guessed(tmp_path):
    root = str(tmp_path / "projects")
    cwd = str(tmp_path / "proj")
    session_id = "sess-n2a"
    # No nested cache_creation object, but the old combined field is present
    # and nonzero -- exactly the shape that has never been observed for real
    # (measured across 9,013 usage objects) but must still not be guessed at.
    usage = {"input_tokens": 100, "output_tokens": 10,
             "cache_read_input_tokens": 500, "cache_creation_input_tokens": 1234}
    lines = [_assistant_line("req-a", "claude-opus-5", usage, "2026-08-30T00:00:01.000Z")]
    _write_session(root, cwd, session_id, lines)

    orchestration, agents, problems = usage_collector.collect(
        session_id, cwd, None, "2026-08-30T00:10:00.000Z", projects_root=root)

    assert orchestration == {}
    assert agents == {}
    assert any("1234" in problem for problem in problems)


# --- timing: 500ms tripwire on an ~4MB transcript --------------------------

def test_collect_under_500ms_on_4mb_transcript(tmp_path):
    root = str(tmp_path / "projects")
    cwd = str(tmp_path / "proj")
    session_id = "sess-timing"

    # ~180 bytes/line -> ~23000 lines for ~4MB, each its own requestId so
    # dedup work is exercised too, not just parsing.
    lines = []
    for n in range(23000):
        ts = "2026-08-30T%02d:%02d:%02d.000Z" % ((n // 3600) % 24, (n // 60) % 60, n % 60)
        lines.append(_assistant_line("req-%d" % n, "claude-opus-5", _usage(n), ts))
    path = _write_session(root, cwd, session_id, lines)
    assert os.path.getsize(path) > 3.5 * 1024 * 1024

    start = time.perf_counter()
    orchestration, agents, problems = usage_collector.collect(
        session_id, cwd, None, "2027-01-01T00:00:00.000Z", projects_root=root)
    elapsed = time.perf_counter() - start

    assert problems == []
    assert orchestration["claude-opus-5"]["input_tokens"] > 0
    assert elapsed < 0.5


# --- aggregate(): the pure per-line function, called directly --------------

def test_aggregate_direct_dedup_and_keys():
    usage = _usage(3)
    lines = [
        _assistant_line("req-x", "claude-opus-5", usage, "2026-08-30T00:00:01.000Z"),
        _assistant_line("req-x", "claude-opus-5", usage, "2026-08-30T00:00:01.500Z"),
    ]
    result = usage_collector.aggregate(lines)
    assert result == {"claude-opus-5": _expected(usage)}


# --- small path-rule sanity for the remaining public functions -------------

def test_encoded_project_dir_replaces_non_alnum():
    assert usage_collector.encoded_project_dir(r"D:\project\claude-all-in-one") == \
        "D--project-claude-all-in-one"


def test_config_root_honours_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert usage_collector.config_root() == str(tmp_path)


def test_central_ledger_and_data_start_are_siblings(monkeypatch, tmp_path):
    monkeypatch.delenv("CAI_USAGE_LEDGER", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    ledger_path = usage_collector.central_ledger_path()
    start_path = usage_collector.data_start_path()
    assert os.path.dirname(ledger_path) == os.path.dirname(start_path)
    assert ledger_path == os.path.join(str(tmp_path), "cai", "usage.jsonl")
    assert start_path == os.path.join(str(tmp_path), "cai", "usage-start.txt")


def test_central_ledger_path_honours_env_override(monkeypatch, tmp_path):
    override = str(tmp_path / "custom-usage.jsonl")
    monkeypatch.setenv("CAI_USAGE_LEDGER", override)
    assert usage_collector.central_ledger_path() == override
    assert usage_collector.data_start_path() == str(tmp_path / "usage-start.txt")


def test_session_id_from_env_missing_is_none(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    assert usage_collector.session_id_from_env() is None


def test_session_id_from_env_present(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-42")
    assert usage_collector.session_id_from_env() == "sess-42"
