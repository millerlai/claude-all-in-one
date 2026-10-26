"""validate.py's R5 (stops) pins: the sentences that change when the track asks
the person -- stage-design.md's Tier 1 bar, approval-gates.md's stop list, and
stage-build.md Step 0.5's automatic lane.

Same arrangement as test_validate_folded_section.py: the section runs in this
process with the working directory moved into a damaged copy of the repo, and
a pin whose sentence is gone must print a FAIL line naming it.
"""
import importlib.util
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATE = REPO_ROOT / "scripts" / "validate.py"
REFS = "plugins/cai/skills/track/references"

# (file, sentence the pin holds, text to put in its place, label fragment)
PINNED = [
    ("stage-design.md",
     "Every Tier 1 entry carries one sentence saying why the evidence cannot",
     "Every Tier 1 entry carries nothing in particular and cannot",
     "stage-design.md's Tier 1 bar"),
    ("stage-design.md",
     "High cost, *and* the evidence and the stance cannot",
     "High cost, *and* the options differ in substance, and cannot",
     "stage-design.md's Tier 1 bar"),
    ("approval-gates.md",
     "the separate cost-sizing stop, the parallel-lane question",
     "the separate cost-sizing stop, nothing else",
     "approval-gates.md's stop list"),
    ("approval-gates.md",
     "- Gate 1 and Gate 2's push",
     "- Gate 2's push",
     "approval-gates.md's stop list"),
    ("approval-gates.md",
     "- Gate 2's triage menu, inside a track once the pull request is open",
     "- Gate 2's fix round, inside a track once the pull request is open",
     "approval-gates.md's stop list"),
    ("stage-build.md",
     "Lanes open on their own when the",
     "Lanes are asked about when the",
     "stage-build.md Step 0.5"),
]


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


def _pin_lines(capsys, prefix="R5:"):
    return [l for l in capsys.readouterr().out.splitlines()
            if l.split(" ", 1)[-1].startswith(prefix)]


def test_the_r5_pins_pass_on_the_checked_in_tree(monkeypatch, capsys, validate_module):
    monkeypatch.chdir(REPO_ROOT)
    validate_module._track_references()
    lines = _pin_lines(capsys)
    assert len(lines) == 3, lines
    assert all(l.startswith("PASS ") for l in lines), lines


# The short path's Gate 1 message shows the Signals rows (I3).
SHORT_PATH = [
    ("approval-gates.md",
     "`Row: verdict — evidence`, and names each `unanswerable` row with its reason,",
     "`Row: verdict — evidence`, and nothing else,",
     "approval-gates.md's short-path Gate 1 message"),
]


@pytest.mark.parametrize("prefix, name, sentence, instead, label",
                         [("R5:",) + p for p in PINNED] + [("I3:",) + p for p in SHORT_PATH])
def test_a_pinned_stop_sentence_that_is_gone_fails_its_pin(
        tmp_path, monkeypatch, capsys, validate_module, prefix, name, sentence, instead, label):
    repo = _copy_repo(tmp_path)
    path = repo / REFS / name
    text = path.read_text(encoding="utf-8")
    # The files wrap lines, so the sentence is found on one line of the file.
    assert text.count(sentence) == 1, sentence
    path.write_bytes(text.replace(sentence, instead).encode("utf-8"))
    monkeypatch.chdir(repo)

    validate_module._track_references()

    failed = [l for l in _pin_lines(capsys, prefix) if l.startswith("FAIL ")]
    assert len(failed) == 1 and label in failed[0], failed
