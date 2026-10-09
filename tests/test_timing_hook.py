"""The hook receiver: spool observations, bind subagents to runs, settle into the journal."""
import json
import os
import re
import subprocess
import sys
import time

import pytest

import timing
import timing_hook

SCRIPTS = os.path.dirname(timing.__file__)


class Env:
    def __init__(self, tmp_path):
        self.project = str(tmp_path / "project")
        self.data = str(tmp_path / "plugin-data")
        os.makedirs(self.project)
        os.makedirs(self.data)
        self.now = 1_000_000
        self.session = "main-session"

    def track(self, name="feature", run_id="run-1", stage="build"):
        path = os.path.join(self.project, ".claude", "track", name)
        timing.begin_run(path, stage, run_id, "claude")
        return path

    def send(self, payload, advance=10, session=None):
        self.now += advance
        payload = dict(payload, session_id=session or self.session)
        timing_hook.observe(payload, self.data, self.project, self.now)

    def start(self, agent):
        self.send({"hook_event_name": "SubagentStart", "agent_id": agent})

    def pre(self, agent, tool):
        self.send({"hook_event_name": "PreToolUse", "agent_id": agent, "tool_name": "Bash", "tool_use_id": tool})

    def batch(self, agent, *tools):
        self.send({"hook_event_name": "PostToolBatch", "agent_id": agent,
                   "tool_calls": [{"tool_use_id": t, "tool_name": "Bash"} for t in tools]})

    def stop(self, agent):
        self.send({"hook_event_name": "SubagentStop", "agent_id": agent})

    def agent_done(self, agent_id, prompt="do it", parent=None, session=None):
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Agent",
                   "tool_input": {"prompt": prompt}, "tool_response": {"agentId": agent_id}}
        if parent:
            payload["agent_id"] = parent
        self.send(payload, session=session)

    def spool(self, kind):
        root = os.path.join(self.data, "timing-spool", kind)
        return sorted(os.listdir(root)) if os.path.isdir(root) else []


def marker(run_id):
    return "cai-timing-run: %s" % run_id


def journal(path):
    events, problems = timing.read_events(path)
    assert not problems
    return events


def work(events, actor=None):
    begins = sorted(e["at_ms"] for e in events if e["kind"] == "work_begin" and actor in (None, e["actor_id"]))
    ends = sorted(e["at_ms"] for e in events if e["kind"] == "work_end" and actor in (None, e["actor_id"]))
    return list(zip(begins, ends))


def gaps(events):
    return sorted((e["actor_id"], e["reason"]) for e in events if e["kind"] == "gap")


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def run_agent(env, agent, tool="t1"):
    env.start(agent)
    env.pre(agent, tool)
    env.batch(agent, tool)
    env.stop(agent)


def test_background_order_binds_first_and_settles_on_stop(env):
    path = env.track()
    env.agent_done("agentA", prompt=marker("run-1") + "\nbuild it")
    run_agent(env, "agentA")
    events = journal(path)
    assert len(work(events, "agentA")) == 2
    assert env.spool("obs") == []  # settled and stopped: spool removed
    assert len(env.spool("bind")) == 1
    bind = [e for e in events if e["kind"] == "actor_bind"][0]
    assert bind["source_id"] == "claude-hooks-1" and bind["source_run_id"] == "agentA"
    assert bind["session_id"] == "main-session" and bind["parent_actor_id"] is None


def test_foreground_order_keeps_spool_until_the_agent_result_arrives(env):
    path = env.track()
    run_agent(env, "agentA")
    assert work(journal(path)) == []
    assert len(env.spool("obs")) == 1  # a stop must not delete a spool that has no bind record yet
    env.agent_done("agentA", prompt=marker("run-1"))
    assert len(work(journal(path), "agentA")) == 2
    assert env.spool("obs") == []


def test_background_and_foreground_give_the_same_segments(env, tmp_path):
    path = env.track()
    env.agent_done("agentA", prompt=marker("run-1"))
    env.now = 2_000_000
    run_agent(env, "agentA")
    bg = [(b - 2_000_000, e - 2_000_000) for b, e in work(journal(path), "agentA")]
    other = Env(tmp_path / "second")
    path2 = other.track()
    other.now = 2_000_000
    run_agent(other, "agentA")
    other.agent_done("agentA", prompt=marker("run-1"))
    fg = [(b - 2_000_000, e - 2_000_000) for b, e in work(journal(path2), "agentA")]
    assert bg == fg == [(10, 20), (30, 40)]


def test_nested_foreground_waits_for_the_whole_chain(env):
    path = env.track()
    run_agent(env, "child", "tc")           # child stops first
    env.start("agentP")
    env.stop("agentP")                       # parent stops before the main session sees the result
    env.agent_done("child", parent="agentP")  # parent's inner Agent result: link written
    assert work(journal(path)) == []          # parent's own bind is still unknown
    assert len(env.spool("obs")) == 2
    env.agent_done("agentP", prompt=marker("run-1"))
    events = journal(path)
    assert len(work(events, "child")) == 2 and len(work(events, "agentP")) == 1
    child_bind = [e for e in events if e["kind"] == "actor_bind" and e["actor_id"] == "child"][0]
    assert child_bind["parent_actor_id"] == "agentP"
    assert env.spool("obs") == []


def test_no_marker_is_unbound_and_spool_is_dropped_after_stop(env):
    path = env.track()
    env.agent_done("agentA", prompt="plain prompt")
    run_agent(env, "agentA")
    assert work(journal(path)) == [] and env.spool("obs") == []


def test_two_different_markers_write_ambiguous_gaps_and_do_not_bind(env):
    first = env.track("one", "run-1")
    second = env.track("two", "run-2")
    env.agent_done("agentA", prompt=marker("run-1") + "\n" + marker("run-2"))
    run_agent(env, "agentA")
    for path in (first, second):
        events = journal(path)
        assert gaps(events) == [("agentA", "binding-ambiguous")]
        assert work(events) == []
    assert env.spool("obs") == []


def test_same_marker_twice_is_one_marker(env):
    path = env.track()
    env.agent_done("agentA", prompt=marker("run-1") + "\n" + marker("run-1"))
    run_agent(env, "agentA")
    assert len(work(journal(path))) == 2


def test_closed_run_writes_a_gap_and_stays_unbound(env):
    path = env.track()
    timing.end_run(path, "run-1")
    env.agent_done("agentA", prompt=marker("run-1"))
    run_agent(env, "agentA")
    events = journal(path)
    assert gaps(events) == [("agentA", "run-closed")] and work(events) == []
    assert env.spool("obs") == []


def test_background_agent_finishing_after_end_is_rejected_with_a_gap(env):
    path = env.track()
    env.agent_done("agentA", prompt=marker("run-1"))
    env.start("agentA")
    env.pre("agentA", "t1")
    env.batch("agentA", "t1")
    timing.end_run(path, "run-1")
    env.stop("agentA")
    events = journal(path)
    assert ("agentA", "run-closed") in gaps(events)
    assert len(work(events, "agentA")) <= 1  # the segment confirmed before end may stay; nothing new opens


def test_closed_run_drops_a_spool_whose_stop_never_arrived(env):
    # #320: a cancelled SubagentStop hook leaves the spool unfinished forever. Every
    # later hook re-settled it until it expired, which pushed settles past the 5 s
    # hook timeout, so later runs of a stage lost their bindings and segments.
    path = env.track()
    env.agent_done("agentA", prompt=marker("run-1"))
    env.start("agentA")
    env.pre("agentA", "t1")
    env.batch("agentA", "t1")
    timing.end_run(path, "run-1")
    timing_hook.settle(env.data, env.now + 1)
    assert env.spool("obs") == []
    assert len(work(journal(path), "agentA")) == 1  # the segment confirmed before end stays


def test_closed_run_drops_a_spool_with_a_tool_left_open(env):
    # #320: same, when the cancelled hook was the PostToolBatch that closes a tool.
    path = env.track()
    env.agent_done("agentA", prompt=marker("run-1"))
    env.start("agentA")
    env.pre("agentA", "t1")
    env.batch("agentA", "t1")
    env.pre("agentA", "t2")
    env.stop("agentA")
    assert len(env.spool("obs")) == 1  # open run: a late batch may still arrive
    timing.end_run(path, "run-1")
    timing_hook.settle(env.data, env.now + 1)
    assert env.spool("obs") == []


def test_cli_end_lets_the_next_settle_drop_an_unfinished_spool(env, capsys):
    # #320 through the CLI the track skill runs: begin leaves the open marker that
    # keeps a live spool, end removes it, and the next settle drops the spool.
    path = os.path.join(env.project, ".claude", "track", "feature")
    assert timing.main(["begin", "--track-dir", path, "--stage", "build", "--platform", "claude"]) == 0
    line = capsys.readouterr().out.strip()
    run_id = line.split(": ", 1)[1]
    env.agent_done("agentA", prompt=line)
    env.start("agentA")
    env.pre("agentA", "t1")
    env.batch("agentA", "t1")
    timing_hook.settle(env.data, env.now + 1)
    assert len(env.spool("obs")) == 1
    assert timing.main(["end", "--track-dir", path, "--run", run_id]) == 0
    timing_hook.settle(env.data, env.now + 2)
    assert env.spool("obs") == []
    assert len(work(journal(path), "agentA")) == 1


def test_unknown_run_marker_is_unbound(env):
    env.track()
    env.agent_done("agentA", prompt=marker("no-such-run"))
    run_agent(env, "agentA")
    assert env.spool("obs") == []


def test_two_tracks_interleaved_in_one_session_do_not_cross(env):
    one, two = env.track("one", "run-1"), env.track("two", "run-2", "verify")
    env.agent_done("a1", prompt=marker("run-1"))
    env.agent_done("a2", prompt=marker("run-2"))
    run_agent(env, "a1", "x1")
    run_agent(env, "a2", "x2")
    assert len(work(journal(one))) == 2 and len(work(journal(two))) == 2
    assert all(e["actor_id"] == "a1" for e in journal(one) if e["kind"] == "work_begin")
    assert all(e["actor_id"] == "a2" for e in journal(two) if e["kind"] == "work_begin")


def test_main_session_input_without_session_id_is_unbound(env):
    path = env.track()
    payload = {"hook_event_name": "PostToolUse", "tool_name": "Agent",
               "tool_input": {"prompt": marker("run-1")}, "tool_response": {"agentId": "agentA"}}
    timing_hook.observe(payload, env.data, env.project, env.now)
    run_agent(env, "agentA")
    assert work(journal(path)) == [] and env.spool("obs") == []


def test_two_different_bindings_for_one_agent_id_do_not_bind(env):
    path = env.track("one", "run-1")
    env.track("two", "run-2")
    env.agent_done("agentA", prompt=marker("run-1"))
    env.agent_done("agentA", prompt=marker("run-2"))
    run_agent(env, "agentA")
    assert work(journal(path)) == []
    assert env.spool("obs") == []


def test_never_bound_spool_and_old_bindings_expire_after_seven_days(env):
    env.track()
    env.now = int(time.time() * 1000)
    env.start("ghost")
    env.agent_done("known", prompt="plain")
    assert env.spool("obs") and env.spool("bind")

    def age(days):
        old = time.time() - days * 24 * 3600
        for kind in ("obs", "bind"):
            for name in env.spool(kind):
                os.utime(os.path.join(env.data, "timing-spool", kind, name), (old, old))
        timing_hook.settle(env.data, int(time.time() * 1000))

    age(6)
    assert env.spool("obs") and env.spool("bind")  # six days: nothing expires
    age(8)
    assert env.spool("obs") == [] and env.spool("bind") == []
    assert not os.path.isdir(os.path.join(env.data, "timing-spool", "obs"))


def test_late_batch_is_merged_without_a_false_gap(env):
    path = env.track()
    env.agent_done("agentA", prompt=marker("run-1"))
    env.start("agentA")
    env.pre("agentA", "t1")
    env.stop("agentA")  # the async batch hook has not landed yet
    assert gaps(journal(path)) == [] and len(env.spool("obs")) == 1
    env.batch("agentA", "t1")
    events = journal(path)
    assert gaps(events) == [] and len(work(events, "agentA")) == 1
    assert env.spool("obs") == []


def test_missing_pre_is_event_missing_and_earlier_segments_stay(env):
    path = env.track()
    env.agent_done("agentA", prompt=marker("run-1"))
    env.start("agentA")
    env.pre("agentA", "t1")
    env.batch("agentA", "t1")
    env.pre("agentA", "t2")
    env.batch("agentA", "t2", "t3")  # t3 never had a PreToolUse
    env.stop("agentA")
    events = journal(path)
    assert gaps(events) == [("agentA", "event-missing")]
    assert len(work(events, "agentA")) == 1


def test_settling_again_changes_nothing(env):
    path = env.track()
    env.agent_done("agentA", prompt=marker("run-1"))
    run_agent(env, "agentA")
    before = open(os.path.join(path, "timing.jsonl"), "rb").read()
    timing_hook.settle(env.data, env.now + 1)
    timing_hook.settle(env.data, env.now + 2)
    assert open(os.path.join(path, "timing.jsonl"), "rb").read() == before


def test_chain_deeper_than_eight_is_unbound(env):
    path = env.track()
    env.agent_done("l0", prompt=marker("run-1"))
    for i in range(1, 10):
        env.agent_done("l%d" % i, parent="l%d" % (i - 1))
    run_agent(env, "l9")
    assert work(journal(path), "l9") == []
    assert env.spool("obs") == []


def test_spool_files_hold_no_prompt_or_tool_content(env):
    env.track()
    env.send({"hook_event_name": "PreToolUse", "agent_id": "agentA", "tool_name": "Bash",
              "tool_use_id": "t1", "tool_input": {"command": "SECRET-COMMAND"}})
    env.agent_done("agentA", prompt=marker("run-1") + "\nSECRET-PROMPT")
    blob = ""
    for kind in ("obs", "bind"):
        for name in env.spool(kind):
            blob += open(os.path.join(env.data, "timing-spool", kind, name), encoding="utf-8").read()
    assert "SECRET" not in blob and "agent_type" not in blob


def test_settling_a_long_agent_does_not_reparse_the_journal_per_segment(env, monkeypatch):
    # Every PostToolBatch settles the agent's whole spool inside the hook's 5 s
    # budget. Re-appending each confirmed segment, with a full journal parse per
    # append, makes one settle cost O(segments x journal) and the hook is killed.
    path = env.track()
    env.agent_done("agentA", prompt=marker("run-1"))
    env.start("agentA")
    for i in range(40):
        env.pre("agentA", "t%d" % i)
        env.batch("agentA", "t%d" % i)
    parses = []
    real = timing._events_from_bytes
    monkeypatch.setattr(timing, "_events_from_bytes", lambda raw: parses.append(1) or real(raw))
    env.pre("agentA", "last")
    env.batch("agentA", "last")
    assert len(work(journal(path), "agentA")) == 41
    assert len(parses) <= 40, len(parses)


def test_track_skill_commands_match_the_cli_and_the_marker_the_hook_reads(env, capsys):
    # The SKILL text is the only production caller of begin/end; each side was
    # otherwise tested against its own hand-written copy of the other.
    skill = open(os.path.join(SCRIPTS, "..", "skills", "track", "SKILL.md"), encoding="utf-8").read()
    flat = " ".join(skill.split())
    for command, names in (("begin", ["track-dir", "stage", "platform"]), ("end", ["track-dir", "run"])):
        text = flat.split("scripts/timing.py " + command + " ", 1)[1].split("`", 1)[0]
        assert re.findall(r"--[a-z-]+", text) == ["--" + n for n in names]
    assert "`cai-timing-run: <run_id>`" in flat
    # A stage re-dispatched after its first report must be timed too.
    assert "re-dispatch" in flat.split("timing.py begin", 1)[1].split("**Record.**", 1)[0]

    path = env.track()
    assert timing.main(["begin", "--track-dir", path, "--stage", "build", "--platform", "claude"]) == 0
    line = capsys.readouterr().out
    run_id = line.strip().split(": ", 1)[1]
    env.agent_done("agentA", prompt=line.strip() + "\nbuild it")
    run_agent(env, "agentA")
    events = journal(path)
    assert len(work(events, "agentA")) == 2
    assert {e["run_id"] for e in events if e["kind"] == "actor_bind"} == {run_id}


def test_file_names_do_not_embed_raw_ids(env):
    env.track()
    env.start("agentA")
    assert all("agentA" not in n and len(n) == len("x" * 32 + ".jsonl") for n in env.spool("obs"))


def test_other_hook_events_and_missing_fields_are_ignored(env):
    env.track()
    for payload in ({}, {"hook_event_name": "PreToolUse"}, {"hook_event_name": "SubagentStart"},
                    {"hook_event_name": "PostToolUse", "tool_name": "Agent"},
                    {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_response": {"agentId": "x"}},
                    {"hook_event_name": "PostToolBatch", "agent_id": "a", "tool_calls": []},
                    {"hook_event_name": "Notification", "agent_id": "a"}):
        env.send(payload)
    assert env.spool("obs") == [] and env.spool("bind") == []


def hook(env_vars, stdin):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "timing_hook.py")], input=stdin,
                          capture_output=True, text=True, env=env_vars, timeout=60)


@pytest.mark.parametrize("stdin", ["", "not json", "[]", "{}", '{"hook_event_name": "SubagentStart"}'])
def test_main_is_silent_and_exits_zero_on_any_input(env, stdin):
    full = dict(os.environ, CLAUDE_PLUGIN_DATA=env.data, CLAUDE_PROJECT_DIR=env.project)
    for variables in (full, {k: v for k, v in full.items() if k != "CLAUDE_PLUGIN_DATA"},
                      {k: v for k, v in full.items() if k != "CLAUDE_PROJECT_DIR"}):
        result = hook(variables, stdin)
        assert result.returncode == 0 and result.stdout == ""
        assert len(result.stderr.strip().splitlines()) <= 1


def test_main_end_to_end_through_a_real_process(env):
    path = env.track()
    full = dict(os.environ, CLAUDE_PLUGIN_DATA=env.data, CLAUDE_PROJECT_DIR=env.project)
    steps = [
        {"hook_event_name": "PostToolUse", "tool_name": "Agent", "session_id": "s",
         "tool_input": {"prompt": marker("run-1")}, "tool_response": {"agentId": "agentA"}},
        {"hook_event_name": "SubagentStart", "agent_id": "agentA", "session_id": "s"},
        {"hook_event_name": "PreToolUse", "agent_id": "agentA", "tool_use_id": "t1", "session_id": "s"},
        {"hook_event_name": "PostToolBatch", "agent_id": "agentA", "session_id": "s",
         "tool_calls": [{"tool_use_id": "t1"}]},
        {"hook_event_name": "SubagentStop", "agent_id": "agentA", "session_id": "s"},
    ]
    for step in steps:
        result = hook(full, json.dumps(step))
        assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
        time.sleep(0.01)
    assert len(work(journal(path), "agentA")) == 2


def test_main_reads_stdin_as_utf8_whatever_the_locale_says(env):
    # Claude Code writes UTF-8; on a cp950 machine text-mode stdin would fail to
    # decode a Chinese tool result and the swallowed error would lose the row.
    path = env.track()
    full = dict(os.environ, CLAUDE_PLUGIN_DATA=env.data, CLAUDE_PROJECT_DIR=env.project,
                PYTHONIOENCODING="ascii")
    full.pop("PYTHONUTF8", None)
    steps = [
        {"hook_event_name": "PostToolUse", "tool_name": "Agent", "session_id": "s",
         "tool_input": {"prompt": marker("run-1")}, "tool_response": {"agentId": "agentA"}},
        {"hook_event_name": "SubagentStart", "agent_id": "agentA", "session_id": "s"},
        {"hook_event_name": "PreToolUse", "agent_id": "agentA", "tool_use_id": "t1", "session_id": "s"},
        {"hook_event_name": "PostToolBatch", "agent_id": "agentA", "session_id": "s",
         "tool_calls": [{"tool_use_id": "t1", "tool_response": "繁體中文"}]},
        {"hook_event_name": "SubagentStop", "agent_id": "agentA", "session_id": "s",
         "last_assistant_message": "完成"},
    ]
    for step in steps:
        result = subprocess.run([sys.executable, os.path.join(SCRIPTS, "timing_hook.py")],
                                input=json.dumps(step, ensure_ascii=False).encode("utf-8"),
                                capture_output=True, env=full, timeout=60)
        assert result.returncode == 0 and result.stdout == b"" and result.stderr == b""
        time.sleep(0.01)
    assert len(work(journal(path), "agentA")) == 2
    blob = "".join(open(os.path.join(env.data, "timing-spool", k, n), encoding="ascii").read()
                   for k in ("obs", "bind") for n in env.spool(k))
    assert "繁" not in blob and "完" not in blob


def replay_payload(rec):
    """Rebuild the hook input of a recorded line, minus the content the probe never kept."""
    payload = {"hook_event_name": rec["event"], "session_id": rec["session_id"]}
    if rec["agent_id"]:
        payload["agent_id"] = rec["agent_id"]
    if rec["tool_use_id"]:
        payload["tool_use_id"] = rec["tool_use_id"]
    if rec["tool_calls_ids"] is not None:
        payload["tool_calls"] = [{"tool_use_id": i} for i in rec["tool_calls_ids"]]
    if rec["event"] == "PostToolUse":
        payload.update(tool_name=rec["tool_name"], tool_input={"prompt": rec["prompt_marker"] or ""},
                       tool_response={"agentId": rec["tool_response_agentId"]})
    return payload


def test_replaying_the_recorded_real_session_gives_the_same_segments_both_orders(env):
    """Foreground result arrives after the subagent stopped, background result right after it started."""
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "timing", "claude-hooks")
    with open(os.path.join(fixture, "session.jsonl"), encoding="ascii") as fh:
        records = [json.loads(line) for line in fh]
    meta = json.load(open(os.path.join(fixture, "meta.json"), encoding="ascii"))
    foreground = env.track("fg", "probe-fg")
    background = env.track("bg", "probe-bg")
    base = 5_000_000
    for rec in records:
        timing_hook.observe(replay_payload(rec), env.data, env.project, base + rec["at_ms"])
    by_agent = {a: [r for r in records if r["agent_id"] == a] for a in meta["agents"].values()}
    for which, path in (("foreground", foreground), ("background", background)):
        agent = meta["agents"][which]
        at = {r["event"]: r["at_ms"] for r in by_agent[agent]}
        assert work(journal(path), agent) == [(base + at["SubagentStart"], base + at["PreToolUse"]),
                                              (base + at["PostToolBatch"], base + at["SubagentStop"])]
        assert gaps(journal(path)) == []
    assert env.spool("obs") == []


# #333: Codex. Its hooks bind a subagent through the main session's
# PostToolUse(spawn_agent), whose tool_input.message carries the marker and whose
# tool_response is a JSON string naming the new agent_id; tools close one by one
# with PostToolUse instead of a PostToolBatch.
class CodexEnv(Env):
    def track(self, name="feature", run_id="run-1", stage="build", platform="codex"):
        path = os.path.join(self.project, ".claude", "track", name)
        timing.begin_run(path, stage, run_id, platform)
        return path

    def send(self, payload, advance=10, session=None):
        self.now += advance
        payload = dict(payload, session_id=session or self.session)
        timing_hook.observe(payload, self.data, self.project, self.now, platform="codex")

    def post(self, agent, tool):
        self.send({"hook_event_name": "PostToolUse", "agent_id": agent, "tool_name": "Bash",
                   "tool_use_id": tool, "tool_response": "ok"})

    def spawn(self, agent_id, message="do it", parent=None, tool=None):
        # Codex's spawn_agent result is that tool's own PostToolUse: same tool_use_id as its pre.
        payload = {"hook_event_name": "PostToolUse", "tool_name": "spawn_agent", "tool_use_id": tool or "spawn-" + agent_id,
                   "tool_input": {"agent_type": "cai_implementer", "message": message},
                   "tool_response": json.dumps({"agent_id": agent_id, "nickname": "N"})}
        if parent:
            payload["agent_id"] = parent
        self.send(payload)


@pytest.fixture
def codex(tmp_path):
    return CodexEnv(tmp_path)


def run_codex_agent(env, agent, tool="t1"):
    env.start(agent)
    env.pre(agent, tool)
    env.post(agent, tool)
    env.stop(agent)


def test_codex_spawn_binds_and_post_closes_each_tool(codex):
    path = codex.track()
    codex.spawn("child", message=marker("run-1") + "\nbuild it")
    run_codex_agent(codex, "child")
    events = journal(path)
    assert work(events, "child") == [(codex.now - 30, codex.now - 20), (codex.now - 10, codex.now)]
    assert gaps(events) == [] and codex.spool("obs") == []
    bind = [e for e in events if e["kind"] == "actor_bind"][0]
    assert (bind["platform"], bind["source_id"], bind["session_id"]) == ("codex", "codex-hooks-1", "main-session")


def test_codex_result_after_the_agent_stopped_still_binds(codex):
    path = codex.track()
    run_codex_agent(codex, "child")
    assert work(journal(path)) == [] and len(codex.spool("obs")) == 1
    codex.spawn("child", message=marker("run-1"))
    assert len(work(journal(path), "child")) == 2 and codex.spool("obs") == []


def test_codex_nested_spawn_binds_through_the_parent(codex):
    path = codex.track()
    codex.spawn("parent", message=marker("run-1"))
    codex.start("parent")
    codex.pre("parent", "spawn")
    codex.spawn("grandchild", parent="parent", tool="spawn")
    run_codex_agent(codex, "grandchild", "g1")
    codex.stop("parent")
    events = journal(path)
    binds = {e["actor_id"]: e["parent_actor_id"] for e in events if e["kind"] == "actor_bind"}
    assert binds == {"parent": None, "grandchild": "parent"}
    assert len(work(events, "grandchild")) == 2 and gaps(events) == []


def test_codex_hook_never_binds_a_claude_run(codex):
    path = codex.track(platform="claude")
    codex.spawn("child", message=marker("run-1"))
    run_codex_agent(codex, "child")
    assert [e for e in journal(path) if e["kind"] != "run_begin"] == []


def test_replaying_the_recorded_real_codex_session_gives_its_segments(codex):
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "timing", "codex-hooks")
    with open(os.path.join(fixture, "session.jsonl"), encoding="ascii") as fh:
        records = [json.loads(line) for line in fh]
    child = json.load(open(os.path.join(fixture, "meta.json"), encoding="ascii"))["agents"]["child"]
    run_id = next(r["marker"] for r in records if r["tool_name"] == "spawn_agent").split(": ", 1)[1]
    path = codex.track(run_id=run_id)
    base = 7_000_000
    for rec in records:
        payload = {"hook_event_name": rec["event"], "session_id": rec["session_id"]}
        for key in ("agent_id", "tool_name", "tool_use_id"):
            if rec[key] is not None:
                payload[key] = rec[key]
        if rec["tool_name"] == "spawn_agent":
            payload["tool_input"] = {"message": rec["marker"]}
            if rec["tool_response_agent_id"]:
                payload["tool_response"] = json.dumps({"agent_id": rec["tool_response_agent_id"]})
        timing_hook.observe(payload, codex.data, codex.project, base + rec["at_ms"], platform="codex")
    at = {r["event"]: r["at_ms"] for r in records if r["agent_id"] == child}
    assert work(journal(path), child) == [(base + at["SubagentStart"], base + at["PreToolUse"]),
                                          (base + at["PostToolUse"], base + at["SubagentStop"])]
    assert gaps(journal(path)) == [] and codex.spool("obs") == []


def test_codex_main_finds_the_project_from_cwd_and_stays_silent(codex, tmp_path):
    path = codex.track()
    nested = os.path.join(codex.project, "src", "pkg")
    os.makedirs(nested)
    env = dict(os.environ, CAI_TIMING_DATA=codex.data)
    for key in ("CLAUDE_PLUGIN_DATA", "CLAUDE_PROJECT_DIR"):
        env.pop(key, None)
    payloads = [
        {"hook_event_name": "PostToolUse", "tool_name": "spawn_agent", "session_id": "s",
         "tool_input": {"message": marker("run-1")}, "tool_response": json.dumps({"agent_id": "child"})},
        {"hook_event_name": "SubagentStart", "agent_id": "child", "session_id": "s"},
        {"hook_event_name": "PreToolUse", "agent_id": "child", "session_id": "s", "tool_use_id": "t1"},
        {"hook_event_name": "PostToolUse", "agent_id": "child", "session_id": "s", "tool_use_id": "t1"},
        {"hook_event_name": "SubagentStop", "agent_id": "child", "session_id": "s"},
    ]
    for payload in payloads:
        result = subprocess.run([sys.executable, os.path.join(SCRIPTS, "timing_hook.py"), "--codex"],
                                input=json.dumps(dict(payload, cwd=nested)).encode("utf-8"),
                                capture_output=True, env=env)
        assert (result.returncode, result.stdout, result.stderr) == (0, b"", b"")
    assert len(work(journal(path), "child")) == 2


@pytest.mark.parametrize("cwd", [None, "relative/dir", "/nonexistent/nowhere"])
def test_codex_main_without_a_project_or_data_dir_is_a_silent_no_op(codex, cwd):
    payload = {"hook_event_name": "SubagentStart", "agent_id": "child", "session_id": "s"}
    if cwd:
        payload["cwd"] = cwd
    for env in (dict(os.environ, CAI_TIMING_DATA=codex.data), {k: v for k, v in os.environ.items() if k != "CAI_TIMING_DATA"}):
        result = subprocess.run([sys.executable, os.path.join(SCRIPTS, "timing_hook.py"), "--codex"],
                                input=json.dumps(payload).encode("utf-8"), capture_output=True, env=env)
        assert (result.returncode, result.stdout, result.stderr) == (0, b"", b"")
    assert codex.spool("obs") == []


def test_codex_track_skill_opens_and_closes_a_codex_run(codex, capsys):
    # #333: the generated Codex track skill is the production caller on Codex.
    skill_path = os.path.join(SCRIPTS, "..", "..", "cai-codex", "skills", "track", "SKILL.md")
    flat = " ".join(open(skill_path, encoding="utf-8").read().split())
    begin = flat.split("<cai> timing begin ", 1)[1].split("`", 1)[0]
    assert re.findall(r"--[a-z-]+ \S+", begin)[-1] == "--platform codex"
    end = flat.split("<cai> timing end ", 1)[1].split("`", 1)[0]
    assert re.findall(r"--[a-z-]+", end) == ["--track-dir", "--run"]
    assert "every dispatch prompt of this stage" in flat
    path = os.path.join(codex.project, ".claude", "track", "feature")
    assert timing.main(["begin", "--track-dir", path, "--stage", "build", "--platform", "codex"]) == 0
    line = capsys.readouterr().out.strip()
    codex.spawn("helper", message="review this\n" + line)
    run_codex_agent(codex, "helper")
    assert len(work(journal(path), "helper")) == 2
