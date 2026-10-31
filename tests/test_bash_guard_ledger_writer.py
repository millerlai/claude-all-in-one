"""bash_guard.py keeps a subagent out of the track ledger (#392).

Gate 1's Approve row in `.cai/track/<feature>/ledger.jsonl` decides whether
build may commit, so only the main session writes it. This file pins the write
tools (Write, Edit, NotebookEdit: the path a call names, however it is
spelled), the bytes-in read of the hook input, and what is left alone: the main
session, other files, and a payload that carries no path.
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

SUB = "agent-ledger-test"
N1 = "/p/.cai/track/t/ledger.jsonl"


def payload(path, tool="Write", field=None, agent_id=SUB, agent_type=None, content="x"):
    field = field or ("notebook_path" if tool == "NotebookEdit" else "file_path")
    data = {"tool_name": tool, "tool_input": {field: path, "content": content}}
    if agent_id is not None:
        data["agent_id"] = agent_id
    if agent_type:
        data["agent_type"] = agent_type
    return data


def run_guard(data, env=None):
    """The guard as a hook runs it: one JSON document of UTF-8 bytes on stdin."""
    raw = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else data
    return subprocess.run([sys.executable, GUARD], input=raw.encode("utf-8"),
                          capture_output=True, env=env)


# --- is_subagent ------------------------------------------------------------

@pytest.mark.parametrize("data, expected", [
    ({"agent_id": SUB}, True),
    ({"agent_id": ""}, False),
    ({}, False),
    ({"agent_id": 7}, False),
    ({"agent_id": None}, False),
])
def test_is_subagent_wants_a_non_empty_string(data, expected):
    assert bash_guard.is_subagent(data) is expected


# --- the spelling matrix (AC2), in-process -----------------------------------

BLOCKED_SPELLINGS = [
    N1,                                        # N1
    "C:\\p\\.claude\\track\\t\\LEDGER.JSONL",  # N2
    "C:/p/t/Ledger.JsonL",                     # N3
    "/p/t/ledger.jsonl.",                      # N4
    "/p/t/ledger.jsonl ",                      # N5
    "/p/t/ledger.jsonl. .",                    # N6
    "/p/t/ledger.jsonl::$DATA",                # N7
    "/p/t/ledger.jsonl:x",                     # N8
    "/p/t/sub/../ledger.jsonl",                # N9
    # `..` or `.` as the LAST segment: only normpath makes these the ledger.
    "/p/t/ledger.jsonl/sub/..",
    "/p/t/ledger.jsonl/.",
    "C:ledger.jsonl",                          # N11
    "\\\\?\\C:\\p\\t\\ledger.jsonl",           # N12
]

ALLOWED_SPELLINGS = [
    "/p/t/ledger.jsonl/../notes.txt",          # N10
    "/p/t/ledger.jsonl/..",                    # names the directory above it
    "/p/t/ledger.jsonl.bak",
    "/p/t/my-ledger.jsonl",
    "/p/t/ledger.json",
]


@pytest.mark.parametrize("path", BLOCKED_SPELLINGS)
def test_a_spelling_that_resolves_to_the_ledger_is_named(path):
    assert bash_guard.LEDGER_NAME in bash_guard.ledger_target_names(path)


@pytest.mark.parametrize("path", ALLOWED_SPELLINGS)
def test_a_spelling_that_resolves_elsewhere_is_not_named(path):
    assert bash_guard.LEDGER_NAME not in bash_guard.ledger_target_names(path)


def test_a_target_that_exists_adds_the_name_it_resolves_to(tmp_path, monkeypatch):
    # LEDGER~1.JSO is what Windows calls ledger.jsonl when it makes 8.3 names.
    # The two replacements are what realpath answers on POSIX and on Windows; the
    # backslash form is why the last segment is taken before ":" is split off.
    short = tmp_path / "LEDGER~1.JSO"
    short.write_bytes(b"")
    real = os.path.realpath
    for answer in ("/p/t/ledger.jsonl", "C:\\p\\t\\ledger.jsonl"):
        monkeypatch.setattr(bash_guard.os.path, "realpath",
                            lambda p, a=answer: a if p == str(short) else real(p))
        assert bash_guard.LEDGER_NAME in bash_guard.ledger_target_names(str(short))


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_a_link_to_the_ledger_is_named(tmp_path):
    (tmp_path / "ledger.jsonl").write_bytes(b"")
    try:
        os.symlink(tmp_path / "ledger.jsonl", tmp_path / "notes.txt")
    except OSError:
        pytest.skip("this account may not create symlinks")
    assert bash_guard.LEDGER_NAME in bash_guard.ledger_target_names(str(tmp_path / "notes.txt"))


@pytest.mark.skipif(os.name != "nt", reason="8.3 names are a Windows filesystem fact")
def test_a_real_short_name_is_named(tmp_path):
    import ctypes
    target = tmp_path / "ledger.jsonl"
    target.write_bytes(b"")
    buf = ctypes.create_unicode_buffer(520)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(target), buf, 520):
        pytest.skip("GetShortPathNameW failed")
    short = buf.value
    if os.path.basename(short).casefold() == "ledger.jsonl":
        pytest.skip("this volume makes no 8.3 names")
    assert bash_guard.LEDGER_NAME in bash_guard.ledger_target_names(short)


def test_an_exception_while_resolving_falls_back_to_the_last_segment(monkeypatch):
    def boom(path):
        raise ValueError("cannot resolve")
    monkeypatch.setattr(bash_guard, "ledger_target_names", boom)
    assert bash_guard.check_ledger_target(payload(N1)) == 2
    assert bash_guard.check_ledger_target(payload("/p/notes.txt")) == 0


# --- check_ledger_target, in-process -----------------------------------------

def test_check_ledger_target_blocks_a_subagent_and_names_the_path(capsys):
    assert bash_guard.check_ledger_target(payload(N1)) == 2
    err = capsys.readouterr().err
    assert "a subagent may not write the track ledger (ledger.jsonl)" in err
    assert N1 in err
    assert "ledger.py show" in err


@pytest.mark.parametrize("data", [
    payload(N1, agent_id=None),                       # the main session
    payload(N1, agent_id=""),                         # an empty id is not a subagent
    payload(N1, tool="NotebookEdit", field="file_path"),  # N15: D3 reads notebook_path only
    {"tool_name": "Write", "agent_id": SUB, "tool_input": {"content": "x"}},
    {"tool_name": "Write", "agent_id": SUB, "tool_input": {"file_path": 7}},
    {"tool_name": "Write", "agent_id": SUB, "tool_input": {"file_path": ""}},
    {"tool_name": "Write", "agent_id": SUB, "tool_input": "ledger.jsonl"},
])
def test_check_ledger_target_lets_these_through(data):
    assert bash_guard.check_ledger_target(data) == 0


# --- out of process, through main() ------------------------------------------

def test_n1_edit_by_a_subagent_is_blocked_and_the_main_sessions_is_not():
    assert run_guard(payload(N1, tool="Edit")).returncode == 2
    assert run_guard(payload(N1, tool="Edit", agent_id=None)).returncode == 0  # N13


def test_n14_notebook_edit_names_notebook_path():
    assert run_guard(payload(N1, tool="NotebookEdit")).returncode == 2
    assert run_guard(payload(N1, tool="NotebookEdit", field="file_path")).returncode == 0  # N15


def test_n16_a_designers_write_is_judged_by_its_path_alone():
    # The content names a force push and the ledger; neither is read.
    result = run_guard(payload("/p/docs/notes.md", agent_type="cai:designer",
                               content="git push --force origin main; ledger.jsonl"))
    assert result.returncode == 0, result.stderr


def test_a_write_reaches_the_ledger_rule_before_the_scoped_guards():
    result = run_guard(payload(N1, agent_type="cai:designer"))
    assert result.returncode == 2
    assert b"a subagent may not write the track ledger" in result.stderr


# --- D7: the hook input is read as bytes -------------------------------------

ASCII_ENV = dict(os.environ, PYTHONIOENCODING="ascii:strict")
ASCII_ENV.pop("PYTHONUTF8", None)


def test_u8_2_a_subagents_write_with_non_ascii_content_is_blocked():
    assert run_guard(payload(N1, content="中文內容"), env=ASCII_ENV).returncode == 2


def test_u8_3_a_non_ascii_comment_does_not_switch_the_rules_off():
    # The main session, so only the force-push rule can decide. Read as text under
    # an ASCII stdin this raised and the guard failed open; as bytes it blocks.
    data = {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main # 中文"}}
    assert run_guard(data, env=ASCII_ENV).returncode == 2


def test_u8_4_a_path_outside_the_console_code_page_does_not_crash_the_block():
    result = run_guard(payload("/p/\U0001f600/ledger.jsonl"), env=ASCII_ENV)
    assert result.returncode == 2, result.stderr
    assert b"Traceback" not in result.stderr


# --- AC1, D5: a subagent's command that writes the ledger ---------------------

def bash(command, tool="Bash", agent_id=SUB, agent_type=None):
    data = {"tool_name": tool, "tool_input": {"command": command}}
    if agent_id is not None:
        data["agent_id"] = agent_id
    if agent_type:
        data["agent_type"] = agent_type
    return data


DESIGN_PROBE = ("python ${CLAUDE_PLUGIN_ROOT}/scripts/design_probe.py --kind detail "
                ".cai/track/t/ledger.jsonl")
B1 = ('python /p/plugins/cai/scripts/ledger.py append --track-dir .cai/track/t '
      '--stage design --outcome passed --gate human --note "commit: yes"')

BLOCKED_COMMANDS = [
    ("B1", "Bash", B1),
    ("B2", "Bash", r'py -3 "C:\x\scripts\LEDGER.PY" append --track-dir t'),
    ("B3", "Bash", "cd plugins/cai/scripts && python ledger.py append --track-dir t"),
    ("B4", "Bash", "python ledger.py --track-dir t --gate human append"),
    ("B5", "Bash", """echo '{"stage":"design"}' >> .cai/track/t/ledger.jsonl"""),
    ("B6", "PowerShell", r"Add-Content .cai\track\t\Ledger.JSONL '{}'"),
    ("B7", "Bash", "python - <<'EOF'\nopen('.cai/track/t/ledger.jsonl','a').write('x')\nEOF"),
    ("B8", "Bash", "cat .cai/track/t/ledger.jsonl"),
    ("B9", "Bash", 'git commit -m "fix ledger.jsonl reader"'),  # accepted over-block
    ("B10", "Bash", 'python ledger.py show --note "append later"'),  # accepted over-block
    ("B11", "Monitor", "python ledger.py append --track-dir t"),
    ("B12", "Bash", "python ledger.pyc append --track-dir t"),
    ("B13", "Bash", "cd plugins/cai/scripts && python -m ledger append --track-dir t"),
    # A line continuation joins two lines into one command (verify: AC1(a)).
    ("C1", "Bash", "python plugins/cai/scripts/ledger.py \\\n    append --track-dir t --stage design"),
    ("C2", "Bash", "python plugins/cai/scripts/ledger.py \\\r\n    append --track-dir t"),
    ("C3", "PowerShell", "python plugins/cai/scripts/ledger.py `\n    append --track-dir t"),
]

ALLOWED_COMMANDS = [
    ("A3", "python -m pytest tests/test_ledger.py"),
    ("A4", "git add plugins/cai/scripts/ledger.py"),
    ("A5", "python plugins/cai/scripts/ledger.py show --track-dir .cai/track/fix-append-x"),
    ("A6", "git log -S append -- plugins/cai/scripts/ledger.py"),
    ("A7", "grep -n append plugins/cai/scripts/ledger.py"),
    ("A8", "git diff plugins/cai/scripts/ledger.py | grep append"),
    ("A10", "python -m ledger show --track-dir t"),
    # The known way round, pinned so a change to it is a decision (D5): the ";"
    # inside the quotes splits the command and `append` lands in the next segment.
    ("K1", 'python ledger.py --note "commit: yes; ok" append --track-dir t'),
]


@pytest.mark.parametrize("name, tool, command", BLOCKED_COMMANDS, ids=[b[0] for b in BLOCKED_COMMANDS])
def test_a_subagent_command_that_writes_or_names_the_ledger_is_blocked(name, tool, command, tmp_path):
    result = run_guard(dict(bash(command, tool), cwd=str(tmp_path)))
    assert result.returncode == 2, result.stderr
    assert b"a subagent may not write the track ledger" in result.stderr


@pytest.mark.parametrize("name, command", ALLOWED_COMMANDS, ids=[a[0] for a in ALLOWED_COMMANDS])
def test_a_command_that_only_looks_like_a_ledger_write_is_allowed(name, command, tmp_path):
    result = run_guard(dict(bash(command), cwd=str(tmp_path)))
    assert result.returncode == 0, result.stderr


def test_b14_the_scoped_guard_letting_a_command_through_does_not_skip_the_ledger_rule(tmp_path):
    designer = dict(bash(DESIGN_PROBE, agent_type="cai:designer"), cwd=str(tmp_path))
    result = run_guard(designer)
    assert result.returncode == 2
    assert b"a subagent may not write the track ledger" in result.stderr
    # The same command from a session with no agent_id is the designer guard's
    # to judge, and it allows design_probe.py: the 2 above is the ledger rule's.
    assert run_guard(dict(designer, **{"agent_id": ""})).returncode == 0
    del designer["agent_id"]
    assert run_guard(designer).returncode == 0  # B14c


@pytest.mark.parametrize("agent_id, agent_type", [
    (None, None),            # A1: the main session
    (None, "cai:implementer"),  # A2: an agent_type alone does not make a subagent
    ("", None),              # A9: an empty id
])
def test_the_main_session_may_append_to_the_ledger(agent_id, agent_type, tmp_path):
    data = dict(bash(B1, agent_id=agent_id, agent_type=agent_type), cwd=str(tmp_path))
    assert run_guard(data).returncode == 0


def test_names_ledger_write_reads_each_segment_of_a_command_on_its_own():
    assert bash_guard.names_ledger_write("python ledger.py append --artifact ledger.py")
    assert not bash_guard.names_ledger_write("python ledger.py show && echo append")
    assert not bash_guard.names_ledger_write("echo append; python ledger.py show")
    # A continuation is not a cut, but what follows it is still its own command.
    assert bash_guard.names_ledger_write("python ledger.py \\\n  append --track-dir t")
    assert not bash_guard.names_ledger_write("python ledger.py show \\\n  --track-dir t")
    assert not bash_guard.names_ledger_write("python ledger.py show \\\n  && git log -S append")
    assert not bash_guard.names_ledger_write("python ledger.py show\ngit log -S append")


# --- D2: Monitor is read as Bash ---------------------------------------------

def monitor(command, agent_id=None, agent_type=None, tool_input=None):
    data = {"tool_name": "Monitor", "tool_input": tool_input or {"command": command}}
    if agent_id is not None:
        data["agent_id"] = agent_id
    if agent_type:
        data["agent_type"] = agent_type
    return data


def test_monitor_goes_through_the_bash_rules(tmp_path):
    cwd = str(tmp_path)
    env = {k: v for k, v in os.environ.items() if k != "CAI_CODEX_GUARD"}
    assert run_guard(dict(monitor("git push --force origin main"), cwd=cwd)).returncode == 2  # M1
    assert run_guard(dict(monitor("echo `date`"), cwd=cwd)).returncode == 2  # M2: Bash-only
    assert run_guard(dict(monitor("Remove-Item build -Recurse -Force"), cwd=cwd)).returncode == 0  # M3
    assert run_guard(dict(monitor("tail -f build.log"), cwd=cwd)).returncode == 0  # M4
    asked = run_guard(dict(monitor("gh pr merge 1"), cwd=cwd), env=env)  # M5
    assert asked.returncode == 0
    assert b'"permissionDecision": "ask"' in asked.stdout
    scoped = run_guard(dict(monitor("tail -f build.log", agent_type="cai:test-runner"), cwd=cwd))
    assert scoped.returncode == 2  # M6: the test-runner's allow-list applies
    assert run_guard(monitor("", tool_input={"ws": "wss://x"})).returncode == 0  # M7


def test_u8_1_a_subagents_non_ascii_note_does_not_hide_the_ledger_append(tmp_path):
    data = dict(bash('python ledger.py append --note "核准"'), cwd=str(tmp_path))
    assert run_guard(data, env=ASCII_ENV).returncode == 2
