"""validate.py's "Shells" pins: the sentences that keep a subagent from leaving
a shell running after it hands back -- a heredoc waiting on stdin, a sleep
poll that never ends, or a timed-out call moved to the background -- and the
track skill's step that stops what a report names.

Same arrangement as test_validate_stop_pins.py: the section runs in this
process with the working directory moved into a damaged copy of the repo, and
a pin whose sentence is gone must print a FAIL line naming it.
"""
import importlib.util
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATE = REPO_ROOT / "scripts" / "validate.py"

# (file, sentence the pin holds, text to put in its place, label fragment)
PINNED = [
    ("plugins/cai/agents/implementer.md",
     "no heredoc (`<<`) for any purpose",
     "heredocs are fine",
     "implementer.md"),
    ("plugins/cai/agents/test-runner.md",
     "Give the Bash call a `timeout` longer than the runner's own",
     "Give the Bash call any `timeout`",
     "test-runner.md"),
    ("plugins/cai/skills/track/references/stage-ship.md",
     "such as `gh pr checks --watch`, a Bash `timeout`",
     "such as `gh pr checks --watch`, no Bash `timeout`",
     "stage-ship.md"),
    ("plugins/cai/skills/track/SKILL.md",
     "stop with TaskStop, or name it to the person when you cannot.",
     "leave it.",
     "track/SKILL.md"),
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


def _shell_lines(capsys):
    return [l for l in capsys.readouterr().out.splitlines()
            if l.split(" ", 1)[-1].startswith("Shells:")]


def test_the_shell_pins_pass_on_the_checked_in_tree(monkeypatch, capsys, validate_module):
    monkeypatch.chdir(REPO_ROOT)
    validate_module._track_references()
    lines = _shell_lines(capsys)
    assert len(lines) == 4, lines
    assert all(l.startswith("PASS ") for l in lines), lines


@pytest.mark.parametrize("name, sentence, instead, label", PINNED)
def test_a_pinned_shell_sentence_that_is_gone_fails_its_pin(
        tmp_path, monkeypatch, capsys, validate_module, name, sentence, instead, label):
    repo = _copy_repo(tmp_path)
    path = repo / name
    text = path.read_text(encoding="utf-8")
    # The files wrap lines, so the sentence is found on one line of the file.
    assert text.count(sentence) == 1, sentence
    path.write_bytes(text.replace(sentence, instead).encode("utf-8"))
    monkeypatch.chdir(repo)

    validate_module._track_references()

    failed = [l for l in _shell_lines(capsys) if l.startswith("FAIL ")]
    assert len(failed) == 1 and label in failed[0], failed
