"""Unit 6: runner_guard (test-runner) and bash_guard's agent_type dispatch --
AC8 and detail design D7.

Fixtures carry no `git init`, so the guard's root falls back to the working
directory (resolve_test_command.find_root's documented fallback).
"""
import json
import os
import subprocess
import sys

import pytest

import resolve_test_command
import runner_guard

SCRIPTS = os.path.dirname(os.path.abspath(runner_guard.__file__))
BASH_GUARD = os.path.join(SCRIPTS, "bash_guard.py")
RESOLVER = "python ${CLAUDE_PLUGIN_ROOT}/scripts/resolve_test_command.py"
RUNNER = "cai:test-runner"


def project(tmp_path, files):
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return str(tmp_path)


@pytest.fixture
def cargo(tmp_path):
    return project(tmp_path, {"Cargo.toml": '[package]\nname = "probe"\nversion = "0.1.0"\n'})


@pytest.fixture
def empty(tmp_path):
    return str(tmp_path)


# --- AC8: only the resolver and what it resolved ---------------------------

@pytest.mark.parametrize("command, expected", [
    ("cargo test", True),
    ("cargo test my_test", True),
    ("cargo   test\tmy_test", True),           # runs of blanks are one separator
    ("cargo test; git stash", False),
    ("cargo test && rm -rf target", False),
    ("cargo test | tee out", False),
    ("cargo test > out.txt", False),
    ("cargo test $(whoami)", False),
    ("cargo test `whoami`", False),
    ("cargo test\nrm -rf target", False),
    # The two habits the pre-change agents had: both are blocked now.
    ("cargo test 2>&1", False),
    ("cd D:/x && cargo test", False),
    ("cargo testing", False),                   # prefix needs the separator
    ("cargo", False),
    ("rm -rf target", False),
    ("git status", False),
])
def test_runner_in_cargo_project(cargo, command, expected):
    assert runner_guard.allowed(command, cargo) is expected


def test_runner_blocks_an_unresolved_command(empty):
    # Nothing resolves here, so no command can be compared against.
    assert runner_guard.allowed("cargo test", empty) is False


def test_several_candidates_resolve_nothing(tmp_path):
    cwd = project(tmp_path, {"Cargo.toml": "", "go.mod": "module x\n"})
    assert resolve_test_command.resolve(cwd)["status"] == "several"
    assert runner_guard.allowed("cargo test", cwd) is False


@pytest.mark.parametrize("command, expected", [
    (RESOLVER, True),
    (RESOLVER + " --project-dir sub", True),
    ('python "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_test_command.py"', True),
    ("python3 ${CLAUDE_PLUGIN_ROOT}/scripts/resolve_test_command.py", True),
    ("py -3 ${CLAUDE_PLUGIN_ROOT}/scripts/resolve_test_command.py", True),
    (RESOLVER + "; git stash", False),
    (RESOLVER + " | cat", False),
    (RESOLVER + " 2>&1", False),
    ("python ${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py", False),
    ("python -c 'print(1)'", False),
    ("python other/resolve_test_command.py", False),
    ("python", False),
])
def test_resolver_invocation(empty, command, expected):
    assert runner_guard.allowed(command, empty) is expected


def test_resolver_by_its_real_path(empty):
    script = os.path.join(SCRIPTS, "resolve_test_command.py")
    assert runner_guard.allowed("python " + script.replace("\\", "/"), empty) is True


def test_declared_commands_all_pass_and_take_arguments(tmp_path):
    cwd = project(tmp_path, {".cai/cai.json": json.dumps(
        {"test": {"commands": ["python -m pytest", "npm test"]}})})
    for command in ("python -m pytest", "python -m pytest tests/a.py -x", "npm test"):
        assert runner_guard.allowed(command, cwd) is True, command
    assert runner_guard.allowed("npm run build", cwd) is False
    assert runner_guard.allowed("python -m pytest; rm x", cwd) is False


def test_runner_may_run_the_launcher_this_machine_has(tmp_path, monkeypatch):
    # #274: only python3 on PATH, so the resolved and allowed command is python3's.
    monkeypatch.setattr(resolve_test_command, "_on_path", lambda name: name == "python3")
    cwd = project(tmp_path, {"pytest.ini": "[pytest]\n"})
    assert runner_guard.allowed("python3 -m pytest tests/a.py", cwd) is True
    assert runner_guard.allowed("python -m pytest", cwd) is False


def dispatch(agent_type, subagent_type, prompt="review the diff"):
    payload = {"tool_name": "Agent", "tool_input": {"subagent_type": subagent_type,
                                                    "description": "x", "prompt": prompt}}
    if agent_type:
        payload["agent_type"] = agent_type
    return subprocess.run([sys.executable, BASH_GUARD], input=json.dumps(payload),
                          capture_output=True, text=True)


def test_bash_rules_never_read_an_agent_prompt():
    # The Bash rules match command text; a prompt that mentions a force push is
    # not one, and the main session must not be blocked for writing it.
    assert dispatch(None, "general-purpose", "never run git push --force origin main").returncode == 0


def test_hooks_json_has_no_agent_dispatch_guard():
    # The only agent whose dispatches were checked (#277) was the verifier, and
    # the verify stage now runs in the main session; a PreToolUse hook on Agent
    # would start a Python process per dispatch and check nothing.
    with open(os.path.join(SCRIPTS, "..", "hooks", "hooks.json"), encoding="utf-8") as fh:
        entries = json.load(fh)["hooks"]["PreToolUse"]
    assert all("Agent" not in e["matcher"].split("|") for e in entries)


def test_declared_string_with_shell_symbols_is_authorised_by_the_person(tmp_path):
    cwd = project(tmp_path, {".cai/cai.json": json.dumps(
        {"test": {"commands": ["make a && make b"]}})})
    assert runner_guard.allowed("make a && make b", cwd) is True
    assert runner_guard.allowed("make a && make b && rm x", cwd) is False


def test_invalid_declaration_resolves_nothing(tmp_path):
    cwd = project(tmp_path, {"Cargo.toml": "", ".cai/cai.json": "not json"})
    assert runner_guard.allowed("cargo test", cwd) is False


def test_go_whole_argument_and_narrowing(tmp_path):
    cwd = project(tmp_path, {"go.mod": "module x\n"})
    for command in ("go test", "go test ./...", "go test ./pkg/foo"):
        assert runner_guard.allowed(command, cwd) is True, command


def test_resolver_raising_blocks(cargo, monkeypatch):
    def boom(_):
        raise RuntimeError("bug")
    monkeypatch.setattr(resolve_test_command, "resolve", boom)
    assert runner_guard.allowed("cargo test", cargo) is False


@pytest.mark.skipif(os.name != "nt", reason="a backslash path is only a path on Windows")
def test_backslash_cwd_is_accepted(tmp_path):
    # The hook payload's cwd is a Windows backslash path (observed in unit 1).
    # On POSIX the same text is one relative filename that does not exist.
    cwd = project(tmp_path, {"Cargo.toml": ""}).replace("/", "\\")
    assert runner_guard.allowed("cargo test", cwd) is True


@pytest.mark.parametrize("command", [
    "git diff", "git log", "git rev-parse --show-toplevel",
    "python ${CLAUDE_PLUGIN_ROOT}/scripts/provenance.py",
    "python ${CLAUDE_PLUGIN_ROOT}/scripts/verify_plan.py plan --track-dir t",
    "python ${CLAUDE_PLUGIN_ROOT}/scripts/local_run.py --track-dir t --stage verify",
])
def test_runner_gets_no_git_shapes_and_no_verify_scripts(empty, command):
    assert runner_guard.allowed(command, empty) is False


# --- check(): payload in, exit code and stderr out -------------------------

def payload(command, agent, cwd):
    return {"agent_type": agent, "cwd": cwd, "tool_name": "Bash",
            "tool_input": {"command": command}}


def test_check_allows_silently(cargo, capsys):
    assert runner_guard.check(payload("cargo test", RUNNER, cargo)) == 0
    assert capsys.readouterr().err == ""


def test_check_blocks_with_a_reason_naming_the_agent(cargo, capsys):
    assert runner_guard.check(payload("cargo test 2>&1", RUNNER, cargo)) == 2
    err = capsys.readouterr().err
    assert err.startswith("Blocked: " + RUNNER)
    assert "test-command.md" in err


@pytest.mark.parametrize("bad", [
    {"agent_type": RUNNER},
    {"agent_type": RUNNER, "tool_input": {}},
    {"agent_type": RUNNER, "tool_input": {"command": 5}},
    {"agent_type": RUNNER, "tool_input": None},
])
def test_check_blocks_a_payload_without_a_command(bad):
    assert runner_guard.check(bad) == 2


UNSAFE_CHARS = [";", "&", "|", "<", ">", "`", "$", "(", ")", "{", "}", "\n", "\r"]


@pytest.mark.parametrize("ch", UNSAFE_CHARS, ids=[hex(ord(c)) for c in UNSAFE_CHARS])
def test_every_unsafe_character_is_refused(ch):
    # Dropping a character from runner_guard.UNSAFE must fail here.
    assert runner_guard.UNSAFE.search(ch)


def test_declared_command_with_repeated_blanks(tmp_path):
    cwd = project(tmp_path, {".cai/cai.json": json.dumps(
        {"test": {"commands": ["cargo  test"]}})})
    assert runner_guard.allowed("cargo test", cwd) is True
    assert runner_guard.allowed("cargo  test", cwd) is True
    assert runner_guard.allowed("cargo test; x", cwd) is False


def test_this_repos_declared_regenerate_and_test_command_is_the_only_extra(tmp_path):
    # #371: the regeneration + pytest chain this repo declares runs, and still
    # nothing else (acceptance condition 3). The declaration lives in .cai/,
    # outside git, so it is written here.
    declared = "python scripts/gen-codex.py && python -m pytest"
    (tmp_path / ".cai").mkdir()
    (tmp_path / ".cai" / "cai.json").write_text(
        json.dumps({"test": {"commands": [declared]}}), encoding="utf-8")
    repo = str(tmp_path)
    assert runner_guard.allowed(declared, repo) is True
    assert runner_guard.allowed(declared + " tests/a.py -x", repo) is True
    for blocked in ("python scripts/gen-codex.py",
                    "python scripts/validate.py",
                    "python scripts/gen-codex.py && python -m pytest; rm x",
                    "python scripts/gen-codex.py && rm -rf x && python -m pytest",
                    "python -c 'print(1)' && python -m pytest"):
        assert runner_guard.allowed(blocked, repo) is False, blocked


# --- bash_guard dispatches on agent_type -----------------------------------

def run_guard(command, agent, cwd):
    body = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}
    if agent:
        body["agent_type"] = agent
    return subprocess.run([sys.executable, BASH_GUARD], input=json.dumps(body),
                          capture_output=True, text=True).returncode


@pytest.mark.parametrize("command, agent, expected", [
    ("cargo test", "cai:test-runner", 0),
    ("cargo test", None, 0),                        # main session: unchanged
    ("rm -rf target", "cai:test-runner", 2),
    ("git status", "cai:test-runner", 2),
    ("git status", None, 0),
    ("git status", "cai:explorer", 0),              # not a scoped agent
    # The retired stage agents are no longer scoped: only the general rules apply.
    ("git status", "cai:designer", 0),
    ("git push --force origin main", "cai:verifier", 2),
])
def test_dispatch(cargo, command, agent, expected):
    assert run_guard(command, agent, cargo) == expected


def test_scoped_agent_still_meets_the_global_rules(tmp_path):
    # An allowed-by-scope command is only the first gate (D7): a declared
    # `git log` plus a plain argument passes the scope, so `--no-verify` is
    # stopped only by the general rule that runs after it.
    cwd = project(tmp_path, {".cai/cai.json": json.dumps({"test": {"commands": ["git log"]}})})
    assert run_guard("git log --oneline", RUNNER, cwd) == 0
    assert runner_guard.allowed("git log --no-verify", cwd) is True
    assert run_guard("git log --no-verify", RUNNER, cwd) == 2


def test_runner_guard_reads_the_git_root_not_the_working_directory(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    project(tmp_path, {"Cargo.toml": ""})
    sub = tmp_path / "sub"
    sub.mkdir()
    assert runner_guard.allowed("cargo test", str(sub)) is True


def test_designer_flag_path_is_gone():
    text = open(BASH_GUARD, encoding="utf-8").read()
    assert "--designer" not in text
