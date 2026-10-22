"""codemap_hook.py and run-codemap.cmd: a fresh index's state line reaches the
read-side agents at SubagentStart, and nothing else ever does."""
import io
import json
import os
import shutil
import subprocess
import sys

import pytest

import codemap_hook
import codemap_index as idx
import codemap_store as store
from codemap_repo import make_repo, write

HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins", "cai", "hooks")
WINDOWS = os.name == "nt"
FILES = {"a.py": "def one():\n    return 1\n"}


def _built(tmp_path):
    make_repo(tmp_path, FILES)
    idx.build(str(tmp_path))
    return str(tmp_path)


def _payload(top, agent="cai:explorer"):
    return {"hook_event_name": "SubagentStart", "agent_type": agent, "cwd": top}


@pytest.mark.parametrize("agent", sorted(codemap_hook.READERS))
def test_fresh_index_gives_each_reader_the_status_line(tmp_path, agent):
    top = _built(tmp_path)
    assert codemap_hook.context_line(_payload(top, agent)) == idx.state_line(idx.status(top))
    assert codemap_hook.context_line(_payload(top, agent)).startswith("codemap: fresh (")


def test_a_subdirectory_cwd_finds_the_index_at_the_top(tmp_path):
    top = _built(tmp_path)
    sub = os.path.join(top, "pkg")
    os.makedirs(sub)
    assert codemap_hook.context_line(_payload(sub)).startswith("codemap: fresh (")


@pytest.mark.parametrize("agent", ["cai:implementer", "explorer", "general-purpose", None])
def test_other_agents_get_nothing(tmp_path, agent):
    top = _built(tmp_path)
    assert codemap_hook.context_line(_payload(top, agent)) is None


def test_no_index_gives_nothing(tmp_path):
    make_repo(tmp_path, FILES)
    assert codemap_hook.context_line(_payload(str(tmp_path))) is None


def test_stale_index_gives_nothing_and_is_not_refreshed(tmp_path):
    top = _built(tmp_path)
    write(top, "a.py", "def one():\n    return 2\n")
    state = os.path.join(store.index_dir(top), store.STATE_NAME)
    before = open(state, "rb").read()
    assert codemap_hook.context_line(_payload(top)) is None
    assert open(state, "rb").read() == before
    assert idx.status(top).word == "stale"


@pytest.mark.parametrize("payload", [[], "x", {"agent_type": "cai:explorer"},
                                     {"agent_type": "cai:explorer", "cwd": ""},
                                     {"agent_type": "cai:explorer", "cwd": 3}])
def test_malformed_payload_gives_nothing(payload):
    assert codemap_hook.context_line(payload) is None


def _run_hook(stdin):
    return subprocess.run([sys.executable, codemap_hook.__file__], input=stdin,
                          capture_output=True, timeout=60)


def test_main_prints_the_subagentstart_context_json(tmp_path):
    top = _built(tmp_path)
    proc = _run_hook(json.dumps(_payload(top)).encode("utf-8"))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out == {"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                          "additionalContext": idx.state_line(idx.status(top))}}


@pytest.mark.parametrize("stdin", [b"", b"not json", b'{"agent_type": "cai:implementer", "cwd": "."}'])
def test_main_prints_nothing_and_exits_zero_otherwise(stdin):
    proc = _run_hook(stdin)
    assert proc.returncode == 0 and proc.stdout == b"" and proc.stderr == b""


def test_main_in_process_prints_the_same_json(tmp_path, monkeypatch, capsys):
    top = _built(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(_payload(top)).encode("utf-8"))))
    assert codemap_hook.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["additionalContext"].startswith("codemap: fresh (")


def test_main_swallows_an_unexpected_failure(monkeypatch, capsys):
    def boom(payload):
        raise RuntimeError("boom")
    monkeypatch.setattr(codemap_hook, "context_line", boom)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"{}")))
    assert codemap_hook.main() == 0
    assert capsys.readouterr().out == ""


# --- run-codemap.cmd -------------------------------------------------------

STUB = """import os, sys
with open(os.environ["SENTINEL"], "w") as fh:
    fh.write(sys.stdin.read())
print("from-stub")
sys.exit(7)  # the launcher must still exit 0
"""


@pytest.fixture
def layout(tmp_path):
    plugin = tmp_path / "plugin"
    (plugin / "hooks").mkdir(parents=True)
    (plugin / "scripts").mkdir()
    launcher = plugin / "hooks" / "run-codemap.cmd"
    shutil.copyfile(os.path.join(HOOKS, "run-codemap.cmd"), launcher)
    (plugin / "scripts" / "codemap_hook.py").write_text(STUB)
    project = tmp_path / "project"
    project.mkdir()
    config = tmp_path / "config"
    (config / "cai").mkdir(parents=True)
    name = "guard-launcher-cmd.txt" if WINDOWS else "guard-launcher-sh.txt"
    line = "cai-launcher 1 path " + sys.executable.replace("\\", "/") + " end"
    (config / "cai" / name).write_bytes((line + ("\r\n" if WINDOWS else "\n")).encode("ascii"))
    return {"launcher": str(launcher), "project": project, "config": config,
            "sentinel": tmp_path / "sentinel.txt"}


def _launch(layout, stdin="{}", project=True):
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(layout["config"]), SENTINEL=str(layout["sentinel"]))
    env.pop("CLAUDE_PROJECT_DIR", None)
    if project:
        env["CLAUDE_PROJECT_DIR"] = str(layout["project"])
    cmd = ["cmd", "/c", layout["launcher"]] if WINDOWS else ["sh", layout["launcher"]]
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env, timeout=60)


def _index(layout):
    index = layout["project"] / ".cai" / "codemap"
    index.mkdir(parents=True)
    (index / "state.json").write_text("{}")


def test_launcher_without_an_index_exits_before_any_interpreter(layout):
    result = _launch(layout)
    assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
    assert not layout["sentinel"].exists()


def test_launcher_without_a_project_dir_exits_cleanly(layout):
    _index(layout)
    result = _launch(layout, project=False)
    assert result.returncode == 0 and not layout["sentinel"].exists()


def test_launcher_with_an_index_passes_stdin_and_stdout_through(layout):
    _index(layout)
    result = _launch(layout, stdin='{"agent_type": "cai:explorer"}')
    assert result.returncode == 0
    assert result.stdout.strip() == "from-stub"
    assert layout["sentinel"].read_text() == '{"agent_type": "cai:explorer"}'


def test_launcher_with_an_index_only_in_a_worktree_runs_the_hook(layout):
    """#466: CLAUDE_PROJECT_DIR stays on the main checkout after EnterWorktree;
    codemap_hook.py reads the index from the input's cwd, so the launcher must
    not stop at the main checkout having none."""
    index = layout["project"] / ".claude" / "worktrees" / "wt" / ".cai" / "codemap"
    index.mkdir(parents=True)
    (index / "state.json").write_text("{}")
    result = _launch(layout, stdin="x")
    assert result.returncode == 0 and result.stdout.strip() == "from-stub"
    assert layout["sentinel"].read_text() == "x"


def test_launcher_with_a_worktree_but_no_index_exits_before_any_interpreter(layout):
    (layout["project"] / ".claude" / "worktrees" / "wt" / ".cai").mkdir(parents=True)
    result = _launch(layout)
    assert result.returncode == 0 and result.stdout == "" and not layout["sentinel"].exists()


def test_launcher_file_is_ascii_lf_without_bom():
    raw = open(os.path.join(HOOKS, "run-codemap.cmd"), "rb").read()
    assert all(b < 128 for b in raw) and b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf")


def test_hooks_json_registers_the_launcher_on_subagentstart_only():
    with open(os.path.join(HOOKS, "hooks.json"), encoding="utf-8") as fh:
        registered = json.load(fh)["hooks"]
    rows = [(event, hook.get("timeout"))
            for event, matchers in registered.items()
            for matcher in matchers
            for hook in matcher["hooks"]
            if "run-codemap.cmd" in hook["command"]]
    assert rows == [("SubagentStart", 10)]
