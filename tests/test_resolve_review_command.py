"""resolve_review_command.py: the platform-review call, or the reason to fall back."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import resolve_review_command as rrc

BASE = "origin/main"
SMALL = [(100, 23, "src/a.py")]
CODEX = {"codex_path": "/bin/codex", "codex_home": "/home/me/.codex"}


def claude(numstat=SMALL, version="2.1.290", **kw):
    return rrc.decide("claude", BASE, numstat, claude_version=version, **kw)


def codex(numstat=SMALL, **kw):
    return rrc.decide("codex", BASE, numstat, **{**CODEX, **kw})


def flat(result):
    return json.dumps(result)


# --- AC1: shape and determinism ------------------------------------------

def test_deterministic():
    assert claude() == claude()
    assert codex() == codex()


def test_claude_run_shape():
    r = claude([(100, 23, "src/a.py")])
    assert r == {
        "format": 1, "platform": "claude", "status": "run", "reason": None,
        "base": BASE, "lines": 123, "docs_only": False, "notes": [],
        "level": "high", "max_findings": 10,
        "args": "high --max-findings 10 origin/main...HEAD",
        "call": "/code-review high --max-findings 10 origin/main...HEAD",
    }


def test_codex_run_shape():
    r = codex([(100, 23, "src/a.py")])
    assert r == {
        "format": 1, "platform": "codex", "status": "run", "reason": None,
        "base": BASE, "lines": 123, "docs_only": False, "notes": [],
        "argv": ["/bin/codex", "exec", "review", "--base", BASE,
                 "-c", "sandbox_mode=read-only"],
        "env": {"CODEX_HOME": "/home/me/.codex"},
        "call": "codex exec review --base origin/main -c sandbox_mode=read-only",
    }


def test_codex_argv_is_read_only_and_has_home():
    r = codex()
    assert "-c" in r["argv"] and "sandbox_mode=read-only" in r["argv"]
    assert "CODEX_HOME" in r["env"]


def test_claude_args_start_with_a_level():
    for numstat in (SMALL, [(1, 1, "a.md")], [(401, 0, "a.py")]):
        assert claude(numstat)["args"].split()[0] in {lv for lv, _ in rrc.LEVELS.values()}


def test_no_ultra_for_any_level():
    assert all(level != "ultra" for level, _ in rrc.LEVELS.values())
    for numstat in (SMALL, [(1, 1, "a.md")], [(9999, 0, "a.py")]):
        assert "ultra" not in flat(claude(numstat))


@pytest.mark.parametrize("numstat", [SMALL, [(1, 1, "a.md")], [(900, 0, "a.py")]])
def test_no_fix_or_comment(numstat):
    for out in (flat(claude(numstat)), flat(codex(numstat))):
        assert "--fix" not in out and "--comment" not in out


# --- AC2: table and boundaries ---------------------------------------------

def test_levels_table():
    assert rrc.LEVELS == {"docs": ("low", 5), "small": ("high", 10), "large": ("max", 15)}
    assert (rrc.LINE_LIMIT, rrc.MIN_CLAUDE_VERSION) == (400, (2, 1, 288))
    assert (rrc.EXIT_RUN, rrc.EXIT_FALLBACK, rrc.EXIT_INVALID) == (0, 3, 5)


def test_docs_only_is_low_5():
    r = claude([(3, 1, "README.md")])
    assert (r["level"], r["max_findings"], r["docs_only"]) == ("low", 5, True)
    assert r["args"] == "low --max-findings 5 origin/main...HEAD"


def test_very_large_docs_diff_is_still_low():
    assert rrc.size_class([(5000, 0, "docs/big.md")]) == "docs"
    assert claude([(5000, 0, "docs/big.md")])["level"] == "low"


@pytest.mark.parametrize("suffix", [".md", ".txt", ".rst"])
def test_each_docs_suffix(suffix):
    assert rrc.size_class([(1, 0, "x/y" + suffix)]) == "docs"


@pytest.mark.parametrize("name", ["README.MD", "NOTES.TXT", "Guide.Rst"])
def test_docs_suffix_ignores_case(name):
    assert rrc.size_class([(1, 0, name)]) == "docs"
    assert claude([(1, 0, name)])["level"] == "low"


def test_other_suffix_is_not_docs():
    assert rrc.size_class([(1, 0, "x/y.mdx")]) == "small"
    assert rrc.size_class([(1, 0, "Makefile")]) == "small"


def test_exactly_400_is_high_and_401_is_max():
    assert rrc.size_class([(300, 100, "a.py")]) == "small"
    r = claude([(300, 100, "a.py")])
    assert (r["level"], r["max_findings"], r["lines"]) == ("high", 10, 400)
    assert rrc.size_class([(300, 101, "a.py")]) == "large"
    r = claude([(300, 101, "a.py")])
    assert (r["level"], r["max_findings"], r["lines"]) == ("max", 15, 401)


def test_lines_sum_over_rows():
    assert rrc.size_class([(200, 100, "a.py"), (100, 1, "b.py")]) == "large"


def test_binary_row_counts_zero_lines_but_keeps_its_path():
    r = claude([(None, None, "logo.png")])
    assert (r["lines"], r["docs_only"], r["level"]) == (0, False, "high")
    r = claude([(None, None, "logo.png"), (5, 0, "a.md")])
    assert r["docs_only"] is False
    r = claude([(None, None, "manual.pdf.md"), (5, 0, "a.md")])
    assert (r["lines"], r["docs_only"]) == (5, True)


def test_mixed_docs_and_code_is_not_docs_only():
    r = claude([(5, 0, "a.md"), (5, 0, "a.py")])
    assert r["docs_only"] is False and r["level"] == "high"


# --- AC3: fallbacks -----------------------------------------------------------

def test_version_unreadable_falls_back():
    r = claude(version=None)
    assert r["status"] == "fallback" and r["call"] is None
    assert r["reason"] == "claude --version unreadable"
    assert "args" not in r


def test_old_version_falls_back_new_runs():
    r = claude(version="2.1.287")
    assert r["status"] == "fallback"
    assert r["reason"] == "claude --version reported 2.1.287, below 2.1.288"
    assert claude(version="2.1.288")["status"] == "run"
    assert claude(version="2.2.0")["status"] == "run"
    assert claude(version="10.0.0")["status"] == "run"


@pytest.mark.parametrize("value", ["user-invocable-only", "off"])
@pytest.mark.parametrize("slot", [0, 1, 2])
def test_skill_override_in_any_layer_falls_back(value, slot):
    layers = [{}, {}, {}]
    layers[slot] = {"skillOverrides": {"code-review": value}}
    r = claude(settings_layers=layers)
    assert r["status"] == "fallback" and r["call"] is None
    assert value in r["reason"]


@pytest.mark.parametrize("value", ["on", "name-only"])
def test_harmless_override_runs(value):
    assert claude(settings_layers=[{"skillOverrides": {"code-review": value}}])["status"] == "run"


def test_unrelated_override_and_junk_settings_run():
    layers = [{"skillOverrides": {"other": "off"}}, {"skillOverrides": []}, {}]
    assert claude(settings_layers=layers)["status"] == "run"


@pytest.mark.parametrize("path", [
    "/p/.claude/skills/code-review", "/home/me/.claude/skills/code-review",
    "/p/.claude/commands/code-review.md", "/home/me/.claude/commands/code-review.md"])
def test_replacing_skill_or_command_falls_back(path):
    r = claude(skill_dirs=[path])
    assert r["status"] == "fallback" and path in r["reason"]


def test_codex_without_path_falls_back():
    r = codex(codex_path=None)
    assert r["status"] == "fallback" and r["call"] is None
    assert "codex" in r["reason"]


def test_claude_checks_do_not_apply_to_codex_and_back():
    assert codex(skill_dirs=["/x"], settings_layers=[{"skillOverrides": {"code-review": "off"}}])["status"] == "run"
    assert rrc.decide("claude", BASE, SMALL, claude_version="2.1.290")["status"] == "run"


def test_notes_are_carried():
    assert claude(notes=["one"])["notes"] == ["one"]


# --- the base ref reaches codex's argv, which cmd.exe may read -----------------

@pytest.mark.parametrize("ref", ["main&calc", "a|b", "a b", "-x", "a;b", "a$(b)", "a`b`",
                                 'a"b', "a%PATH%", "a^b", "a<b", "a>b", "a(b)", ""])
@pytest.mark.parametrize("platform", ["claude", "codex"])
def test_unsafe_base_ref_is_invalid_and_builds_no_call(platform, ref):
    r = rrc.decide(platform, ref, SMALL, claude_version="2.1.290", **CODEX)
    assert r["status"] == "invalid" and r["call"] is None
    assert "argv" not in r and "args" not in r
    assert ref not in r["reason"] or ref == ""


@pytest.mark.parametrize("ref", ["origin/main", "main", "v1.2.3", "feature/x_y-z", "HEAD~3",
                                 "abc123", "release+1", "user@host"])
def test_ordinary_base_refs_still_run(ref):
    assert rrc.decide("codex", ref, SMALL, **CODEX)["status"] == "run"
    assert rrc.decide("claude", ref, SMALL, claude_version="2.1.290")["status"] == "run"


# --- exit 5 -------------------------------------------------------------------

def test_empty_numstat_is_invalid():
    r = claude(numstat=[])
    assert r["status"] == "invalid" and r["reason"] and r["call"] is None


def test_unknown_platform_is_invalid():
    r = rrc.decide("gemini", BASE, SMALL)
    assert r["status"] == "invalid" and "gemini" in r["reason"]


# --- gather and main against a real repo -------------------------------------

def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false", *args],
                   check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    (r / "a.py").write_text("x = 1\n")
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "init")
    git(r, "checkout", "-q", "-b", "feat")
    (r / "a.py").write_text("x = 1\ny = 2\nz = 3\n")
    (r / "notes.md").write_text("hello\n")
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "work")
    (r / "a.py").write_text("x = 1\ny = 2\nz = 3\nw = 4\n")  # uncommitted, tracked
    return r


def fake_exe(directory, name, line):
    directory.mkdir(exist_ok=True)
    if os.name == "nt":
        path = directory / (name + ".bat")
        path.write_text("@echo off\r\necho " + line + "\r\n")
    else:
        path = directory / name
        path.write_text("#!/bin/sh\necho '" + line + "'\n")
        path.chmod(0o755)
    return path


def on_path(monkeypatch, directory):
    monkeypatch.setenv("PATH", str(directory) + os.pathsep + os.environ["PATH"])


def test_gather_reads_numstat_against_the_worktree(repo, tmp_path):
    g = rrc.gather("codex", "main", str(repo), environ={"CODEX_HOME": str(tmp_path / "ch")})
    assert sorted((a, d, p) for a, d, p in g["numstat"]) == [(1, 0, "notes.md"), (3, 0, "a.py")]
    assert g["codex_home"] == str(tmp_path / "ch")
    assert g["base_ref"] == "main"


def test_gather_codex_home_defaults_to_dot_codex(repo):
    g = rrc.gather("codex", "main", str(repo), environ={})
    assert Path(g["codex_home"]) == Path.home() / ".codex"


def test_gather_reads_settings_layers_and_skill_dirs(repo, tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    (cfg / "skills" / "code-review").mkdir(parents=True)
    (cfg / "commands").mkdir()
    (cfg / "commands" / "code-review.md").write_text("x")
    (cfg / "settings.json").write_text(json.dumps({"skillOverrides": {"code-review": "off"}}))
    (repo / ".claude" / "skills" / "code-review").mkdir(parents=True)
    (repo / ".claude" / "commands").mkdir()
    (repo / ".claude" / "commands" / "code-review.md").write_text("x")
    (repo / ".claude" / "settings.json").write_text("{not json")
    (repo / ".claude" / "settings.local.json").write_text(json.dumps({"a": 1}))
    on_path(monkeypatch, fake_exe(tmp_path / "bin", "claude", "2.1.290 (Claude Code)").parent)
    g = rrc.gather("claude", "main", str(repo), environ={"CLAUDE_CONFIG_DIR": str(cfg)})
    assert g["claude_version"] == "2.1.290"
    assert g["settings_layers"] == [{"skillOverrides": {"code-review": "off"}}, {}, {"a": 1}]
    assert len(g["notes"]) == 1 and "settings.json" in g["notes"][0]
    assert sorted(Path(p) for p in g["skill_dirs"]) == sorted([
        repo / ".claude" / "skills" / "code-review", cfg / "skills" / "code-review",
        repo / ".claude" / "commands" / "code-review.md", cfg / "commands" / "code-review.md"])


def test_gather_without_layers_or_dirs(repo, tmp_path, monkeypatch):
    on_path(monkeypatch, fake_exe(tmp_path / "bin", "claude", "claude 2.1.300").parent)
    g = rrc.gather("claude", "main", str(repo), environ={"CLAUDE_CONFIG_DIR": str(tmp_path / "none")})
    assert g["settings_layers"] == [{}, {}, {}] and g["skill_dirs"] == [] and g["notes"] == []
    assert g["claude_version"] == "2.1.300"


@pytest.mark.parametrize("environ", [{}, {"CLAUDE_CONFIG_DIR": ""}])
def test_gather_config_dir_defaults_to_dot_claude_in_home(repo, tmp_path, monkeypatch, environ):
    home = tmp_path / "home"
    (home / ".claude" / "skills" / "code-review").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"skillOverrides": {"code-review": "off"}}))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    on_path(monkeypatch, fake_exe(tmp_path / "bin", "claude", "claude 2.1.300").parent)
    g = rrc.gather("claude", "main", str(repo), environ=environ)
    assert g["settings_layers"][0] == {"skillOverrides": {"code-review": "off"}}
    assert [Path(p) for p in g["skill_dirs"]] == [home / ".claude" / "skills" / "code-review"]


def test_gather_measures_from_the_merge_base_not_the_ref_itself(repo, tmp_path):
    # `main` moves on after `feat` branched off it. Diffing against main's tip
    # would list that file as deleted here, and the review would be sized by work
    # that is not on this branch.
    git(repo, "checkout", "-q", "--", "a.py")  # drop the fixture's uncommitted edit
    git(repo, "checkout", "-q", "main")
    (repo / "other.py").write_text("o = 1\n")
    git(repo, "add", "other.py")
    git(repo, "commit", "-q", "-m", "main moves on")
    git(repo, "checkout", "-q", "feat")
    g = rrc.gather("codex", "main", str(repo), environ={"CODEX_HOME": str(tmp_path / "ch")})
    assert sorted(p for _, _, p in g["numstat"]) == ["a.py", "notes.md"]


@pytest.mark.parametrize("content", [b"\xff\xfe\xff not utf-8", b"[1, 2]", b"{broken"])
def test_gather_unreadable_or_non_object_settings_are_empty_with_a_note(
        repo, tmp_path, monkeypatch, content):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "settings.json").write_bytes(content)
    on_path(monkeypatch, fake_exe(tmp_path / "bin", "claude", "claude 2.1.300").parent)
    g = rrc.gather("claude", "main", str(repo), environ={"CLAUDE_CONFIG_DIR": str(cfg)})
    assert g["settings_layers"][0] == {}
    assert len(g["notes"]) == 1 and "settings.json" in g["notes"][0]
    assert str(cfg) not in g["notes"][0]  # the file name only, never the path


def test_gather_settings_path_that_is_a_directory_is_empty_with_a_note(repo, tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    (cfg / "settings.json").mkdir(parents=True)
    on_path(monkeypatch, fake_exe(tmp_path / "bin", "claude", "claude 2.1.300").parent)
    g = rrc.gather("claude", "main", str(repo), environ={"CLAUDE_CONFIG_DIR": str(cfg)})
    assert g["settings_layers"][0] == {} and "could not be read" in g["notes"][0]


def test_gather_ignores_a_codex_found_inside_the_reviewed_repo(repo, tmp_path, monkeypatch):
    # A checkout can carry its own `node_modules/.bin/codex`, and a PATH entry
    # that points into it would otherwise be run with the person's environment.
    (repo / "node_modules").mkdir()
    planted = fake_exe(repo / "node_modules" / ".bin", "codex", "planted")
    on_path(monkeypatch, planted.parent)
    g = rrc.gather("codex", "main", str(repo), environ={})
    assert g["codex_path"] is None
    assert any("inside the reviewed repository" in n for n in g["notes"])
    assert rrc.decide(**g)["status"] == "fallback"


def test_gather_keeps_a_codex_outside_the_reviewed_repo(repo, tmp_path, monkeypatch):
    outside = fake_exe(tmp_path / "bin", "codex", "x")
    on_path(monkeypatch, outside.parent)
    g = rrc.gather("codex", "main", str(repo), environ={})
    assert Path(g["codex_path"]) == outside and g["notes"] == []


def test_gather_version_unreadable(repo, tmp_path, monkeypatch):
    on_path(monkeypatch, fake_exe(tmp_path / "bin", "claude", "no number here").parent)
    g = rrc.gather("claude", "main", str(repo), environ={"CLAUDE_CONFIG_DIR": str(tmp_path / "none")})
    assert g["claude_version"] is None


def test_gather_codex_path_none_when_missing(repo, monkeypatch):
    monkeypatch.setattr(rrc.tool_path, "resolve",
                        lambda name, cwd=None: (_ for _ in ()).throw(FileNotFoundError(name))
                        if name == "codex" else "git")
    assert rrc.gather("codex", "main", str(repo), environ={})["codex_path"] is None


def test_gather_bad_ref_raises(repo):
    with pytest.raises(rrc.GatherError):
        rrc.gather("codex", "no-such-ref", str(repo), environ={})


def run_main(argv, capsys):
    code = rrc.main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_main_codex_run(repo, tmp_path, monkeypatch, capsys):
    exe = fake_exe(tmp_path / "bin", "codex", "x")
    on_path(monkeypatch, exe.parent)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "ch"))
    code, out = run_main(["--platform", "codex", "--base", "main", "--project-dir", str(repo)], capsys)
    assert code == rrc.EXIT_RUN
    assert out["status"] == "run" and out["lines"] == 4 and out["docs_only"] is False
    assert Path(out["argv"][0]) == exe and out["env"] == {"CODEX_HOME": str(tmp_path / "ch")}


def test_main_claude_fallback_exit_3(repo, tmp_path, monkeypatch, capsys):
    on_path(monkeypatch, fake_exe(tmp_path / "bin", "claude", "2.1.280").parent)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "none"))
    code, out = run_main(["--platform", "claude", "--base", "main", "--project-dir", str(repo)], capsys)
    assert code == rrc.EXIT_FALLBACK
    assert out["reason"] == "claude --version reported 2.1.280, below 2.1.288"


def test_main_empty_diff_exit_5(repo, tmp_path, monkeypatch, capsys):
    git(repo, "checkout", "-q", "--", "a.py")
    git(repo, "checkout", "-q", "main")
    on_path(monkeypatch, fake_exe(tmp_path / "bin", "codex", "x").parent)
    code, out = run_main(["--platform", "codex", "--base", "main", "--project-dir", str(repo)], capsys)
    assert code == rrc.EXIT_INVALID and out["status"] == "invalid"


def test_main_git_failure_exit_5(repo, capsys):
    code, out = run_main(["--platform", "codex", "--base", "no-such-ref", "--project-dir", str(repo)], capsys)
    assert code == rrc.EXIT_INVALID and out["status"] == "invalid" and out["reason"]


def test_main_not_a_repo_exit_5(tmp_path, capsys):
    code, out = run_main(["--platform", "codex", "--base", "main", "--project-dir", str(tmp_path)], capsys)
    assert code == rrc.EXIT_INVALID


def test_main_argparse_errors_exit_2(capsys):
    with pytest.raises(SystemExit) as e:
        rrc.main(["--platform", "gemini", "--base", "main"])
    assert e.value.code == 2
    with pytest.raises(SystemExit) as e:
        rrc.main(["--platform", "claude"])
    assert e.value.code == 2


def test_script_runs_as_a_program(repo, tmp_path):
    exe = fake_exe(tmp_path / "bin", "codex", "x")
    env = {**os.environ, "PATH": str(exe.parent) + os.pathsep + os.environ["PATH"],
           "CODEX_HOME": str(tmp_path / "ch")}
    script = Path(rrc.__file__)
    p = subprocess.run([sys.executable, str(script), "--platform", "codex", "--base", "main",
                        "--project-dir", str(repo)], capture_output=True, env=env)
    assert p.returncode == 0
    assert json.loads(p.stdout.decode("utf-8"))["platform"] == "codex"
