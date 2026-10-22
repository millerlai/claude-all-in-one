"""#375: stage-design.md sends the dispatched designer to `plan-review`, a skill
the designer has no tool to invoke. validate.py's track-stages section pins that
the gate section says how it runs and that the tool it names is one designer.md
grants. Same shape as test_validate_folded_section.py: the section runs in
process on the checked-in validate.py, against a copy of the repo that has been
damaged, so the lines it executes are credited to the checked-in file."""
import importlib.util
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATE = REPO_ROOT / "scripts" / "validate.py"
DESIGN = "plugins/cai/skills/track/references/stage-design.md"
DESIGNER = "plugins/cai/agents/designer.md"


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
    assert any(l.startswith("PASS") and "grants" in l for l in lines), lines
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


def test_a_run_through_a_tool_the_designer_lacks_fails(
        tmp_path, monkeypatch, capsys, validate_module):
    repo = _copy_repo(tmp_path)
    ref = repo / DESIGN
    text = ref.read_text(encoding="utf-8")
    gate = text.find("## The gate every mode shares")
    assert gate >= 0
    # Same document, but the gate now says to invoke the skill: a tool that
    # designer.md's `tools:` line does not grant.
    ref.write_text(text[:gate] + text[gate:].replace("`Agent`", "`Skill`", 1),
                   encoding="utf-8")
    assert "Skill" not in (repo / DESIGNER).read_text(encoding="utf-8").split("---")[1]
    lines = _run(validate_module, repo, monkeypatch, capsys)
    assert any(l.startswith("FAIL") and "`Skill`" in l for l in lines), lines
