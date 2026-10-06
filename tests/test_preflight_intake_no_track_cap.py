"""#309: intake no longer caps how many tracks may be open at once. The cap
blocked a sixth feature for no reason a person could act on -- how many
features they carry is theirs to decide."""
import os
import subprocess
import sys

import preflight

PREFLIGHT_PY = os.path.join(os.path.dirname(preflight.__file__), "preflight.py")
TRACK_SKILL = os.path.join(os.path.dirname(preflight.__file__), "..",
                           "skills", "track", "SKILL.md")


def init_repo(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "work", str(path)], check=True)
    return path


def test_intake_passes_with_many_active_tracks(tmp_path):
    repo = init_repo(tmp_path / "repo")
    root = repo / ".claude" / "track"
    for i in range(10):
        (root / ("f%d" % i)).mkdir(parents=True)

    done = subprocess.run(
        [sys.executable, PREFLIGHT_PY, "intake", "--track-dir", str(root / "f-new"),
         "--project-dir", str(repo)],
        capture_output=True, text=True, encoding="utf-8")

    assert done.returncode == 0, done.stdout
    assert "active_tracks" not in done.stdout


def test_track_skill_does_not_refuse_a_sixth_track():
    with open(TRACK_SKILL, encoding="utf-8") as fh:
        text = fh.read()
    assert "instead of creating a sixth" not in text
