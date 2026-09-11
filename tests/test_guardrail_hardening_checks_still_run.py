"""Issue #64's convention, applied to this track's own checks: the guards
`validate.py` runs are themselves unguarded unless something asserts they
still run at all. Deleting a `check()` call leaves `validate.py` exit 0 --
nothing else in this repo would notice.

Mirrors `tests/test_track_skill_ticket_pointer.py`'s
`test_every_prose_guard_in_the_track_skill_block_still_runs`: one short,
stable fragment per check (a reasonable label reword must not turn this
red), plus a count for the three restatement checks that share one label
shape. A single subprocess run of validate.py is cached and shared across
every test in this file -- the full run takes tens of seconds, and this
file's tests would otherwise pay for it three times over.
"""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATE = os.path.join(REPO_ROOT, "scripts", "validate.py")

_VALIDATE_RESULT = []


def _run_validate():
    if not _VALIDATE_RESULT:
        _VALIDATE_RESULT.append(subprocess.run(
            [sys.executable, VALIDATE], cwd=REPO_ROOT,
            capture_output=True, text=True, encoding="utf-8"))
    return _VALIDATE_RESULT[0]


# UC1: the provenance ledger's six checks.
UC1_FRAGMENTS = (
    "the provenance ledger is present",
    "the provenance ledger has entries",
    "carry all five fields",
    "entry ids are unique",
    "Cited by targets all resolve",
    "does not @-import the provenance ledger",
)

# UC2: the derivation check plus the three restatement checks, which share
# one label shape -- counted, not fragment-matched, for the same reason
# stage-build.md's three table-shape guards are counted in the #64 test.
UC2_DERIVED_FRAGMENT = "the parallel cap is derivable from model-selection.md"
UC2_RESTATED_FRAGMENT = "still restates the parallel cap"

# UC4: the three pinned-clause checks over stage-verify.md's own sections.
UC4_FRAGMENTS = (
    "Step 2 still requires every finding to name a requirement",
    "Fixing section still refuses untraceable findings",
    "Report section still asks for parked proposals",
)


def test_uc1_ledger_checks_still_run():
    out = _run_validate().stdout
    for fragment in UC1_FRAGMENTS:
        assert fragment in out, fragment


def test_uc2_parallel_cap_checks_still_run():
    out = _run_validate().stdout
    assert UC2_DERIVED_FRAGMENT in out
    restated = [l for l in out.splitlines() if UC2_RESTATED_FRAGMENT in l]
    assert len(restated) == 3, restated


def test_uc4_stage_verify_pinned_clause_checks_still_run():
    out = _run_validate().stdout
    for fragment in UC4_FRAGMENTS:
        assert fragment in out, fragment


def test_uc4_report_check_is_anchored_to_the_real_heading():
    """Regression for an unanchored-find() bug in validate.py's
    verify_section(): stage-verify.md's own Report section quotes
    "## Report" in backticks, describing itself, a few lines below the real
    heading. A plain find(heading) matches that backticked mention once the
    real heading is renamed or deleted, slices decoy-to-EOF, and the slice
    still contains the pinned clause -- passing on a section that no longer
    exists. This mutates the real file and restores it byte-for-byte in a
    finally block, the same way the validate_hook probe above breaks and
    then removes its own throwaway fixture; it cannot share `_run_validate`'s
    cached result since it needs a run against altered content.
    """
    path = os.path.join(
        REPO_ROOT, "plugins", "cai", "skills", "track", "references",
        "stage-verify.md")
    with open(path, "rb") as fh:
        original = fh.read()
    assert original.count(b"\n## Report\n") == 1, "expected one real heading"
    mutated = original.replace(b"\n## Report\n", b"\n## Handback\n", 1)
    try:
        with open(path, "wb") as fh:
            fh.write(mutated)
        result = subprocess.run(
            [sys.executable, VALIDATE], cwd=REPO_ROOT,
            capture_output=True, text=True, encoding="utf-8")
        report_lines = [
            l for l in result.stdout.splitlines()
            if "Report section still asks for parked" in l]
        assert report_lines == [
            "FAIL stage-verify.md's Report section still asks for parked "
            "proposals"], report_lines
    finally:
        with open(path, "wb") as fh:
            fh.write(original)
