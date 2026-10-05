"""The reduced check (no working Python) blocks `gh pr merge`.

Without Python the guard cannot ask, and nothing may let a merge through
unasked (stance I3), so `reduced-check-patterns.txt` carries two merge rows and
the person runs the command themselves. The check matches the whole hook input,
quoted text included, so a message that merely mentions a merge is blocked too:
a known, accepted over-block.

bash_guard.BLOCKED does not contain merge (it asks instead), so
tests/test_open_issues.py's comparison against BLOCKED cannot cover these rows.
"""
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

HOOKS = Path("plugins/cai/hooks")
PATTERN_FILE = HOOKS / "reduced-check-patterns.txt"
LAUNCHER = HOOKS / "run-guard.cmd"


@pytest.fixture
def pattern_copy(tmp_path):
    """A private copy: findstr /G: holds its pattern file open exclusively, and
    under xdist that collides with other tests copying plugins/cai (see
    tests/test_open_issues.py's fixture of the same name)."""
    copy = tmp_path / "patterns.txt"
    for _ in range(20):
        try:
            copy.write_bytes(PATTERN_FILE.read_bytes())
            return copy
        except PermissionError:
            time.sleep(0.05)
    raise AssertionError("could not read %s" % PATTERN_FILE)


def _hits(payload_text, patterns):
    """0 when the tool the dispatcher uses on this platform matches, 1 when not."""
    if os.name == "nt":
        argv = ["findstr", "/R", "/G:" + str(patterns)]
    else:
        argv = ["grep", "-q", "-f", str(patterns)]
    return subprocess.run(argv, input=payload_text, capture_output=True,
                          text=True).returncode


MERGES = [
    "gh pr merge 123",
    "gh pr merge 123 --squash",
    "gh pr merge --auto 123",
    "gh -R owner/repo pr merge 123",
    "gh --repo=owner/repo pr merge 123",
    "gh pr  merge 123",
    "true && gh pr merge 1",
    "if true; then gh pr merge 1; fi",
    "bash -c 'gh pr merge 1'",
    "gh api -X PUT repos/owner/repo/pulls/123/merge",
    "gh api --method POST repos/owner/repo/pulls/123/merge",
    "gh --repo owner/repo api -X PUT repos/o/r/pulls/5/merge",
]

NOT_MERGES = [
    "gh pr view 123",
    "gh pr list",
    "gh pr create --title x --body y",
    "gh pr checks 123",
    "git merge feature-branch",
    "gh api repos/owner/repo/pulls/123/comments",
    "gh api repos/owner/repo/pulls",
    "git status",
]


@pytest.mark.parametrize("compact", [True, False])
def test_the_pattern_file_hits_every_merge_and_no_other_gh_command(compact, pattern_copy):
    separators = (",", ":") if compact else None
    for command, expected in [(c, 0) for c in MERGES] + [(c, 1) for c in NOT_MERGES]:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}},
                             separators=separators)
        assert _hits(payload, pattern_copy) == expected, command


def test_both_launcher_blocks_name_merge_in_their_message():
    # The CMD block and the sh block each print what the reduced check covers;
    # a merge that is blocked but unlisted would read as a bug to the person.
    lines = [ln for ln in LAUNCHER.read_text(encoding="ascii").splitlines()
             if "cai guard reduced check:" in ln]
    assert len(lines) == 2, lines
    for line in lines:
        assert "gh pr merge" in line, line
