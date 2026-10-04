"""Regression checks for the September open-issue batch."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import types

import pytest

import ledger
import usage_collector
import usage_report


def test_bad_transcript_lines_are_bounded_per_file(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("bad\n" * 45 + '{"type":"assistant"}\n' * 30,
                          encoding="utf-8")
    for since, until in [(0, 2000), (2000, 6000)]:
        problems = []
        assert usage_collector.read_window(transcript, since, until, problems) == []
        assert len(problems) == 2
        assert "45 unparseable lines" in problems[0]
        assert "first: line 1" in problems[0]
        assert "30 missing or unparseable timestamps" in problems[1]
        assert "first: line 46" in problems[1]


def test_crlf_records_have_no_malformed_rows(tmp_path):
    rows = [{"stage": "build", "note": "one"}, {"stage": "verify", "note": "two"}]
    (tmp_path / "ledger.jsonl").write_bytes(
        ("\r\n".join(json.dumps(row) for row in rows) + "\r\n").encode())
    assert ledger.records(str(tmp_path)) == [dict(row, line=i) for i, row in enumerate(rows, 1)]


def test_crlf_central_records_have_no_malformed_rows(tmp_path):
    path = tmp_path / "usage.jsonl"
    rows = [{"note": "one"}, {"note": "two"}]
    path.write_bytes(("\r\n".join(json.dumps(row) for row in rows) + "\r\n").encode())
    records, malformed = usage_report._read_central_records(str(path))
    assert malformed == 0
    assert records == [dict(row, line=i) for i, row in enumerate(rows, 1)]


def test_crlf_window_reads_both_records(tmp_path, monkeypatch):
    path = tmp_path / "usage.jsonl"
    rows = [{"session_id": "crlf", "window_end": value} for value in
            ["2026-09-30T00:00:02.000Z", "2026-09-30T00:00:01.000Z"]]
    path.write_bytes(("\r\n".join(json.dumps(row) for row in rows) + "\r\n").encode())
    monkeypatch.setattr(usage_collector, "central_ledger_path", lambda: str(path))
    monkeypatch.setattr(ledger, "_data_start_floor", lambda: None)
    assert ledger._window_since("crlf") == rows[0]["window_end"]
    rows.reverse()
    path.write_bytes(("\r\n".join(json.dumps(row) for row in rows) + "\r\n").encode())
    assert ledger._window_since("crlf") == rows[1]["window_end"]


def test_read_only_lenses_have_no_shell():
    for name in ["reviewer", "security-reviewer", "explorer"]:
        text = Path("plugins/cai/agents", name + ".md").read_text(encoding="utf-8")
        tools = next(line for line in text.splitlines() if line.startswith("tools:"))
        assert tools == "tools: Read, Grep, Glob"


def test_no_detail_design_has_explicit_brief_and_traceability():
    build = Path("plugins/cai/skills/track/references/stage-build.md").read_text(encoding="utf-8")
    intake = Path("plugins/cai/skills/track/references/stage-intake.md").read_text(encoding="utf-8")
    assert "## Invariants preserved" in build
    assert "no `UC`/`R` ids and is not a diagnosis" in build
    assert "AC1, AC2" in intake


def test_designer_hook_blocks_out_of_scope_commands():
    guard = Path("plugins/cai/scripts/designer_guard.py")
    for command, expected in [
        ("git status", 2), ("git stash -u", 2), ("python -c 'print(1)'", 2),
        ("python scripts/validate.py", 2),
        ("python plugins/cai/scripts/design_probe.py --kind detail doc.md", 0),
        ("python ${CLAUDE_PLUGIN_ROOT}/scripts/design_probe.py --kind detail doc.md", 0),
        ('python "${CLAUDE_PLUGIN_ROOT}/scripts/options_lint.py" options.md', 0),
        ("mmdc -i diagram.mmd -o diagram.svg", 0),
        ("mmdc -i diagram.mmd > code.py", 2),
        ("python plugins/cai/scripts/design_probe.py doc.md; git stash", 2),
        ("python plugins/cai/scripts/design_probe.py $(git stash)", 2),
        ("mmdc -i (Start-Process calc)", 2),
    ]:
        result = subprocess.run([sys.executable, str(guard)], input=json.dumps({
            "tool_name": "Bash", "tool_input": {"command": command}}),
            capture_output=True, text=True)
        assert result.returncode == expected, (command, result.stderr)


def test_designer_is_held_by_the_global_hook_through_agent_type(tmp_path):
    # The platform ignores `hooks:` in a plugin agent's frontmatter, so the
    # boundary lives in the one global hook and is chosen by `agent_type`.
    # A temporary config root: the dispatcher writes a launcher record there,
    # and the real one under ~/.claude/cai/ is not a test's to fill.
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(tmp_path / "cfg"))
    agent = Path("plugins/cai/agents/designer.md").read_text(encoding="utf-8")
    assert "hooks:" not in agent.split("\n---", 1)[0]
    wrapper = Path("plugins/cai/hooks/run-guard.cmd").resolve()
    for command, agent_type, expected in [
            ("git stash -u", "cai:designer", 2),
            ("python ${CLAUDE_PLUGIN_ROOT}/scripts/design_probe.py --kind detail doc.md",
             "cai:designer", 0),
            ("git stash -u", None, 0)]:  # the main session has no agent_type
        argv = ["cmd", "/c", str(wrapper)] if os.name == "nt" else ["sh", str(wrapper)]
        payload = {"tool_name": "Bash", "tool_input": {"command": command}}
        if agent_type:
            payload["agent_type"] = agent_type
        result = subprocess.run(argv, input=json.dumps(payload),
                                capture_output=True, text=True, env=env)
        assert result.returncode == expected, result.stderr


def _private_hooks(tmp_path):
    """A copy of plugins/cai/hooks to run the dispatcher from.

    Only for tests that end in the reduced check, where the guard never runs, so
    `..\\scripts` need not exist. findstr /G: holds the pattern file against every
    other reader while it runs; reading a copy keeps those tests from making
    another test's copytree of plugins/cai fail with a sharing violation."""
    hooks = tmp_path / "plugin" / "hooks"
    hooks.mkdir(parents=True)
    for source in Path("plugins/cai/hooks").iterdir():
        for attempt in range(20):
            try:
                shutil.copyfile(source, hooks / source.name)
                break
            except PermissionError:
                time.sleep(0.05)
        else:
            raise AssertionError("could not read %s" % source)
    return hooks


def _wrapper_env(tmp_path, standins=(), private_hooks=False):
    """argv and env that run run-guard.cmd with only `standins` as interpreters.

    A `bin` directory under tmp_path is the whole PATH, plus System32 on Windows.
    Windows: System32 holds neither `py` nor `python` (checked below, and the
    test skips if a machine puts one there). POSIX: `bin` also holds links to
    only the four programs the sh branch calls. CLAUDE_CONFIG_DIR is a
    temporary config root, so the dispatcher never writes the real record."""
    hooks = _private_hooks(tmp_path) if private_hooks else Path("plugins/cai/hooks")
    wrapper = str((hooks / "run-guard.cmd").resolve())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    if os.name == "nt":
        path = os.pathsep.join([str(bin_dir), os.path.join(os.environ["SystemRoot"], "System32")])
        argv = [os.environ["COMSPEC"], "/c", wrapper]
    else:
        for name in ("sh", "grep", "dirname", "rm"):
            os.symlink(shutil.which(name), str(bin_dir / name))
        path = str(bin_dir)
        argv = [str(bin_dir / "sh"), wrapper]
    for name, mode in standins:
        _standin(bin_dir, name, mode)
    env = dict(os.environ, PATH=path, CLAUDE_CONFIG_DIR=str(tmp_path / "cfg"))
    return argv, env


def _wrapper_without_python(tmp_path):
    argv, env = _wrapper_env(tmp_path, private_hooks=True)
    for name in ("py", "python", "python3"):
        if shutil.which(name, path=env["PATH"]):
            pytest.skip("%s is on the reduced PATH" % name)
    return argv, env


def _standin(directory, name, mode, log=None):
    """A stand-in interpreter that hands control back, as a real one does.

    Windows writes a `.bat` (ending in `exit /b`); POSIX a `#!/bin/sh` file with
    mode 0o755 (CLAUDE.md, "A test that plants a fake executable"). Modes:
    exit0 and exit9 answer that code to anything; input9 answers 9 when stdin
    holds a line and 0 when it is empty; forward appends a line to `log` then
    runs the real interpreter with the same arguments; drainw reads all of stdin,
    then exits 1 for the record writer and 0 for the guard."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        body = {"exit0": "exit /b 0", "exit9": "exit /b 9",
                "input9": 'set "X="\nset /p X=\nif defined X exit /b 9\nexit /b 0',
                "drainw": 'findstr "^" >nul\nif "%~nx1"=="record_launcher.py" exit /b 1\nexit /b 0',
                "forward": 'echo x>>"%s"\n"%s" %%*\nexit /b %%ERRORLEVEL%%' % (log, sys.executable)}[mode]
        path = directory / (name + ".bat")
        path.write_bytes(("@echo off\r\n" + body.replace("\n", "\r\n") + "\r\n").encode("ascii"))
        return path
    body = {"exit0": "exit 0", "exit9": "exit 9",
            "input9": 'IFS= read -r X\n[ -n "$X" ] && exit 9\nexit 0',
            "drainw": 'while IFS= read -r L; do :; done\ncase "$1" in *record_launcher.py) exit 1;; esac\nexit 0',
            "forward": 'echo x >> "%s"\nexec "%s" "$@"' % (log, sys.executable)}[mode]
    path = directory / name
    path.write_bytes(("#!/bin/sh\n" + body + "\n").encode("utf-8"))
    path.chmod(0o755)
    return path


# The name a stand-in must take to be the first candidate found, per platform.
FIRST = "python" if os.name == "nt" else "python3"
CANDIDATE_NAMES = ("py", "python") if os.name == "nt" else ("python3", "python")


def _call(argv, env, command, agent_type=None, compact=True):
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    if agent_type:
        payload["agent_type"] = agent_type
    separators = (",", ":") if compact else None  # the platform sends compact JSON
    return subprocess.run(argv, input=json.dumps(payload, separators=separators),
                          capture_output=True, text=True, env=env)


def _record_file(env):
    return Path(env["CLAUDE_CONFIG_DIR"], "cai",
                "guard-launcher-cmd.txt" if os.name == "nt" else "guard-launcher-sh.txt")


def _plant_record(env, text):
    path = _record_file(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((text + ("\r\n" if os.name == "nt" else "\n")).encode("ascii"))


def _safe_interpreter():
    writer = _load_writer()
    if writer.record_line(sys.executable, "python").startswith("cai-launcher 1 name"):
        pytest.skip("sys.executable is not a plain ASCII path, so no path record is written")
    return writer.record_line(sys.executable, "python")


@pytest.mark.parametrize("compact", [True, False])
def test_wrapper_without_python_runs_the_reduced_check(tmp_path, compact):
    argv, env = _wrapper_without_python(tmp_path)
    for agent_type, expected in [("cai:test-runner", 2), ("cai:verifier", 2),
                                 ("cai:designer", 2), ("cai:explorer", 0), (None, 0)]:
        result = _call(argv, env, "git status", agent_type, compact)
        assert result.returncode == expected, (agent_type, result.stderr)
    result = _call(argv, env, "git status", None, compact)
    assert (result.returncode, result.stderr) == (0, "")  # silent when it lets a call through
    result = _call(argv, env, "git push --force origin main", None, compact)
    assert result.returncode == 2
    assert "cai guard reduced check:" in result.stderr
    assert "bash_guard blocked this command" not in result.stderr
    assert _call(argv, env, "git commit -m x", None, compact).returncode == 0
    assert not _record_file(env).exists()  # "not found" is never recorded


def test_broken_interpreters_first_on_path_leave_scoped_agents_blocked(tmp_path):
    # Issue #273 AC1: a stand-in that exits 9 (as the Store stub's 9009 does) on
    # every candidate name, no record yet, a scoped agent's payload: exit 2.
    argv, env = _wrapper_env(tmp_path, [(name, "exit9") for name in CANDIDATE_NAMES],
                             private_hooks=True)
    for agent_type, expected in [("cai:test-runner", 2), ("cai:verifier", 2),
                                 ("cai:designer", 2), ("cai:explorer", 0), (None, 0)]:
        result = _call(argv, env, "git status", agent_type)
        assert result.returncode == expected, (agent_type, result.stderr)
    assert _call(argv, env, "git push --force origin main").returncode == 2
    assert not _record_file(env).exists()


def test_probes_leave_the_hook_input_for_the_reduced_check(tmp_path):
    # Every candidate runs the guard (exit 0) but its writer fails, and it reads
    # all of stdin first. A probe that was handed the real input would leave the
    # reduced check an empty stream, and `grep -q`/`findstr` then pass a force push.
    argv, env = _wrapper_env(tmp_path, [(name, "drainw") for name in CANDIDATE_NAMES],
                             private_hooks=True)
    result = _call(argv, env, "git push --force origin main")
    assert result.returncode == 2
    assert "cai guard reduced check:" in result.stderr
    assert not _record_file(env).exists()


def test_missing_pattern_file_blocks_every_call(tmp_path):
    argv, env = _wrapper_without_python(tmp_path)
    (Path(argv[-1]).parent / "reduced-check-patterns.txt").unlink()
    for command in ("git status", "git push --force origin main"):
        result = _call(argv, env, command)
        assert result.returncode == 2, command
        assert "cai guard reduced check:" in result.stderr


@pytest.mark.skipif(os.name != "nt", reason="findstr /G: is the only reader that takes the file")
def test_reduced_check_waits_out_another_reader_of_the_pattern_file(tmp_path):
    # Two degraded calls at once: while one findstr /G: has the pattern file, the
    # other cannot open it and exits 2. That is a collision, not a verdict, so a
    # harmless call must still pass once the file is free again.
    import ctypes
    import threading
    argv, env = _wrapper_without_python(tmp_path)
    patterns = str(Path(argv[-1]).parent / "reduced-check-patterns.txt")
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                     ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                     ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.CreateFileW(patterns, 0x80000000, 0, None, 3, 0x80, None)  # no sharing
    assert handle not in (None, ctypes.c_void_p(-1).value)
    timer = threading.Timer(0.8, kernel32.CloseHandle, [handle])
    timer.start()
    try:
        assert _call(argv, env, "git status").returncode == 0
    finally:
        timer.join()


def test_first_call_records_the_real_interpreter_and_the_second_does_not_probe(tmp_path):
    expected = _safe_interpreter()
    log = tmp_path / "launches.txt"
    argv, env = _wrapper_env(tmp_path)
    _standin(tmp_path / "bin", FIRST, "forward", log)
    assert _call(argv, env, "git status").returncode == 0
    line = _record_file(env).read_bytes().decode("ascii").splitlines()
    assert line == [expected]
    assert len(log.read_text(encoding="ascii").splitlines()) == 2  # probe step 1 and 2
    assert _call(argv, env, "git status").returncode == 0
    assert len(log.read_text(encoding="ascii").splitlines()) == 2  # the recorded path runs the guard directly


def test_recorded_launcher_that_fails_on_this_input_only_is_kept(tmp_path):
    argv, env = _wrapper_env(tmp_path)
    standin = _standin(tmp_path / "standins", "input9", "input9")
    _plant_record(env, "cai-launcher 1 path %s end" % standin)
    result = _call(argv, env, "git status")
    assert result.returncode == 2  # every caller, even the main session's git status
    assert "cai guard launcher failed:" in result.stderr
    assert "bash_guard blocked this command" not in result.stderr
    assert _record_file(env).exists()  # it still runs the guard on empty input


def test_recorded_launcher_that_always_fails_is_dropped_and_the_next_call_probes(tmp_path):
    argv, env = _wrapper_env(tmp_path)
    log = tmp_path / "launches.txt"
    standin = _standin(tmp_path / "standins", "exit9", "exit9")
    _plant_record(env, "cai-launcher 1 path %s end" % standin)
    result = _call(argv, env, "git status")
    assert result.returncode == 2
    assert "cai guard launcher failed:" in result.stderr
    assert not _record_file(env).exists()
    _standin(tmp_path / "bin", FIRST, "forward", log)
    assert _call(argv, env, "git status").returncode == 0
    assert _record_file(env).read_bytes().startswith(b"cai-launcher 1 path ")


def test_recorded_path_that_no_longer_exists_is_dropped(tmp_path):
    argv, env = _wrapper_env(tmp_path)
    _plant_record(env, "cai-launcher 1 path %s end" % (tmp_path / "gone" / "python.exe"))
    result = _call(argv, env, "git status")
    assert result.returncode == 2
    assert "cai guard launcher failed:" in result.stderr
    assert "no longer exists" in result.stderr
    assert not _record_file(env).exists()


def test_interpreter_that_answers_zero_to_everything_is_not_recorded(tmp_path):
    argv, env = _wrapper_env(tmp_path, [(name, "exit0") for name in CANDIDATE_NAMES],
                             private_hooks=True)
    assert _call(argv, env, "git status").returncode == 0
    result = _call(argv, env, "git push --force origin main")
    assert result.returncode == 2
    assert "cai guard reduced check:" in result.stderr
    assert not _record_file(env).exists()


def test_truncated_record_is_ignored_and_overwritten(tmp_path):
    expected = _safe_interpreter()
    argv, env = _wrapper_env(tmp_path)
    _standin(tmp_path / "bin", FIRST, "forward", tmp_path / "launches.txt")
    _plant_record(env, "cai-launcher 1 path %s" % sys.executable)  # no end field
    assert _call(argv, env, "git status").returncode == 0
    assert _record_file(env).read_bytes().decode("ascii").splitlines() == [expected]


def test_unwritable_config_root_still_runs_the_guard_by_name(tmp_path):
    argv, env = _wrapper_env(tmp_path)
    _standin(tmp_path / "bin", FIRST, "forward", tmp_path / "launches.txt")
    cfg = Path(env["CLAUDE_CONFIG_DIR"])
    cfg.mkdir()
    (cfg / "cai").write_text("a file where the directory should be", encoding="utf-8")
    result = _call(argv, env, "git reset --hard HEAD~1")
    assert result.returncode == 2
    assert "bash_guard blocked this command" in result.stderr
    assert _call(argv, env, "git status").returncode == 0
    assert (cfg / "cai").is_file()  # nothing replaced it


WRITER = Path("plugins/cai/hooks/record_launcher.py")


def _load_writer():
    # exec, not importlib's file loader: that one writes a __pycache__ into
    # plugins/cai/hooks, which ships.
    module = types.ModuleType("record_launcher")
    exec(compile(WRITER.read_text(encoding="utf-8"), str(WRITER), "exec"), module.__dict__)
    return module


def _run_writer(form, candidate, record, extra_env=None):
    env = {key: value for key, value in os.environ.items() if key != "CAI_GUARD_RECORD"}
    if record is not None:
        env["CAI_GUARD_RECORD"] = str(record)
    env.update(extra_env or {})
    return subprocess.run([sys.executable, str(WRITER), form, candidate],
                          capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)


def test_record_line_writes_a_path_only_for_a_safe_existing_absolute_file(tmp_path):
    writer = _load_writer()
    safe = tmp_path / "my dir" / "python-3.13_x(1).exe"
    safe.parent.mkdir()
    safe.write_bytes(b"")
    assert writer.record_line(str(safe), "py -3") == "cai-launcher 1 path %s end" % safe
    for name in ("%x%.exe", "a^b.exe", "a&b.exe", "a!b.exe", "a,b.exe", "王小明.exe"):
        odd = tmp_path / name
        odd.write_bytes(b"")
        assert writer.record_line(str(odd), "python") == "cai-launcher 1 name python end", name
    assert writer.record_line(str(tmp_path / "missing.exe"), "python3") == \
        "cai-launcher 1 name python3 end"
    assert writer.record_line("python.exe", "py -3") == "cai-launcher 1 name py -3 end"


def test_record_writer_writes_one_line_per_form(tmp_path):
    record = tmp_path / "cfg" / "cai" / "guard-launcher-cmd.txt"
    result = _run_writer("cmd", "py -3", record)
    assert result.returncode == 0, result.stderr
    line = _load_writer().record_line(sys.executable, "py -3")  # T1 pins its value
    assert record.read_bytes() == line.encode("ascii") + b"\r\n"
    sh_record = tmp_path / "cfg" / "cai" / "guard-launcher-sh.txt"
    assert _run_writer("sh", "python3", sh_record).returncode == 0
    assert sh_record.read_bytes().endswith(b" end\n")
    assert not sh_record.read_bytes().endswith(b"\r\n")


def test_record_writer_exits_73_when_it_cannot_write_and_1_on_bad_input(tmp_path):
    (tmp_path / "cai").write_text("a file where the directory should be", encoding="utf-8")
    result = _run_writer("cmd", "python", tmp_path / "cai" / "guard-launcher-cmd.txt")
    assert result.returncode == 73
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cai"]
    assert _run_writer("cmd", "python", None).returncode == 1
    assert _run_writer("cmd", "python", "relative.txt").returncode == 1
    assert _run_writer("bat", "python", tmp_path / "r.txt").returncode == 1
    assert _run_writer("cmd", "ruby", tmp_path / "r.txt").returncode == 1
    assert not (tmp_path / "r.txt").exists()


def test_four_record_writers_at_once_leave_one_valid_line_and_no_temp_file(tmp_path):
    record = tmp_path / "cai" / "guard-launcher-cmd.txt"
    env = dict(os.environ, CAI_GUARD_RECORD=str(record))
    procs = [subprocess.Popen([sys.executable, str(WRITER), "cmd", "python"], env=env,
                              stdin=subprocess.DEVNULL) for _ in range(4)]
    codes = [proc.wait() for proc in procs]
    assert set(codes) <= {0, 73}, codes  # 73: Windows refused to replace a file in use
    assert 0 in codes
    lines = record.read_bytes().split(b"\r\n")
    assert len(lines) == 2 and lines[1] == b""
    assert lines[0].startswith((b"cai-launcher 1 path ", b"cai-launcher 1 name ")) \
        and lines[0].endswith(b" end")
    assert sorted(p.name for p in record.parent.iterdir()) == [record.name]


PATTERN_FILE = Path("plugins/cai/hooks/reduced-check-patterns.txt")

# Commands the full guard's five BLOCKED rules decide (bash_guard.py:70-84).
T13_COMMANDS = [
    "git push --force origin main", "git push -f origin main",
    "git push origin +HEAD:main", "git push origin +main",
    "git push --force-with-lease origin main", "git push --force-with-lease origin feature",
    "git push --force-with-lease", "git push origin feature", "git push",
    "git push origin main:feat/x", "git push origin v1.0", "git push --tags",
    "git push origin feat/x > out.txt 2>&1", "echo hi && git push --force origin main",
    "git -C /repo push --force origin main",
    'git -C "C:\\Users\\Jane Doe\\project" push --force origin main',
    "git reset --hard HEAD~1", "git -c user.name=x reset --hard HEAD~1",
    "git reset --soft HEAD~1", "git clean -fd", "git --no-pager clean -fd",
    "git clean -n", "git clean --force",
    "git commit --no-verify -m x", "git status && npm publish --no-verify",
    "git commit -m \"x\"", "git commit -m x", "git status",
    "git log --grep='git push origin main'",
    "rm -rf build/", "rm -fr x", "rm -r -f build/", "rm -f -r x", "rm -r x -f",
    "rm -R -f x", "rm -Rf x", "rm --recursive --force build/", "rm --force --recursive x",
    "rm --recursive -f x", "rm -r --force x", "rm -f --recursive x", "rm --force -r x",
    "rm -r build", "rm -f x", "rm -f notes.txt", 'rm \\"a b\\" -rf',
    "echo rm -rf is dangerous",
    "git commit -F - <<'EOF'\nfix: mention --no-verify\nEOF",
    "git push origin feature\nls -f",
]

# The pattern file matches the whole hook JSON, where a newline is the two
# characters backslash-n and stops no pattern, so a rule can read across lines;
# the full guard reads the real text. Each of these over-blocks on purpose
# (stance Sacrifices, the heredoc line) and nothing else may.
T13_KNOWN_OVER_BLOCKS = {
    "git commit -F - <<'EOF'\nfix: mention --no-verify\nEOF",
    "git push origin feature\nls -f",
}


@pytest.fixture
def pattern_copy(tmp_path):
    """The pattern file, copied for the tool to read.

    findstr /G: opens the file so that nothing else may read it while it runs
    (measured: 46 000 refused reads in 150 runs). T13 starts the tool a hundred
    times, and under xdist that made other tests' copytree of plugins/cai fail
    with a sharing violation, so it reads a private copy instead."""
    copy = tmp_path / "patterns.txt"
    for attempt in range(20):
        try:
            copy.write_bytes(PATTERN_FILE.read_bytes())
            return copy
        except PermissionError:
            time.sleep(0.05)
    raise AssertionError("could not read %s" % PATTERN_FILE)


def _pattern_file_hits(payload_text, patterns):
    """exit code of the tool the dispatcher uses on this platform: 0 hit, 1 none."""
    if os.name == "nt":
        argv = ["findstr", "/R", "/G:" + str(patterns)]
    else:
        argv = ["grep", "-q", "-f", str(patterns)]
    return subprocess.run(argv, input=payload_text, capture_output=True,
                          text=True).returncode


@pytest.mark.parametrize("compact", [True, False])
def test_pattern_file_agrees_with_the_guards_five_rules(compact, pattern_copy):
    import bash_guard
    separators = (",", ":") if compact else None
    for command in T13_COMMANDS:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}},
                             separators=separators)
        blocked = any(re.search(rule[0], command) for rule in bash_guard.BLOCKED)
        hit = _pattern_file_hits(payload, pattern_copy)
        assert hit in (0, 1), (command, "the tool failed", hit)
        if blocked:
            assert hit == 0, ("missed", command)
        elif hit == 0:
            assert command in T13_KNOWN_OVER_BLOCKS, ("over-blocks", command)
    for command in T13_KNOWN_OVER_BLOCKS:
        assert not any(re.search(rule[0], command) for rule in bash_guard.BLOCKED), command


@pytest.mark.parametrize("compact", [True, False])
def test_pattern_file_holds_the_three_scoped_agents(compact, pattern_copy):
    separators = (",", ":") if compact else None
    for agent_type, expected in [("cai:test-runner", 0), ("cai:verifier", 0),
                                 ("cai:designer", 0), ("cai:explorer", 1), (None, 1)]:
        payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
        if agent_type:
            payload["agent_type"] = agent_type
        assert _pattern_file_hits(json.dumps(payload, separators=separators),
                                  pattern_copy) == expected, agent_type


def test_designer_guard_uses_its_installed_path_with_spaces(tmp_path):
    scripts = tmp_path / "plugin with spaces" / "scripts"
    scripts.mkdir(parents=True)
    guard = scripts / "designer_guard.py"
    guard.write_bytes(Path("plugins/cai/scripts/designer_guard.py").read_bytes())
    for script in ("design_probe.py", "options_lint.py"):
        command = 'python "%s" doc.md' % (scripts / script)
        result = subprocess.run([sys.executable, str(guard)], input=json.dumps({
            "cwd": str(tmp_path), "tool_input": {"command": command}}),
            capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    other = tmp_path / "design_probe.py"
    result = subprocess.run([sys.executable, str(guard)], input=json.dumps({
        "cwd": str(tmp_path), "tool_input": {"command": 'python "%s" doc.md' % other}}),
        capture_output=True, text=True)
    assert result.returncode == 2


def test_bad_line_summaries_preserve_note_and_usage_on_append(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cwd = str(tmp_path)
    root = tmp_path / "projects"
    project = root / usage_collector.encoded_project_dir(cwd)
    project.mkdir(parents=True)
    transcript = project / "summary.jsonl"
    row = {"type": "assistant", "timestamp": "2026-09-30T00:00:01.000Z",
           "requestId": "one", "message": {"model": "test-model", "usage": {
               "input_tokens": 100, "output_tokens": 10, "cache_read_input_tokens": 0}}}
    transcript.write_text("bad\n" * 545 + json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(usage_collector, "_projects_root", lambda: str(root))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "summary")
    monkeypatch.setattr(ledger, "_window_since", lambda _: None)
    monkeypatch.setattr(ledger, "_now_ms", lambda: "2026-09-30T00:00:02.000Z")
    artifact = tmp_path / "design.md"
    artifact.write_text("design", encoding="utf-8")
    track = tmp_path / "track"
    track.mkdir()
    note = "important failure detail " * 26
    result = ledger.append(str(track), "build", "failed", artifact=str(artifact), note=note)
    assert result["note"] == note
    assert result["artifact"] == str(artifact)
    assert len(result["usage_problems"]) == 1
    assert "545 unparseable lines" in result["usage_problems"][0]
    assert result["orchestration"]["test-model"]["input_tokens"] == 100
    assert len((track / "ledger.jsonl").read_bytes()) <= ledger.MAX_RECORD
