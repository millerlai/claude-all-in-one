#!/usr/bin/env python3
"""Maintainer probe for unit 4a of the agent-viewer total-time design (Ours, not shipped).

Two modes:

  record <out_file>   a hook receiver: reads one hook JSON from stdin and appends ONE
                      content-free line to <out_file>. Only field names, identifiers and
                      clock readings are kept -- never prompt, tool input or tool output.
  run                 builds a throwaway plugin under a short %TEMP% path, runs one real
                      non-interactive Claude Code session with that plugin loaded for that
                      run only (`claude -p --plugin-dir`), then writes the content-free
                      fixtures under tests/fixtures/timing/claude-hooks/ and removes the
                      temp directory.

It never touches settings.json, installed plugins, or Codex config.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(os.path.dirname(HERE), "tests", "fixtures", "timing", "claude-hooks")
EVENTS = [
    ("PreToolUse", "*", False),
    ("PostToolBatch", None, True),
    ("PostToolUse", "Agent|Task", False),
    ("SubagentStart", None, False),
    ("SubagentStop", None, False),
]
MARKERS = ("cai-timing-run: probe-fg", "cai-timing-run: probe-bg")


def _keys(value):
    return sorted(value) if isinstance(value, dict) else None


def describe(payload, now_ms, env):
    """One content-free record. Pure: takes the clock and env as arguments."""
    tin = payload.get("tool_input")
    tout = payload.get("tool_response")
    calls = payload.get("tool_calls")
    prompt = tin.get("prompt") if isinstance(tin, dict) else None
    tout_id = tout.get("agentId") if isinstance(tout, dict) else None
    rec = {
        "at_ms": now_ms,
        "event": payload.get("hook_event_name"),
        "keys": sorted(payload),
        "tool_name": payload.get("tool_name"),
        "session_id": payload.get("session_id"),
        "agent_id": payload.get("agent_id"),
        "tool_use_id": payload.get("tool_use_id"),
        "tool_input_keys": _keys(tin),
        "tool_response_keys": _keys(tout),
        "tool_response_agentId": tout_id,
        "run_in_background": tin.get("run_in_background") if isinstance(tin, dict) else None,
        # Which marker (if any) the prompt carries; the prompt text itself is dropped.
        "prompt_marker": next((m for m in MARKERS if isinstance(prompt, str) and m in prompt), None),
        "tool_calls_keys": _keys(calls[0]) if isinstance(calls, list) and calls and isinstance(calls[0], dict) else None,
        "tool_calls_ids": [c.get("tool_use_id") for c in calls if isinstance(c, dict)] if isinstance(calls, list) else None,
        "env_project_dir_set": bool(env.get("CLAUDE_PROJECT_DIR")),
        "env_plugin_data_set": bool(env.get("CLAUDE_PLUGIN_DATA")),
        "env_plugin_root_set": bool(env.get("CLAUDE_PLUGIN_ROOT")),
        "env_project_dir_hash": hashlib.sha256(os.path.normcase(env.get("CLAUDE_PROJECT_DIR", "")).encode()).hexdigest()[:8],
    }
    return rec


def record(out_file):
    now_ms = time.time_ns() // 1_000_000  # first action: read the clock
    try:
        payload = json.loads(sys.stdin.read())
        line = json.dumps(describe(payload, now_ms, os.environ), ensure_ascii=True)
        with open(out_file, "a", encoding="ascii") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    return 0  # never write stdout: PreToolUse stdout is parsed as a decision


def build_plugin(base, out_file):
    plugin = os.path.join(base, "plugin")
    os.makedirs(os.path.join(plugin, ".claude-plugin"))
    os.makedirs(os.path.join(plugin, "hooks"))
    with open(os.path.join(plugin, ".claude-plugin", "plugin.json"), "w", encoding="ascii") as fh:
        json.dump({"name": "cai-timing-probe", "version": "0.0.0", "description": "4a probe"}, fh)
    cmd = '"%s" "%s" record "%s"' % (sys.executable.replace("\\", "/"), os.path.abspath(__file__).replace("\\", "/"), out_file.replace("\\", "/"))
    hooks = {}
    for name, matcher, is_async in EVENTS:
        h = {"type": "command", "command": cmd, "timeout": 5}
        if is_async:
            h["async"] = True
        entry = {"hooks": [h]}
        if matcher:
            entry["matcher"] = matcher
        hooks[name] = [entry]
    with open(os.path.join(plugin, "hooks", "hooks.json"), "w", encoding="ascii") as fh:
        json.dump({"hooks": hooks}, fh, indent=2)
    return plugin


PROMPT = (
    "Do exactly this and nothing else. Step 1: call the Agent tool in the foreground with "
    "subagent_type general-purpose and a prompt of exactly two lines. Line 1: "
    + MARKERS[0] + " . Line 2: Run the Bash command `echo hi` then reply with the single word done. "
    "Step 2: call the Agent tool with run_in_background true, subagent_type general-purpose, and the "
    "same two-line prompt but with line 1 being " + MARKERS[1] + " . Then wait for the background "
    "agent's completion notice and reply with the single word finished."
)


def run():
    base = os.path.join(tempfile.gettempdir(), "cai4a")  # short path: deep paths broke plugin clones here
    shutil.rmtree(base, ignore_errors=True)
    os.makedirs(os.path.join(base, "project"))
    os.makedirs(os.path.join(base, "out"))
    out_file = os.path.join(base, "out", "hooks.jsonl")
    plugin = build_plugin(base, out_file)
    version = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    env = dict(os.environ, CLAUDE_CODE_SUBAGENT_MODEL="haiku")
    cmd = ["claude", "-p", PROMPT, "--plugin-dir", plugin, "--model", "haiku",
           "--allowedTools", "Agent,Bash(echo:*)", "--no-session-persistence"]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=os.path.join(base, "project"), env=env,
                              capture_output=True, text=True, timeout=540)
        status = {"returncode": proc.returncode, "stdout_chars": len(proc.stdout), "stderr_chars": len(proc.stderr)}
    except subprocess.TimeoutExpired:
        status = {"returncode": "timeout"}
    status["seconds"] = round(time.time() - t0, 1)
    records = []
    if os.path.exists(out_file):
        with open(out_file, encoding="ascii") as fh:
            records = [json.loads(x) for x in fh if x.strip()]
    records.sort(key=lambda r: r["at_ms"])
    os.makedirs(FIXTURES, exist_ok=True)
    t_zero = records[0]["at_ms"] if records else 0
    for r in records:
        r["at_ms"] -= t_zero  # relative times only
    with open(os.path.join(FIXTURES, "session.jsonl"), "w", encoding="ascii", newline="\n") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=True) + "\n")
    with open(os.path.join(FIXTURES, "meta.json"), "w", encoding="ascii", newline="\n") as fh:
        json.dump({"claude_code_version": version, "recorded": time.strftime("%Y-%m-%d"),
                   "model": "haiku", "run": status, "records": len(records),
                   "note": "content-free: field names, identifiers and relative millisecond clocks only"},
                  fh, indent=2)
        fh.write("\n")
    shutil.rmtree(base, ignore_errors=True)
    print(json.dumps({"version": version, "status": status, "records": len(records)}))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["record"] and len(argv) == 2:
        return record(argv[1])
    if argv == ["run"]:
        return run()
    print("usage: probe_timing_hooks.py record <out_file> | run", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
