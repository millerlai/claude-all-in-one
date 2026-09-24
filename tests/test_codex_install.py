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
import shutil
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


def fake_cache(chome, models, fetched_at=None):
    """Writes a `models_cache.json` (C1 shape,
    `docs/design/2026-09-22-codex-model-fallback-detail.md`, "decisions.md:22")
    into `chome`, for `detect()` to read."""
    data = {"models": models}
    if fetched_at is not None:
        data["fetched_at"] = fetched_at
    return write(chome, install_codex.MODELS_CACHE_NAME, json.dumps(data))


def run(env):
    return subprocess.run([sys.executable, str(SCRIPT)],
                          capture_output=True, encoding="utf-8", env=env)


# ---------------------------------------------------------------------------
# Line rewriter -- rewrite_model_lines, fallback_effort
# ---------------------------------------------------------------------------

SHIPPED_AGENTS_DIR = REPO_ROOT / "plugins" / "cai-codex" / "agents"


@pytest.mark.parametrize("toml_path", sorted(SHIPPED_AGENTS_DIR.glob("*.toml")))
def test_rewrite_model_lines_only_changes_lines_4_and_5(toml_path):
    original = toml_path.read_bytes()
    rewritten = install_codex.rewrite_model_lines(original, "gpt-9-nova", "xhigh")

    orig_lines = original.split(b"\n")
    new_lines = rewritten.split(b"\n")
    assert len(orig_lines) == len(new_lines)
    assert new_lines[0] == orig_lines[0]  # line 1, the version stamp, untouched
    assert new_lines[3] == b'model = "gpt-9-nova"'
    assert new_lines[4] == b'model_reasoning_effort = "xhigh"'
    for i in range(len(orig_lines)):
        if i in (3, 4):
            continue
        assert new_lines[i] == orig_lines[i], f"line {i + 1} changed unexpectedly"


def test_rewrite_model_lines_crlf_input_keeps_crlf():
    real = (SHIPPED_AGENTS_DIR / "cai_explorer.toml").read_bytes()
    crlf = real.replace(b"\n", b"\r\n")

    rewritten = install_codex.rewrite_model_lines(crlf, "gpt-9-nova", "xhigh")

    assert b"\r\n" in rewritten
    assert b"\n" not in rewritten.replace(b"\r\n", b"")  # no bare \n snuck in
    lines = rewritten.split(b"\r\n")
    assert lines[0] == crlf.split(b"\r\n")[0]
    assert lines[3] == b'model = "gpt-9-nova"'
    assert lines[4] == b'model_reasoning_effort = "xhigh"'


@pytest.mark.parametrize("bad_model", [
    'has"quote', "has\nnewline", "$(echo x)", "Uppercase", "a" * 65, "gpt-5.6-sol\n",
])
def test_rewrite_model_lines_rejects_invalid_model(bad_model):
    real = (SHIPPED_AGENTS_DIR / "cai_explorer.toml").read_bytes()
    with pytest.raises(ValueError):
        install_codex.rewrite_model_lines(real, bad_model, "high")


def test_slug_re_rejects_invalid_slugs():
    for bad in ['has"quote', "has\nnewline", "$(echo x)", "Uppercase", "a" * 65]:
        assert install_codex.SLUG_RE.match(bad) is None


def test_slug_re_rejects_trailing_newline():
    """A bare `$` anchor (no `re.MULTILINE`) matches just before a string's
    final `\\n`, not only at the true end of string -- so `"gpt-5.6-sol\\n"`
    would wrongly pass a `$`-anchored pattern even though `\\n` is outside
    `[a-z0-9.-]`, and then be written as a raw newline inside a TOML basic
    string, breaking it (AC7, M4, D7)."""
    assert install_codex.SLUG_RE.match("gpt-5.6-sol\n") is None


def test_slug_re_accepts_max_length_slug():
    assert install_codex.SLUG_RE.match("a" * 64) is not None


def test_rewrite_model_lines_anchor_missing_raises():
    toml = b'# cai-codex-version: 0.1.1\nname = "x"\ndescription = "d"\n'
    with pytest.raises(install_codex.AnchorError):
        install_codex.rewrite_model_lines(toml, "gpt-9-nova", "high")


def test_rewrite_model_lines_anchor_duplicated_raises():
    toml = (
        b'# cai-codex-version: 0.1.1\n'
        b'model = "a"\n'
        b'model = "b"\n'
        b'model_reasoning_effort = "low"\n'
    )
    with pytest.raises(install_codex.AnchorError):
        install_codex.rewrite_model_lines(toml, "gpt-9-nova", "high")


def test_rewrite_model_lines_ignores_model_line_inside_developer_instructions():
    toml = (
        b'# cai-codex-version: 0.1.1\n'
        b'model = "a"\n'
        b'model_reasoning_effort = "low"\n'
        b"developer_instructions = '''\n"
        b'model = "not a real anchor, this is body text"\n'
        b"'''\n"
    )
    rewritten = install_codex.rewrite_model_lines(toml, "gpt-9-nova", "high")

    assert b'model = "gpt-9-nova"' in rewritten
    assert b'model_reasoning_effort = "high"' in rewritten
    # the body-text line, past the developer_instructions split, is untouched
    assert b'model = "not a real anchor, this is body text"' in rewritten


def test_fallback_effort_returns_own_when_offered():
    assert install_codex.fallback_effort("high", ("low", "medium", "high")) == "high"


def test_fallback_effort_falls_back_to_next_lower_when_own_missing():
    assert install_codex.fallback_effort("high", ("low", "medium")) == "medium"


def test_fallback_effort_falls_back_to_lowest_when_none_lower():
    assert install_codex.fallback_effort("low", ("medium", "high")) == "medium"


def test_fallback_effort_returns_own_when_levels_is_none():
    assert install_codex.fallback_effort("high", None) == "high"


def test_fallback_effort_returns_own_when_levels_has_no_known_names():
    assert install_codex.fallback_effort("high", ("turbo", "ultra-plus")) == "high"


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


# ---------------------------------------------------------------------------
# Detection -- detect
# Design: docs/design/2026-09-22-codex-model-fallback-detail.md, "Detection".
# ---------------------------------------------------------------------------

def test_detect_missing_file(tmp_path):
    chome = tmp_path / ".codex"
    chome.mkdir()

    d = install_codex.detect(chome)

    assert d.ok is False
    assert d.reason == f"{chome / install_codex.MODELS_CACHE_NAME} is missing"
    assert d.offered == ()
    assert d.total == 0
    assert d.ignored == 0
    assert d.fetched_at is None


def test_detect_unparsable_json(tmp_path):
    chome = tmp_path / ".codex"
    write(chome, install_codex.MODELS_CACHE_NAME, "{not json")

    d = install_codex.detect(chome)

    assert d.ok is False
    assert d.reason.startswith(f"{chome / install_codex.MODELS_CACHE_NAME} cannot be parsed:")


def test_detect_top_level_not_object(tmp_path):
    chome = tmp_path / ".codex"
    write(chome, install_codex.MODELS_CACHE_NAME, json.dumps([1, 2, 3]))

    d = install_codex.detect(chome)

    assert d.ok is False
    assert "cannot be parsed" in d.reason


def test_detect_models_not_list(tmp_path):
    chome = tmp_path / ".codex"
    write(chome, install_codex.MODELS_CACHE_NAME, json.dumps({"models": "nope"}))

    d = install_codex.detect(chome)

    assert d.ok is False
    assert "cannot be parsed" in d.reason


def test_detect_models_entry_not_object(tmp_path):
    chome = tmp_path / ".codex"
    write(chome, install_codex.MODELS_CACHE_NAME, json.dumps({"models": ["not an object"]}))

    d = install_codex.detect(chome)

    assert d.ok is False
    assert "cannot be parsed" in d.reason


def test_detect_no_offered_after_filtering(tmp_path):
    chome = tmp_path / ".codex"
    fake_cache(chome, [{"slug": "gpt-hidden", "visibility": "hide",
                         "supported_reasoning_levels": []}])

    d = install_codex.detect(chome)

    assert d.ok is False
    assert d.reason == f"{chome / install_codex.MODELS_CACHE_NAME} lists no offered models"
    assert d.total == 1
    assert d.ignored == 0


def test_detect_non_str_slug_skipped_not_counted_anywhere(tmp_path):
    chome = tmp_path / ".codex"
    fake_cache(chome, [
        {"slug": 123, "visibility": "list", "supported_reasoning_levels": []},
        {"slug": "gpt-5.6-sol", "visibility": "list", "supported_reasoning_levels": []},
    ])

    d = install_codex.detect(chome)

    assert d.ok is True
    assert d.total == 1  # the non-str-slug entry counted in neither total, offered, nor ignored
    assert d.ignored == 0
    assert d.offered == ("gpt-5.6-sol",)


def test_detect_ignored_counts_a_bad_slug(tmp_path):
    chome = tmp_path / ".codex"
    fake_cache(chome, [
        {"slug": "Bad Slug!", "visibility": "list", "supported_reasoning_levels": []},
        {"slug": "gpt-5.6-sol", "visibility": "list", "supported_reasoning_levels": []},
    ])

    d = install_codex.detect(chome)

    assert d.ok is True
    assert d.total == 2
    assert d.ignored == 1
    assert d.offered == ("gpt-5.6-sol",)


def test_detect_offered_levels_and_fetched_at(tmp_path):
    chome = tmp_path / ".codex"
    fake_cache(chome, [
        {"slug": "gpt-5.6-sol", "visibility": "list",
         "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}]},
    ], fetched_at="2026-09-22T08:13:21.014621200Z")

    d = install_codex.detect(chome)

    assert d.ok is True
    assert d.reason == ""
    assert d.offered == ("gpt-5.6-sol",)
    assert d.levels == {"gpt-5.6-sol": ("low", "high")}
    assert d.fetched_at == "2026-09-22T08:13:21.014621200Z"
    assert d.source == chome / install_codex.MODELS_CACHE_NAME


def test_detect_hidden_and_no_visibility_key_not_offered(tmp_path):
    """D5: `visibility: "hide"` and no `visibility` key at all are both NOT
    offered -- only `visibility == "list"` is."""
    chome = tmp_path / ".codex"
    fake_cache(chome, [
        {"slug": "gpt-hidden", "visibility": "hide", "supported_reasoning_levels": []},
        {"slug": "gpt-novis", "supported_reasoning_levels": []},
        {"slug": "gpt-5.6-sol", "visibility": "list", "supported_reasoning_levels": []},
    ])

    d = install_codex.detect(chome)

    assert d.ok is True
    assert d.offered == ("gpt-5.6-sol",)


# ---------------------------------------------------------------------------
# Saved choice -- load_choice, save_choice
# ---------------------------------------------------------------------------

def test_load_choice_missing_file_returns_empty(tmp_path):
    chome = tmp_path / ".codex"
    assert install_codex.load_choice(chome) == {}


def test_load_choice_invalid_json_raises(tmp_path):
    chome = tmp_path / ".codex"
    write(chome, install_codex.CHOICE_NAME, "{not json")

    with pytest.raises(install_codex.ChoiceParseError):
        install_codex.load_choice(chome)


def test_load_choice_wrong_format_raises(tmp_path):
    chome = tmp_path / ".codex"
    write(chome, install_codex.CHOICE_NAME, json.dumps({"format": 2, "roles": {}}))

    with pytest.raises(install_codex.ChoiceParseError):
        install_codex.load_choice(chome)


def test_load_choice_non_str_role_value_raises(tmp_path):
    chome = tmp_path / ".codex"
    write(chome, install_codex.CHOICE_NAME, json.dumps({"format": 1, "roles": {"build": 5}}))

    with pytest.raises(install_codex.ChoiceParseError):
        install_codex.load_choice(chome)


def test_load_choice_bad_slug_raises(tmp_path):
    chome = tmp_path / ".codex"
    write(chome, install_codex.CHOICE_NAME,
          json.dumps({"format": 1, "roles": {"build": "Uppercase Nope"}}))

    with pytest.raises(install_codex.ChoiceParseError):
        install_codex.load_choice(chome)


def test_load_choice_valid_roundtrip(tmp_path):
    chome = tmp_path / ".codex"
    write(chome, install_codex.CHOICE_NAME,
          json.dumps({"format": 1, "roles": {"build": "gpt-5.6-sol"}}))

    assert install_codex.load_choice(chome) == {"build": "gpt-5.6-sol"}


def test_save_choice_writes_lf_no_bom_and_the_sample_shape(tmp_path):
    chome = tmp_path / ".codex"

    dest = install_codex.save_choice(chome, {"build": "gpt-5.6-sol"})

    data = dest.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")  # no BOM
    assert b"\r\n" not in data  # LF only
    text = data.decode("utf-8")
    assert json.loads(text) == {"format": 1, "roles": {"build": "gpt-5.6-sol"}}
    assert text == '{\n  "format": 1,\n  "roles": {\n    "build": "gpt-5.6-sol"\n  }\n}\n'


def test_save_choice_empty_roles_writes_empty_object(tmp_path):
    chome = tmp_path / ".codex"

    dest = install_codex.save_choice(chome, {})

    assert json.loads(dest.read_text(encoding="utf-8")) == {"format": 1, "roles": {}}


# ---------------------------------------------------------------------------
# Role map -- role_agents, shipped_defaults
# ---------------------------------------------------------------------------

CAI_CODEX_ROOT = REPO_ROOT / "plugins" / "cai-codex"


def test_role_agents_matches_the_real_tree():
    agents = install_codex.role_agents(CAI_CODEX_ROOT)

    assert list(agents.keys()) == ["chore", "build", "think"]
    assert agents["chore"] == ["cai_explorer.toml", "cai_shipper.toml", "cai_test-runner.toml"]


def test_shipped_defaults_matches_the_real_tree():
    agents = install_codex.role_agents(CAI_CODEX_ROOT)

    defaults = install_codex.shipped_defaults(CAI_CODEX_ROOT, agents)

    assert defaults["chore"] == ("gpt-5.6-luna", "low")
    assert defaults["build"] == ("gpt-5.6-terra", "medium")
    assert defaults["think"] == ("gpt-6-astra", "high")


# ---------------------------------------------------------------------------
# Planner -- plan_roles, ask_directive
# ---------------------------------------------------------------------------

def _detection(ok, offered=(), levels=None, reason=""):
    return install_codex.Detection(
        ok=ok, reason=reason, source=Path("/fake/models_cache.json"),
        offered=tuple(offered), levels=levels or {}, total=len(offered),
        ignored=0, fetched_at=None)


def test_plan_roles_reask_true_when_saved_slug_missing_or_hidden():
    agents = {"build": ["cai_implementer.toml"]}
    defaults = {"build": ("gpt-5.6-terra", "medium")}
    detection = _detection(True, offered=("gpt-5.6-terra", "gpt-5.6-sol"))
    saved = {"build": "gpt-reserve"}  # not offered by this detection

    plans = install_codex.plan_roles(agents, defaults, detection, saved)

    assert plans["build"].reask is True
    assert plans["build"].in_effect == "gpt-reserve"
    assert plans["build"].offer[0] == "gpt-5.6-terra"  # cai default, offered
    assert plans["build"].effort == "medium"  # fallback_effort(own, None) == own


def test_plan_roles_offer0_is_first_offered_when_default_not_offered():
    agents = {"build": ["cai_implementer.toml"]}
    defaults = {"build": ("gpt-5.6-terra", "medium")}
    detection = _detection(True, offered=("gpt-5.6-sol", "gpt-5.6-nova"))
    saved = {"build": "gpt-reserve"}  # not offered; default also not offered

    plans = install_codex.plan_roles(agents, defaults, detection, saved)

    assert plans["build"].reask is True
    assert plans["build"].offer[0] == "gpt-5.6-sol"  # first offered, catalog order
    assert plans["build"].offer == ("gpt-5.6-sol", "gpt-5.6-nova")


def test_plan_roles_reask_false_when_saved_slug_still_offered():
    agents = {"build": ["cai_implementer.toml"]}
    defaults = {"build": ("gpt-5.6-terra", "medium")}
    detection = _detection(True, offered=("gpt-5.6-sol", "gpt-5.6-terra"))
    saved = {"build": "gpt-5.6-sol"}

    plans = install_codex.plan_roles(agents, defaults, detection, saved)

    assert plans["build"].reask is False
    assert plans["build"].in_effect == "gpt-5.6-sol"
    assert plans["build"].offer == ("gpt-5.6-sol", "gpt-5.6-terra")


def test_plan_roles_unlisted_default_only_for_unsaved_role_on_success():
    agents = {"build": ["cai_implementer.toml"], "chore": ["cai_explorer.toml"]}
    defaults = {"build": ("gpt-5.6-terra", "medium"), "chore": ("gpt-5.6-luna", "low")}
    detection = _detection(True, offered=("gpt-5.6-sol",))
    saved = {"chore": "gpt-5.6-sol"}  # chore saved; build unsaved, default unlisted

    plans = install_codex.plan_roles(agents, defaults, detection, saved)

    assert plans["build"].unlisted_default is True
    assert plans["chore"].unlisted_default is False  # saved, never marked


def test_plan_roles_unlisted_default_never_set_when_detection_failed():
    agents = {"build": ["cai_implementer.toml"]}
    defaults = {"build": ("gpt-5.6-terra", "medium")}
    detection = _detection(False, reason="boom")
    saved = {}

    plans = install_codex.plan_roles(agents, defaults, detection, saved)

    assert plans["build"].unlisted_default is False
    assert plans["build"].reask is False
    assert plans["build"].offer == ()


def test_plan_roles_drops_saved_role_not_present_in_agents():
    agents = {"build": ["cai_implementer.toml"]}
    defaults = {"build": ("gpt-5.6-terra", "medium")}
    detection = _detection(True, offered=("gpt-5.6-terra",))
    saved = {"build": "gpt-5.6-terra", "ghost-role": "gpt-5.6-sol"}

    plans = install_codex.plan_roles(agents, defaults, detection, saved)

    assert set(plans.keys()) == {"build"}


def test_ask_directive_ok_detection_is_keep_or_switch():
    detection = _detection(True, offered=("gpt-5.6-sol",))
    plans = {"build": install_codex.RolePlan(
        "build", (), "gpt-5.6-terra", "medium", "gpt-5.6-terra", False, "medium",
        False, False, ("gpt-5.6-terra",))}

    assert install_codex.ask_directive(plans, detection) == "ask: keep-or-switch"


def test_ask_directive_failed_detection_lists_unsaved_roles_in_role_order():
    detection = _detection(False, reason="boom")
    plans = {
        "chore": install_codex.RolePlan("chore", (), "m", "low", "m", True, "low",
                                         False, False, ()),
        "build": install_codex.RolePlan("build", (), "m", "medium", "m", False, "medium",
                                         False, False, ()),
        "think": install_codex.RolePlan("think", (), "m", "high", "m", False, "high",
                                         False, False, ()),
    }

    assert install_codex.ask_directive(plans, detection) == "ask: keep-or-type build think"


def test_ask_directive_failed_detection_all_saved_is_nothing():
    detection = _detection(False, reason="boom")
    plans = {
        "chore": install_codex.RolePlan("chore", (), "m", "low", "m", True, "low",
                                         False, False, ()),
        "build": install_codex.RolePlan("build", (), "m", "medium", "m", True, "medium",
                                         False, False, ()),
    }

    assert install_codex.ask_directive(plans, detection) == "ask: nothing"


# ---------------------------------------------------------------------------
# agent_bytes -- every shipped cai_*.toml name -> bytes
# ---------------------------------------------------------------------------

def _real_plans(saved, detection=None):
    agents = install_codex.role_agents(CAI_CODEX_ROOT)
    defaults = install_codex.shipped_defaults(CAI_CODEX_ROOT, agents)
    detection = detection if detection is not None else _detection(False, reason="no cache")
    return install_codex.plan_roles(agents, defaults, detection, saved)


def test_agent_bytes_unsaved_role_is_shipped_bytes():
    plans = _real_plans({})

    contents = install_codex.agent_bytes(CAI_CODEX_ROOT, plans)

    shipped = (CAI_CODEX_ROOT / "agents" / "cai_explorer.toml").read_bytes()
    assert contents["cai_explorer.toml"] == shipped


def test_agent_bytes_saved_role_is_rewritten():
    plans = _real_plans({"build": "gpt-5.6-sol"})

    contents = install_codex.agent_bytes(CAI_CODEX_ROOT, plans)

    shipped = (CAI_CODEX_ROOT / "agents" / "cai_implementer.toml").read_bytes()
    expected = install_codex.rewrite_model_lines(
        shipped, "gpt-5.6-sol", plans["build"].effort)
    assert contents["cai_implementer.toml"] == expected
    # an unsaved role's file in the same tree stays shipped
    assert contents["cai_architect.toml"] == (
        CAI_CODEX_ROOT / "agents" / "cai_architect.toml").read_bytes()


def test_agent_bytes_covers_every_shipped_toml():
    plans = _real_plans({})

    contents = install_codex.agent_bytes(CAI_CODEX_ROOT, plans)

    shipped_names = {p.name for p in CAI_CODEX_ROOT.glob("agents/cai_*.toml")}
    assert set(contents.keys()) == shipped_names


# ---------------------------------------------------------------------------
# install_agents(contents=...) -- optional override, unchanged when None
# ---------------------------------------------------------------------------

def test_install_agents_writes_given_contents(tmp_path):
    root = tmp_path / "root"
    write(root, "agents/cai_a.toml", "shipped a\n")
    write(root, "agents/cai_b.toml", "shipped b\n")
    home = tmp_path / "codex_home"

    written, removed = install_codex.install_agents(
        root, home, {"cai_a.toml": b"rewritten a\n", "cai_b.toml": b"shipped b\n"})

    assert (home / "agents" / "cai_a.toml").read_text(encoding="utf-8") == "rewritten a\n"
    assert (home / "agents" / "cai_b.toml").read_text(encoding="utf-8") == "shipped b\n"
    assert {p.name for p in written} == {"cai_a.toml", "cai_b.toml"}
    assert removed == []


# ---------------------------------------------------------------------------
# render_mapping
# ---------------------------------------------------------------------------

def _plan(role, agents, default_model, default_effort, in_effect, saved, effort,
          reask, unlisted_default, offer):
    return install_codex.RolePlan(role, agents, default_model, default_effort, in_effect,
                                   saved, effort, reask, unlisted_default, offer)


def test_render_mapping_models_line_ok_with_fetched_at():
    detection = install_codex.Detection(
        True, "", Path("/x/.codex/models_cache.json"), ("gpt-a",), {}, 3, 0,
        "2026-09-22T08:13:21.014621200Z")
    plans = {}

    lines = install_codex.render_mapping(plans, detection, Path("/x/.codex"), full=True)

    assert lines[0] == (
        f"models: detected 1 of 3 from {Path('/x/.codex/models_cache.json')} "
        "(fetched 2026-09-22T08:13:21.014621200Z)")


def test_render_mapping_models_line_ok_no_fetched_at():
    detection = install_codex.Detection(
        True, "", Path("/x/.codex/models_cache.json"), ("gpt-a",), {}, 1, 0, None)
    lines = install_codex.render_mapping({}, detection, Path("/x/.codex"), full=True)
    assert lines[0] == f"models: detected 1 of 1 from {Path('/x/.codex/models_cache.json')}"


def test_render_mapping_models_line_failed():
    detection = _detection(False, reason="boom")
    lines = install_codex.render_mapping({}, detection, Path("/x/.codex"), full=True)
    assert lines[0] == "models: detection failed: boom"


def test_render_mapping_ignored_line_only_when_positive():
    detection = install_codex.Detection(
        True, "", Path("/x"), ("gpt-a",), {}, 2, 1, None)
    lines = install_codex.render_mapping({}, detection, Path("/x/.codex"), full=True)
    assert "models: ignored 1 slug(s) outside [a-z0-9.-]" in lines

    detection2 = install_codex.Detection(
        True, "", Path("/x"), ("gpt-a",), {}, 1, 0, None)
    lines2 = install_codex.render_mapping({}, detection2, Path("/x/.codex"), full=True)
    assert not any(line.startswith("models: ignored") for line in lines2)


def test_render_mapping_full_sample_matches_design():
    # Built with `/` rather than a backslash literal: on POSIX a backslash is an
    # ordinary character, so `render_mapping`'s own `chome / name` would join
    # with `/` and never match a hard-coded Windows path.
    chome = Path("...") / ".codex"
    detection = install_codex.Detection(
        True, "", chome / "models_cache.json",
        ("gpt-5.6-luna", "gpt-5.6-sol", "gpt-6-astra", "gpt-5.6-terra", "gpt-5.5"),
        {}, 7, 0, "2026-09-22T08:13:21.014621200Z")
    plans = {
        "chore": _plan("chore", ("cai_explorer.toml", "cai_shipper.toml", "cai_test-runner.toml"),
                        "gpt-5.6-luna", "low", "gpt-5.6-luna", False, "low", False, False,
                        ("gpt-5.6-luna", "gpt-5.6-sol", "gpt-6-astra", "gpt-5.6-terra", "gpt-5.5")),
        "build": _plan("build", ("cai_implementer.toml", "cai_refactoring-detector.toml",
                                  "cai_reviewer.toml", "cai_security-reviewer.toml",
                                  "cai_verifier.toml"),
                        "gpt-5.6-terra", "medium", "gpt-reserve", True, "medium", True, False,
                        ("gpt-5.6-terra", "gpt-5.6-sol", "gpt-6-astra", "gpt-5.6-luna", "gpt-5.5")),
        "think": _plan("think", ("cai_architect.toml", "cai_designer.toml"),
                        "gpt-5.6-terra", "high", "gpt-5.6-terra", False, "high", False, False,
                        ("gpt-5.6-terra", "gpt-5.6-sol", "gpt-6-astra", "gpt-5.6-luna", "gpt-5.5")),
    }

    lines = install_codex.render_mapping(plans, detection, chome, full=True)

    assert lines == [
        f"models: detected 5 of 7 from {chome / 'models_cache.json'} "
        "(fetched 2026-09-22T08:13:21.014621200Z)",
        "role chore: gpt-5.6-luna / low (cai default) -- "
        "cai_explorer, cai_shipper, cai_test-runner",
        "role build: gpt-reserve / medium (saved; cai default gpt-5.6-terra) -- "
        "cai_implementer, cai_refactoring-detector, cai_reviewer, "
        "cai_security-reviewer, cai_verifier",
        "role think: gpt-5.6-terra / high (cai default) -- cai_architect, cai_designer",
        "offer chore: gpt-5.6-luna (in effect, cai default), gpt-5.6-sol, gpt-6-astra, "
        "gpt-5.6-terra, gpt-5.5",
        "offer build: gpt-5.6-terra (cai default), gpt-5.6-sol, gpt-6-astra, "
        "gpt-5.6-luna, gpt-5.5",
        "offer think: gpt-5.6-terra (in effect, cai default), gpt-5.6-sol, gpt-6-astra, "
        "gpt-5.6-luna, gpt-5.5",
        "ask again build: saved gpt-reserve is not offered by this detection; "
        "default answer gpt-5.6-terra",
        "ask: keep-or-switch",
        f"answers file: {chome / 'cai-model-answers.json'}",
    ]


def test_render_mapping_g1_line():
    detection = _detection(True, offered=("gpt-5.6-sol",))
    plans = {
        "think": _plan("think", ("cai_architect.toml",), "gpt-5.6-terra", "high",
                        "gpt-5.6-terra", False, "high", False, True, ("gpt-5.6-sol",)),
    }

    lines = install_codex.render_mapping(plans, detection, Path("/x/.codex"), full=True)

    assert ("not offered think: gpt-5.6-terra is in effect but this detection "
            "does not list it") in lines


def test_render_mapping_not_full_omits_offer_and_appends_applied_count():
    detection = _detection(True, offered=("gpt-5.6-sol",))
    plans = {
        "build": _plan("build", ("cai_implementer.toml",), "gpt-5.6-terra", "medium",
                        "gpt-5.6-sol", True, "medium", False, False, ("gpt-5.6-sol",)),
        "chore": _plan("chore", ("cai_explorer.toml",), "gpt-5.6-luna", "low",
                        "gpt-5.6-luna", False, "low", False, False, ("gpt-5.6-luna",)),
    }

    lines = install_codex.render_mapping(plans, detection, Path("/x/.codex"), full=False)

    assert not any(line.startswith("offer ") for line in lines)
    assert not any(line.startswith("ask:") for line in lines)
    assert not any(line.startswith("answers file:") for line in lines)
    assert lines[-1] == "applied: 1 role(s) saved"


# ---------------------------------------------------------------------------
# CLI, run 1 -- AC1, AC3, AC6, decision 5, decision 13
# ---------------------------------------------------------------------------

def test_cli_run1_no_saved_roles_leaves_toml_shipped_bytes_and_asks_keep_or_switch(tmp_path):
    """AC1 / UC1 / M2."""
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    fake_cache(chome, [
        {"slug": "gpt-5.6-luna", "visibility": "list", "supported_reasoning_levels": []},
        {"slug": "gpt-5.6-terra", "visibility": "list", "supported_reasoning_levels": []},
    ])

    result = run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    real_agents = sorted((REPO_ROOT / "plugins" / "cai-codex" / "agents").glob("cai_*.toml"))
    for p in real_agents:
        assert (chome / "agents" / p.name).read_bytes() == p.read_bytes()
    assert "ask: keep-or-switch" in result.stdout


def test_cli_ac3_saved_role_rewritten_from_a_copied_and_updated_tree(tmp_path):
    """AC3 / UC3: run against a copied `<cai-root>` whose shipped TOMLs were
    just "updated" (a new stamp), with `build` saved from before the update."""
    copy_root = tmp_path / "cai-codex-copy"
    shutil.copytree(REPO_ROOT / "plugins" / "cai-codex", copy_root)
    new_stamp = b"# cai-codex-version: 9.9.9"
    for p in (copy_root / "agents").glob("cai_*.toml"):
        data = p.read_bytes()
        first_nl = data.index(b"\n")
        p.write_bytes(new_stamp + data[first_nl:])

    home = tmp_path / "home"
    chome = home / ".codex"
    fake_cache(chome, [
        {"slug": "gpt-5.6-sol", "visibility": "list", "supported_reasoning_levels": []},
        {"slug": "gpt-5.6-terra", "visibility": "list", "supported_reasoning_levels": []},
    ])
    write(chome, install_codex.CHOICE_NAME,
          json.dumps({"format": 1, "roles": {"build": "gpt-5.6-sol"}}))

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CODEX_HOME"] = str(chome)
    result = subprocess.run(
        [sys.executable, str(copy_root / "scripts" / "install_codex.py")],
        capture_output=True, encoding="utf-8", env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    build_toml = (chome / "agents" / "cai_implementer.toml").read_bytes()
    lines = build_toml.split(b"\n")
    assert lines[0] == b"# cai-codex-version: 9.9.9"
    assert lines[3] == b'model = "gpt-5.6-sol"'
    assert "saved; cai default" in result.stdout


def test_cli_ac6_no_cache_build_saved_asks_keep_or_type_unsaved_roles(tmp_path):
    """AC6 / UC5: no cache present, `build` saved -- build's saved slug
    installs unchanged and the ask directive lists only unsaved roles."""
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    write(chome, install_codex.CHOICE_NAME,
          json.dumps({"format": 1, "roles": {"build": "gpt-5.6-sol"}}))

    result = run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    shipped = (REPO_ROOT / "plugins" / "cai-codex" / "agents"
               / "cai_implementer.toml").read_bytes()
    expected = install_codex.rewrite_model_lines(shipped, "gpt-5.6-sol", "medium")
    assert (chome / "agents" / "cai_implementer.toml").read_bytes() == expected
    assert "ask: keep-or-type chore think" in result.stdout


def test_cli_ac6_every_role_saved_no_cache_asks_nothing(tmp_path):
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    write(chome, install_codex.CHOICE_NAME, json.dumps({"format": 1, "roles": {
        "chore": "gpt-5.6-luna", "build": "gpt-5.6-terra", "think": "gpt-5.6-terra"}}))

    result = run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ask: nothing" in result.stdout


def test_cli_invalid_saved_choice_exits_1_before_any_write(tmp_path):
    """Decision 5."""
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    write(chome, install_codex.CHOICE_NAME, "{not json")

    assert not (tmp_path / ".codex" / "cai" / "launcher.py").is_file()

    result = run(env)

    assert result.returncode == 1
    assert not (tmp_path / ".codex" / "cai" / "launcher.py").is_file()
    assert not list((chome / "agents").glob("cai_*.toml")) if (chome / "agents").is_dir() else True
    assert "invalid saved model choice, not overwritten" in result.stdout


def test_cli_removes_stale_answers_file(tmp_path):
    """Decision 13."""
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    stale = write(chome, "cai-model-answers.json", json.dumps({"format": 1, "roles": {}}))

    result = run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not stale.exists()
    assert f"removed stale {stale}" in result.stdout


@pytest.mark.skipif(platform.system() != "Windows",
                     reason="POSIX permits unlinking an open file; only Windows locks it")
def test_cli_stale_answers_file_locked_reports_instead_of_crashing(tmp_path):
    """`apply_answers`'s own end-of-run cleanup of this same file is wrapped
    in `try/except OSError` (`:784-789`), but run 1's stale-file removal
    was not -- a routine Windows file lock (open elsewhere, an antivirus
    scan) on an abandoned setup's leftover answers file used to crash the
    whole install with an unhandled exception instead of the module's own
    documented exit-code contract ("1 a write failed ... with the failing
    path printed")."""
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    stale = write(chome, install_codex.ANSWERS_NAME, json.dumps({"format": 1, "roles": {}}))

    fh = open(stale, "r")
    try:
        # errors="replace": the locked-file OSError's message is localized by
        # Windows into the console's own codepage, not necessarily UTF-8 --
        # unrelated to what this test checks, so decode leniently rather than
        # letting an unrelated UnicodeDecodeError mask the real assertion.
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True,
                                 encoding="utf-8", errors="replace", env=env)
    finally:
        fh.close()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "could not remove stale" in result.stdout
    # the rest of the install still completed despite the locked leftover file
    real_agents = sorted((REPO_ROOT / "plugins" / "cai-codex" / "agents").glob("cai_*.toml"))
    for p in real_agents:
        assert (chome / "agents" / p.name).read_bytes() == p.read_bytes()


def run_apply(env):
    return subprocess.run([sys.executable, str(SCRIPT), "--apply"],
                          capture_output=True, encoding="utf-8", env=env)


def run_models(env):
    return subprocess.run([sys.executable, str(SCRIPT), "--models"],
                          capture_output=True, encoding="utf-8", env=env)


def test_cli_models_prints_the_mapping_block_and_writes_nothing(tmp_path):
    """`$models` changes the mapping without a reinstall, so `--models` prints
    run 1's mapping block and touches nothing: no launcher, no agents, no
    hooks.json, no AGENTS.md."""
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    fake_cache(chome, [
        {"slug": "gpt-5.6-luna", "visibility": "list", "supported_reasoning_levels": []},
        {"slug": "gpt-5.6-terra", "visibility": "list", "supported_reasoning_levels": []},
        {"slug": "gpt-6-astra", "visibility": "list", "supported_reasoning_levels": []},
    ])
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))

    result = run_models(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before
    lines = result.stdout.splitlines()
    for prefix in ("models: detected 3 of 3", "role chore:", "role build:", "role think:",
                   "offer think:", "ask: keep-or-switch", "answers file:"):
        assert any(line.startswith(prefix) for line in lines), prefix


def test_cli_models_shows_a_saved_role_as_saved(tmp_path):
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    fake_cache(chome, [
        {"slug": "gpt-5.6-sol", "visibility": "list", "supported_reasoning_levels": []},
    ])
    write(chome, install_codex.CHOICE_NAME,
          json.dumps({"format": 1, "roles": {"build": "gpt-5.6-sol"}}))

    result = run_models(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "role build: gpt-5.6-sol / medium (saved; cai default gpt-5.6-terra)" in result.stdout


def test_cli_models_invalid_saved_choice_exits_1(tmp_path):
    env = fake_env(tmp_path)
    write(tmp_path / ".codex", install_codex.CHOICE_NAME, "{not json")

    result = run_models(env)

    assert result.returncode == 1
    assert "invalid saved model choice, not overwritten" in result.stdout


def test_cli_models_and_apply_together_is_a_usage_error(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), "--models", "--apply"],
                            capture_output=True, encoding="utf-8", env=fake_env(tmp_path))

    assert result.returncode == 2


def test_cli_apply_no_answers_file_exits_1(tmp_path):
    env = fake_env(tmp_path)
    assert run(env).returncode == 0

    result = run_apply(env)

    assert result.returncode == 1
    assert "answers not applied:" in result.stdout
    assert "is missing" in result.stdout


def test_cli_apply_answers_malformed_json_exits_1(tmp_path):
    """`read_answers`'s malformed-JSON branch (`install_codex.py:497-507`)
    had no CLI test -- stance.md's "Optimises for" commits every rule about
    what gets written to a `tests/test_codex_install.py` case."""
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    assert run(env).returncode == 0

    write(chome, install_codex.ANSWERS_NAME, "{not json")

    result = run_apply(env)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "answers not applied:" in result.stdout
    assert "cannot be parsed" in result.stdout
    assert not (chome / install_codex.CHOICE_NAME).exists()


def test_cli_apply_answers_unknown_role_exits_1(tmp_path):
    """`read_answers`'s unknown-role branch (`install_codex.py:511-512`) had
    no CLI test."""
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    assert run(env).returncode == 0

    write(chome, install_codex.ANSWERS_NAME,
          json.dumps({"format": 1, "roles": {"no-such-role": "gpt-5.6-sol"}}))

    result = run_apply(env)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "answers not applied:" in result.stdout
    assert "unknown role" in result.stdout
    assert not (chome / install_codex.CHOICE_NAME).exists()


def test_cli_apply_invalid_saved_choice_exits_1_before_any_write(tmp_path):
    """`apply_answers`'s own `load_choice`/`ChoiceParseError` handling
    (`install_codex.py:733-738`) mirrors run 1's (already covered by
    `test_cli_invalid_saved_choice_exits_1_before_any_write`), but had no
    test of its own on the `--apply` path."""
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    assert run(env).returncode == 0  # run 1, valid install

    write(chome, install_codex.CHOICE_NAME, "{not json")
    write(chome, install_codex.ANSWERS_NAME,
          json.dumps({"format": 1, "roles": {"build": "gpt-5.6-sol"}}))

    result = run_apply(env)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "invalid saved model choice, not overwritten" in result.stdout
    agents = install_codex.role_agents(CAI_CODEX_ROOT)
    for name in agents["build"]:
        shipped = (CAI_CODEX_ROOT / "agents" / name).read_bytes()
        assert (chome / "agents" / name).read_bytes() == shipped


def test_cli_apply_merges_answers_and_removes_answers_file(tmp_path):
    """AC2/UC2/D6: an answer equal to the role's cai default is not saved,
    while a different answer is saved and rewrites that role's TOMLs."""
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    assert run(env).returncode == 0  # run 1, no cache yet -- shipped bytes

    chore_default = install_codex.shipped_defaults(
        CAI_CODEX_ROOT, install_codex.role_agents(CAI_CODEX_ROOT))["chore"][0]
    write(chome, install_codex.ANSWERS_NAME, json.dumps({
        "format": 1,
        "roles": {"build": "gpt-5.6-sol", "chore": chore_default},
    }))

    result = run_apply(env)

    assert result.returncode == 0, result.stdout + result.stderr
    agents = install_codex.role_agents(CAI_CODEX_ROOT)
    for name in agents["build"]:
        rewritten = (chome / "agents" / name).read_bytes()
        assert rewritten.split(b"\n")[3] == b'model = "gpt-5.6-sol"'
    for name in agents["chore"]:
        shipped = (CAI_CODEX_ROOT / "agents" / name).read_bytes()
        assert (chome / "agents" / name).read_bytes() == shipped

    choice = json.loads((chome / install_codex.CHOICE_NAME).read_text(encoding="utf-8"))
    assert choice["roles"] == {"build": "gpt-5.6-sol"}
    assert not (chome / install_codex.ANSWERS_NAME).exists()


@pytest.mark.parametrize("bad_value_label,bad_value", [
    ("embedded_quote", 'x"y'),
    ("embedded_newline", 'has\nmodel = "z"'),
    ("trailing_newline", "gpt-5.6-sol\n"),
    ("dollar_subexpression", None),  # filled per-test with a real marker path
])
def test_cli_apply_ac7_rejects_shell_hostile_answers(tmp_path, bad_value_label, bad_value):
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    assert run(env).returncode == 0  # run 1, no cache yet -- shipped bytes

    marker = tmp_path / "PWNED_APPLY_ANSWERS"
    if bad_value_label == "dollar_subexpression":
        bad_value = f"$(touch {marker.as_posix()})"

    write(chome, install_codex.ANSWERS_NAME,
          json.dumps({"format": 1, "roles": {"build": bad_value}}))

    result = run_apply(env)

    assert result.returncode == 1, result.stdout + result.stderr
    assert not (chome / install_codex.CHOICE_NAME).exists()
    agents = install_codex.role_agents(CAI_CODEX_ROOT)
    for name in agents["build"]:
        shipped = (CAI_CODEX_ROOT / "agents" / name).read_bytes()
        assert (chome / "agents" / name).read_bytes() == shipped
    if bad_value_label == "dollar_subexpression":
        assert not marker.exists(), "the $(...) subexpression ran"


def test_cli_apply_m1_answer_not_offered_by_detection_is_rejected(tmp_path):
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    fake_cache(chome, [
        {"slug": "gpt-5.6-terra", "visibility": "list", "supported_reasoning_levels": []},
        {"slug": "gpt-5.6-luna", "visibility": "list", "supported_reasoning_levels": []},
    ])
    assert run(env).returncode == 0  # run 1, with cache -- detection.ok True

    write(chome, install_codex.ANSWERS_NAME,
          json.dumps({"format": 1, "roles": {"build": "gpt-9-unoffered"}}))

    result = run_apply(env)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "is not offered by this detection; run $models to pick one it offers" in result.stdout
    assert not (chome / install_codex.CHOICE_NAME).exists()
    agents = install_codex.role_agents(CAI_CODEX_ROOT)
    for name in agents["build"]:
        shipped = (CAI_CODEX_ROOT / "agents" / name).read_bytes()
        assert (chome / "agents" / name).read_bytes() == shipped


def test_cli_apply_m1_no_detection_accepts_typed_slug_with_own_effort(tmp_path):
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    assert run(env).returncode == 0  # run 1, no cache -- detection.ok False

    write(chome, install_codex.ANSWERS_NAME,
          json.dumps({"format": 1, "roles": {"build": "gpt-9-custom"}}))

    result = run_apply(env)

    assert result.returncode == 0, result.stdout + result.stderr
    build_default_effort = install_codex.shipped_defaults(
        CAI_CODEX_ROOT, install_codex.role_agents(CAI_CODEX_ROOT))["build"][1]
    agents = install_codex.role_agents(CAI_CODEX_ROOT)
    for name in agents["build"]:
        rewritten = (chome / "agents" / name).read_bytes()
        lines = rewritten.split(b"\n")
        assert lines[3] == b'model = "gpt-9-custom"'
        assert lines[4] == f'model_reasoning_effort = "{build_default_effort}"'.encode()


@pytest.mark.skipif(
    platform.system() == "Windows" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod-based unwritable-dir test only works as non-root on POSIX")
def test_cli_apply_partial_failure_keeps_answers_file_then_succeeds_on_retry(tmp_path):
    env = fake_env(tmp_path)
    chome = tmp_path / ".codex"
    assert run(env).returncode == 0  # run 1, creates chome/agents

    write(chome, install_codex.ANSWERS_NAME,
          json.dumps({"format": 1, "roles": {"build": "gpt-5.6-sol"}}))

    os.chmod(chome / "agents", 0o555)
    try:
        result = run_apply(env)

        assert result.returncode == 1, result.stdout + result.stderr
        assert "write failed:" in result.stdout
        assert "re-run $setup to finish" in result.stdout
        choice = json.loads((chome / install_codex.CHOICE_NAME).read_text(encoding="utf-8"))
        assert choice["roles"] == {"build": "gpt-5.6-sol"}
        assert (chome / install_codex.ANSWERS_NAME).exists()
    finally:
        os.chmod(chome / "agents", 0o755)

    retry = run_apply(env)

    assert retry.returncode == 0, retry.stdout + retry.stderr
    agents = install_codex.role_agents(CAI_CODEX_ROOT)
    for name in agents["build"]:
        rewritten = (chome / "agents" / name).read_bytes()
        assert rewritten.split(b"\n")[3] == b'model = "gpt-5.6-sol"'


def test_cli_unknown_argument_exits_2(tmp_path):
    env = fake_env(tmp_path)
    result = subprocess.run([sys.executable, str(SCRIPT), "--bogus"],
                             capture_output=True, encoding="utf-8", env=env)
    assert result.returncode == 2
