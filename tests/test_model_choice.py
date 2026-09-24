"""model_choice.py -- a person's own tier -> model choice, applied to an
installed copy of the cai plugin.

Every test runs the script from a COPY of the plugin under tmp_path, with
CLAUDE_CONFIG_DIR inside tmp_path too. The script rewrites the plugin root it
sits in, so running it in place would rewrite this repo's own frontmatter,
and its choice file would land in the real ~/.claude.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_PLUGIN = REPO_ROOT / "plugins" / "cai"


def installed_copy(tmp_path):
    """Stands in for ~/.claude/plugins/cache/<marketplace>/cai/<version>:
    the shipped files, with no marketplace.json two levels up."""
    root = tmp_path / "cache" / "claude-all-in-one" / "cai" / "9.9.9"
    shutil.copytree(REAL_PLUGIN, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def source_copy(tmp_path):
    """Stands in for a checkout or marketplace clone: marketplace.json sits
    two levels above the plugin root."""
    src = tmp_path / "src"
    root = src / "plugins" / "cai"
    shutil.copytree(REAL_PLUGIN, root, ignore=shutil.ignore_patterns("__pycache__"))
    (src / ".claude-plugin").mkdir()
    (src / ".claude-plugin" / "marketplace.json").write_text("{}", encoding="utf-8")
    return root


def run(root, tmp_path, *args):
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(tmp_path / "config"))
    return subprocess.run([sys.executable, str(root / "scripts" / "model_choice.py"), *args],
                          capture_output=True, encoding="utf-8", env=env)


def spec():
    return json.loads((REAL_PLUGIN / "models.json").read_text(encoding="utf-8"))


def default(tier):
    return spec()["roles"][tier]["alias"]


def members(tier):
    return sorted(p for p, t in spec()["assignments"].items() if t == tier)


def model_of(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("model:"):
            return line.split(":", 1)[1].strip()
    return None


def choice_file(tmp_path):
    return tmp_path / "config" / "cai" / "model-choice.json"


def saved(tmp_path):
    return json.loads(choice_file(tmp_path).read_text(encoding="utf-8"))


def assigned_bytes(root):
    return {rel: (root / rel).read_bytes() for rel in spec()["assignments"]}


def test_show_prints_every_tier_on_its_default_and_writes_nothing(tmp_path):
    root = installed_copy(tmp_path)
    before = assigned_bytes(root)

    done = run(root, tmp_path, "show")

    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    for tier in spec()["roles"]:
        assert any(line.startswith(f"tier {tier}: {default(tier)} (cai default) -- ")
                   for line in lines), tier
        assert any(line.startswith(f"offer {tier}: ") for line in lines), tier
    assert any(line.startswith("choice file: ") for line in lines)
    assert assigned_bytes(root) == before
    assert not (tmp_path / "config").exists()


def test_every_offer_line_fits_one_menu_and_leads_with_the_model_in_effect(tmp_path):
    root = installed_copy(tmp_path)
    assert run(root, tmp_path, "set", "think=claude-some-new-model").returncode == 0

    done = run(root, tmp_path, "show")

    offer = next(l for l in done.stdout.splitlines() if l.startswith("offer think: "))
    entries = offer[len("offer think: "):].split(", ")
    assert len(entries) <= 4
    assert entries[0] == "claude-some-new-model (in effect)"


def test_set_rewrites_exactly_that_tiers_components_and_saves_the_choice(tmp_path):
    root = installed_copy(tmp_path)
    before = assigned_bytes(root)

    done = run(root, tmp_path, "set", "think=fable")

    assert done.returncode == 0, done.stdout + done.stderr
    assert saved(tmp_path) == {"format": 1, "roles": {"think": "fable"}}
    for rel, data in before.items():
        if rel in members("think"):
            assert model_of(root / rel) == "fable", rel
        else:
            assert (root / rel).read_bytes() == data, rel
    assert f"tier think: fable (saved; cai default {default('think')}) -- " in done.stdout
    assert "restart Claude Code" in done.stdout


def test_setting_a_tier_to_its_default_drops_it_from_the_choice(tmp_path):
    root = installed_copy(tmp_path)
    assert run(root, tmp_path, "set", "think=fable").returncode == 0

    done = run(root, tmp_path, "set", f"think={default('think')}")

    assert done.returncode == 0, done.stdout + done.stderr
    assert saved(tmp_path) == {"format": 1, "roles": {}}
    for rel in members("think"):
        assert model_of(root / rel) == default("think"), rel


def test_reset_puts_one_tier_back_and_reset_alone_clears_every_tier(tmp_path):
    root = installed_copy(tmp_path)
    assert run(root, tmp_path, "set", "think=fable", "chore=claude-x").returncode == 0

    assert run(root, tmp_path, "reset", "think").returncode == 0
    assert saved(tmp_path)["roles"] == {"chore": "claude-x"}
    assert model_of(root / members("think")[0]) == default("think")

    assert run(root, tmp_path, "reset").returncode == 0
    assert saved(tmp_path)["roles"] == {}
    assert model_of(root / members("chore")[0]) == default("chore")


@pytest.mark.parametrize("bad", ["think", "think=", "think=Opus", "think=a b",
                                 "think=x;rm", "nosuch=fable"])
def test_a_malformed_or_unknown_answer_is_refused_before_any_write(tmp_path, bad):
    root = installed_copy(tmp_path)
    before = assigned_bytes(root)

    done = run(root, tmp_path, "set", bad)

    assert done.returncode == 2, done.stdout + done.stderr
    assert not (tmp_path / "config").exists()
    assert assigned_bytes(root) == before


def test_apply_puts_the_choice_back_after_an_update_then_does_nothing(tmp_path):
    """An update installs a fresh copy carrying cai's defaults; the
    SessionStart hook's `apply --hook` restores the saved choice, once."""
    root = installed_copy(tmp_path)
    assert run(root, tmp_path, "set", "think=fable").returncode == 0
    for rel in members("think"):  # what /plugin update leaves behind
        shutil.copy(REAL_PLUGIN / rel, root / rel)

    first = run(root, tmp_path, "apply", "--hook")
    second = run(root, tmp_path, "apply", "--hook")

    assert first.returncode == 0 and second.returncode == 0
    for rel in members("think"):
        assert model_of(root / rel) == "fable", rel
    assert "restart" in json.loads(first.stdout)["systemMessage"]
    assert second.stdout == ""


def test_apply_with_no_saved_choice_changes_nothing(tmp_path):
    root = installed_copy(tmp_path)
    before = assigned_bytes(root)

    done = run(root, tmp_path, "apply", "--hook")

    assert done.returncode == 0
    assert done.stdout == ""
    assert assigned_bytes(root) == before


def test_apply_hook_never_fails_a_session_start(tmp_path):
    root = installed_copy(tmp_path)
    choice_file(tmp_path).parent.mkdir(parents=True)
    choice_file(tmp_path).write_text("{not json", encoding="utf-8")

    done = run(root, tmp_path, "apply", "--hook")

    assert done.returncode == 0
    assert "/cai:models" in json.loads(done.stdout)["systemMessage"]


def test_crlf_files_keep_their_line_endings(tmp_path):
    root = installed_copy(tmp_path)
    path = root / members("think")[0]
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    crlf_before = path.read_bytes().count(b"\r\n")

    assert run(root, tmp_path, "set", "think=fable").returncode == 0

    after = path.read_bytes()
    assert after.count(b"\r\n") == crlf_before
    assert b"\nmodel: fable\r\n" in after


def test_a_model_line_outside_the_frontmatter_is_left_alone(tmp_path):
    root = installed_copy(tmp_path)
    path = root / members("think")[0]
    path.write_bytes(path.read_bytes() + b"\nmodel: quoted-in-prose\n")

    assert run(root, tmp_path, "set", "think=fable").returncode == 0

    assert path.read_bytes().endswith(b"\nmodel: quoted-in-prose\n")
    assert model_of(path) == "fable"


def test_a_plugin_source_tree_is_never_rewritten(tmp_path):
    """A checkout or marketplace clone is what everyone installs from, so one
    person's choice must never be written into it."""
    root = source_copy(tmp_path)
    before = assigned_bytes(root)
    choice_file(tmp_path).parent.mkdir(parents=True)
    choice_file(tmp_path).write_text(json.dumps({"format": 1, "roles": {"think": "fable"}}),
                                     encoding="utf-8")

    refused = run(root, tmp_path, "set", "build=fable")
    hooked = run(root, tmp_path, "apply", "--hook")

    assert refused.returncode == 1
    assert "source tree" in refused.stdout
    assert hooked.returncode == 0
    assert hooked.stdout == ""
    assert assigned_bytes(root) == before
