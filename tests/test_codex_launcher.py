"""launcher.py -- the fixed-path Codex entry point installed at
$HOME/.codex/cai/launcher.py (D1=C).

Design: docs/design/2026-09-18-codex-support-detail.md, "### launcher.py".
U4 owns: version resolution, `--root`, the stamp check, and the guard
adapter. Every test fakes `$CODEX_HOME` in `tmp_path` rather than touching a
real `~/.codex` -- per the "never let a test write the real tree" rule this
repo already follows for gen-codex.py.

The module file is `launcher.py`, loaded through `importlib` so its
functions are testable directly, matching test_gen_codex.py's pattern.
"""
import base64
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "plugins" / "cai-codex" / "scripts" / "launcher.py"
REAL_GUARD = REPO_ROOT / "plugins" / "cai-codex" / "scripts" / "bash_guard.py"

# SCRIPT lives inside the generated Codex tree gen-codex.py's --check compares
# byte for byte; a stray __pycache__/*.pyc written there by this import would
# read back as drift (validate.py "plugins/cai-codex matches gen-codex.py").
sys.dont_write_bytecode = True

_spec = importlib.util.spec_from_file_location("codex_launcher", SCRIPT)
launcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(launcher)


def make_version_dir(cache_dir, version, marketplace="claude-all-in-one"):
    """A `plugins/cache/<marketplace>/cai-codex/<version>/` dir with a
    `.codex-plugin/plugin.json` and a `scripts/` dir, mirroring the layout
    E1 observed."""
    version_dir = cache_dir / marketplace / "cai-codex" / version
    (version_dir / "scripts").mkdir(parents=True)
    (version_dir / ".codex-plugin").mkdir()
    (version_dir / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "cai-codex", "version": version}), encoding="utf-8")
    return version_dir


def stamp_agents(codex_home, version, name="cai_verifier"):
    agents_dir = codex_home / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.toml").write_text(
        f"# cai-codex-version: {version}\nname = \"{name}\"\n", encoding="utf-8")


def run(argv, stdin_text="", env=None, cwd=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        input=stdin_text, capture_output=True, encoding="utf-8", env=env, cwd=cwd)


# ---------------------------------------------------------------------------
# Resolution: highest version, --root, exit 4 with no cache
# ---------------------------------------------------------------------------

def test_resolve_picks_the_highest_version(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    make_version_dir(tmp_path / "plugins" / "cache", "0.1.0")
    high = make_version_dir(tmp_path / "plugins" / "cache", "0.2.0")
    assert launcher.resolve_cai_root() == high


def test_root_flag_prints_the_resolved_root(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    make_version_dir(tmp_path / "plugins" / "cache", "0.1.0")
    high = make_version_dir(tmp_path / "plugins" / "cache", "0.2.0")
    result = run(["--root"], env={**_env_without_codex_home(), "CODEX_HOME": str(tmp_path)})
    assert result.returncode == 0
    assert result.stdout.strip() == str(high)


def test_no_cache_exits_4(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert launcher.resolve_cai_root() is None
    result = run(["--root"], env={**_env_without_codex_home(), "CODEX_HOME": str(tmp_path)})
    assert result.returncode == 4
    assert "not installed" in result.stderr


def _env_without_codex_home():
    import os
    return dict(os.environ)


# ---------------------------------------------------------------------------
# Stamp check
# ---------------------------------------------------------------------------

def test_stamp_mismatch_exits_3(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    make_version_dir(tmp_path / "plugins" / "cache", "0.2.0")
    stamp_agents(tmp_path, "0.1.0")
    result = run(["preflight"], env={**_env_without_codex_home(), "CODEX_HOME": str(tmp_path)})
    assert result.returncode == 3
    assert "0.1.0" in result.stderr and "0.2.0" in result.stderr


def test_matching_stamp_runs_the_script(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    root = make_version_dir(tmp_path / "plugins" / "cache", "0.2.0")
    stamp_agents(tmp_path, "0.2.0")
    (root / "scripts" / "hello.py").write_text(
        "import sys\nsys.exit(42)\n", encoding="utf-8")
    result = run(["hello"], env={**_env_without_codex_home(), "CODEX_HOME": str(tmp_path)})
    assert result.returncode == 42


def test_run_script_declares_the_cwd_a_safe_directory(tmp_path, monkeypatch):
    """Codex's elevated Windows sandbox runs commands as a different user
    than the repo's owner, so a script's own `git` calls fail with "dubious
    ownership" -- run_script must add exactly one GIT_CONFIG_* pair naming
    the launcher's own cwd as safe.directory."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    root = make_version_dir(tmp_path / "plugins" / "cache", "0.2.0")
    stamp_agents(tmp_path, "0.2.0")
    (root / "scripts" / "printenv.py").write_text(
        "import json, os\n"
        "c = int(os.environ[\"GIT_CONFIG_COUNT\"])\n"
        "print(json.dumps({\n"
        "    \"count\": c,\n"
        "    \"key\": os.environ.get(f\"GIT_CONFIG_KEY_{c - 1}\"),\n"
        "    \"value\": os.environ.get(f\"GIT_CONFIG_VALUE_{c - 1}\"),\n"
        "}))\n",
        encoding="utf-8")
    cwd = tmp_path / "workdir"
    cwd.mkdir()
    result = run(["printenv"], env={**_env_without_codex_home(), "CODEX_HOME": str(tmp_path)},
                 cwd=cwd)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["key"] == "safe.directory"
    assert payload["value"] == cwd.as_posix()


def test_run_script_appends_after_existing_git_config_pairs(tmp_path, monkeypatch):
    """An environment that already carries GIT_CONFIG_* pairs (e.g. from an
    outer git invocation) must keep them -- the launcher's own pair is
    appended at the next index, not clobbering index 0."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    root = make_version_dir(tmp_path / "plugins" / "cache", "0.2.0")
    stamp_agents(tmp_path, "0.2.0")
    (root / "scripts" / "printenv.py").write_text(
        "import json, os\n"
        "c = int(os.environ[\"GIT_CONFIG_COUNT\"])\n"
        "print(json.dumps({\n"
        "    \"count\": c,\n"
        "    \"key0\": os.environ.get(\"GIT_CONFIG_KEY_0\"),\n"
        "    \"value0\": os.environ.get(\"GIT_CONFIG_VALUE_0\"),\n"
        "    \"key1\": os.environ.get(\"GIT_CONFIG_KEY_1\"),\n"
        "    \"value1\": os.environ.get(\"GIT_CONFIG_VALUE_1\"),\n"
        "}))\n",
        encoding="utf-8")
    cwd = tmp_path / "workdir"
    cwd.mkdir()
    env = {
        **_env_without_codex_home(), "CODEX_HOME": str(tmp_path),
        "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "foo.bar", "GIT_CONFIG_VALUE_0": "baz",
    }
    result = run(["printenv"], env=env, cwd=cwd)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["count"] == 2
    assert payload["key0"] == "foo.bar"
    assert payload["value0"] == "baz"
    assert payload["key1"] == "safe.directory"
    assert payload["value1"] == cwd.as_posix()


def test_run_script_git_config_env_works_against_real_git(tmp_path, monkeypatch):
    """Proves the GIT_CONFIG_* mechanism itself works against a real `git`
    binary -- this cannot reproduce the actual Windows "dubious ownership"
    mismatch (that needs the sandbox's user/owner split), only that a real
    git sees the safe.directory value the launcher sets."""
    git = shutil.which("git")
    if git is None:
        pytest.skip("no git on PATH")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    root = make_version_dir(tmp_path / "plugins" / "cache", "0.2.0")
    stamp_agents(tmp_path, "0.2.0")
    (root / "scripts" / "gitcheck.py").write_text(
        "import subprocess\n"
        "result = subprocess.run([\"git\", \"config\", \"--get-all\", \"safe.directory\"],\n"
        "                        capture_output=True, encoding=\"utf-8\")\n"
        "print(result.stdout, end=\"\")\n",
        encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run([git, "init"], cwd=repo, capture_output=True, encoding="utf-8")
    env = {
        **_env_without_codex_home(), "CODEX_HOME": str(tmp_path),
        # Isolate from the real user's global/system gitconfig (never touch
        # the real home directory in a test) -- both files are left absent
        # on purpose, so only the launcher's own GIT_CONFIG_* pair applies.
        "GIT_CONFIG_GLOBAL": str(tmp_path / "no-such-gitconfig"),
        "GIT_CONFIG_SYSTEM": str(tmp_path / "no-such-systemconfig"),
    }
    result = run(["gitcheck"], env=env, cwd=repo)
    assert result.returncode == 0, result.stderr
    assert repo.as_posix() in result.stdout


def test_root_and_guard_are_not_given_the_child_env(tmp_path, monkeypatch):
    """--root never runs git. guard here gets an unparsable payload, which
    short-circuits before any subprocess call (bash_guard.py never even
    starts) -- see test_guard_declares_the_payload_cwd_a_safe_directory for
    a valid payload, where guard's own git-dependent checks do need (and
    now get) a safe.directory override. Both must keep working from an
    environment with no GIT_CONFIG_* pairs at all."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    make_version_dir(tmp_path / "plugins" / "cache", "0.1.0")
    env = {k: v for k, v in _env_without_codex_home().items() if not k.startswith("GIT_CONFIG_")}
    env["CODEX_HOME"] = str(tmp_path)
    result = run(["--root"], env=env)
    assert result.returncode == 0
    result = run(["guard"], stdin_text="not json", env=env)
    assert result.returncode == 0


def test_root_and_guard_skip_the_stamp_check(tmp_path, monkeypatch):
    """A mismatch must not block --root or guard (contract: neither is a
    documented Codex hook outcome, and the guard stays fail-open)."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    root = make_version_dir(tmp_path / "plugins" / "cache", "0.2.0")
    stamp_agents(tmp_path, "0.1.0")
    result = run(["--root"], env={**_env_without_codex_home(), "CODEX_HOME": str(tmp_path)})
    assert result.returncode == 0
    assert result.stdout.strip() == str(root)


# ---------------------------------------------------------------------------
# Guard adapter
# ---------------------------------------------------------------------------

def test_adapt_command_string_passes_through():
    assert launcher._adapt_command("git status") == "git status"


def test_adapt_command_plain_list_is_joined():
    assert launcher._adapt_command(["git", "status", "-s"]) == "git status -s"


def test_adapt_command_powershell_dash_c_unwraps():
    assert launcher._adapt_command(["pwsh", "-Command", "git status"]) == "git status"


def test_adapt_command_bash_dash_c_unwraps():
    assert launcher._adapt_command(["bash", "-c", "git status"]) == "git status"


def test_adapt_payload_sets_tool_name(monkeypatch):
    monkeypatch.setattr(launcher.os, "name", "nt")
    adapted = launcher._adapt_payload({"tool_input": {"command": "git status"}})
    assert adapted["tool_name"] == "PowerShell"
    monkeypatch.setattr(launcher.os, "name", "posix")
    adapted = launcher._adapt_payload({"tool_input": {"command": "git status"}})
    assert adapted["tool_name"] == "Bash"


def test_adapt_payload_missing_command_passes_through():
    adapted = launcher._adapt_payload({"cwd": "/repo"})
    assert "tool_input" not in adapted
    assert adapted["cwd"] == "/repo"


def test_guard_unparsable_payload_fails_open(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    make_version_dir(tmp_path / "plugins" / "cache", "0.1.0")
    result = run(["guard"], stdin_text="not json",
                 env={**_env_without_codex_home(), "CODEX_HOME": str(tmp_path)})
    assert result.returncode == 0


def test_guard_end_to_end_blocks_force_push(tmp_path, monkeypatch):
    """The real bash_guard.py, invoked through the adapter, on a Codex-shaped
    payload -- the documented shape is UNVERIFIED (C9)."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    root = make_version_dir(tmp_path / "plugins" / "cache", "0.1.0")
    (root / "scripts" / "bash_guard.py").write_bytes(REAL_GUARD.read_bytes())
    payload = json.dumps({"tool_input": {"command": "git push --force origin main"}})
    result = run(["guard"], stdin_text=payload,
                 env={**_env_without_codex_home(), "CODEX_HOME": str(tmp_path)})
    assert result.returncode == 2


def test_guard_end_to_end_allows_plain_status(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    root = make_version_dir(tmp_path / "plugins" / "cache", "0.1.0")
    (root / "scripts" / "bash_guard.py").write_bytes(REAL_GUARD.read_bytes())
    payload = json.dumps({"tool_input": {"command": "git status"}})
    result = run(["guard"], stdin_text=payload,
                 env={**_env_without_codex_home(), "CODEX_HOME": str(tmp_path)})
    assert result.returncode == 0


def test_guard_declares_the_payload_cwd_a_safe_directory(tmp_path, monkeypatch):
    """bash_guard.py's own git() calls (current_branch()/worktree_dirty(),
    used to block a protected-branch commit or a dirty-tree discard) run in
    the payload's own `cwd` (bash_guard.py:198), not the launcher's --
    Codex's elevated Windows sandbox makes an ungranted directory's git
    calls fail with "dubious ownership", which both of those checks treat
    as "can't tell" and fail open (allow). run_guard must give bash_guard.py
    the same safe.directory override run_script gives a dispatched script,
    scoped to the payload's cwd."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    root = make_version_dir(tmp_path / "plugins" / "cache", "0.1.0")
    (root / "scripts" / "bash_guard.py").write_text(
        "import json, os\n"
        "c = int(os.environ.get('GIT_CONFIG_COUNT', '0'))\n"
        "print(json.dumps({\n"
        "    'count': c,\n"
        "    'key': os.environ.get(f'GIT_CONFIG_KEY_{c - 1}') if c else None,\n"
        "    'value': os.environ.get(f'GIT_CONFIG_VALUE_{c - 1}') if c else None,\n"
        "}))\n",
        encoding="utf-8")
    target_cwd = (tmp_path / "workdir").as_posix()
    payload = json.dumps({"tool_input": {"command": "git status"}, "cwd": target_cwd})
    result = run(["guard"], stdin_text=payload,
                 env={**_env_without_codex_home(), "CODEX_HOME": str(tmp_path)})
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["count"] == 1
    assert out["key"] == "safe.directory"
    assert out["value"] == target_cwd


def test_adapt_payload_tool_name_follows_the_command_program_not_the_host_os(monkeypatch):
    """A POSIX host running Codex through cross-platform `pwsh` must still
    get PowerShell's rule set, and a Windows host running real Bash (Git
    Bash/WSL) must still get Bash's -- the program named in command[0] is
    known, so guessing from os.name is only a fallback for a bare string."""
    monkeypatch.setattr(launcher.os, "name", "posix")
    adapted = launcher._adapt_payload(
        {"tool_input": {"command": ["pwsh", "-Command", "Remove-Item -Recurse -Force ./build"]}})
    assert adapted["tool_name"] == "PowerShell"

    monkeypatch.setattr(launcher.os, "name", "nt")
    adapted = launcher._adapt_payload({"tool_input": {"command": ["bash", "-c", "git status"]}})
    assert adapted["tool_name"] == "Bash"


def test_adapt_command_powershell_encoded_command_decodes():
    """`-EncodedCommand` carries a base64, UTF-16LE script instead of literal
    text -- decode it so bash_guard.py's regexes see the real command
    instead of an opaque token they can never match."""
    script = "Remove-Item -Recurse -Force ./build"
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    assert launcher._adapt_command(["powershell.exe", "-EncodedCommand", encoded]) == script


def test_guard_end_to_end_blocks_a_force_push_hidden_in_encoded_command(tmp_path, monkeypatch):
    """Without decoding, `git push --force origin main` reaches bash_guard.py
    as an opaque base64 token and is silently allowed."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    root = make_version_dir(tmp_path / "plugins" / "cache", "0.1.0")
    (root / "scripts" / "bash_guard.py").write_bytes(REAL_GUARD.read_bytes())
    encoded = base64.b64encode(
        "git push --force origin main".encode("utf-16-le")).decode("ascii")
    payload = json.dumps(
        {"tool_input": {"command": ["powershell.exe", "-EncodedCommand", encoded]}})
    result = run(["guard"], stdin_text=payload,
                 env={**_env_without_codex_home(), "CODEX_HOME": str(tmp_path)})
    assert result.returncode == 2
