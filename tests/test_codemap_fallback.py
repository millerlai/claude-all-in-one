"""AC1: a repository without a usable index behaves exactly as before.

Preflight is run on the same repository three ways -- no `.cai/codemap/`, a
good one, a damaged one -- and prints the same thing; the read-side texts all
carry the fallback sentence; and codemap-brief.md says that a non-zero exit or
no line means no line.
"""
import os
import subprocess
import sys

import pytest

import codemap_index as idx
import preflight
from codemap_repo import git, make_repo

PLUGIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "plugins", "cai")
PREFLIGHT = os.path.join(PLUGIN, "scripts", "preflight.py")
FALLBACK = "Any other line, or none, means Read/Grep/Glob as you would without it."
READ_SIDE = [
    "agents/architect.md", "agents/designer.md", "agents/explorer.md",
    "skills/track/references/stage-intake.md",
    "skills/track/references/stage-discover.md",
    "skills/track/references/stage-design.md",
]


def _folded(rel):
    with open(os.path.join(PLUGIN, *rel.split("/")), encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def _preflight(stage, repo, track):
    done = subprocess.run(
        [sys.executable, PREFLIGHT, stage, "--track-dir", str(track),
         "--project-dir", str(repo)],
        capture_output=True, encoding="utf-8", errors="replace")
    return done.returncode, done.stdout.replace(str(repo), "<repo>").replace(str(track), "<track>")


def _repo(root, variant):
    repo = root / variant
    repo.mkdir()
    make_repo(repo, {"a.py": "x = 1\n"})
    git(repo, "switch", "-q", "-c", "track/feature")
    track = repo / ".cai" / "track" / "feature"
    track.mkdir(parents=True)
    if variant != "none":
        idx.build(str(repo))
    if variant == "damaged":
        (repo / ".cai" / "codemap" / "state.json").write_text("{broken", encoding="utf-8")
    return repo, track


@pytest.mark.parametrize("stage", ["intake", "discover", "design"])
def test_preflight_prints_the_same_with_no_index_a_good_one_and_a_damaged_one(tmp_path, stage):
    outputs = {}
    for variant in ("none", "good", "damaged"):
        repo, track = _repo(tmp_path, variant)
        outputs[variant] = _preflight(stage, repo, track)
        assert "Traceback" not in outputs[variant][1]
    assert outputs["good"] == outputs["none"]
    assert outputs["damaged"] == outputs["none"]


def test_preflight_source_never_mentions_the_index():
    with open(PREFLIGHT, encoding="utf-8") as fh:
        assert "codemap" not in fh.read().lower()
    assert not hasattr(preflight, "codemap")


@pytest.mark.parametrize("rel", READ_SIDE)
def test_every_read_side_text_carries_the_fallback_sentence(rel):
    assert FALLBACK in _folded(rel)


def test_brief_says_no_line_when_the_index_is_absent_or_a_command_fails():
    text = _folded("skills/track/references/codemap-brief.md")
    assert "Without that line, or on any exit other than 0, stop here: add no line" in text
    assert "Any exit other than 0: add no line" in text
    assert "Anything else: add no line" in text
    assert "Never run `build` here" in text
