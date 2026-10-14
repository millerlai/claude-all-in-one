"""bash_guard.py keeps a subagent away from the guard's own launcher record (#414).

`run-guard.cmd` starts the guard with whatever interpreter
`guard-launcher-cmd.txt` / `guard-launcher-sh.txt` names, checking only the
record's shape. A record pointed at a program that always exits 0 turns every
rule off, so a subagent may neither write it nor run a command naming it. The
main session, and other files, are left alone. Spellings reuse the ledger
rule's path handling, so the ledger tests' matrix is not repeated here.
"""
import json
import os
import subprocess
import sys

import pytest

import bash_guard

GUARD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins", "cai", "scripts", "bash_guard.py")
SUB = "agent-launcher-test"


def write(path, tool="Write", agent_id=SUB):
    field = "notebook_path" if tool == "NotebookEdit" else "file_path"
    data = {"tool_name": tool, "tool_input": {field: path, "content": "x"}}
    if agent_id is not None:
        data["agent_id"] = agent_id
    return data


def bash(command, agent_id=SUB):
    data = {"tool_name": "Bash", "tool_input": {"command": command}}
    if agent_id is not None:
        data["agent_id"] = agent_id
    return data


def run_guard(data):
    return subprocess.run([sys.executable, GUARD], input=json.dumps(data).encode("utf-8"),
                          capture_output=True)


@pytest.mark.parametrize("path", [
    "/home/u/.claude/cai/guard-launcher-sh.txt",
    "C:\\Users\\u\\.claude\\cai\\guard-launcher-cmd.txt",
    "C:\\Users\\u\\.claude\\cai\\GUARD-LAUNCHER-CMD.TXT. ",
    "C:\\Users\\u\\.claude\\cai\\guard-launcher-cmd.txt::$DATA",
])
@pytest.mark.parametrize("tool", ["Write", "Edit", "NotebookEdit"])
def test_a_subagent_write_to_the_record_is_blocked(path, tool):
    done = run_guard(write(path, tool))
    assert done.returncode == 2
    assert "launcher record" in done.stderr.decode("utf-8")


def test_a_link_resolving_to_the_record_is_blocked(tmp_path):
    record = tmp_path / "guard-launcher-sh.txt"
    record.write_text("cai-launcher 1 name python3 end\n", encoding="utf-8")
    link = tmp_path / "notes.txt"
    try:
        os.symlink(str(record), str(link))
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need privileges here")
    assert run_guard(write(str(link))).returncode == 2


@pytest.mark.parametrize("command", [
    "echo cai-launcher 1 path /bin/true end > ~/.claude/cai/guard-launcher-sh.txt",
    'printf "cai-launcher 1 path C:/x/true.exe end" > "%USERPROFILE%\\.claude\\cai\\Guard-Launcher-Cmd.txt"',
    "cp /tmp/r ~/.claude/cai/guard-launcher-sh.txt",
])
def test_a_subagent_command_naming_the_record_is_blocked(command):
    done = run_guard(bash(command))
    assert done.returncode == 2
    assert "launcher record" in done.stderr.decode("utf-8")


@pytest.mark.parametrize("data", [
    write("/home/u/.claude/cai/guard-launcher-sh.txt", agent_id=None),
    bash("cat ~/.claude/cai/guard-launcher-sh.txt", agent_id=None),
    write("/p/docs/guard-launcher.md"),
    write("/p/guard-launcher-sh.txt.bak"),
    bash("python record_launcher.py --help"),
])
def test_the_main_session_and_other_names_pass(data):
    assert run_guard(data).returncode == 0


def test_the_reduced_write_patterns_name_the_record():
    patterns = os.path.join(os.path.dirname(GUARD), "..", "hooks",
                            "reduced-check-write-patterns.txt")
    with open(patterns, encoding="utf-8") as fh:
        text = fh.read()
    assert text.count("guard-launcher-") == 4


def test_the_name_rule_matches_both_records_only():
    assert bash_guard.LAUNCHER_RECORD.fullmatch("guard-launcher-cmd.txt")
    assert bash_guard.LAUNCHER_RECORD.fullmatch("guard-launcher-sh.txt")
    assert not bash_guard.LAUNCHER_RECORD.fullmatch("guard-launcher-sh.txt.bak")
