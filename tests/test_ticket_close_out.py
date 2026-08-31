"""Unit 6: closing out ticket-integration -- AC4 and AC8.

AC4's `validate.py` half is already asserted by
tests/test_track_skill_ticket_pointer.py's
test_validate_exits_0_with_zero_fail_lines; nothing here duplicates that run
(see that file's own docstring on why a second independent run is not free
-- three separate runs took the suite from 13 seconds to 90). AC4's other
half -- `python -m pytest` itself fully green -- is not something a test
inside that same run can assert without being circular; it is verified
operationally, by actually running the suite.

AC8 is what this file exists for: after a track runs end to end, none of
the files it writes may hold a credential.
"""
import json
import os
import subprocess

import pytest

import ledger
import ticket
import usage_collector

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A plain case-insensitive substring grep, matching the design's own AC8
# wording -- a false positive (one of these words turning up in ordinary
# text) would just fail the test loudly enough to be noticed and adjusted,
# never silently pass, so no word-boundary logic is needed here.
FORBIDDEN = ("token", "password", "authorization", "bearer", "api_key")


def _grep_forbidden(text):
    low = text.lower()
    return [word for word in FORBIDDEN if word in low]


SIX_ROWS = [
    ("intake", "done", "docs/design/x-intake.md", "signed off"),
    ("discover", "skipped", "-", "reason: closed at the program layer"),
    ("design", "done", "docs/design/x-detail.md", "HLD and detail both signed off"),
    ("build", "passed", "-", ""),
    ("verify", "passed", "-", ""),
    ("ship", "passed", "-", ""),
]


def _make_state_md(track_dir, rows=SIX_ROWS):
    lines = ["# fixture", "", "branch: feat/fixture", "started: 2026-08-29", "",
             "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track_dir / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_a_track(track_dir, project_dir):
    """Simulates one track running end to end: six ledger records (a
    realistic note on each, the same shape the real stages write) plus one
    ticket-mirror projection through the no-network `local-stub` backend --
    close enough to a real run to be what AC8 is about, without touching
    the network."""
    track_dir.mkdir()
    _make_state_md(track_dir)
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "cai.json").write_text(
        json.dumps({"ticket": {"enabled": True, "backend": "local-stub"}}),
        encoding="utf-8")

    for stage, outcome, note in (
            ("intake", "passed", "signed off by the user"),
            ("discover", "skipped", "closed at the program layer"),
            ("design", "passed", "HLD and detail both signed off"),
            ("build", "passed", "tests green"),
            ("verify", "passed", "reviewer approved"),
            ("ship", "passed", "PR opened")):
        ledger.append(str(track_dir), stage, outcome, note=note)

    ticket.point(str(track_dir), "48", "local-stub")
    ticket.project(str(track_dir), str(project_dir))


def test_ac8_no_file_a_track_writes_holds_a_credential(tmp_path):
    track_dir = tmp_path / "track"
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _run_a_track(track_dir, project_dir)

    paths = {
        "ledger.jsonl": track_dir / "ledger.jsonl",
        "central ledger": usage_collector.central_ledger_path(),
        ".claude/cai.json": project_dir / ".claude" / "cai.json",
        "ticket.json": track_dir / "ticket.json",
        "state.md": track_dir / "state.md",
    }
    for label, path in paths.items():
        path = str(path)
        assert os.path.exists(path), "%s: %s does not exist" % (label, path)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        hits = _grep_forbidden(text)
        assert hits == [], "%s contains %r" % (label, hits)


def test_ac8_committed_cai_json_has_no_credential_markers():
    """The other half of AC8: the version-controlled copy, checked against
    its committed content rather than the working tree the test above
    already covers. Skipped while the file is still untracked, so the
    suite does not need the very commit that adds this test in order to
    pass -- otherwise this assertion is a trap for whoever runs it next."""
    rel = ".claude/cai.json"
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel],
        cwd=REPO_ROOT, capture_output=True, text=True)
    if tracked.returncode != 0:
        pytest.skip("%s is not tracked yet" % rel)

    shown = subprocess.run(
        ["git", "show", "HEAD:%s" % rel],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8")
    assert shown.returncode == 0, shown.stderr
    hits = _grep_forbidden(shown.stdout)
    assert hits == []
