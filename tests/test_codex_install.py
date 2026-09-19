"""install_codex.py -- makes a user's `~/.codex` match the installed
cai-codex tree.

Design: docs/design/2026-09-18-codex-support-detail.md, "### install_codex.py".
U5 owns this file, the setup skill, and the `HAND_WRITTEN` entry for the
setup skill's `agents/openai.yaml`.

Every test fakes `HOME`, `USERPROFILE` and `CODEX_HOME` in `tmp_path` --
NEVER the real `~/.codex` or real home, per this build's hard safety rule.
The module-level unit tests below call its functions directly, on synthetic
`root`/`home` trees, matching test_gen_codex.py's and test_codex_launcher.py's
"never let a test write the real tree" pattern. The subprocess tests at the
bottom cover the CLI end to end, including the Verification row's AC8 case,
against the real generated `plugins/cai-codex` tree -- read-only, since every
write target is the faked home.
"""
import importlib.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "plugins" / "cai-codex" / "scripts" / "install_codex.py"

sys.dont_write_bytecode = True  # never leave a __pycache__ inside the generated tree

_spec = importlib.util.spec_from_file_location("install_codex", SCRIPT)
install_codex = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(install_codex)


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def fake_env(tmp_path, **extra):
    """A subprocess environment isolated to `tmp_path`: HOME, USERPROFILE
    (Windows' Path.home() source) and CODEX_HOME all point inside it, so a
    bug can never reach the real `~/.codex`."""
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    env["CODEX_HOME"] = str(tmp_path / ".codex")
    env.update(extra)
    return env


def run(env):
    return subprocess.run([sys.executable, str(SCRIPT)],
                          capture_output=True, encoding="utf-8", env=env)


# ---------------------------------------------------------------------------
# Step 1 -- launcher
# ---------------------------------------------------------------------------

def test_install_launcher_copies_bytes(tmp_path):
    root = tmp_path / "root"
    write(root, "scripts/launcher.py", "print('launcher')\n")
    home = tmp_path / "home"

    dest = install_codex.install_launcher(root, home)

    assert dest == home / ".codex" / "cai" / "launcher.py"
    assert dest.read_text(encoding="utf-8") == "print('launcher')\n"


# ---------------------------------------------------------------------------
# Step 2 -- agents
# ---------------------------------------------------------------------------

def test_install_agents_copies_and_removes_stale(tmp_path):
    root = tmp_path / "root"
    write(root, "agents/cai_a.toml", "name = \"cai_a\"\n")
    write(root, "agents/cai_b.toml", "name = \"cai_b\"\n")

    home = tmp_path / "codex_home"
    write(home, "agents/cai_a.toml", "stale old content\n")     # will be overwritten
    write(home, "agents/cai_old.toml", "no longer shipped\n")   # will be removed
    write(home, "agents/personal.toml", "the user's own\n")     # not cai_-prefixed: untouched

    written, removed = install_codex.install_agents(root, home)

    assert {p.name for p in written} == {"cai_a.toml", "cai_b.toml"}
    assert [p.name for p in removed] == ["cai_old.toml"]
    assert (home / "agents" / "cai_a.toml").read_text(encoding="utf-8") == "name = \"cai_a\"\n"
    assert (home / "agents" / "cai_b.toml").read_text(encoding="utf-8") == "name = \"cai_b\"\n"
    assert not (home / "agents" / "cai_old.toml").exists()
    assert (home / "agents" / "personal.toml").read_text(encoding="utf-8") == "the user's own\n"


# ---------------------------------------------------------------------------
# Step 3 -- hooks.json
# ---------------------------------------------------------------------------

def test_install_hooks_creates_file_when_absent(tmp_path):
    home = tmp_path / "codex_home"
    launcher_path = home / ".codex" / "cai" / "launcher.py"

    dest = install_codex.install_hooks(home, launcher_path)

    data = json.loads(dest.read_text(encoding="utf-8"))
    entries = data["hooks"]["PreToolUse"]
    assert len(entries) == 1
    # Scoped to shell commands only (learn.chatgpt.com/docs/hooks, C9): a
    # wildcard would also fire the guard on edits and MCP calls, where
    # tool_input has no `command` field bash_guard can safely read.
    assert entries[0]["matcher"] == "Bash"
    cmd = entries[0]["hooks"][0]["command"]
    assert cmd == f"'{sys.executable}' '{launcher_path.as_posix()}' guard"
    # commandWindows (learn.chatgpt.com/docs/hooks: "Windows-specific command
    # overrides") is Codex's own escape hatch: on Windows, Codex runs a
    # hook's `command` through `powershell.exe -Command`, where a bare
    # `'prog' 'arg'` line is a syntax error (a line starting with a quoted
    # string is an expression; the following quoted token is unexpected), so
    # the guard never runs and Codex reports "Hook failed" -- observed,
    # codex-cli 0.155.0. `&` forces PowerShell to invoke the string as a
    # command, and `exit $LASTEXITCODE` re-surfaces the child's real exit
    # code, since PowerShell otherwise collapses any nonzero child exit to 1.
    cmd_windows = entries[0]["hooks"][0]["commandWindows"]
    assert cmd_windows == (
        f"& '{sys.executable}' '{launcher_path.as_posix()}' guard; exit $LASTEXITCODE")


def test_install_hooks_preserves_other_entries_and_replaces_ours(tmp_path):
    home = tmp_path / "codex_home"
    other_entry = {"matcher": "Foo", "hooks": [{"type": "command", "command": "echo hi"}]}
    old_ours = {"matcher": ".*", "hooks": [{"type": "command",
                "command": '"old-python" "/old/path/.codex/cai/launcher.py" guard'}]}
    write(home, "hooks.json", json.dumps({"hooks": {"PreToolUse": [other_entry, old_ours]}}))

    launcher_path = home / ".codex" / "cai" / "launcher.py"
    dest = install_codex.install_hooks(home, launcher_path)

    entries = json.loads(dest.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert other_entry in entries
    # An old, single-`command` entry (pre-commandWindows) upgrades in place
    # rather than leaving a second, stale copy behind.
    assert len(entries) == 2
    ours = [e for e in entries if e != other_entry][0]
    assert ours["matcher"] == "Bash"
    assert ours["hooks"][0]["command"] == f"'{sys.executable}' '{launcher_path.as_posix()}' guard"
    assert ours["hooks"][0]["commandWindows"] == (
        f"& '{sys.executable}' '{launcher_path.as_posix()}' guard; exit $LASTEXITCODE")


def test_install_hooks_invalid_json_raises_and_never_overwrites(tmp_path):
    home = tmp_path / "codex_home"
    bad = write(home, "hooks.json", "{not json")

    launcher_path = home / ".codex" / "cai" / "launcher.py"
    try:
        install_codex.install_hooks(home, launcher_path)
        assert False, "expected HooksParseError"
    except install_codex.HooksParseError:
        pass

    assert bad.read_text(encoding="utf-8") == "{not json"


# ---------------------------------------------------------------------------
# Step 4 -- AGENTS.md
# ---------------------------------------------------------------------------

def test_install_agents_md_creates_when_absent(tmp_path):
    home = tmp_path / "codex_home"

    dest = install_codex.install_agents_md(home, "some rules text")

    text = dest.read_text(encoding="utf-8")
    assert text == "<!-- cai-codex:begin -->\nsome rules text\n<!-- cai-codex:end -->\n"


def test_install_agents_md_replaces_block_leaves_outside_text_untouched(tmp_path):
    home = tmp_path / "codex_home"
    write(home, "AGENTS.md",
          "# My project\n\nBefore text.\n\n"
          "<!-- cai-codex:begin -->\nold rules\n<!-- cai-codex:end -->\n\nAfter text.\n")

    dest = install_codex.install_agents_md(home, "new rules")

    text = dest.read_text(encoding="utf-8")
    assert text == ("# My project\n\nBefore text.\n\n"
                     "<!-- cai-codex:begin -->\nnew rules\n<!-- cai-codex:end -->\n\nAfter text.\n")


def test_install_agents_md_appends_when_no_markers_present(tmp_path):
    home = tmp_path / "codex_home"
    write(home, "AGENTS.md", "# My project\n\nsome existing content\n")

    dest = install_codex.install_agents_md(home, "the rules")

    text = dest.read_text(encoding="utf-8")
    assert text == ("# My project\n\nsome existing content\n"
                     "<!-- cai-codex:begin -->\nthe rules\n<!-- cai-codex:end -->\n")


def test_install_agents_md_begin_without_end_raises_and_never_overwrites(tmp_path):
    home = tmp_path / "codex_home"
    original = "# My project\n\n<!-- cai-codex:begin -->\nno end marker here\n"
    dest_path = write(home, "AGENTS.md", original)

    try:
        install_codex.install_agents_md(home, "new rules")
        assert False, "expected MarkerError"
    except install_codex.MarkerError:
        pass

    assert dest_path.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# CLI, end to end against the real generated plugins/cai-codex tree
# (read-only for the tree itself -- every write lands under the faked home)
# ---------------------------------------------------------------------------

def test_cli_first_run_writes_everything_and_reports(tmp_path):
    env = fake_env(tmp_path)
    result = run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    home = tmp_path
    codex_home = tmp_path / ".codex"

    assert (home / ".codex" / "cai" / "launcher.py").is_file()
    real_agents = sorted((REPO_ROOT / "plugins" / "cai-codex" / "agents").glob("cai_*.toml"))
    for p in real_agents:
        assert (codex_home / "agents" / p.name).is_file()

    hooks = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    entries = hooks["hooks"]["PreToolUse"]
    assert len(entries) == 1
    assert entries[0]["matcher"] == "Bash"

    agents_md = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_md.count("<!-- cai-codex:begin -->") == 1
    assert agents_md.count("<!-- cai-codex:end -->") == 1

    assert "rules: " in result.stdout and " bytes " in result.stdout
    assert "inactive until you trust it with /hooks" in result.stdout


def test_cli_twice_gives_one_agents_md_block_agents_copied_other_hooks_preserved(tmp_path):
    """AC8 / Verification row: two installer runs give one AGENTS.md block,
    agents copied, and any other hooks.json entry preserved."""
    env = fake_env(tmp_path)
    codex_home = tmp_path / ".codex"

    # A pre-existing, unrelated hook entry that must survive both runs.
    other_entry = {"matcher": "Foo", "hooks": [{"type": "command", "command": "echo untouched"}]}
    write(codex_home, "hooks.json", json.dumps({"hooks": {"PreToolUse": [other_entry]}}))

    first = run(env)
    assert first.returncode == 0, first.stdout + first.stderr
    second = run(env)
    assert second.returncode == 0, second.stdout + second.stderr

    agents_md = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_md.count("<!-- cai-codex:begin -->") == 1
    assert agents_md.count("<!-- cai-codex:end -->") == 1

    hooks = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    entries = hooks["hooks"]["PreToolUse"]
    assert other_entry in entries
    assert len(entries) == 2  # the unrelated one, plus exactly one of ours
    ours = [e for e in entries if e != other_entry][0]
    assert ours["matcher"] == "Bash"

    real_agents = sorted((REPO_ROOT / "plugins" / "cai-codex" / "agents").glob("cai_*.toml"))
    for p in real_agents:
        assert (codex_home / "agents" / p.name).is_file()

    assert "rules: " in second.stdout and " bytes " in second.stdout
    assert "inactive until you trust it with /hooks" in second.stdout


def test_cli_idempotent_second_run_is_byte_identical(tmp_path):
    env = fake_env(tmp_path)
    codex_home = tmp_path / ".codex"

    assert run(env).returncode == 0
    hooks_1 = (codex_home / "hooks.json").read_bytes()
    agents_md_1 = (codex_home / "AGENTS.md").read_bytes()
    launcher_1 = (tmp_path / ".codex" / "cai" / "launcher.py").read_bytes()

    assert run(env).returncode == 0
    assert (codex_home / "hooks.json").read_bytes() == hooks_1
    assert (codex_home / "AGENTS.md").read_bytes() == agents_md_1
    assert (tmp_path / ".codex" / "cai" / "launcher.py").read_bytes() == launcher_1


def test_cli_removes_stale_cai_agent_but_keeps_the_users_own(tmp_path):
    env = fake_env(tmp_path)
    codex_home = tmp_path / ".codex"
    write(codex_home, "agents/cai_no-longer-shipped.toml", "stale\n")
    write(codex_home, "agents/personal.toml", "mine\n")

    result = run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (codex_home / "agents" / "cai_no-longer-shipped.toml").exists()
    assert (codex_home / "agents" / "personal.toml").read_text(encoding="utf-8") == "mine\n"


# ---------------------------------------------------------------------------
# commandWindows -- Codex's Windows override for a hook's command
# ---------------------------------------------------------------------------

def test_our_hook_entry_carries_a_windows_override_that_surfaces_the_exit_code():
    launcher_path = Path("/home/user/.codex/cai/launcher.py")
    entry = install_codex._our_hook_entry("/usr/bin/python3", launcher_path)
    hook = entry["hooks"][0]
    assert hook["command"] == "'/usr/bin/python3' '/home/user/.codex/cai/launcher.py' guard"
    assert hook["commandWindows"] == (
        "& '/usr/bin/python3' '/home/user/.codex/cai/launcher.py' guard; exit $LASTEXITCODE")


# ---------------------------------------------------------------------------
# command -- the plain (non-Windows) hook command, run through a POSIX shell
# ---------------------------------------------------------------------------

def test_our_hook_entry_command_escapes_embedded_single_quotes():
    """Same failure mode as commandWindows, on the POSIX side: a `'` in a
    path must not end the single-quoted literal early and turn the rest of
    the line into a second, attacker- or accident-controlled shell
    command."""
    launcher_path = Path("/home/weird'user/.codex/cai/launcher.py")
    entry = install_codex._our_hook_entry("/usr/bin/py'thon3", launcher_path)
    hook = entry["hooks"][0]
    assert hook["command"] == (
        r"'/usr/bin/py'\''thon3' '/home/weird'\''user/.codex/cai/launcher.py' guard")


def test_our_hook_entry_command_does_not_expand_a_dollar_subexpression():
    """A *double*-quoted `sh` string expands `$(...)`/backtick command
    substitution inside it even with no `"` to break out of -- the plain
    `command` field must single-quote instead, so a path containing one
    can't run as a command the moment Codex hands this to a POSIX shell."""
    launcher_path = Path("/home/evil$(echo PWNED)/.codex/cai/launcher.py")
    entry = install_codex._our_hook_entry("/usr/bin/python3", launcher_path)
    hook = entry["hooks"][0]
    assert hook["command"] == (
        "'/usr/bin/python3' '/home/evil$(echo PWNED)/.codex/cai/launcher.py' guard")


def test_our_hook_entry_command_survives_a_dollar_subexpression_through_real_bash(tmp_path):
    """Proves the non-expansion above against a real POSIX shell, not just a
    string comparison: a `$(...)` in the launcher path must reach `bash -c`
    as literal text and never run, regardless of what the resulting command
    line does afterward (here, fail to find the program -- irrelevant,
    since shell expansion happens before that lookup)."""
    import shutil as _shutil
    bash = _shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on PATH")
    marker = tmp_path / "PWNED_POSIX_COMMAND"
    launcher_path = Path(f"/home/evil$(touch {marker.as_posix()})/launcher.py")
    entry = install_codex._our_hook_entry("/usr/bin/python3", launcher_path)
    command = entry["hooks"][0]["command"]
    subprocess.run([bash, "-c", command], capture_output=True, encoding="utf-8")
    assert not marker.exists(), "the $(...) subexpression ran"


def test_our_hook_entry_windows_override_escapes_embedded_single_quotes():
    """A `'` in a path (or, in principle, in sys.executable) must not let
    the single-quoted literal end early and turn the rest of the line into
    a second, attacker- or accident-controlled PowerShell statement."""
    launcher_path = Path("/home/weird'user/.codex/cai/launcher.py")
    entry = install_codex._our_hook_entry("/usr/bin/py'thon3", launcher_path)
    hook = entry["hooks"][0]
    assert hook["commandWindows"] == (
        "& '/usr/bin/py''thon3' '/home/weird''user/.codex/cai/launcher.py'"
        " guard; exit $LASTEXITCODE")


def test_our_hook_entry_windows_override_does_not_expand_a_dollar_subexpression():
    """A *double*-quoted PowerShell string expands a `$(...)` subexpression
    inside it even with no `"` to break out of -- single-quoting must pass
    a path containing one through as literal text instead, so it can't run
    as code the moment Codex hands this to `powershell.exe -Command`."""
    launcher_path = Path("/home/evil$(Write-Output PWNED)/.codex/cai/launcher.py")
    entry = install_codex._our_hook_entry("/usr/bin/python3", launcher_path)
    hook = entry["hooks"][0]
    assert hook["commandWindows"] == (
        "& '/usr/bin/python3' '/home/evil$(Write-Output PWNED)/.codex/cai/launcher.py'"
        " guard; exit $LASTEXITCODE")


@pytest.mark.skipif(platform.system() != "Windows",
                     reason="commandWindows only makes sense run through powershell.exe")
def test_ps_quote_survives_a_dollar_subexpression_through_real_powershell():
    """Proves the non-expansion above against the real interpreter, not
    just a string comparison: fed to `powershell.exe -Command`, the value
    must come back unchanged, and PWNED must never be printed."""
    value = "evil$(Write-Output PWNED)tail"
    quoted = install_codex._ps_quote(value)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", f"Write-Output {quoted}"],
        capture_output=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    # If PowerShell had expanded the subexpression, this would come back as
    # "evilPWNEDtail" -- the `$(...)` syntax itself gone, replaced by its
    # own output. Getting the literal text back, parens included, is the
    # proof nothing ran.
    assert result.stdout.strip() == value


def test_posix_quote_survives_a_dollar_subexpression_through_real_bash():
    """POSIX equivalent of the PowerShell proof above: `sh` still expands
    `$(...)` inside a double-quoted string, so single-quoting must pass a
    path containing one through as literal text and never run it."""
    import shutil as _shutil
    bash = _shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on PATH")
    value = "evil$(echo PWNED)tail"
    quoted = install_codex._posix_quote(value)
    result = subprocess.run([bash, "-c", f"echo {quoted}"],
                             capture_output=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    # If `sh` had run the command substitution, this would come back as
    # "evilPWNEDtail" -- the `$(...)` syntax itself gone, replaced by its
    # own output. Getting the literal text back, parens included, is the
    # proof nothing ran.
    assert result.stdout.strip() == value


# ---------------------------------------------------------------------------
# cai_command_line() -- the recorded interpreter + launcher path, per OS
# ---------------------------------------------------------------------------

def test_cai_command_line_windows_form():
    line = install_codex.cai_command_line(
        "C:\\Python313\\python.exe", "C:\\Users\\a\\.codex\\cai\\launcher.py", "nt")
    assert line == (
        "& { & 'C:\\Python313\\python.exe' 'C:\\Users\\a\\.codex\\cai\\launcher.py'"
        ' @args 2>&1 | ForEach-Object { "$_" }; exit $LASTEXITCODE }')


def test_cai_command_line_posix_form():
    line = install_codex.cai_command_line(
        "/usr/bin/python3", "/home/a/.codex/cai/launcher.py", "posix")
    assert line == "'/usr/bin/python3' '/home/a/.codex/cai/launcher.py'"


def test_cai_command_line_quotes_a_space_and_an_embedded_single_quote_in_the_path():
    path = "C:\\Users\\a b\\my'launcher.py"

    nt_line = install_codex.cai_command_line("python", path, "nt")
    assert nt_line == (
        "& { & 'python' 'C:\\Users\\a b\\my''launcher.py'"
        ' @args 2>&1 | ForEach-Object { "$_" }; exit $LASTEXITCODE }')

    posix_line = install_codex.cai_command_line("python", path, "posix")
    assert posix_line == "'python' 'C:\\Users\\a b\\my'\\''launcher.py'"


@pytest.mark.skipif(platform.system() != "Windows",
                     reason="commandWindows only makes sense run through powershell.exe")
def test_command_windows_runs_the_real_guard_through_powershell(tmp_path):
    """End to end: install the launcher and a real bash_guard.py into a
    faked `~/.codex` plugin cache, build the hook entry, and run its
    `commandWindows` string through the same interpreter Codex uses on
    Windows -- with a path containing a space, since that's the failure
    mode the quoting fix exists for."""
    home = tmp_path / "user name" / "home"
    codex_home = home / ".codex"
    version_dir = (codex_home / "plugins" / "cache" / "claude-all-in-one"
                    / "cai-codex" / "0.1.0")
    (version_dir / "scripts").mkdir(parents=True)
    (version_dir / ".codex-plugin").mkdir()
    (version_dir / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "cai-codex", "version": "0.1.0"}), encoding="utf-8")
    real_guard = REPO_ROOT / "plugins" / "cai-codex" / "scripts" / "bash_guard.py"
    (version_dir / "scripts" / "bash_guard.py").write_bytes(real_guard.read_bytes())

    root = REPO_ROOT / "plugins" / "cai-codex"
    launcher_dest = install_codex.install_launcher(root, home)
    entry = install_codex._our_hook_entry(sys.executable, launcher_dest)
    command_windows = entry["hooks"][0]["commandWindows"]

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CODEX_HOME"] = str(codex_home)

    def run_guard(payload: dict):
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command_windows],
            input=json.dumps(payload), capture_output=True, encoding="utf-8", env=env)

    blocked = run_guard({"tool_input": {"command": "git push --force origin main"}})
    assert blocked.returncode == 2, blocked.stdout + blocked.stderr

    allowed = run_guard({"tool_input": {"command": "git status"}})
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr


def _fake_cache_home(tmp_path):
    """A faked `$CODEX_HOME` whose plugin cache holds a copy of the real
    cai-codex tree, so `<cai-root>/scripts/launcher.py --root` can resolve
    and print it, matching resolve_cai_root()'s expected layout."""
    home = tmp_path / "user name" / "home"
    codex_home = home / ".codex"
    version_dir = (codex_home / "plugins" / "cache" / "claude-all-in-one"
                    / "cai-codex" / "0.1.0")
    version_dir.mkdir(parents=True)
    (version_dir / ".codex-plugin").mkdir()
    (version_dir / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "cai-codex", "version": "0.1.0"}), encoding="utf-8")
    (version_dir / "scripts").mkdir()
    real_launcher = REPO_ROOT / "plugins" / "cai-codex" / "scripts" / "launcher.py"
    (version_dir / "scripts" / "launcher.py").write_bytes(real_launcher.read_bytes())
    return home, codex_home, version_dir


@pytest.mark.skipif(platform.system() != "Windows",
                     reason="cai_command_line's nt form only makes sense run through powershell.exe")
def test_cai_command_line_windows_form_runs_the_real_launcher_through_powershell(tmp_path):
    home, codex_home, version_dir = _fake_cache_home(tmp_path)
    launcher_dest = install_codex.install_launcher(
        REPO_ROOT / "plugins" / "cai-codex", home)
    rendered = install_codex.cai_command_line(sys.executable, str(launcher_dest), "nt")

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CODEX_HOME"] = str(codex_home)

    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", rendered + " --root"],
        capture_output=True, encoding="utf-8", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == str(version_dir)

    # A missing script proves stdout/stderr both reach the pipeline and that
    # `exit $LASTEXITCODE` surfaces the real exit code, not PowerShell's own
    # collapsed one for the pipeline. run_script()'s `except FileNotFoundError`
    # (plugins/cai-codex/scripts/launcher.py:178-182) never fires here: the
    # interpreter itself exists, so subprocess.run() doesn't raise -- the
    # *interpreter* is the one that can't open the missing script file and
    # exits 2 with its own "can't open file ... No such file or directory"
    # on stderr (confirmed by running the launcher directly, not assumed).
    missing = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", rendered + " no-such-script-xyz"],
        capture_output=True, encoding="utf-8", env=env)
    assert missing.returncode == 2, missing.stdout + missing.stderr
    assert "no-such-script-xyz" in missing.stdout
    assert "No such file or directory" in missing.stdout


def test_cai_command_line_posix_form_runs_the_real_launcher_through_bash():
    import shutil as _shutil
    bash = _shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on PATH -- macOS itself was not exercised by this test")

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        home, codex_home, version_dir = _fake_cache_home(tmp_path)
        launcher_dest = install_codex.install_launcher(
            REPO_ROOT / "plugins" / "cai-codex", home)
        # A POSIX-style python path, as a proxy for macOS/Linux where
        # sys.executable is already forward-slashed -- this machine's own
        # sys.executable is a Windows backslash path Git Bash can't resolve
        # as a command name.
        python_posix = sys.executable.replace("\\", "/")
        line = install_codex.cai_command_line(
            python_posix, launcher_dest.as_posix(), "posix") + " --root"

        env = dict(os.environ)
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        env["CODEX_HOME"] = str(codex_home)

        result = subprocess.run([bash, "-c", line],
                                 capture_output=True, encoding="utf-8", env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.strip() == str(version_dir)


# ---------------------------------------------------------------------------
# The AGENTS.md "cai command" block install_agents_md now carries
# ---------------------------------------------------------------------------

def test_cai_command_block_wording():
    block = install_codex.cai_command_block('"python" "/x/launcher.py"')
    assert "To run a cai-codex script" in block
    assert '"python" "/x/launcher.py"' in block


def test_cli_agents_md_contains_the_cai_command_line_once_after_two_runs(tmp_path):
    env = fake_env(tmp_path)
    codex_home = tmp_path / ".codex"

    assert run(env).returncode == 0
    assert run(env).returncode == 0

    agents_md = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_md.count("To run a cai-codex script") == 1
