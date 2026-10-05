"""run-timing.cmd: exits before any interpreter when no run is open, runs the hook when one is."""
import os
import shutil
import subprocess
import sys

import pytest

HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins", "cai", "hooks")
WINDOWS = os.name == "nt"
STUB = """import os, sys
with open(os.environ["SENTINEL"], "w") as fh:
    fh.write(sys.stdin.read())
sys.exit(7)  # the launcher must still exit 0
"""


@pytest.fixture
def layout(tmp_path):
    plugin = tmp_path / "plugin"
    (plugin / "hooks").mkdir(parents=True)
    (plugin / "scripts").mkdir()
    launcher = plugin / "hooks" / "run-timing.cmd"
    shutil.copyfile(os.path.join(HOOKS, "run-timing.cmd"), launcher)
    (plugin / "scripts" / "timing_hook.py").write_text(STUB)
    project = tmp_path / "project"
    (project / ".claude" / "track").mkdir(parents=True)
    config = tmp_path / "config"
    (config / "cai").mkdir(parents=True)
    return {"launcher": str(launcher), "project": project, "config": config,
            "sentinel": tmp_path / "sentinel.txt", "tmp": tmp_path}


def record(layout, line=None):
    name = "guard-launcher-cmd.txt" if WINDOWS else "guard-launcher-sh.txt"
    # Importing record_launcher would leave a __pycache__ in hooks/, which other tests copy file by file.
    line = line or "cai-launcher 1 path " + sys.executable.replace("\\", "/") + " end"
    (layout["config"] / "cai" / name).write_bytes((line + ("\r\n" if WINDOWS else "\n")).encode("ascii"))


def call(layout, stdin="{}", project=True, extra=None):
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(layout["config"]), SENTINEL=str(layout["sentinel"]))
    env.pop("CLAUDE_PROJECT_DIR", None)
    if project:
        env["CLAUDE_PROJECT_DIR"] = str(layout["project"])
    env.update(extra or {})
    cmd = ["cmd", "/c", layout["launcher"]] if WINDOWS else ["sh", layout["launcher"]]
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env, timeout=60)


def open_run(layout):
    (layout["project"] / ".claude" / "track" / "timing-open.abc").write_text("")


def test_no_open_marker_exits_before_any_interpreter(layout):
    record(layout)
    result = call(layout)
    assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
    assert not layout["sentinel"].exists()


def test_open_marker_runs_the_hook_with_the_input_and_ignores_its_exit_code(layout):
    record(layout)
    open_run(layout)
    result = call(layout, stdin='{"hook_event_name": "SubagentStart"}')
    assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
    assert layout["sentinel"].read_text() == '{"hook_event_name": "SubagentStart"}'


def test_marker_in_a_different_project_does_not_trigger(layout):
    record(layout)
    other = layout["tmp"] / "other" / ".claude" / "track"
    other.mkdir(parents=True)
    (other / "timing-open.abc").write_text("")
    assert call(layout).returncode == 0
    assert not layout["sentinel"].exists()


def test_a_marker_that_is_a_directory_name_without_prefix_does_not_trigger(layout):
    record(layout)
    (layout["project"] / ".claude" / "track" / "feature").mkdir()
    (layout["project"] / ".claude" / "track" / "timing.open").write_text("")
    assert call(layout).returncode == 0 and not layout["sentinel"].exists()


@pytest.mark.parametrize("line", [
    "garbage",
    "cai-launcher 1 path " + os.path.join(os.sep, "no", "such", "python").replace("\\", "/") + " end",
    "cai-launcher 2 path /x end",
    "cai-launcher 1 path /x",
])
def test_bad_or_stale_record_means_exit_zero_and_nothing_runs(layout, line):
    open_run(layout)
    record(layout, line)
    result = call(layout)
    assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
    assert not layout["sentinel"].exists()


def test_no_record_never_probes_or_writes(layout):
    open_run(layout)
    result = call(layout)
    assert result.returncode == 0 and not layout["sentinel"].exists()
    assert list((layout["config"] / "cai").iterdir()) == []


def test_missing_project_dir_is_a_clean_exit(layout):
    record(layout)
    open_run(layout)
    result = call(layout, project=False)
    assert result.returncode == 0 and not layout["sentinel"].exists()


def test_name_record_runs_the_named_interpreter(layout):
    name = "python" if WINDOWS else "python3"
    if shutil.which(name) is None:
        pytest.skip(name + " is not on PATH")
    record(layout, "cai-launcher 1 name %s end" % name)
    open_run(layout)
    assert call(layout, stdin="x").returncode == 0
    assert layout["sentinel"].read_text() == "x"


def test_launcher_file_is_ascii_lf_without_bom():
    raw = open(os.path.join(HOOKS, "run-timing.cmd"), "rb").read()
    assert all(b < 128 for b in raw) and b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf")


def timing_entries():
    import json
    with open(os.path.join(HOOKS, "hooks.json"), encoding="utf-8") as fh:
        registered = json.load(fh)["hooks"]
    rows = []
    for event, matchers in registered.items():
        for matcher in matchers:
            for hook in matcher["hooks"]:
                if "run-timing.cmd" in hook["command"]:
                    rows.append((event, matcher.get("matcher"), hook.get("async", False), hook["timeout"], hook["command"]))
    return rows, registered


def test_hooks_json_registers_exactly_the_five_timing_entries():
    rows, registered = timing_entries()
    command = '"${CLAUDE_PLUGIN_ROOT}/hooks/run-timing.cmd"'
    assert sorted(rows) == sorted([
        ("PreToolUse", "*", False, 5, command),
        ("PostToolBatch", None, True, 5, command),
        ("PostToolUse", "Agent|Task", False, 5, command),
        ("SubagentStart", None, False, 5, command),
        ("SubagentStop", None, False, 5, command),
    ], key=str)
    # the existing guard and model-choice entries are untouched
    guard = [(e, m.get("matcher"), h["command"]) for e, ms in registered.items() for m in ms
             for h in m["hooks"] if "run-timing" not in h["command"]]
    assert sorted(guard) == sorted([
        ("PreToolUse", "Bash|PowerShell", '"${CLAUDE_PLUGIN_ROOT}/hooks/run-guard.cmd"'),
        ("PreToolUse", "Agent|Task", '"${CLAUDE_PLUGIN_ROOT}/hooks/run-guard.cmd" agent'),
        ("SessionStart", None, '"${CLAUDE_PLUGIN_ROOT}/hooks/run-models.cmd"'),
    ], key=str)
