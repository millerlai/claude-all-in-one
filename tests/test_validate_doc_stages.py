"""R3 (documents): validate.py's `doc-stages` section fails when a front-door
document still lists `intake` or `discover` as a track stage. The section runs
in process on the checked-in validate.py against a scratch directory holding
only the documents the test writes, so the lines it executes are credited to the
checked-in file."""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATE = REPO_ROOT / "scripts" / "validate.py"
DOCS = ("README.md", "README.zh-TW.md", "REFERENCE.md", "MANUAL.md", "GUIDE.md")


@pytest.fixture
def validate_module():
    spec = importlib.util.spec_from_file_location("validate_under_test", VALIDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(validate_module, directory, monkeypatch, capsys):
    monkeypatch.chdir(directory)
    validate_module._doc_stages()
    return [l for l in capsys.readouterr().out.splitlines() if "R3" in l]


def test_the_checked_in_documents_pass(monkeypatch, capsys, validate_module):
    lines = _run(validate_module, REPO_ROOT, monkeypatch, capsys)
    assert len([l for l in lines if l.startswith("PASS")]) == len(DOCS), lines
    assert not [l for l in lines if l.startswith("FAIL")], lines


@pytest.mark.parametrize("name", DOCS)
@pytest.mark.parametrize("bad", [
    "- **The six stages.** `intake`, `discover`, `design`, `build`, `verify`, `ship`.\n",
    "- **六個階段（stage）。** `intake`、`discover`、`design`\n",
    "Opens a track, walks six stages\n",
    "carries one feature through six SDLC stages\n",
    "Type `/cai:intake` first.\n",
    '    S1["intake<br/>a problem statement you can check"] --> S2\n',
])
def test_a_document_that_lists_a_retired_stage_fails(
        tmp_path, monkeypatch, capsys, validate_module, name, bad):
    (tmp_path / name).write_text("# Doc\n\n" + bad, encoding="utf-8")
    lines = _run(validate_module, tmp_path, monkeypatch, capsys)
    assert any(l.startswith("FAIL") and name in l for l in lines), lines


def test_prose_that_only_names_the_retired_stages_passes(
        tmp_path, monkeypatch, capsys, validate_module):
    # What the documents now say: the stages are folded into `design`, and
    # `/cai:discover` is a standalone command -- neither is a stage list.
    (tmp_path / "MANUAL.md").write_text(
        "The old `intake` and `discover` stages are folded in. `/cai:discover` "
        "is still a command. The six stage rows of an old track still read.\n",
        encoding="utf-8")
    lines = _run(validate_module, tmp_path, monkeypatch, capsys)
    assert not [l for l in lines if l.startswith("FAIL")], lines
