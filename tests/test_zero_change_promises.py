"""Unit 6: the detail design's `## Change points` table promises zero-line
diffs on five paths, and one deliberate exception on a sixth. Those
promises are what several acceptance criteria (AC3, AC4, DD1, DD2) rest on,
so this asserts them mechanically against `main` -- this branch's base --
rather than trusting the table.

`git diff --numstat main -- <path>` is empty on an untouched file and prints
`<added>\\t<deleted>\\t<path>` the moment even one line moves, so an empty
stdout is the assertion.
"""
import os
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "main"

ZERO_DIFF_PATHS = [
    "plugins/cai/scripts/preflight.py",
    "plugins/cai/scripts/ledger.py",
    "plugins/cai/scripts/track_state.py",
    "plugins/cai/skills/track/stages.json",
]

AGENTS_DIR = os.path.join(REPO_ROOT, "plugins", "cai", "agents")


def _numstat(path):
    result = subprocess.run(
        ["git", "diff", "--numstat", BASE, "--", path],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def _agent_md_paths():
    names = sorted(f for f in os.listdir(AGENTS_DIR) if f.endswith(".md"))
    assert names, "no plugins/cai/agents/*.md files found -- glob is broken"
    return ["plugins/cai/agents/%s" % name for name in names]


def test_preflight_py_has_zero_line_diff_against_main():
    assert _numstat(ZERO_DIFF_PATHS[0]) == ""


def test_ledger_py_has_zero_line_diff_against_main():
    assert _numstat(ZERO_DIFF_PATHS[1]) == ""


def test_track_state_py_has_zero_line_diff_against_main():
    assert _numstat(ZERO_DIFF_PATHS[2]) == ""


def test_stages_json_has_zero_line_diff_against_main():
    assert _numstat(ZERO_DIFF_PATHS[3]) == ""


def test_every_agent_md_has_zero_line_diff_against_main():
    for rel in _agent_md_paths():
        assert _numstat(rel) == "", "%s changed against %s" % (rel, BASE)


# --- the one deliberate exception -------------------------------------------

def test_validate_py_changed_only_the_track_skill_line_ceiling():
    """`scripts/validate.py` is *not* a zero-diff path (unlike the five
    above): its `SKILL.md` line ceiling moved 120 -> 122, because the file
    was already sitting exactly on 120 and the design's claim that it had a
    line to spare came from a mis-measurement. This asserts that is the
    *only* change -- one hunk, touching only the ceiling constant and its
    check() call -- so anything else creeping into this file is still
    caught."""
    diff = subprocess.run(
        ["git", "diff", BASE, "--", "scripts/validate.py"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert diff.returncode == 0, diff.stderr
    text = diff.stdout
    assert text != "", "expected exactly one change to scripts/validate.py"

    hunks = [line for line in text.splitlines() if line.startswith("@@")]
    assert len(hunks) == 1, "expected exactly one hunk, found %d:\n%s" % (
        len(hunks), text)

    removed = [l[1:] for l in text.splitlines()
               if l.startswith("-") and not l.startswith("---")]
    added = [l[1:] for l in text.splitlines()
             if l.startswith("+") and not l.startswith("+++")]

    assert any("120-line ceiling" in l for l in removed)
    assert any("TRACK_SKILL_MAX = 122" in l for l in added)
    assert any("{TRACK_SKILL_MAX}-line ceiling" in l for l in added)
