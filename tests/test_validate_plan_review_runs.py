"""#375: inside a track the session that wrote the design must not review it,
so stage-design.md's gate section says how `plan-review` runs. validate.py's
track-stages section pins that the gate names the skill file and the tool it
runs through. Same shape as test_validate_folded_section.py: the section runs in
process on the checked-in validate.py, against a copy of the repo that has been
damaged, so the lines it executes are credited to the checked-in file."""
import importlib.util
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATE = REPO_ROOT / "scripts" / "validate.py"
DESIGN = "plugins/cai/skills/track/references/stage-design.md"


@pytest.fixture
def validate_module():
    spec = importlib.util.spec_from_file_location("validate_under_test", VALIDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_repo(tmp_path):
    common = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".coverage*")

    def ignore(src, names):
        skipped = set(common(src, names))
        if Path(src) == REPO_ROOT / ".cai" and "track" in names:
            skipped.add("track")
        return skipped

    dest = tmp_path / "repo"
    shutil.copytree(REPO_ROOT, dest, ignore=ignore)
    return dest


def _run(validate_module, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    validate_module._track_stages()
    return [l for l in capsys.readouterr().out.splitlines() if "plan-review" in l]


def test_the_shipped_files_pass(tmp_path, monkeypatch, capsys, validate_module):
    lines = _run(validate_module, _copy_repo(tmp_path), monkeypatch, capsys)
    assert any(l.startswith("PASS") and "names the plan-review skill file" in l
               for l in lines), lines
    assert any(l.startswith("PASS") and "names the tool plan-review runs through" in l
               for l in lines), lines
    assert not [l for l in lines if l.startswith("FAIL")], lines


def test_a_gate_that_names_no_skill_file_fails(tmp_path, monkeypatch, capsys, validate_module):
    repo = _copy_repo(tmp_path)
    ref = repo / DESIGN
    text = ref.read_text(encoding="utf-8")
    path = "${CLAUDE_PLUGIN_ROOT}/skills/plan-review/SKILL.md"
    assert path in text
    ref.write_text(text.replace(path, "the plan-review skill"), encoding="utf-8")
    lines = _run(validate_module, repo, monkeypatch, capsys)
    assert any(l.startswith("FAIL") and "names the plan-review skill file" in l
               for l in lines), lines


def test_a_gate_that_names_no_tool_fails(tmp_path, monkeypatch, capsys, validate_module):
    repo = _copy_repo(tmp_path)
    ref = repo / DESIGN
    text = ref.read_text(encoding="utf-8")
    gate = text.find("## The gate every mode shares")
    assert gate >= 0
    end = text.find("\n## ", gate + 1)
    section = text[gate:end]
    assert "`Agent`" in section
    # Same document, but the gate no longer says what plan-review runs through.
    damaged = section.replace("`Agent`", "an agent").replace("`Skill`", "a skill")
    ref.write_text(text[:gate] + damaged + text[end:], encoding="utf-8")
    lines = _run(validate_module, repo, monkeypatch, capsys)
    assert any(l.startswith("FAIL") and "names the tool plan-review runs through" in l
               for l in lines), lines
