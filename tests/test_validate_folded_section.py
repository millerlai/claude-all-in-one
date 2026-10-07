"""validate.py's `folded_section` (track-references) pins sentences that make the
model use verify_plan.py and local_run.py. Its two `return ""` exits -- the file
is gone, the heading is gone -- are what turn a deleted or renamed reference into
a FAIL line naming the pin, instead of a crash that hides every later check.

The section runs in this process, on the checked-in scripts/validate.py, with
the working directory moved into a damaged copy of the repo (validate.py reads
every path relative to the cwd). In process rather than as a child, so the lines
it executes are credited to the checked-in file by `pytest --cov` whatever
directory the child's coverage would have resolved its relative `source` in.
`main()` is not called: it repoints `tempfile.tempdir` and registers an atexit.
"""
import importlib.util
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATE = REPO_ROOT / "scripts" / "validate.py"
REFS = "plugins/cai/skills/track/references"


@pytest.fixture
def validate_module():
    spec = importlib.util.spec_from_file_location("validate_under_test", VALIDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_repo(tmp_path):
    common = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".coverage*")

    def ignore(src, names):
        # .claude/track holds live per-track state, among it a timing.jsonl a hook
        # keeps open (WinError 33 on Windows); this section reads none of it.
        skipped = set(common(src, names))
        if Path(src) == REPO_ROOT / ".claude" and "track" in names:
            skipped.add("track")
        return skipped

    dest = tmp_path / "repo"
    shutil.copytree(REPO_ROOT, dest, ignore=ignore)
    return dest


def test_a_missing_reference_and_a_renamed_heading_fail_their_pins_without_a_crash(
        tmp_path, monkeypatch, capsys, validate_module):
    repo = _copy_repo(tmp_path)
    refs = repo / REFS
    # approval-gates.md is the one pinned file validate.py reads only behind an
    # isfile guard everywhere else; deleting any other pinned file would crash
    # an unguarded read before the pin is reached.
    (refs / "approval-gates.md").unlink()  # the file is gone
    pending = refs / "pending-questions.md"
    original = pending.read_bytes()
    renamed = original.replace(b"# pending-questions", b"# queued-questions", 1)
    assert renamed != original  # the heading existed, so the rename took
    pending.write_bytes(renamed)  # the file is there, its heading is not
    monkeypatch.chdir(repo)

    validate_module._track_references()  # a crash here is the failure being guarded

    lines = capsys.readouterr().out.splitlines()
    failed = [l for l in lines if l.startswith("FAIL ")]
    assert validate_module.FAIL == 1
    assert any(l.startswith("FAIL AC6: approval-gates.md's The merge lists verify_plan.py")
               for l in failed), failed
    assert any(l.startswith("FAIL AC15: pending-questions.md has the main session run the "
                            "command the chosen option carries") for l in failed), failed
    # The pins in files left alone still pass: only the two damaged ones went red.
    assert any(l.startswith("PASS AC7: stage-build.md's Step 3 takes the local-run baseline")
               for l in lines), lines[-20:]
