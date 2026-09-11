"""install_statusline.py — the half of issue #75 that touches a real user's
global configuration.

`~/.claude/settings.json` holds their permissions, enabled plugins and
marketplaces. Everything asserted here is a way that file can be damaged or a
way the installed status line can fail silently, which are the two outcomes
nobody reports as a bug because neither looks like one:

- a rewrite that drops keys, or mangles a non-ASCII value (this repo's
  CLAUDE.md already records what PowerShell redirection does to UTF-8, and a
  `json.dump` without `ensure_ascii=False` does the readable version of the
  same damage)
- a `statusLine.command` that the shell cannot run, which shows as a blank bar
- clobbering a status line the user set up themselves

Run as a subprocess rather than by importing `main()`: the exit code is the
contract `/cai:setup` reads to decide whether to ask before overwriting.
"""
import json
import os
import subprocess
import sys

import install_statusline

SCRIPT = install_statusline.__file__
SHIPPED = install_statusline.SOURCE

# A settings file shaped like a real one: keys the installer must not touch,
# and a value outside ASCII that a careless write turns into "繁...".
EXISTING = {
    "model": "opus[1m]",
    "language": "繁體中文",
    "permissions": {"allow": ["WebSearch"]},
    "enabledPlugins": {"cai@claude-all-in-one": True},
}


def run(claude_dir, *args):
    return subprocess.run([sys.executable, SCRIPT, "--claude-dir", str(claude_dir), *args],
                          capture_output=True, text=True)


def settings_of(claude_dir):
    return json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))


def seed(claude_dir, settings):
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "settings.json").write_text(
        json.dumps(settings, ensure_ascii=False), encoding="utf-8")


def test_a_fresh_install_ships_the_current_script(tmp_path):
    done = run(tmp_path / "cd")
    assert done.returncode == 0, done.stdout

    installed = tmp_path / "cd" / "cai-statusline.py"
    # Byte-identical, because re-running setup after a plugin update is the
    # only route a fixed status line has to an existing installation.
    assert installed.read_bytes() == SHIPPED.read_bytes()
    assert settings_of(tmp_path / "cd")["statusLine"]["type"] == "command"


def test_the_installed_copy_runs_outside_the_plugin_tree(tmp_path):
    # It is copied to ~/.claude/, away from everything else in scripts/, so an
    # import added to statusline.py from a sibling module would break only
    # after installation -- on someone else's machine, as a blank status bar.
    done = run(tmp_path / "cd")
    assert "verified: the installed script prints a status line" in done.stdout


def test_the_copy_does_not_take_the_built_in_statusline_filename():
    # ~/.claude/statusline.py is whatever the built-in `/statusline` command
    # last generated. Installing over it would eat work this plugin never made.
    assert install_statusline.SCRIPT_NAME != "statusline.py"


def test_the_rest_of_the_settings_file_survives(tmp_path):
    claude_dir = tmp_path / "cd"
    seed(claude_dir, EXISTING)

    assert run(claude_dir).returncode == 0
    after = settings_of(claude_dir)

    for key, value in EXISTING.items():
        assert after[key] == value
    # Not just equal after a round trip -- readable in the file itself. A
    # \u-escaped value parses back fine and still ruins the file for the
    # person who opens it next.
    assert "繁體中文" in (claude_dir / "settings.json").read_text(encoding="utf-8")


def test_the_command_survives_a_shell_that_is_not_git_bash(tmp_path):
    claude_dir = tmp_path / "cd"
    assert run(claude_dir).returncode == 0
    command = settings_of(claude_dir)["statusLine"]["command"]

    # Windows without Git Bash runs this through PowerShell, where a command
    # line that opens with a quote is a string literal, not a command.
    assert not command.startswith('"')
    # Git Bash eats an unquoted backslash as an escape, so no path may carry
    # one; the argument is quoted because a home directory may contain spaces.
    assert "\\" not in command
    assert command.endswith('"%s"' % str(claude_dir / "cai-statusline.py").replace(os.sep, "/"))


def test_a_relative_claude_dir_still_writes_an_absolute_path(tmp_path):
    # Claude Code runs the status line from wherever it likes; a relative
    # path in settings.json resolves against the wrong directory or none.
    done = subprocess.run([sys.executable, SCRIPT, "--claude-dir", "cd"],
                          cwd=str(tmp_path), capture_output=True, text=True)
    assert done.returncode == 0, done.stdout
    command = settings_of(tmp_path / "cd")["statusLine"]["command"]
    assert os.path.isabs(command.split('"')[1])


def test_a_status_line_someone_else_configured_is_refused(tmp_path):
    claude_dir = tmp_path / "cd"
    theirs = dict(EXISTING, statusLine={"type": "command", "command": "my-own-thing"})
    seed(claude_dir, theirs)
    before = (claude_dir / "settings.json").read_bytes()

    done = run(claude_dir)

    assert done.returncode == 2
    assert "my-own-thing" in done.stdout
    # Refused means nothing happened, not "happened and then reported".
    assert (claude_dir / "settings.json").read_bytes() == before
    assert not (claude_dir / "cai-statusline.py").exists()


def test_force_replaces_it_and_leaves_the_old_one_recoverable(tmp_path):
    claude_dir = tmp_path / "cd"
    theirs = dict(EXISTING, statusLine={"type": "command", "command": "my-own-thing"})
    seed(claude_dir, theirs)

    assert run(claude_dir, "--force").returncode == 0

    assert "cai-statusline.py" in settings_of(claude_dir)["statusLine"]["command"]
    backup = json.loads((claude_dir / "settings.json.bak").read_text(encoding="utf-8"))
    assert backup["statusLine"]["command"] == "my-own-thing"


def test_reinstalling_our_own_needs_no_force(tmp_path):
    # This is the update path: setup runs again after `/plugin update` and has
    # to refresh the copied script without stopping to ask.
    claude_dir = tmp_path / "cd"
    assert run(claude_dir).returncode == 0
    assert run(claude_dir).returncode == 0


def test_reinstalling_does_not_consume_the_only_copy_of_their_old_setting(tmp_path):
    # Setup is meant to be re-run after every plugin update. A backup taken on
    # each run would, on the second one, replace the user's original
    # statusLine with cai's -- losing it for good, quietly, later.
    claude_dir = tmp_path / "cd"
    seed(claude_dir, dict(EXISTING, statusLine={"type": "command",
                                                "command": "my-own-thing"}))
    assert run(claude_dir, "--force").returncode == 0

    done = run(claude_dir)

    assert done.returncode == 0
    assert "backup:" not in done.stdout
    backup = json.loads((claude_dir / "settings.json.bak").read_text(encoding="utf-8"))
    assert backup["statusLine"]["command"] == "my-own-thing"


def test_an_unparseable_settings_file_is_left_alone(tmp_path):
    claude_dir = tmp_path / "cd"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text("{ not json", encoding="utf-8")

    done = run(claude_dir)

    assert done.returncode == 1
    assert (claude_dir / "settings.json").read_text(encoding="utf-8") == "{ not json"


def test_check_reports_without_changing_anything(tmp_path):
    claude_dir = tmp_path / "cd"
    seed(claude_dir, EXISTING)
    before = (claude_dir / "settings.json").read_bytes()

    done = run(claude_dir, "--check")

    assert done.returncode == 0
    assert "statusLine: none configured" in done.stdout
    assert (claude_dir / "settings.json").read_bytes() == before
    assert not (claude_dir / "cai-statusline.py").exists()
