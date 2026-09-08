"""context_peak.py: peak per-request context occupancy for one
orchestrator session.

The design is docs/design/2026-09-07-track-context-budget-detail.md; each
test names the AC (or D-decision) it stands for, so a failure says what
broke, not just where.
"""
import json
import os

import context_peak
import ledger
import usage_collector


def _usage(input_tokens, cache_read, ephemeral_1h=0, ephemeral_5m=0,
           flat_cache_creation=None, iterations=None):
    """Build a message.usage dict. `flat_cache_creation`, when given,
    replaces the nested `cache_creation` object with the old flat
    `cache_creation_input_tokens` field instead (used to exercise the
    fallback in usage_collector.cache_creation_total())."""
    usage = {"input_tokens": input_tokens, "output_tokens": 1,
              "cache_read_input_tokens": cache_read}
    if flat_cache_creation is not None:
        usage["cache_creation_input_tokens"] = flat_cache_creation
    else:
        usage["cache_creation"] = {"ephemeral_1h_input_tokens": ephemeral_1h,
                                    "ephemeral_5m_input_tokens": ephemeral_5m}
    if iterations is not None:
        usage["iterations"] = iterations
    return usage


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
        fh.write("\n".join(lines) + "\n" if lines else "")
    return path


def _write_ledger(track_dir, records):
    os.makedirs(track_dir, exist_ok=True)
    path = os.path.join(track_dir, "ledger.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")
    return path


# --- AC6-c: peak is the largest occupancy among a session's requests; a
# tie between an earlier and a later record goes to the earlier one -------

def test_peak_returns_largest_occupancy_ties_go_to_first():
    lines = [
        _assistant_line("req-a", "claude-opus-5", _usage(100, 200, 0, 0), "t1"),  # 300
        _assistant_line("req-b", "claude-opus-5", _usage(50, 50, 0, 0), "t2"),    # 100
        _assistant_line("req-c", "claude-opus-5", _usage(150, 150, 0, 0), "t3"),  # 300 (tie with a)
    ]
    problems = []
    records = usage_collector.usage_records(lines, "<test>", problems)
    tokens, record = context_peak.peak(records)
    assert problems == []
    assert tokens == 300
    assert record[1] == "req-a"


# --- AC6-c: the same requestId on two lines is counted once, not twice ----

def test_same_request_id_counted_once():
    usage_a = _usage(100, 100, 0, 0)
    usage_b = _usage(999, 999, 0, 0)  # would dominate the peak if not deduped
    lines = [
        _assistant_line("req-dup", "claude-opus-5", usage_a, "t1"),
        _assistant_line("req-dup", "claude-opus-5", usage_b, "t2"),
    ]
    problems = []
    records = list(usage_collector.usage_records(lines, "<test>", problems))
    assert len(records) == 1
    tokens, record = context_peak.peak(records)
    assert tokens == 200  # from usage_a, the first (and only) yielded record


# --- AC6-e: only the nested cache_creation object is present -- the write
# still counts toward occupancy -------------------------------------------

def test_nested_cache_creation_counted_in_peak():
    usage = _usage(100, 100, ephemeral_1h=300, ephemeral_5m=200)
    tokens, _record = context_peak.peak(
        usage_collector.usage_records(
            [_assistant_line("req-a", "claude-opus-5", usage, "t1")], "<test>", []))
    assert tokens == 100 + 100 + 300 + 200


# --- AC6-e: only the flat cache_creation_input_tokens field is present --
# (nested cache_creation absent) -- the write still counts ----------------

def test_flat_cache_creation_counted_in_peak():
    usage = _usage(100, 100, flat_cache_creation=500)
    tokens, _record = context_peak.peak(
        usage_collector.usage_records(
            [_assistant_line("req-a", "claude-opus-5", usage, "t1")], "<test>", []))
    assert tokens == 100 + 100 + 500


# --- AC6-e: message.usage carries an undocumented `iterations` array that
# repeats the same token fields -- summing it would double-count, so the
# peak must be identical with or without it present -----------------------

def test_iterations_array_does_not_change_the_peak():
    usage_without = _usage(100, 100, ephemeral_1h=50, ephemeral_5m=25)
    usage_with = _usage(100, 100, ephemeral_1h=50, ephemeral_5m=25,
                         iterations=[dict(usage_without) for _ in range(3)])
    tokens_without, _ = context_peak.peak(
        usage_collector.usage_records(
            [_assistant_line("req-a", "claude-opus-5", usage_without, "t1")], "<test>", []))
    tokens_with, _ = context_peak.peak(
        usage_collector.usage_records(
            [_assistant_line("req-b", "claude-opus-5", usage_with, "t1")], "<test>", []))
    assert tokens_with == tokens_without


# --- AC6-c: read_window(path, None, None, []) is unbounded on both sides
# and returns every assistant line without raising -------------------------

def test_read_window_unbounded_returns_all_lines(tmp_path):
    root = str(tmp_path / "projects")
    cwd = str(tmp_path / "proj")
    session_id = "sess-unbounded"
    lines = [
        _assistant_line("req-a", "claude-opus-5", _usage(1, 1), "2026-08-30T00:00:01.000Z"),
        _assistant_line("req-b", "claude-opus-5", _usage(2, 2), "2026-08-30T00:00:02.000Z"),
    ]
    path = _write_session(root, cwd, session_id, lines)
    problems = []
    result = usage_collector.read_window(path, None, None, problems)
    assert problems == []
    assert len(result) == 2


# --- D7 case 1: same requestId with unsplittable cache_creation on two
# lines -- collect()'s problems gets exactly ONE complaint, not two -------

def test_d7_repeated_unsplittable_request_id_flagged_once(tmp_path):
    root = str(tmp_path / "projects")
    cwd = str(tmp_path / "proj")
    session_id = "sess-d7a"
    usage = _usage(100, 100, flat_cache_creation=1234)  # unsplittable: no nested dict
    lines = [
        _assistant_line("req-dup", "claude-opus-5", usage, "2026-08-30T00:00:01.000Z"),
        _assistant_line("req-dup", "claude-opus-5", usage, "2026-08-30T00:00:02.000Z"),
    ]
    _write_session(root, cwd, session_id, lines)

    orchestration, _agents, problems = usage_collector.collect(
        session_id, cwd, None, "2026-08-30T00:10:00.000Z", projects_root=root)

    assert orchestration == {}
    matching = [p for p in problems if "1234" in p]
    assert len(matching) == 1


# --- D7 case 2: same requestId, first line unsplittable, second line
# splittable -- the requestId is marked seen as soon as _valid_usage()
# passes (inside usage_records()), before ephemeral resolution runs. So the
# second (splittable, would-be-good) line is treated as an already-seen
# duplicate and dropped before _aggregate_with_problems() ever sees it.
# The request disappears entirely from collect()'s totals -- accepted (D7),
# never observed on real data, but must not be assumed impossible. ---------

def test_d7_first_unsplittable_second_splittable_request_dropped_entirely(tmp_path):
    root = str(tmp_path / "projects")
    cwd = str(tmp_path / "proj")
    session_id = "sess-d7b"
    unsplittable = _usage(100, 100, flat_cache_creation=1234)
    splittable = _usage(200, 200, ephemeral_1h=50, ephemeral_5m=50)
    lines = [
        _assistant_line("req-dup", "claude-opus-5", unsplittable, "2026-08-30T00:00:01.000Z"),
        _assistant_line("req-dup", "claude-opus-5", splittable, "2026-08-30T00:00:02.000Z"),
    ]
    _write_session(root, cwd, session_id, lines)

    orchestration, _agents, problems = usage_collector.collect(
        session_id, cwd, None, "2026-08-30T00:10:00.000Z", projects_root=root)

    assert orchestration == {}
    assert any("1234" in p for p in problems)


# --- AC6-c / D16: format_line's timestamp and requestId come straight from
# the generator, with no second json.loads downstream ----------------------

def test_format_line_carries_timestamp_and_request_id_verbatim(tmp_path, monkeypatch):
    root = str(tmp_path / "projects")
    cwd = str(tmp_path / "proj")
    session_id = "sess-format"
    ts = "2026-08-30T00:00:01.234Z"
    lines = [_assistant_line("req-format-me", "claude-opus-5", _usage(100, 100), ts)]
    _write_session(root, cwd, session_id, lines)

    tokens, record, problems = context_peak.measure(session_id, cwd, projects_root=root)
    assert problems == []
    line = context_peak.format_line(session_id, tokens, record, context_peak.DEFAULT_WINDOW)
    assert ts in line
    assert "req-format-me" in line


# --- main(): a ledger with only null session_id values yields no session
# to measure -- session_ids() returns [], main() exits 2 -------------------

def test_main_ledger_with_only_null_session_ids_exits_2(tmp_path, capsys):
    track_dir = str(tmp_path / "track")
    _write_ledger(track_dir, [
        {"stage": "build", "outcome": "pass", "session_id": None},
        {"stage": "verify", "outcome": "pass", "session_id": None},
    ])
    assert context_peak.session_ids(track_dir) == []

    exit_code = context_peak.main(["--track-dir", track_dir])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "peak 0" not in captured.out


# --- main(): a transcript that exists but has no usable assistant record
# (empty file) exits 2, names a reason on stderr, and never claims a peak
# of 0 -- zero would assert the session used nothing, which cannot be told
# apart from "could not be measured" -----------------------------------------

def test_main_empty_transcript_exits_2_and_never_reports_peak_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    root = str(tmp_path / "config" / "projects")
    cwd = str(tmp_path / "proj")
    session_id = "sess-empty"
    _write_session(root, cwd, session_id, [])

    exit_code = context_peak.main(
        ["--session-id", session_id, "--project-dir", cwd])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "peak 0" not in captured.out
    assert captured.err.strip() != ""
