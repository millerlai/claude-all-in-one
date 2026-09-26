"""viewer.py's ### tail and ### claude_source / classify_claude components.

Fixtures are entirely synthetic: made-up pids, paths, question text -- never
anything read from a real transcript. Registry and transcript key names
match what unit 2's task brief confirmed against real local files.
"""
import json
import os
import platform
import sys

import viewer

_LOCAL_PID_DOMAIN = "%s:%s" % (sys.platform, platform.node())


# ================================================================ tail ====

def test_read_tail_returns_empty_list_for_missing_file(tmp_path):
    assert viewer.read_tail(str(tmp_path / "nope.jsonl"), 1024) == []


def test_read_tail_parses_every_json_object_line(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(
        json.dumps({"a": 1}) + "\n" + json.dumps({"a": 2}) + "\n", encoding="utf-8")
    rows = viewer.read_tail(str(path), 65536)
    assert rows == [{"a": 1}, {"a": 2}]


def test_read_tail_skips_unparseable_and_non_dict_lines(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(
        json.dumps({"a": 1}) + "\nnot json\n" + json.dumps([1, 2]) + "\n"
        + json.dumps({"a": 2}) + "\n", encoding="utf-8")
    rows = viewer.read_tail(str(path), 65536)
    assert rows == [{"a": 1}, {"a": 2}]


def test_read_tail_discards_partial_line_at_front_of_a_bounded_read(tmp_path):
    path = tmp_path / "t.jsonl"
    # Three full lines; a max_bytes small enough to land inside line 2 means
    # line 2's partial fragment must be discarded, leaving only line 3.
    lines = [json.dumps({"n": i}) for i in range(3)]
    text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
    # Land a few bytes into line 2 (not exactly on its boundary), so its
    # fragment plus the rest of line 2 is what gets discarded, leaving 3.
    tail_len = len(lines[2].encode("utf-8")) + 1 + 3
    rows = viewer.read_tail(str(path), tail_len)
    assert rows == [{"n": 2}]


def test_read_tail_caches_until_the_file_changes(tmp_path, monkeypatch):
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps({"a": 1}) + "\n", encoding="utf-8")
    viewer._tail_cache.clear()

    first = viewer.read_tail(str(path), 65536)
    assert first == [{"a": 1}]

    calls = []
    real_open = open

    def spy_open(*a, **k):
        calls.append(a)
        return real_open(*a, **k)

    monkeypatch.setattr("builtins.open", spy_open)
    second = viewer.read_tail(str(path), 65536)
    assert second == first
    assert calls == []  # cache hit: no re-open

    path.write_text(json.dumps({"a": 2}) + "\n", encoding="utf-8")
    third = viewer.read_tail(str(path), 65536)
    assert third == [{"a": 2}]


def test_read_first_line_returns_the_first_full_line(tmp_path):
    path = tmp_path / "meta.jsonl"
    path.write_text(
        json.dumps({"type": "session_meta", "id": "abc"}) + "\n"
        + json.dumps({"type": "other"}) + "\n", encoding="utf-8")
    assert viewer.read_first_line(str(path)) == {"type": "session_meta", "id": "abc"}


def test_read_first_line_returns_none_for_missing_file(tmp_path):
    assert viewer.read_first_line(str(tmp_path / "nope.jsonl")) is None


def test_read_first_line_returns_none_for_unparseable_first_line(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    assert viewer.read_first_line(str(path)) is None


# =================================================== classify_claude ====

def _reg(status, **overrides):
    reg = {"pid": 4242, "procStart": "1000", "sessionId": "sess-1",
          "cwd": "D:\\made-up\\project", "status": status,
          "statusUpdatedAt": 1_700_000_000_000, "kind": "interactive",
          "pidDomain": _LOCAL_PID_DOMAIN}
    reg.update(overrides)
    return reg


def _tool_use(tool_id, name, tool_input):
    return {"type": "assistant", "message": {"model": "made-up-model",
           "content": [{"type": "tool_use", "id": tool_id, "name": name,
                       "input": tool_input}]}}


def _tool_result(tool_id):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tool_id, "content": "ok"}]}}


# A background Agent or Workflow call is answered at once: the tool_result
# block plus a row-level toolUseResult saying "async_launched" and naming
# the task (agentId for a subagent, taskId plus workflowName for a
# workflow). Its finish is a later queue-operation row carrying a
# <task-notification> for that id. Shapes confirmed read-only against real
# local transcripts 2026-09-26; ids and text here are made up.
def _async_launch_result(tool_id, **result):
    row = _tool_result(tool_id)
    row["toolUseResult"] = dict({"isAsync": True, "status": "async_launched"}, **result)
    return row


def _task_notification(task_id, status="completed"):
    return {"type": "queue-operation", "operation": "enqueue",
            "content": "<task-notification>\n<task-id>%s</task-id>\n"
                       "<status>%s</status>\n</task-notification>" % (task_id, status)}


def _turn_duration(**pending):
    row = {"type": "system", "subtype": "turn_duration"}
    row.update(pending)
    return row


def _workflow_launch(tool_id, task_id, name):
    return [_tool_use(tool_id, "Workflow", {"script": "export const meta = {name: 'x'}"}),
            _async_launch_result(tool_id, taskId=task_id, taskType="local_workflow",
                                 workflowName=name)]


def test_unknown_status_maps_to_unknown_state():
    reg = _reg("stopped")
    out = viewer.classify_claude(reg, [], 0)
    assert out["state"] == "unknown"
    assert out["certainty"] == "confirmed"
    assert out["entryId"] == "unknown:1700000000000"


def test_waiting_with_escalated_waiting_for_is_attention():
    reg = _reg("waiting", waitingFor="dialog open")
    out = viewer.classify_claude(reg, [], 0)
    assert out["state"] == "attention"
    assert out["certainty"] == "confirmed"
    assert "dialog open" in out["notes"]


def test_waiting_with_unresolved_ask_user_question_is_question():
    tool_input = {"questions": [{"question": "要重新命名這個分支嗎？",
                                "header": "分支命名", "multiSelect": False,
                                "options": [{"label": "是", "description": "改名"},
                                          {"label": "否", "description": "保留原名"}]}]}
    tail = [_tool_use("toolu_1", "AskUserQuestion", tool_input)]
    reg = _reg("waiting")
    out = viewer.classify_claude(reg, tail, 0)
    assert out["state"] == "question"
    assert out["certainty"] == "confirmed"
    assert out["entryId"] == "toolu_1"
    assert out["question"]["text"] == "要重新命名這個分支嗎？"
    assert out["question"]["options"] == ["是", "否"]


def test_waiting_with_unresolved_other_tool_is_permission():
    tail = [_tool_use("toolu_2", "Bash", {"command": "rm -rf made-up-dir"})]
    reg = _reg("waiting")
    out = viewer.classify_claude(reg, tail, 0)
    assert out["state"] == "permission"
    assert out["entryId"] == "toolu_2"
    assert out["permission"] == {"tool": "Bash", "input": "rm -rf made-up-dir"}


def test_waiting_with_a_resolved_tool_use_falls_back_to_attention():
    tail = [_tool_use("toolu_3", "Bash", {"command": "echo hi"}),
           _tool_result("toolu_3")]
    reg = _reg("waiting")
    out = viewer.classify_claude(reg, tail, 0)
    assert out["state"] == "attention"
    assert out["notes"] == ["原因未知"]


def test_idle_is_done():
    reg = _reg("idle")
    out = viewer.classify_claude(reg, [], 0)
    assert out["state"] == "done"
    assert out["certainty"] == "confirmed"
    assert out["notes"] == []
    assert out["background"] is False


def test_idle_with_an_unpaired_background_agent_is_background_working():
    # AC5: idle only means "done" when no background work is left -- V8's
    # background check runs even on idle (main does not, #162's gap).
    reg = _reg("idle")
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer",
                                      "description": "做 build 階段", "prompt": "p"}),
           _async_launch_result("a1", agentId="agent-bg-1")]
    out = viewer.classify_claude(reg, tail, reg["statusUpdatedAt"])
    assert out["state"] == "working"
    assert out["certainty"] == "inferred"
    assert out["background"] is True
    assert out["notes"] == []
    assert out["current"]["tool"] == "Agent"


def test_idle_after_every_background_task_ended_is_done():
    reg = _reg("idle")
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer",
                                      "description": "d", "prompt": "p"}),
           _async_launch_result("a1", agentId="agent-bg-1"),
           _turn_duration(pendingBackgroundAgentCount=1),
           _task_notification("agent-bg-1"),
           {"type": "user", "message": {"content": [{"type": "text", "text": "continue"}]}},
           {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}},
           _turn_duration(pendingBackgroundAgentCount=0)]
    out = viewer.classify_claude(reg, tail, reg["statusUpdatedAt"])
    assert out["state"] == "done"
    assert out["certainty"] == "confirmed"
    assert out["background"] is False


def test_idle_with_only_a_pending_count_is_background_without_names():
    # AC6: the launch itself fell out of the tail (接續 or pushed out) --
    # still background, just with no name to show (decisions D4).
    reg = _reg("idle")
    tail = [_turn_duration(pendingBackgroundAgentCount=1)]
    out = viewer.classify_claude(reg, tail, reg["statusUpdatedAt"])
    assert out["state"] == "working"
    assert out["certainty"] == "inferred"
    assert out["background"] is True
    assert out["current"] is None
    assert viewer._claude_subagents(tail) == []


def test_shell_is_working_with_note():
    # 2026-09-26 correction: a still-running background Bash needs no human,
    # so this is `working`, not `done` -- see the decisions doc Tier 3 row.
    reg = _reg("shell")
    out = viewer.classify_claude(reg, [], 0)
    assert out["state"] == "working"
    assert out["certainty"] == "confirmed"
    assert out["entryId"] == "working:%s" % reg["statusUpdatedAt"]
    assert out["notes"] == ["背景 shell 執行中"]
    assert out["current"] is None


def _bash_result(tool_id, task_id):
    """A background Bash's tool_result: unlike the async-subagent shape, the
    task id sits directly on the row-level toolUseResult as
    "backgroundTaskId", confirmed read-only against a real local transcript
    2026-09-26 (line 745 of the session cited in the design doc)."""
    row = _tool_result(tool_id)
    row["toolUseResult"] = {"stdout": "", "stderr": "", "interrupted": False,
                            "isImage": False, "noOutputExpected": False,
                            "backgroundTaskId": task_id}
    return row


def test_shell_current_shows_background_bash_by_description():
    tail = [_tool_use("b1", "Bash", {"command": "pytest -q", "description": "跑測試",
                                     "run_in_background": True}),
           _bash_result("b1", "task-1")]
    reg = _reg("shell")
    out = viewer.classify_claude(reg, tail, 0)
    assert out["state"] == "working"
    assert out["current"] == {"tool": "Bash", "input": "跑測試",
                              "since": reg["statusUpdatedAt"]}


def test_shell_current_falls_back_to_command_without_description():
    tail = [_tool_use("b1", "Bash", {"command": "pytest -q", "run_in_background": True}),
           _bash_result("b1", "task-1")]
    reg = _reg("shell")
    out = viewer.classify_claude(reg, tail, 0)
    assert out["current"]["input"] == "pytest -q"


def test_shell_current_excludes_a_background_bash_already_notified():
    tail = [_tool_use("b1", "Bash", {"command": "pytest -q", "description": "跑測試",
                                     "run_in_background": True}),
           _bash_result("b1", "task-1"),
           _task_notification("task-1")]
    reg = _reg("shell")
    out = viewer.classify_claude(reg, tail, 0)
    assert out["state"] == "working"
    assert out["current"] is None


def test_shell_current_is_none_without_a_background_bash_call():
    tail = [_tool_use("t1", "Read", {"file_path": "a.py"})]
    reg = _reg("shell")
    out = viewer.classify_claude(reg, tail, 0)
    assert out["current"] is None


def test_shell_current_picks_the_newest_still_running_background_bash():
    tail = [_tool_use("b1", "Bash", {"command": "cmd1", "description": "第一個",
                                     "run_in_background": True}),
           _bash_result("b1", "task-1"),
           _tool_use("b2", "Bash", {"command": "cmd2", "description": "第二個",
                                     "run_in_background": True}),
           _bash_result("b2", "task-2")]
    reg = _reg("shell")
    out = viewer.classify_claude(reg, tail, 0)
    assert out["current"]["input"] == "第二個"


def test_shell_with_a_background_agent_is_plain_working_with_note():
    # decisions: shell never runs the background check; #172 made shell
    # itself "working", so a background agent alongside changes nothing.
    reg = _reg("shell")
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer",
                                      "description": "d", "prompt": "p"}),
           _async_launch_result("a1", agentId="agent-bg-1")]
    out = viewer.classify_claude(reg, tail, reg["statusUpdatedAt"])
    assert out["state"] == "working"
    assert out["certainty"] == "confirmed"
    assert out["notes"] == ["背景 shell 執行中"]
    assert out["background"] is False


def test_busy_with_stale_turn_duration_tail_is_inferred_done():
    reg = _reg("busy")
    tail = [{"type": "system", "subtype": "turn_duration"}]
    now_ms = reg["statusUpdatedAt"] + 61000
    out = viewer.classify_claude(reg, tail, now_ms)
    assert out["state"] == "done"
    assert out["certainty"] == "inferred"
    assert out["notes"] == ["登記檔可能過時"]


def test_busy_with_recent_turn_duration_tail_is_working():
    reg = _reg("busy")
    tail = [{"type": "system", "subtype": "turn_duration"}]
    now_ms = reg["statusUpdatedAt"] + 1000
    out = viewer.classify_claude(reg, tail, now_ms)
    assert out["state"] == "working"


def test_busy_with_unresolved_tool_use_reports_current():
    tail = [_tool_use("toolu_4", "Read", {"file_path": "D:\\made-up\\file.py"})]
    reg = _reg("busy")
    out = viewer.classify_claude(reg, tail, reg["statusUpdatedAt"])
    assert out["state"] == "working"
    assert out["certainty"] == "confirmed"
    assert out["current"] == {"tool": "Read", "input": "D:\\made-up\\file.py",
                              "since": reg["statusUpdatedAt"]}


def test_busy_with_no_unresolved_tool_use_has_no_current():
    reg = _reg("busy")
    out = viewer.classify_claude(reg, [], reg["statusUpdatedAt"])
    assert out["state"] == "working"
    assert out["current"] is None


def test_busy_turn_end_with_pending_agents_is_background_working():
    # The main turn ended but a background subagent is still running: this
    # is 「執行中（背景）」, inferred, not the stale-registry "done" branch --
    # and not "working"/"confirmed" either (#162's behaviour before this fix).
    reg = _reg("busy")
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer",
                                      "description": "做 build 階段", "prompt": "p"}),
           _async_launch_result("a1", agentId="agent-bg-1"),
           _turn_duration(pendingBackgroundAgentCount=1)]
    now_ms = reg["statusUpdatedAt"] + 61000
    out = viewer.classify_claude(reg, tail, now_ms)
    assert out["state"] == "working"
    assert out["certainty"] == "inferred"
    assert out["background"] is True
    assert out["notes"] == []
    assert out["current"] == {"tool": "Agent", "input": "做 build 階段",
                              "since": reg["statusUpdatedAt"]}


def test_busy_turn_duration_tail_with_zero_pending_agents_is_still_inferred_done():
    reg = _reg("busy")
    tail = [_turn_duration(pendingBackgroundAgentCount=0)]
    now_ms = reg["statusUpdatedAt"] + 61000
    out = viewer.classify_claude(reg, tail, now_ms)
    assert out["state"] == "done"
    assert out["certainty"] == "inferred"


def test_turn_still_pending_only_counts_positive_numbers():
    assert viewer._turn_still_pending(_turn_duration(pendingBackgroundAgentCount=1))
    assert viewer._turn_still_pending(_turn_duration(pendingWorkflowCount=2))
    assert not viewer._turn_still_pending(_turn_duration(pendingBackgroundAgentCount=0))
    assert not viewer._turn_still_pending(_turn_duration(pendingBackgroundAgentCount="0"))
    assert not viewer._turn_still_pending(_turn_duration())
    # V8/Ruled out: only the two named keys count -- a future pending key
    # (here a made-up pendingShellCount) is not background work.
    assert not viewer._turn_still_pending(_turn_duration(pendingShellCount=1))


def test_busy_turn_end_behind_bookkeeping_rows_is_still_background():
    # decisions D2: a bookkeeping row after the turn_duration (last-prompt,
    # mode, pr-link -- Claude Code's own between-turn notes) must not read
    # as "a newer turn already started".
    reg = _reg("busy")
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer",
                                      "description": "d", "prompt": "p"}),
           _async_launch_result("a1", agentId="agent-bg-1"),
           _turn_duration(pendingBackgroundAgentCount=1),
           {"type": "last-prompt"}, {"type": "mode"}, {"type": "pr-link"}]
    out = viewer.classify_claude(reg, tail, reg["statusUpdatedAt"] + 61000)
    assert out["state"] == "working"
    assert out["certainty"] == "inferred"
    assert out["background"] is True


def test_busy_new_turn_after_pending_turn_duration_is_not_background():
    # decisions D2, the other half of the bookkeeping test above: a genuine
    # user/assistant row (not a bookkeeping one) after the turn_duration
    # does mean a newer turn has started, so a stale pendingBackgroundAgent-
    # Count from the earlier turn must not resurface as background. Neither
    # test_busy_turn_end_with_pending_agents_is_background_working (tail
    # ends on the turn_duration itself) nor
    # test_busy_turn_end_behind_bookkeeping_rows_is_still_background (tail
    # ends on bookkeeping rows) reaches this branch of _last_turn_end.
    reg = _reg("busy")
    tail = [_turn_duration(pendingBackgroundAgentCount=1),
           {"type": "user", "message": {"content": [{"type": "text", "text": "next"}]}},
           {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}]
    out = viewer.classify_claude(reg, tail, reg["statusUpdatedAt"] + 61000)
    assert out["state"] == "working"
    assert out["certainty"] == "confirmed"
    assert out["background"] is False


def test_busy_after_a_completion_notice_is_plain_working():
    reg = _reg("busy")
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer",
                                      "description": "d", "prompt": "p"}),
           _async_launch_result("a1", agentId="agent-bg-1"),
           _turn_duration(pendingBackgroundAgentCount=1),
           _task_notification("agent-bg-1")]
    out = viewer.classify_claude(reg, tail, reg["statusUpdatedAt"] + 61000)
    assert out["state"] == "working"
    assert out["certainty"] == "confirmed"
    assert out["background"] is False


def test_busy_turn_end_then_a_foreign_notice_is_still_background():
    # verify's AC8 live check: a completion notice whose task id was never
    # launched in THIS tail (e.g. a nested subagent's own lens calls,
    # interleaved into the parent session's transcript) must not read as
    # "this session's turn moved on" -- only a notice for a task
    # _launched_task_ids() says this tail itself launched may do that
    # (see test_busy_after_a_completion_notice_is_plain_working above).
    reg = _reg("busy")
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer",
                                      "description": "d", "prompt": "p"}),
           _async_launch_result("a1", agentId="own-agent"),
           _turn_duration(pendingBackgroundAgentCount=1),
           _task_notification("nested-agent")]
    out = viewer.classify_claude(reg, tail, reg["statusUpdatedAt"] + 61000)
    assert out["state"] == "working"
    assert out["certainty"] == "inferred"
    assert out["background"] is True


def test_a_notice_with_another_status_does_not_end_a_launch():
    launch = [_tool_use("a1", "Agent", {"subagent_type": "implementer",
                                        "description": "d", "prompt": "p"}),
             _async_launch_result("a1", agentId="agent-bg-1")]
    still_running = launch + [_task_notification("agent-bg-1", status="progress")]
    assert [name for name, _ in viewer._async_subagents(still_running)] == ["implementer"]

    ended = launch + [_task_notification("agent-bg-1", status="stopped")]
    assert viewer._async_subagents(ended) == []


def test_busy_turn_end_with_pending_workflow_is_background_working():
    reg = _reg("busy")
    tail = _workflow_launch("w1", "w-task-1", "made-up-sweep") + [
        _turn_duration(pendingWorkflowCount=1)]
    out = viewer.classify_claude(reg, tail, reg["statusUpdatedAt"] + 61000)
    assert out["state"] == "working"
    assert out["certainty"] == "inferred"
    assert out["background"] is True
    assert out["current"]["tool"] == "Workflow"


def test_busy_current_prefers_an_unresolved_tool_use_over_a_background_agent():
    reg = _reg("busy")
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer",
                                      "description": "d", "prompt": "p"}),
           _async_launch_result("a1", agentId="agent-bg-1"),
           _tool_use("t1", "Read", {"file_path": "D:\\made-up\\file.py"})]
    out = viewer.classify_claude(reg, tail, reg["statusUpdatedAt"])
    assert out["current"]["tool"] == "Read"


def test_permission_input_is_truncated_to_500_chars():
    long_cmd = "x" * 600
    tail = [_tool_use("toolu_5", "Bash", {"command": long_cmd})]
    reg = _reg("waiting")
    out = viewer.classify_claude(reg, tail, 0)
    assert len(out["permission"]["input"]) == 500


def test_current_input_is_truncated_to_120_chars():
    long_path = "y" * 200
    tail = [_tool_use("toolu_6", "Read", {"file_path": long_path})]
    reg = _reg("busy")
    out = viewer.classify_claude(reg, tail, reg["statusUpdatedAt"])
    assert len(out["current"]["input"]) == 120


def test_question_text_and_options_are_truncated():
    long_question = "z" * 1500
    options = [{"label": "o" * 300, "description": "d"} for _ in range(15)]
    tool_input = {"questions": [{"question": long_question, "header": "h",
                                "multiSelect": False, "options": options}]}
    tail = [_tool_use("toolu_7", "AskUserQuestion", tool_input)]
    reg = _reg("waiting")
    out = viewer.classify_claude(reg, tail, 0)
    assert len(out["question"]["text"]) == 1000
    assert len(out["question"]["options"]) == 10
    assert all(len(label) == 200 for label in out["question"]["options"])


# ============== D2: summary (rule 1) / recent (rule 2) / subagents (rule 3)
# Key names (message.content[].type == "text", "timestamp" ISO8601Z on the
# row, tool_use.input.subagent_type) confirmed read-only against real local
# transcripts 2026-09-25 (verify round 2); no conversation content copied.

def _assistant_text(text, ts=None):
    row = {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
    if ts is not None:
        row["timestamp"] = ts
    return row


def test_last_assistant_text_returns_the_last_assistant_message_text():
    tail = [_assistant_text("先做的那句"), _assistant_text("後做的那句，應該回這句")]
    assert viewer._last_assistant_text(tail) == "後做的那句，應該回這句"


def test_last_assistant_text_joins_multiple_text_blocks_in_one_message():
    row = {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "第一段"}, {"type": "text", "text": "第二段"}]}}
    assert viewer._last_assistant_text([row]) == "第一段\n第二段"


def test_last_assistant_text_is_none_when_last_assistant_message_has_no_text_block():
    tail = [_assistant_text("有文字的那句"), _tool_use("toolu_x", "Read", {"file_path": "a"})]
    assert viewer._last_assistant_text(tail) is None


def test_last_assistant_text_is_none_for_empty_tail():
    assert viewer._last_assistant_text([]) is None


def test_recent_claude_actions_keeps_last_eight_in_order():
    tail = [_tool_use("t%d" % i, "Read", {"file_path": "f%d.py" % i}) for i in range(10)]
    recent = viewer._recent_claude_actions(tail)
    assert [r["tool"] for r in recent] == ["Read"] * 8
    assert [r["input"] for r in recent] == ["f%d.py" % i for i in range(2, 10)]


def test_recent_claude_actions_input_is_truncated_to_80_chars():
    long_cmd = "x" * 200
    tail = [_tool_use("t1", "Bash", {"command": long_cmd})]
    recent = viewer._recent_claude_actions(tail)
    assert len(recent[0]["input"]) == 80


def test_recent_claude_actions_reads_at_from_row_timestamp():
    import datetime as dt
    ts = "2026-09-25T00:00:00.000Z"
    expected_ms = int(dt.datetime(2026, 9, 25, tzinfo=dt.timezone.utc).timestamp() * 1000)
    row = {"type": "assistant", "timestamp": ts,
          "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Read",
                                   "input": {"file_path": "a.py"}}]}}
    recent = viewer._recent_claude_actions([row])
    assert recent[0]["at"] == expected_ms


def test_recent_claude_actions_at_is_none_without_a_timestamp():
    tail = [_tool_use("t1", "Read", {"file_path": "a.py"})]
    recent = viewer._recent_claude_actions(tail)
    assert recent[0]["at"] is None


def test_claude_subagents_lists_unresolved_agent_and_task_calls():
    tail = [_tool_use("a1", "Agent", {"subagent_type": "reviewer", "description": "d", "prompt": "p"}),
           _tool_use("a2", "Task", {"subagent_type": "explorer", "description": "d", "prompt": "p"})]
    assert viewer._claude_subagents(tail) == ["reviewer", "explorer"]


def test_claude_subagents_excludes_resolved_calls():
    tail = [_tool_use("a1", "Agent", {"subagent_type": "reviewer", "description": "d", "prompt": "p"}),
           _tool_result("a1")]
    assert viewer._claude_subagents(tail) == []


def test_claude_subagents_ignores_non_subagent_tools():
    tail = [_tool_use("a1", "Bash", {"command": "echo hi"})]
    assert viewer._claude_subagents(tail) == []


def test_claude_subagents_falls_back_to_tool_name_without_subagent_type():
    tail = [_tool_use("a1", "Agent", {"description": "d", "prompt": "p"})]
    assert viewer._claude_subagents(tail) == ["Agent"]


def test_claude_subagents_lists_a_background_agent_until_its_task_notification():
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer", "description": "d", "prompt": "p"}),
           _async_launch_result("a1", agentId="agent-bg-1"),
           _turn_duration(pendingBackgroundAgentCount=1)]
    assert viewer._claude_subagents(tail) == ["implementer"]


def test_claude_subagents_drops_a_background_agent_after_its_task_notification():
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer", "description": "d", "prompt": "p"}),
           _async_launch_result("a1", agentId="agent-bg-1"),
           _tool_use("a2", "Agent", {"subagent_type": "reviewer", "description": "d", "prompt": "p"}),
           _async_launch_result("a2", agentId="agent-bg-2"),
           _task_notification("agent-bg-1"),
           _task_notification("agent-bg-2", status="failed")]
    assert viewer._claude_subagents(tail) == []


def test_claude_subagents_keeps_background_agents_whose_notification_names_another_task():
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer", "description": "d", "prompt": "p"}),
           _async_launch_result("a1", agentId="agent-bg-1"),
           _task_notification("some-other-task")]
    assert viewer._claude_subagents(tail) == ["implementer"]


def test_claude_subagents_lists_sync_then_background_agents():
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer", "description": "d", "prompt": "p"}),
           _async_launch_result("a1", agentId="agent-bg-1"),
           _tool_use("a2", "Task", {"subagent_type": "explorer", "description": "d", "prompt": "p"})]
    assert viewer._claude_subagents(tail) == ["explorer", "implementer"]


def test_claude_subagents_lists_a_background_workflow_by_its_name():
    tail = _workflow_launch("w1", "w-task-1", "made-up-sweep")
    assert viewer._claude_subagents(tail) == ["Workflow made-up-sweep"]


def test_claude_subagents_drops_a_background_workflow_after_its_task_notification():
    tail = _workflow_launch("w1", "w-task-1", "made-up-sweep") + [_task_notification("w-task-1")]
    assert viewer._claude_subagents(tail) == []


def test_claude_subagents_does_not_guess_when_one_row_answers_two_launches():
    two_results = _tool_result("a1")
    two_results["message"]["content"].append(
        {"type": "tool_result", "tool_use_id": "a2", "content": "ok"})
    two_results["toolUseResult"] = {"isAsync": True, "status": "async_launched",
                                    "agentId": "agent-bg-1"}
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer", "description": "d", "prompt": "p"}),
           _tool_use("a2", "Agent", {"subagent_type": "reviewer", "description": "d", "prompt": "p"}),
           two_results]
    assert viewer._claude_subagents(tail) == []


def test_claude_subagents_ignores_async_results_of_non_subagent_tools():
    row = _async_launch_result("b1", agentId="bg-shell-1")
    tail = [_tool_use("b1", "Bash", {"command": "sleep 100", "run_in_background": True}), row]
    assert viewer._claude_subagents(tail) == []


def test_recent_claude_actions_shows_an_agent_call_by_its_description():
    tail = [_tool_use("a1", "Agent", {"subagent_type": "implementer",
                                      "description": "做 build 階段", "prompt": "p"})]
    recent = viewer._recent_claude_actions(tail)
    assert recent[0]["input"] == "做 build 階段"


# ========================================================= claude_rows ====

def _write_registry(sessions_dir, pid, status, **overrides):
    reg = _reg(status, pid=pid)
    reg.update(overrides)
    path = os.path.join(sessions_dir, "%d.json" % pid)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(reg, fh)
    return reg


def test_claude_rows_skips_non_interactive_kind(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    _write_registry(str(sessions_dir), 1, "idle", kind="background")
    rows, problems = viewer.claude_rows(str(tmp_path), 0)
    assert rows == []
    assert problems == []


def test_claude_rows_skips_bad_json_and_reports_a_problem(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "1.json").write_text("not json", encoding="utf-8")
    rows, problems = viewer.claude_rows(str(tmp_path), 0)
    assert rows == []
    assert len(problems) == 1


def test_claude_rows_never_opens_key_files(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "1.key").write_text("secret-material", encoding="utf-8")
    rows, problems = viewer.claude_rows(str(tmp_path), 0)
    assert rows == []
    assert problems == []


def test_claude_rows_marks_a_foreign_pid_domain_unknown_without_check_alive(
        tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    _write_registry(str(sessions_dir), 2, "idle", pidDomain="plan9:some-other-host")

    def boom(*a, **k):
        raise AssertionError("check_alive must not be called for a foreign pidDomain")
    monkeypatch.setattr(viewer, "check_alive", boom)

    rows, problems = viewer.claude_rows(str(tmp_path), 0)
    assert len(rows) == 1
    assert rows[0]["state"] == "unknown"


def test_claude_rows_drops_a_gone_process(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    _write_registry(str(sessions_dir), 3, "idle")
    monkeypatch.setattr(viewer, "check_alive", lambda *a, **k: "gone")
    rows, problems = viewer.claude_rows(str(tmp_path), 0)
    assert rows == []


def test_claude_rows_notes_alive_unverified(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    _write_registry(str(sessions_dir), 4, "idle")
    monkeypatch.setattr(viewer, "check_alive", lambda *a, **k: "alive-unverified")
    rows, problems = viewer.claude_rows(str(tmp_path), 0)
    assert len(rows) == 1
    assert "存活：推斷" in rows[0]["notes"]
    assert rows[0]["state"] == "done"
    # V4: an inferred liveness must be tagged as such so the page's
    # unconditional "存活：推斷" meta line (rowHTML's sinceNote) can fire.
    assert rows[0]["aliveCertainty"] == "inferred"


def test_claude_rows_builds_a_row_with_identifying_fields(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    reg = _write_registry(str(sessions_dir), 5, "idle",
                          cwd=os.path.join(os.sep, "made-up", "project-x"), sessionId="sess-xyz")
    monkeypatch.setattr(viewer, "check_alive", lambda *a, **k: "alive")
    rows, problems = viewer.claude_rows(str(tmp_path), 0)
    assert len(rows) == 1
    row = rows[0]
    assert row["key"] == "claude:5:%s" % reg["procStart"]
    assert row["platform"] == "claude"
    assert row["project"] == "project-x"
    assert row["cwd"] == os.path.join(os.sep, "made-up", "project-x")
    assert row["sessionId"] == "sess-xyz"
    assert row["model"] is None
    assert row["state"] == "done"
    assert row["notes"] == []
    assert row["aliveCertainty"] == "confirmed"


def test_claude_rows_missing_transcript_treats_tail_as_empty(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    _write_registry(str(sessions_dir), 6, "waiting",
                    cwd="D:\\made-up\\no-transcript-project", sessionId="sess-none")
    monkeypatch.setattr(viewer, "check_alive", lambda *a, **k: "alive")
    rows, problems = viewer.claude_rows(str(tmp_path), 0)
    assert len(rows) == 1
    # No transcript on disk -> no unresolved tool_use can be found -> attention.
    assert rows[0]["state"] == "attention"


def test_claude_rows_populates_summary_recent_and_subagents_from_transcript(
        tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    cwd = "D:\\made-up\\project-d2"
    _write_registry(str(sessions_dir), 7, "idle", cwd=cwd, sessionId="sess-d2")
    monkeypatch.setattr(viewer, "check_alive", lambda *a, **k: "alive")

    encoded = viewer.usage_collector.encoded_project_dir(cwd)
    transcript_dir = tmp_path / "projects" / encoded
    transcript_dir.mkdir(parents=True)
    transcript_path = transcript_dir / "sess-d2.jsonl"
    lines = [
        json.dumps(_tool_use("t1", "Read", {"file_path": "a.py"})),
        json.dumps(_tool_result("t1")),
        json.dumps({"type": "assistant", "message": {"content":
                    [{"type": "text", "text": "完成了 D2 測試"}]}}),
    ]
    transcript_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    rows, problems = viewer.claude_rows(str(tmp_path), 0)
    assert len(rows) == 1
    row = rows[0]
    assert row["summary"] == "完成了 D2 測試"
    assert row["recent"] == [{"at": None, "tool": "Read", "input": "a.py"}]
    assert row["subagents"] == []


def test_claude_rows_unknown_domain_row_has_d2_defaults(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    _write_registry(str(sessions_dir), 8, "idle", pidDomain="plan9:some-other-host")
    rows, problems = viewer.claude_rows(str(tmp_path), 0)
    assert len(rows) == 1
    assert rows[0]["summary"] is None
    assert rows[0]["recent"] == []
    assert rows[0]["subagents"] == []
