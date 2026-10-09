"""claude-hooks-1: one subagent's ordered hook observations -> confirmed model segments."""
import json
import os

import pytest

import timing
import timing_sources

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "timing", "claude-hooks")
BINDING = {"run_id": "run", "stage": "build", "actor_id": "agent-a", "source_id": "claude-hooks-1"}


def obs(seq, event, at_ms, tool_use_id=None, tool_use_ids=None):
    row = {"seq": seq, "event": event, "at_ms": at_ms}
    if tool_use_id is not None:
        row["tool_use_id"] = tool_use_id
    if tool_use_ids is not None:
        row["tool_use_ids"] = tool_use_ids
    return row


def run(rows, binding=BINDING):
    return timing_sources.normalize_event("claude", {"observations": rows}, binding)


def segments(events):
    begins = {e["activity_id"]: e["at_ms"] for e in events if e["kind"] == "work_begin"}
    ends = {e["activity_id"]: e["at_ms"] for e in events if e["kind"] == "work_end"}
    assert begins.keys() == ends.keys()
    return sorted((begins[k], ends[k]) for k in begins)


def gaps(events):
    return [e["reason"] for e in events if e["kind"] == "gap"]


def fixture_observations(agent_id):
    """The recorded hook lines of one subagent, in the shape timing_hook will write."""
    kinds = {"SubagentStart": "start", "PreToolUse": "pre", "PostToolBatch": "batch", "SubagentStop": "stop"}
    rows = []
    with open(os.path.join(FIXTURE, "session.jsonl"), encoding="ascii") as fh:
        for line in fh:
            rec = json.loads(line)
            if rec["agent_id"] != agent_id or rec["event"] not in kinds:
                continue
            row = {"seq": len(rows), "event": kinds[rec["event"]], "at_ms": rec["at_ms"]}
            if rec["event"] == "PreToolUse":
                row["tool_use_id"] = rec["tool_use_id"]
            if rec["event"] == "PostToolBatch":
                row["tool_use_ids"] = rec["tool_calls_ids"]
            rows.append(row)
    return rows


def fixture_agents():
    with open(os.path.join(FIXTURE, "meta.json"), encoding="ascii") as fh:
        meta = json.load(fh)
    return meta["agents"], meta["claude_code_version"]


def test_only_claude_hooks_1_on_claude_is_admitted():
    assert timing_sources.source_admitted("claude-hooks-1", "claude") is True
    assert timing_sources.source_admitted("claude-hooks-1", "codex") is False
    assert timing_sources.source_admitted("claude-hooks-2", "claude") is False
    assert timing_sources.source_admitted("source:v1", "claude") is False


@pytest.mark.parametrize("which", ["foreground", "background"])
def test_recorded_real_session_gives_model_segments(which):
    agents, version = fixture_agents()
    assert version.startswith("2.1.")  # fixtures carry the Claude Code version they came from
    rows = fixture_observations(agents[which])
    assert [r["event"] for r in rows] == ["start", "pre", "batch", "stop"]
    at = [r["at_ms"] for r in rows]
    events = run(rows)
    assert gaps(events) == []
    # start..pre and batch..stop; the pre..batch tool segment is not counted
    assert segments(events) == [(at[0], at[1]), (at[2], at[3])]


def test_tool_segments_are_never_counted():
    events = run([obs(0, "start", 0), obs(1, "pre", 30, "t1"), obs(2, "batch", 40, tool_use_ids=["t1"]),
                  obs(3, "stop", 70)])
    assert segments(events) == [(0, 30), (40, 70)]  # the 30..40 tool segment may hold a permission wait


def test_output_shape_has_no_source_coverage_and_is_deterministic():
    rows = [obs(0, "start", 0), obs(1, "stop", 5)]
    first, second = run(rows), run(list(reversed(rows)))
    assert first == second
    assert {e["kind"] for e in first} == {"work_begin", "work_end"}
    for e in first:
        assert e["source_id"] == "claude-hooks-1" and e["platform"] == "claude"
        assert e["run_id"] == "run" and e["stage"] == "build" and e["actor_id"] == "agent-a"
        assert len(e["event_id"]) == 64 and len(e["activity_id"]) == 32


def test_events_pass_the_journal_validation(tmp_path):
    track = tmp_path / ".claude" / "track" / "feature"
    timing.begin_run(str(track), "build", "run", "claude")
    timing.bind_actor(str(track), "run", "agent-a", "sess", "claude-hooks-1", "agent-a")
    binding = dict(BINDING)
    reasons = timing.collect_event(str(tmp_path), "claude", "sess", "agent-a", "agent-a",
                                   {"observations": [obs(0, "start", 0), obs(1, "pre", 30, "t1"),
                                                     obs(2, "batch", 40, tool_use_ids=["t1"]), obs(3, "stop", 70)]})
    assert reasons == []
    again = timing.collect_event(str(tmp_path), "claude", "sess", "agent-a", "agent-a",
                                 {"observations": [obs(0, "start", 0), obs(1, "pre", 30, "t1"),
                                                   obs(2, "batch", 40, tool_use_ids=["t1"]), obs(3, "stop", 70)]})
    assert again == []
    events, problems = timing.read_events(str(track))
    assert not problems
    assert sorted((e["at_ms"] for e in events if e["kind"] == "work_begin")) == [0, 40]  # no duplicates
    assert binding["source_id"] == "claude-hooks-1"


def test_parallel_tools_one_batch():
    events = run([obs(0, "start", 0), obs(1, "pre", 10, "t1"), obs(2, "pre", 11, "t2"),
                  obs(3, "batch", 50, tool_use_ids=["t2", "t1"]), obs(4, "stop", 60)])
    assert gaps(events) == [] and segments(events) == [(0, 10), (50, 60)]


def test_unconfirmed_segment_is_not_written_until_the_batch():
    events = run([obs(0, "start", 0), obs(1, "pre", 30, "t1")])
    assert events == []  # nothing proves the tool was seen to the end yet


def test_missing_pre_is_event_missing_and_stops_the_actor():
    events = run([obs(0, "start", 0), obs(1, "pre", 10, "t1"), obs(2, "batch", 20, tool_use_ids=["t1", "t2"]),
                  obs(3, "start", 25), obs(4, "stop", 90)])
    assert gaps(events) == ["event-missing"]
    assert segments(events) == []  # the pending 0..10 was never confirmed
    # earlier confirmed segments survive
    events = run([obs(0, "start", 0), obs(1, "pre", 10, "t1"), obs(2, "batch", 20, tool_use_ids=["t1"]),
                  obs(3, "pre", 30, "t2"), obs(4, "batch", 40, tool_use_ids=["t2", "t9"]), obs(5, "stop", 80)])
    assert gaps(events) == ["event-missing"]
    assert segments(events) == [(0, 10)]


def test_batch_with_tools_still_outstanding_is_missing():
    events = run([obs(0, "start", 0), obs(1, "pre", 10, "t1"), obs(2, "pre", 11, "t2"),
                  obs(3, "batch", 20, tool_use_ids=["t1"]), obs(4, "stop", 30)])
    assert gaps(events) == ["event-missing"] and segments(events) == []


def test_start_while_segment_open_is_missing():
    events = run([obs(0, "start", 0), obs(1, "start", 5), obs(2, "stop", 9)])
    assert gaps(events) == ["event-missing"] and segments(events) == []


def test_two_subagents_mixed_into_one_spool_is_missing_not_inflated():
    events = run([obs(0, "start", 0), obs(1, "start", 1), obs(2, "pre", 10, "a"), obs(3, "pre", 11, "b"),
                  obs(4, "batch", 20, tool_use_ids=["a"]), obs(5, "batch", 21, tool_use_ids=["b"]),
                  obs(6, "stop", 30), obs(7, "stop", 31)])
    assert "event-missing" in gaps(events)
    assert segments(events) == []


def test_stop_with_outstanding_tool_discards_pending():
    events = run([obs(0, "start", 0), obs(1, "pre", 10, "t1"), obs(2, "stop", 30)])
    assert events == []


def test_late_batch_after_stop_confirms_without_fake_gap():
    rows = [obs(0, "start", 0), obs(1, "pre", 10, "t1"), obs(2, "stop", 30)]
    assert run(rows) == []
    events = run(rows + [obs(3, "batch", 35, tool_use_ids=["t1"])])
    assert gaps(events) == [] and segments(events) == [(0, 10)]


def test_clock_going_backwards_is_missing():
    events = run([obs(0, "start", 100), obs(1, "pre", 50, "t1"), obs(2, "batch", 60, tool_use_ids=["t1"]),
                  obs(3, "stop", 40)])
    assert gaps(events) == ["event-missing"]


def test_stop_without_start_writes_nothing():
    assert run([obs(0, "stop", 5)]) == []


def test_resumed_subagent_gets_a_second_segment():
    events = run([obs(0, "start", 0), obs(1, "stop", 10), obs(2, "start", 100), obs(3, "stop", 130)])
    assert gaps(events) == [] and segments(events) == [(0, 10), (100, 130)]


def test_progress_never_extends_to_now():
    open_only = run([obs(0, "start", 0)])
    assert open_only == []


@pytest.mark.parametrize("bad", [
    {"seq": 0, "event": "start", "at_ms": "0"},
    {"seq": 0, "event": "start", "at_ms": True},
    {"seq": 0, "event": "start", "at_ms": -1},
    {"seq": 0, "event": "nap", "at_ms": 1},
    {"seq": 0, "event": "pre", "at_ms": 1},
    {"seq": 0, "event": "batch", "at_ms": 1, "tool_use_ids": "t1"},
    "not a row",
])
def test_bad_observation_is_missing_not_an_exception(bad):
    events = run([bad])
    assert gaps(events) == ["event-missing"]


def test_bad_payload_is_missing():
    for payload in ({}, {"observations": "x"}, []):
        events = timing_sources.normalize_event("claude", payload, BINDING)
        assert gaps(events) == ["event-missing"]


def test_gap_ids_are_stable_across_calls():
    rows = [obs(0, "start", 0), obs(1, "start", 5)]
    assert run(rows) == run(rows)


def test_other_platform_or_source_stays_unverified():
    events = timing_sources.normalize_event("codex", {"observations": []}, BINDING)
    assert gaps(events) == ["source-unverified"]
    other = dict(BINDING, source_id="source:v1")
    assert gaps(timing_sources.normalize_event("claude", {"observations": []}, other)) == ["source-unverified"]


# #333: codex-hooks-1. Codex has no PostToolBatch; each tool closes with its own
# PostToolUse ("post"), and the tools a subagent ran in parallel count as one
# batch once the last of them has closed.
CODEX_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "timing", "codex-hooks")
CODEX_BINDING = dict(BINDING, source_id="codex-hooks-1")


def codex_run(rows, binding=CODEX_BINDING):
    return timing_sources.normalize_event("codex", {"observations": rows}, binding)


def codex_fixture_observations():
    kinds = {"SubagentStart": "start", "PreToolUse": "pre", "PostToolUse": "post", "SubagentStop": "stop"}
    with open(os.path.join(CODEX_FIXTURE, "meta.json"), encoding="ascii") as fh:
        child = json.load(fh)["agents"]["child"]
    rows = []
    with open(os.path.join(CODEX_FIXTURE, "session.jsonl"), encoding="ascii") as fh:
        for line in fh:
            rec = json.loads(line)
            if rec["agent_id"] != child or rec["event"] not in kinds:
                continue
            row = {"seq": len(rows), "event": kinds[rec["event"]], "at_ms": rec["at_ms"]}
            if rec["tool_use_id"]:
                row["tool_use_id"] = rec["tool_use_id"]
            rows.append(row)
    return rows


def test_codex_hooks_1_is_admitted_only_on_codex():
    assert timing_sources.source_admitted("codex-hooks-1", "codex") is True
    assert timing_sources.source_admitted("codex-hooks-1", "claude") is False
    assert timing_sources.source_admitted("codex-hooks-2", "codex") is False
    # An unknown platform has no source, even when the binding names none (PR #337 review).
    assert timing_sources.source_admitted(None, "other") is False


def test_unknown_platform_with_no_source_is_unverified_not_an_error():
    binding = dict(BINDING, source_id=None)
    events = timing_sources.normalize_event("other", {"observations": [obs(0, "start", 0)]}, binding)
    assert gaps(events) == ["source-unverified"]


def test_codex_recorded_real_session_gives_model_segments():
    rows = codex_fixture_observations()
    at = {row["event"]: row["at_ms"] for row in rows}
    events = codex_run(rows)
    assert gaps(events) == []
    assert segments(events) == [(at["start"], at["pre"]), (at["post"], at["stop"])]


def test_codex_parallel_tools_count_as_one_batch_after_the_last_post():
    events = codex_run([obs(0, "start", 0), obs(1, "pre", 10, "t1"), obs(2, "pre", 11, "t2"),
                        obs(3, "post", 30, "t2"), obs(4, "post", 50, "t1"), obs(5, "stop", 60)])
    assert gaps(events) == [] and segments(events) == [(0, 10), (50, 60)]


def test_codex_post_without_its_pre_is_missing():
    events = codex_run([obs(0, "start", 0), obs(1, "pre", 10, "t1"), obs(2, "post", 20, "t9"),
                        obs(3, "stop", 30)])
    assert "event-missing" in gaps(events)


def test_codex_events_pass_the_journal_validation(tmp_path):
    track = tmp_path / ".claude" / "track" / "feature"
    timing.begin_run(str(track), "build", "run", "codex")
    timing.bind_actor(str(track), "run", "agent-a", "sess", "codex-hooks-1", "agent-a")
    rows = [obs(0, "start", 0), obs(1, "pre", 30, "t1"), obs(2, "post", 40, "t1"), obs(3, "stop", 70)]
    assert timing.collect_event(str(tmp_path), "codex", "sess", "agent-a", "agent-a",
                                {"observations": rows}) == []
    events, problems = timing.read_events(str(track))
    assert not problems
    assert sorted(e["at_ms"] for e in events if e["kind"] == "work_begin") == [0, 40]


@pytest.mark.parametrize("platform,binding,event", [
    ("claude", BINDING, "post"),        # Claude closes tools with a batch, never a post
    ("codex", CODEX_BINDING, "batch"),  # and Codex has no batch hook at all
])
def test_each_platform_rejects_the_other_platforms_tool_close(platform, binding, event):
    extra = {"tool_use_id": "t1"} if event == "post" else {"tool_use_ids": ["t1"]}
    rows = [obs(0, "start", 0), obs(1, "pre", 10, "t1"), dict(obs(2, event, 20), **extra), obs(3, "stop", 30)]
    events = timing_sources.normalize_event(platform, {"observations": rows}, binding)
    assert gaps(events) == ["event-missing"] and segments(events) == []
