"""viewer.py's ### codex_source / classify_codex components.

Fixtures are entirely synthetic sqlite databases and rollout files -- shapes
match what unit 3's task brief confirmed read-only against real local Codex
data (column names, the id/thread_id join, the rollout-filename-tail-as-id
trick), but no content is copied from anything real.
"""
import datetime as dt
import json
import os
import sqlite3

import viewer

BASE_MS = 1_800_000_000_000  # an arbitrary fixed "now" for deterministic math


def _iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).isoformat().replace(
        "+00:00", "Z")


# ============================================================ fixtures ====

def _rollout_line(ordinal, type_, payload, ms=None):
    line = {"ordinal": ordinal, "type": type_, "payload": payload}
    if ms is not None:
        line["timestamp"] = _iso(ms)
    return line


def _session_meta(originator="codex-tui", thread_source="user", cwd="D:\\made-up\\proj",
                  source=None):
    payload = {"originator": originator, "thread_source": thread_source,
               "cwd": cwd, "session_id": "made-up-session"}
    if source is not None:  # "cli" / "vscode", confirmed read-only 2026-09-26
        payload["source"] = source
    return _rollout_line(0, "session_meta", payload, ms=BASE_MS)


def _task_started(ordinal, ms):
    return _rollout_line(ordinal, "event_msg",
                         {"type": "task_started", "turn_id": "turn-1"}, ms=ms)


def _task_complete(ordinal, ms):
    return _rollout_line(ordinal, "event_msg",
                         {"type": "task_complete", "turn_id": "turn-1"}, ms=ms)


def _function_call(ordinal, call_id, name, ms=None, arguments="{}"):
    return _rollout_line(ordinal, "response_item",
                         {"type": "function_call", "call_id": call_id, "name": name,
                          "arguments": arguments}, ms=ms)


def _message(ordinal, role, content, ms=None):
    return _rollout_line(ordinal, "response_item",
                         {"type": "message", "role": role, "content": content}, ms=ms)


def _output_text(text):
    return {"type": "output_text", "text": text}


def _function_call_output(ordinal, call_id, ms=None):
    return _rollout_line(ordinal, "response_item",
                         {"type": "function_call_output", "call_id": call_id, "output": "ok"},
                         ms=ms)


def _write_rollout(path, lines, mtime_ms=BASE_MS):
    # Real mtimes are "now" (2026), while BASE_MS is a fixed, arbitrary
    # instant used as "now" throughout these tests -- pin the file's mtime
    # to it so the fallback path's 24h-age filter sees what the test means.
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(json.dumps(line) + "\n")
    if mtime_ms is not None:
        os.utime(path, (mtime_ms / 1000, mtime_ms / 1000))


def _make_state_db(codex_home, n, threads, spawn_edges=(), sources=None):
    path = os.path.join(codex_home, "state_%d.sqlite" % n)
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE threads (
        id TEXT, rollout_path TEXT, cwd TEXT, updated_at_ms INTEGER,
        thread_source TEXT, originator TEXT, archived INTEGER, name TEXT)""")
    conn.executemany(
        "INSERT INTO threads (id, rollout_path, cwd, updated_at_ms, thread_source, "
        "originator, archived, name) VALUES (?,?,?,?,?,?,?,?)", threads)
    # The real `source` column ("cli" / "vscode", confirmed read-only
    # 2026-09-26) only when a test asks for it, so the others keep exercising
    # the older schema without one.
    if sources is not None:
        conn.execute("ALTER TABLE threads ADD COLUMN source TEXT")
        conn.executemany("UPDATE threads SET source = ? WHERE id = ?",
                         [(source, tid) for tid, source in sources.items()])
    # Real schema, confirmed read-only 2026-09-25 (verify round 2): columns
    # parent_thread_id, child_thread_id, status -- only "open" seen locally.
    conn.execute("""CREATE TABLE thread_spawn_edges (
        parent_thread_id TEXT, child_thread_id TEXT, status TEXT)""")
    conn.executemany(
        "INSERT INTO thread_spawn_edges (parent_thread_id, child_thread_id, status) "
        "VALUES (?,?,?)", spawn_edges)
    conn.commit()
    conn.close()
    return path


def _make_history_db(codex_home, n, turns):
    path = os.path.join(codex_home, "thread_history_%d.sqlite" % n)
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE thread_turns (
        thread_id TEXT, turn_id TEXT, status TEXT, started_at INTEGER,
        completed_at INTEGER, duration_ms INTEGER)""")
    conn.executemany(
        "INSERT INTO thread_turns (thread_id, turn_id, status, started_at, completed_at, "
        "duration_ms) VALUES (?,?,?,?,?,?)", turns)
    conn.commit()
    conn.close()
    return path


def _thread_id(n):
    prefix = "made-up-thread-uuid-"
    return prefix + str(n).zfill(36 - len(prefix))  # 36 chars total


# ==================================================== classify_codex ====

def test_empty_tail_is_unknown():
    out = viewer.classify_codex("inProgress", [], BASE_MS, BASE_MS)
    assert out["state"] == "unknown"
    assert out["certainty"] == "confirmed"


def test_in_progress_with_unresolved_request_user_input_is_question():
    tail = [_function_call(1, "call-1", "request_user_input", ms=BASE_MS)]
    out = viewer.classify_codex("inProgress", tail, BASE_MS, BASE_MS)
    assert out["state"] == "question"
    assert out["certainty"] == "confirmed"
    assert out["entryId"] == "call-1"


def test_in_progress_with_unresolved_other_call_past_threshold_is_permission():
    tail = [_function_call(1, "call-2", "send_message", ms=BASE_MS)]
    now_ms = BASE_MS + 30001
    out = viewer.classify_codex("inProgress", tail, now_ms, BASE_MS)
    assert out["state"] == "permission"
    assert out["certainty"] == "inferred"
    assert out["entryId"] == "call-2"


def test_in_progress_with_unresolved_other_call_within_threshold_is_working():
    tail = [_function_call(1, "call-3", "send_message", ms=BASE_MS)]
    now_ms = BASE_MS + 1000
    out = viewer.classify_codex("inProgress", tail, now_ms, BASE_MS)
    assert out["state"] == "working"


def test_in_progress_with_resolved_call_is_working():
    tail = [_function_call(1, "call-4", "send_message", ms=BASE_MS),
           _function_call_output(2, "call-4", ms=BASE_MS)]
    now_ms = BASE_MS + 60000
    out = viewer.classify_codex("inProgress", tail, now_ms, BASE_MS)
    assert out["state"] == "working"


def test_in_progress_uses_last_unresolved_call_not_first():
    tail = [_function_call(1, "call-5", "send_message", ms=BASE_MS),
           _function_call_output(2, "call-5", ms=BASE_MS),
           _function_call(3, "call-6", "request_user_input", ms=BASE_MS)]
    out = viewer.classify_codex("inProgress", tail, BASE_MS, BASE_MS)
    assert out["state"] == "question"
    assert out["entryId"] == "call-6"


def test_in_progress_event_timestamp_overrides_tail_mtime_for_threshold():
    # the function_call's own timestamp is 40s before now -> past threshold,
    # even though tail_mtime_ms (fallback) is "now" and would not be.
    tail = [_function_call(1, "call-7", "send_message", ms=BASE_MS - 40000)]
    out = viewer.classify_codex("inProgress", tail, BASE_MS, BASE_MS)
    assert out["state"] == "permission"


def test_not_in_progress_with_dangling_async_question_in_last_turn():
    tail = [_task_started(1, BASE_MS - 5000),
           _function_call(2, "call-8", "request_user_input_async", ms=BASE_MS)]
    out = viewer.classify_codex("completed", tail, BASE_MS, BASE_MS)
    assert out["state"] == "question"
    assert out["certainty"] == "confirmed"


def test_not_in_progress_no_signal_is_done():
    tail = [_task_started(1, BASE_MS - 5000), _task_complete(2, BASE_MS)]
    out = viewer.classify_codex("completed", tail, BASE_MS, BASE_MS)
    assert out["state"] == "done"
    assert out["notes"] == []


def test_not_in_progress_failed_status_notes_it():
    tail = [_task_started(1, BASE_MS - 5000), _task_complete(2, BASE_MS)]
    out = viewer.classify_codex("failed", tail, BASE_MS, BASE_MS)
    assert out["state"] == "done"
    assert out["notes"] == ["\u4e0a\u4e00\u8f2a failed\uff0finterrupted"]


def test_not_in_progress_interrupted_status_notes_it():
    tail = [_task_started(1, BASE_MS - 5000)]
    out = viewer.classify_codex("interrupted", tail, BASE_MS, BASE_MS)
    assert out["notes"] == ["\u4e0a\u4e00\u8f2a failed\uff0finterrupted"]


def test_fallback_in_progress_inferred_from_task_started_after_task_complete():
    tail = [_task_complete(1, BASE_MS - 5000), _task_started(2, BASE_MS)]
    out = viewer.classify_codex(None, tail, BASE_MS, BASE_MS)
    assert out["state"] == "working"
    assert out["certainty"] == "inferred"


def test_fallback_not_in_progress_when_task_complete_is_last():
    tail = [_task_started(1, BASE_MS - 5000), _task_complete(2, BASE_MS)]
    out = viewer.classify_codex(None, tail, BASE_MS, BASE_MS)
    assert out["state"] == "done"
    assert out["certainty"] == "confirmed"  # not-in-progress "done" branch is confirmed


# ============== D2: summary (rule 1) / recent (rule 2) / subagents (rule 3)
# Key names (response_item/message/role/content[].type=="output_text",
# function_call.arguments as a JSON string with "agent_type" for spawn_agent
# and "questions" for request_user_input(_async), thread_spawn_edges'
# columns) confirmed read-only against real local Codex data 2026-09-25
# (verify round 2); no conversation content copied.

def test_last_assistant_text_codex_returns_last_assistant_message():
    tail = [_message(1, "user", [{"type": "input_text", "text": "問題"}]),
           _message(2, "assistant", [_output_text("先回的")]),
           _message(3, "assistant", [_output_text("後回的，應該取這句")])]
    assert viewer._last_assistant_text_codex(tail) == "後回的，應該取這句"


def test_last_assistant_text_codex_ignores_non_assistant_roles():
    tail = [_message(1, "assistant", [_output_text("這句才對")]),
           _message(2, "developer", [{"type": "input_text", "text": "不算"}])]
    assert viewer._last_assistant_text_codex(tail) == "這句才對"


def test_last_assistant_text_codex_none_when_last_assistant_message_has_no_output_text():
    tail = [_function_call(1, "call-1", "send_message")]
    assert viewer._last_assistant_text_codex(tail) is None


def test_recent_codex_actions_keeps_last_eight_in_order():
    tail = [_function_call(i, "call-%d" % i, "wait", ms=BASE_MS,
                           arguments=json.dumps({"cmd": "step-%d" % i}))
           for i in range(10)]
    recent = viewer._recent_codex_actions(tail, BASE_MS)
    assert [r["input"] for r in recent] == ["step-%d" % i for i in range(2, 10)]


def test_recent_codex_actions_reads_the_cmd_key():
    tail = [_function_call(1, "call-1", "exec_command", ms=BASE_MS,
                           arguments=json.dumps({"cmd": "pytest -q"}))]
    recent = viewer._recent_codex_actions(tail, BASE_MS)
    assert recent[0]["tool"] == "exec_command"
    assert recent[0]["input"] == "pytest -q"


def test_recent_codex_actions_at_falls_back_to_tail_mtime_without_a_timestamp():
    tail = [_function_call(1, "call-1", "wait")]  # no ms -> no "timestamp" key
    recent = viewer._recent_codex_actions(tail, BASE_MS)
    assert recent[0]["at"] == BASE_MS


def test_codex_question_payload_decodes_arguments():
    questions = [{"question": "要重新命名嗎？", "header": "h", "options":
                 [{"label": "是", "description": "d"}, {"label": "否", "description": "d"}]}]
    tail = [_function_call(1, "call-1", "request_user_input", ms=BASE_MS,
                           arguments=json.dumps({"questions": questions}))]
    out = viewer.classify_codex("inProgress", tail, BASE_MS, BASE_MS)
    assert out["question"]["text"] == "要重新命名嗎？"
    assert out["question"]["options"] == ["是", "否"]


def test_codex_async_question_payload_decodes_arguments():
    questions = [{"question": "非同步問題", "header": "h", "options": []}]
    tail = [_task_started(1, BASE_MS - 5000),
           _function_call(2, "call-2", "request_user_input_async", ms=BASE_MS,
                          arguments=json.dumps({"questions": questions}))]
    out = viewer.classify_codex("completed", tail, BASE_MS, BASE_MS)
    assert out["state"] == "question"
    assert out["question"]["text"] == "非同步問題"


def test_codex_tail_subagents_lists_unresolved_spawn_agent_calls():
    tail = [_function_call(1, "call-1", "spawn_agent", ms=BASE_MS,
                           arguments=json.dumps({"agent_type": "reviewer",
                                                 "task_name": "t", "message": "m"}))]
    assert viewer._codex_tail_subagents(tail) == ["reviewer"]


def test_codex_tail_subagents_excludes_resolved_calls():
    tail = [_function_call(1, "call-1", "spawn_agent", ms=BASE_MS,
                           arguments=json.dumps({"agent_type": "reviewer"})),
           _function_call_output(2, "call-1", ms=BASE_MS)]
    assert viewer._codex_tail_subagents(tail) == []


# ======================================================= codex_rows ====
# primary (sqlite) path

def test_codex_rows_returns_empty_when_process_count_is_zero(tmp_path):
    codex_home = str(tmp_path)
    tid = _thread_id(1)
    rollout_path = os.path.join(codex_home, "sessions", "rollout-2026-09-24T00-00-00-%s.jsonl" % tid)
    _write_rollout(rollout_path, [_session_meta(), _task_started(1, BASE_MS)])
    _make_state_db(codex_home, 1, [(tid, rollout_path, "D:\\made-up\\proj", BASE_MS,
                                    "user", "codex-tui", 0, "made-up-name")])
    _make_history_db(codex_home, 1, [(tid, "turn-1", "inProgress", BASE_MS, None, None)])

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 0)
    assert rows == []
    assert problems == []


def test_codex_rows_builds_a_row_with_identifying_fields(tmp_path):
    codex_home = str(tmp_path)
    tid = _thread_id(2)
    rollout_path = os.path.join(codex_home, "sessions", "rollout-2026-09-24T00-00-00-%s.jsonl" % tid)
    _write_rollout(rollout_path, [_session_meta(cwd=os.path.join(os.sep, "made-up", "project-y")),
                                  _task_started(1, BASE_MS), _task_complete(2, BASE_MS)])
    _make_state_db(codex_home, 1, [(tid, rollout_path, os.path.join(os.sep, "made-up", "project-y"), BASE_MS,
                                    "user", "codex-tui", 0, "made-up-name")])
    _make_history_db(codex_home, 1, [(tid, "turn-1", "completed", BASE_MS, BASE_MS, 10)])

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 5)
    assert problems == []
    assert len(rows) == 1
    row = rows[0]
    assert row["key"] == "codex:%s" % tid
    assert row["platform"] == "codex"
    assert row["project"] == "project-y"
    assert row["cwd"] == os.path.join(os.sep, "made-up", "project-y")
    assert row["sessionId"] == tid
    assert row["name"] == "made-up-name"
    assert row["state"] == "done"


def test_codex_rows_excludes_archived_exec_and_subagent_threads(tmp_path):
    codex_home = str(tmp_path)
    rows_data = []
    for i, (archived, originator, source) in enumerate(
            [(1, "codex-tui", "user"), (0, "codex_exec", "user"), (0, "codex-tui", "subagent")], start=3):
        tid = _thread_id(i)
        rollout_path = os.path.join(codex_home, "sessions",
                                    "rollout-2026-09-24T00-00-00-%s.jsonl" % tid)
        _write_rollout(rollout_path, [_session_meta()])
        rows_data.append((tid, rollout_path, "D:\\made-up\\proj", BASE_MS, source, originator,
                          archived, None))
    _make_state_db(codex_home, 1, rows_data)
    _make_history_db(codex_home, 1, [])

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 5)
    assert rows == []


def test_codex_rows_caps_at_process_count_prioritizing_in_progress(tmp_path):
    codex_home = str(tmp_path)
    threads, turns = [], []
    for i in range(4):
        tid = _thread_id(10 + i)
        rollout_path = os.path.join(codex_home, "sessions",
                                    "rollout-2026-09-24T00-00-00-%s.jsonl" % tid)
        status = "inProgress" if i in (0, 1) else "completed"
        _write_rollout(rollout_path, [_session_meta(), _task_started(1, BASE_MS)])
        threads.append((tid, rollout_path, "D:\\made-up\\proj", BASE_MS - i, "user",
                        "codex-tui", 0, None))
        turns.append((tid, "turn-1", status, BASE_MS, BASE_MS, 10))
    _make_state_db(codex_home, 1, threads)
    _make_history_db(codex_home, 1, turns)

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 3)
    assert len(rows) == 3
    confirmed = [r for r in rows if r["aliveCertainty"] == "confirmed"]
    inferred = [r for r in rows if r["aliveCertainty"] == "inferred"]
    assert len(confirmed) == 2
    assert len(inferred) == 1


def _two_threads(codex_home, newest_status, oldest_status):
    """A newer thread (id 40) and an older one (id 41) with the given turn
    statuses; returns their ids."""
    threads, turns = [], []
    for i, status in enumerate((newest_status, oldest_status)):
        tid = _thread_id(40 + i)
        rollout_path = os.path.join(codex_home, "sessions",
                                    "rollout-2026-09-24T00-00-00-%s.jsonl" % tid)
        _write_rollout(rollout_path, [_session_meta(), _task_started(1, BASE_MS)])
        threads.append((tid, rollout_path, "D:\\made-up\\proj", BASE_MS - i, "user",
                        "codex-tui", 0, None))
        turns.append((tid, "turn-1", status, BASE_MS, BASE_MS, 10))
    _make_history_db(codex_home, 1, turns)
    return threads


def test_codex_rows_lists_nothing_alive_by_inference_when_only_the_app_server_runs(tmp_path):
    # The user's case: two codex processes exist (the VS Code extension's
    # daemon), no interactive session does -- so no idle thread is alive.
    codex_home = str(tmp_path)
    threads = _two_threads(codex_home, "completed", "completed")
    _make_state_db(codex_home, 1, threads, sources={threads[0][0]: "vscode", threads[1][0]: "cli"})

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 2, 0)
    assert rows == []


def test_codex_rows_never_infers_a_vscode_thread_alive(tmp_path):
    codex_home = str(tmp_path)
    threads = _two_threads(codex_home, "completed", "completed")
    _make_state_db(codex_home, 1, threads, sources={threads[0][0]: "vscode", threads[1][0]: "cli"})

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 3, 1)
    assert [r["sessionId"] for r in rows] == [threads[1][0]]
    assert rows[0]["aliveCertainty"] == "inferred"


def test_codex_rows_lists_an_in_progress_vscode_thread_without_taking_a_session_slot(tmp_path):
    codex_home = str(tmp_path)
    threads = _two_threads(codex_home, "inProgress", "completed")
    _make_state_db(codex_home, 1, threads, sources={threads[0][0]: "vscode", threads[1][0]: "cli"})

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 3, 1)
    by_id = {r["sessionId"]: r["aliveCertainty"] for r in rows}
    assert by_id == {threads[0][0]: "confirmed", threads[1][0]: "inferred"}


def test_codex_rows_lists_every_in_progress_thread_regardless_of_process_count(tmp_path):
    # The app-server runs any number of VS Code turns at once, so two
    # in-progress threads must both show even with a single codex process.
    codex_home = str(tmp_path)
    threads = _two_threads(codex_home, "inProgress", "inProgress")
    _make_state_db(codex_home, 1, threads,
                   sources={threads[0][0]: "vscode", threads[1][0]: "vscode"})

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 1, 0)
    assert sorted(r["sessionId"] for r in rows) == sorted(t[0] for t in threads)
    assert all(r["aliveCertainty"] == "confirmed" for r in rows)


def test_codex_rows_session_count_defaults_to_process_count(tmp_path):
    codex_home = str(tmp_path)
    threads = _two_threads(codex_home, "completed", "completed")
    _make_state_db(codex_home, 1, threads)  # older schema: no source column

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 2)
    assert len(rows) == 2


def test_codex_rows_thread_with_no_turns_row_gets_turn_status_none(tmp_path):
    codex_home = str(tmp_path)
    tid = _thread_id(20)
    rollout_path = os.path.join(codex_home, "sessions", "rollout-2026-09-24T00-00-00-%s.jsonl" % tid)
    _write_rollout(rollout_path, [_session_meta()])
    _make_state_db(codex_home, 1, [(tid, rollout_path, "D:\\made-up\\proj", BASE_MS, "user",
                                    "codex-tui", 0, None)])
    _make_history_db(codex_home, 1, [])

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 5)
    assert len(rows) == 1
    # No thread_turns row -> turn_status None; tail has only session_meta,
    # no task_started/task_complete/dangling-question signal -> done.
    assert rows[0]["state"] == "done"


def test_codex_rows_uses_the_highest_numbered_sqlite_files(tmp_path):
    codex_home = str(tmp_path)
    tid_old = _thread_id(30)
    tid_new = _thread_id(31)
    rollout_old = os.path.join(codex_home, "sessions", "rollout-old-%s.jsonl" % tid_old)
    rollout_new = os.path.join(codex_home, "sessions", "rollout-new-%s.jsonl" % tid_new)
    _write_rollout(rollout_old, [_session_meta()])
    _write_rollout(rollout_new, [_session_meta(cwd="D:\\made-up\\new-proj")])
    _make_state_db(codex_home, 1, [(tid_old, rollout_old, "D:\\made-up\\proj", BASE_MS, "user",
                                    "codex-tui", 0, None)])
    _make_history_db(codex_home, 1, [])
    _make_state_db(codex_home, 2, [(tid_new, rollout_new, "D:\\made-up\\new-proj", BASE_MS, "user",
                                    "codex-tui", 0, None)])
    _make_history_db(codex_home, 2, [])

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 5)
    assert len(rows) == 1
    assert rows[0]["sessionId"] == tid_new


# ---------------------------------------- D2 wiring through codex_rows ----

def test_codex_rows_populates_summary_recent_and_fallback_subagents(tmp_path):
    codex_home = str(tmp_path)
    tid = _thread_id(50)
    rollout_path = os.path.join(codex_home, "sessions", "rollout-2026-09-24T00-00-00-%s.jsonl" % tid)
    _write_rollout(rollout_path, [
        _session_meta(),
        _function_call(1, "call-1", "wait", ms=BASE_MS, arguments=json.dumps({"cmd": "step-1"})),
        _function_call_output(2, "call-1", ms=BASE_MS),
        _message(3, "assistant", [_output_text("做完了")], ms=BASE_MS),
        _task_complete(4, BASE_MS)])
    _make_state_db(codex_home, 1, [(tid, rollout_path, "D:\\made-up\\proj", BASE_MS,
                                    "user", "codex-tui", 0, None)])
    _make_history_db(codex_home, 1, [(tid, "turn-1", "completed", BASE_MS, BASE_MS, 10)])

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 5)
    assert len(rows) == 1
    row = rows[0]
    assert row["summary"] == "做完了"
    assert row["recent"] == [{"at": BASE_MS, "tool": "wait", "input": "step-1"}]
    assert row["subagents"] == []


def test_codex_rows_primary_reports_open_child_threads_as_subagents(tmp_path):
    codex_home = str(tmp_path)
    parent_id = _thread_id(51)
    child_id = _thread_id(52)
    parent_rollout = os.path.join(codex_home, "sessions", "rollout-parent-%s.jsonl" % parent_id)
    _write_rollout(parent_rollout, [_session_meta()])
    _make_state_db(
        codex_home, 1,
        [(parent_id, parent_rollout, "D:\\made-up\\proj", BASE_MS, "user", "codex-tui", 0, None),
         (child_id, "D:\\ignored", "D:\\made-up\\proj", BASE_MS, "subagent", "codex-tui", 0, "reviewer")],
        spawn_edges=[(parent_id, child_id, "open")])
    _make_history_db(codex_home, 1, [])

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 5)
    # the child thread itself is filtered out (thread_source == "subagent"),
    # so only the parent's row comes back, carrying the child's name.
    assert len(rows) == 1
    assert rows[0]["subagents"] == ["reviewer"]


def test_codex_rows_primary_ignores_closed_spawn_edges(tmp_path):
    codex_home = str(tmp_path)
    parent_id = _thread_id(53)
    child_id = _thread_id(54)
    parent_rollout = os.path.join(codex_home, "sessions", "rollout-parent2-%s.jsonl" % parent_id)
    _write_rollout(parent_rollout, [_session_meta()])
    _make_state_db(codex_home, 1,
                   [(parent_id, parent_rollout, "D:\\made-up\\proj", BASE_MS, "user", "codex-tui", 0, None)],
                   spawn_edges=[(parent_id, child_id, "closed")])
    _make_history_db(codex_home, 1, [])

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 5)
    assert rows[0]["subagents"] == []


def test_codex_rows_primary_tolerates_a_missing_thread_spawn_edges_table(tmp_path):
    codex_home = str(tmp_path)
    tid = _thread_id(55)
    rollout_path = os.path.join(codex_home, "sessions", "rollout-noedges-%s.jsonl" % tid)
    _write_rollout(rollout_path, [_session_meta()])
    # A state db without thread_spawn_edges at all -- an older Codex schema.
    # The primary (sqlite) path must still work, just with no subagents
    # data, rather than falling all the way back to the rollout scan.
    path = os.path.join(codex_home, "state_1.sqlite")
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE threads (
        id TEXT, rollout_path TEXT, cwd TEXT, updated_at_ms INTEGER,
        thread_source TEXT, originator TEXT, archived INTEGER, name TEXT)""")
    conn.execute("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?)",
                (tid, rollout_path, "D:\\made-up\\proj", BASE_MS, "user", "codex-tui", 0, None))
    conn.commit()
    conn.close()
    _make_history_db(codex_home, 1, [])

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 5)
    assert problems == []  # still the primary path, not the fallback
    assert len(rows) == 1
    assert rows[0]["subagents"] == []


# ----------------------------------------------------- fallback path ----

def test_codex_rows_falls_back_when_no_sqlite_files_present(tmp_path):
    codex_home = str(tmp_path)
    tid = _thread_id(40)
    rollout_path = os.path.join(codex_home, "sessions",
                                "rollout-2026-09-24T00-00-00-%s.jsonl" % tid)
    _write_rollout(rollout_path, [_session_meta(cwd=os.path.join(os.sep, "made-up", "fallback-proj")),
                                  _task_started(1, BASE_MS), _task_complete(2, BASE_MS)])

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 5)
    assert len(rows) == 1
    row = rows[0]
    assert row["sessionId"] == tid
    assert row["project"] == "fallback-proj"
    assert row["certainty"] == "inferred"
    assert row["aliveCertainty"] == "inferred"
    assert any("Codex" in p for p in problems)


def test_codex_rows_falls_back_when_sqlite_is_corrupt(tmp_path):
    codex_home = str(tmp_path)
    with open(os.path.join(codex_home, "state_1.sqlite"), "w", encoding="utf-8") as fh:
        fh.write("not a real sqlite file")
    with open(os.path.join(codex_home, "thread_history_1.sqlite"), "w", encoding="utf-8") as fh:
        fh.write("not a real sqlite file")

    tid = _thread_id(41)
    rollout_path = os.path.join(codex_home, "sessions",
                                "rollout-2026-09-24T00-00-00-%s.jsonl" % tid)
    _write_rollout(rollout_path, [_session_meta(), _task_started(1, BASE_MS)])

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 5)
    assert len(rows) == 1
    assert rows[0]["certainty"] == "inferred"
    assert any("Codex" in p for p in problems)


def test_codex_rows_fallback_excludes_exec_and_subagent_originators(tmp_path):
    codex_home = str(tmp_path)
    tid_exec = _thread_id(42)
    tid_subagent = _thread_id(43)
    tid_ok = _thread_id(44)
    rollout_exec = os.path.join(codex_home, "sessions",
                                "rollout-2026-09-24T00-00-00-%s.jsonl" % tid_exec)
    rollout_subagent = os.path.join(codex_home, "sessions",
                                    "rollout-2026-09-24T00-00-00-%s.jsonl" % tid_subagent)
    rollout_ok = os.path.join(codex_home, "sessions",
                              "rollout-2026-09-24T00-00-00-%s.jsonl" % tid_ok)
    _write_rollout(rollout_exec, [_session_meta(originator="codex_exec")])
    _write_rollout(rollout_subagent, [_session_meta(thread_source="subagent")])
    _write_rollout(rollout_ok, [_session_meta()])

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 5)
    assert len(rows) == 1
    assert rows[0]["sessionId"] == tid_ok


def test_codex_rows_fallback_never_infers_a_vscode_thread_alive(tmp_path):
    codex_home = str(tmp_path)
    paths = {}
    for i, source in enumerate(("vscode", "cli")):
        tid = _thread_id(50 + i)
        path = os.path.join(codex_home, "sessions", "2026", "09", "24",
                            "rollout-2026-09-24T00-00-00-%s.jsonl" % tid)
        _write_rollout(path, [_session_meta(source=source), _task_started(1, BASE_MS),
                              _task_complete(2, BASE_MS)], mtime_ms=BASE_MS - i)
        paths[source] = tid

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 3, 1)
    assert [r["sessionId"] for r in rows] == [paths["cli"]]


def test_codex_rows_fallback_lists_every_in_progress_rollout_regardless_of_process_count(tmp_path):
    codex_home = str(tmp_path)
    tids = []
    for i in range(2):
        tid = _thread_id(60 + i)
        path = os.path.join(codex_home, "sessions", "2026", "09", "24",
                            "rollout-2026-09-24T00-00-00-%s.jsonl" % tid)
        _write_rollout(path, [_session_meta(source="vscode"), _task_started(1, BASE_MS)],
                       mtime_ms=BASE_MS - i)
        tids.append(tid)

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 1, 0)
    assert sorted(r["sessionId"] for r in rows) == sorted(tids)


def test_codex_rows_fallback_skips_rollouts_older_than_24h(tmp_path):
    codex_home = str(tmp_path)
    tid_old = _thread_id(45)
    tid_new = _thread_id(46)
    rollout_old = os.path.join(codex_home, "sessions",
                               "rollout-2026-09-24T00-00-00-%s.jsonl" % tid_old)
    rollout_new = os.path.join(codex_home, "sessions",
                               "rollout-2026-09-24T00-00-00-%s.jsonl" % tid_new)
    _write_rollout(rollout_old, [_session_meta()], mtime_ms=BASE_MS - 25 * 3600 * 1000)
    _write_rollout(rollout_new, [_session_meta()])

    rows, problems = viewer.codex_rows(codex_home, BASE_MS, 5)
    assert len(rows) == 1
    assert rows[0]["sessionId"] == tid_new
