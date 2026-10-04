"""Unit 6: runner_guard (test-runner, verifier), designer_guard's new entry and
bash_guard's agent_type dispatch -- AC8, AC15 and detail design D7.

Fixtures carry no `git init`, so the guard's root falls back to the working
directory (resolve_test_command.find_root's documented fallback).
"""
import json
import os
import subprocess
import sys

import pytest

import designer_guard
import resolve_test_command
import runner_guard

SCRIPTS = os.path.dirname(os.path.abspath(runner_guard.__file__))
BASH_GUARD = os.path.join(SCRIPTS, "bash_guard.py")
RESOLVER = "python ${CLAUDE_PLUGIN_ROOT}/scripts/resolve_test_command.py"
RUNNER, VERIFIER = "cai:test-runner", "cai:verifier"


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
    assert runner_guard.allowed(command, cargo, RUNNER) is expected


def test_runner_blocks_an_unresolved_command(empty):
    # Nothing resolves here, so no command can be compared against.
    assert runner_guard.allowed("cargo test", empty, RUNNER) is False


def test_several_candidates_resolve_nothing(tmp_path):
    cwd = project(tmp_path, {"Cargo.toml": "", "go.mod": "module x\n"})
    assert resolve_test_command.resolve(cwd)["status"] == "several"
    assert runner_guard.allowed("cargo test", cwd, RUNNER) is False


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
    assert runner_guard.allowed(command, empty, RUNNER) is expected


def test_resolver_by_its_real_path(empty):
    script = os.path.join(SCRIPTS, "resolve_test_command.py")
    assert runner_guard.allowed("python " + script.replace("\\", "/"), empty, RUNNER) is True


def test_declared_commands_all_pass_and_take_arguments(tmp_path):
    cwd = project(tmp_path, {".claude/cai.json": json.dumps(
        {"test": {"commands": ["python -m pytest", "npm test"]}})})
    for command in ("python -m pytest", "python -m pytest tests/a.py -x", "npm test"):
        assert runner_guard.allowed(command, cwd, RUNNER) is True, command
    assert runner_guard.allowed("npm run build", cwd, RUNNER) is False
    assert runner_guard.allowed("python -m pytest; rm x", cwd, RUNNER) is False


def test_declared_string_with_shell_symbols_is_authorised_by_the_person(tmp_path):
    cwd = project(tmp_path, {".claude/cai.json": json.dumps(
        {"test": {"commands": ["make a && make b"]}})})
    assert runner_guard.allowed("make a && make b", cwd, RUNNER) is True
    assert runner_guard.allowed("make a && make b && rm x", cwd, RUNNER) is False


def test_invalid_declaration_resolves_nothing(tmp_path):
    cwd = project(tmp_path, {"Cargo.toml": "", ".claude/cai.json": "not json"})
    assert runner_guard.allowed("cargo test", cwd, RUNNER) is False


def test_go_whole_argument_and_narrowing(tmp_path):
    cwd = project(tmp_path, {"go.mod": "module x\n"})
    for command in ("go test", "go test ./...", "go test ./pkg/foo"):
        assert runner_guard.allowed(command, cwd, RUNNER) is True, command


def test_resolver_raising_blocks(cargo, monkeypatch):
    def boom(_):
        raise RuntimeError("bug")
    monkeypatch.setattr(resolve_test_command, "resolve", boom)
    assert runner_guard.allowed("cargo test", cargo, RUNNER) is False


@pytest.mark.skipif(os.name != "nt", reason="a backslash path is only a path on Windows")
def test_backslash_cwd_is_accepted(tmp_path):
    # The hook payload's cwd is a Windows backslash path (observed in unit 1).
    # On POSIX the same text is one relative filename that does not exist.
    cwd = project(tmp_path, {"Cargo.toml": ""}).replace("/", "\\")
    assert runner_guard.allowed("cargo test", cwd, RUNNER) is True


def test_runner_gets_no_git_shapes(empty):
    for command in ("git diff", "git log", "git rev-parse --show-toplevel",
                    "python ${CLAUDE_PLUGIN_ROOT}/scripts/provenance.py"):
        assert runner_guard.allowed(command, empty, RUNNER) is False, command


# --- D7: what only the verifier may also run -------------------------------

@pytest.mark.parametrize("command, expected", [
    ("git diff", True),
    ("git diff --stat a...HEAD", True),
    ("git log --oneline -5", True),
    ("git log", True),
    ("git show HEAD:README.md", True),
    ("git merge-base HEAD main", True),
    ("git symbolic-ref --short refs/remotes/origin/HEAD", True),
    ("git rev-parse --show-toplevel", True),
    ("git symbolic-ref HEAD refs/heads/x", False),   # two arguments would write a ref
    ("git symbolic-ref --short refs/remotes/origin/HEAD extra", False),
    ("git rev-parse --show-toplevel extra", False),
    ("git rev-parse HEAD", False),
    ("git merge-base HEAD", False),
    ("git merge-base HEAD main; git stash", False),
    ("git merge-base HEAD $(x)", False),
    ("git difftool", False),
    ("git logx", False),
    ("git diff; git push", False),
    ("git diff | cat", False),
    ("git push origin x", False),
    ("git status", False),
    ("python ${CLAUDE_PLUGIN_ROOT}/scripts/provenance.py", True),
    ("python ${CLAUDE_PLUGIN_ROOT}/scripts/provenance.py --check x", True),
    ("python ${CLAUDE_PLUGIN_ROOT}/scripts/provenance.py x; rm y", False),
])
def test_verifier_extra_allowances(empty, command, expected):
    assert runner_guard.allowed(command, empty, VERIFIER) is expected


def test_verifier_still_gets_the_resolver_and_resolved_commands(cargo):
    assert runner_guard.allowed(RESOLVER, cargo, VERIFIER) is True
    assert runner_guard.allowed("cargo test", cargo, VERIFIER) is True


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
    assert "git diff" not in err                    # the verifier's sentence only


def test_check_verifier_reason_lists_git_and_provenance(cargo, capsys):
    assert runner_guard.check(payload("git push", VERIFIER, cargo)) == 2
    err = capsys.readouterr().err
    assert "git diff" in err and "provenance.py" in err


@pytest.mark.parametrize("bad", [
    {"agent_type": RUNNER},
    {"agent_type": RUNNER, "tool_input": {}},
    {"agent_type": RUNNER, "tool_input": {"command": 5}},
    {"agent_type": RUNNER, "tool_input": None},
])
def test_check_blocks_a_payload_without_a_command(bad):
    assert runner_guard.check(bad) == 2


# --- designer_guard: the function entry and the two fixed commands ---------

@pytest.mark.parametrize("command, expected", [
    ("date +%F", True),
    ("date  +%F", True),
    ("git rev-parse --show-toplevel", True),
    ("date +%s", False),
    ("date +%F; git stash", False),
    ("git rev-parse HEAD", False),
    ("git rev-parse --show-toplevel --git-dir", False),
    ("git status", False),
    ("mmdc -i a.mmd -o a.svg", True),
])
def test_designer_allowed(tmp_path, command, expected):
    assert designer_guard.allowed(command, str(tmp_path)) is expected


def test_designer_check_exit_codes(tmp_path, capsys):
    ok = {"cwd": str(tmp_path), "tool_input": {"command": "date +%F"}}
    assert designer_guard.check(ok) == 0
    assert capsys.readouterr().err == ""
    assert designer_guard.check({"tool_input": {"command": "git status"}}) == 2
    err = capsys.readouterr().err
    assert "date +%F" in err and "git rev-parse --show-toplevel" in err
    assert designer_guard.check({}) == 2


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
    ("git status", "cai:designer", 2),
    ("mmdc -i a.mmd -o a.svg", "cai:designer", 0),
    ("date +%F", "cai:designer", 0),
    ("git diff", "cai:verifier", 0),
    ("git push origin x", "cai:verifier", 2),
])
def test_dispatch(cargo, command, agent, expected):
    assert run_guard(command, agent, cargo) == expected


def test_scoped_agent_still_meets_the_global_rules(cargo):
    # An allowed-by-scope command is only the first gate (D7): `git log` plus a
    # plain argument passes the scope, so `--no-verify` is stopped only by the
    # general rule that runs after it.
    assert run_guard("git log --oneline", "cai:verifier", cargo) == 0
    assert runner_guard.allowed("git log --no-verify", cargo, VERIFIER) is True
    assert run_guard("git log --no-verify", "cai:verifier", cargo) == 2


def test_runner_guard_reads_the_git_root_not_the_working_directory(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    project(tmp_path, {"Cargo.toml": ""})
    sub = tmp_path / "sub"
    sub.mkdir()
    assert runner_guard.allowed("cargo test", str(sub), RUNNER) is True


def test_designer_flag_path_is_gone():
    text = open(BASH_GUARD, encoding="utf-8").read()
    assert "--designer" not in text
