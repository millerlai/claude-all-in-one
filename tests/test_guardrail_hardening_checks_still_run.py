"""Issue #64's convention, applied to this track's own checks: the guards
`validate.py` runs are themselves unguarded unless something asserts they
still run at all. Deleting a `check()` call leaves `validate.py` exit 0 --
nothing else in this repo would notice.

The provenance ledger's checks now all funnel through one subprocess call
to `provenance.py` (its `probes()` output is relayed line-by-line into
`check()`), rather than several hand-written blocks in validate.py -- so
there is no longer a UC1/UC2 split to pin separately; one test asserts all
six probe labels still appear.

Mirrors `tests/test_track_skill_ticket_pointer.py`'s
`test_every_prose_guard_in_the_track_skill_block_still_runs`: one short,
stable fragment per check (a reasonable label reword must not turn this
red). A single subprocess run of validate.py is cached and shared across
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


# The provenance ledger's six probe labels, relayed from provenance.py's
# probes() into validate.py's check() calls. Only the bare label name, not
# the parenthesised count -- that count changes as ledger data grows.
PROVENANCE_PROBE_LABELS = (
    "entry_fields_complete",
    "entry_ids_unique",
    "cited_by_resolves",
    "rule_quote_in_cited_section",
    "restated_quote_in_section",
    "shared_value_in_every_quote",
)

# A check unrelated to provenance.py's job -- it reads CLAUDE.md's own text,
# not the ledger's entries -- that used to live in the same deleted span by
# line-range coincidence and is kept in validate.py on purpose (issue #78
# build notes). Pinned separately so dropping it again would still be
# caught by this file's own reason for existing.
CLAUDE_MD_IMPORT_FRAGMENT = "does not @-import the provenance ledger"

# UC4: the three pinned-clause checks over stage-verify.md's own sections.
UC4_FRAGMENTS = (
    "Step 2 still requires every finding to name a requirement",
    "Fixing section still refuses untraceable findings",
    "Report section still asks for parked proposals",
)

# Pins scripts/validate.py's own check on the provenance.py subprocess call's
# exit code, not just its relayed PASS/FAIL lines -- a crash (exit 1, no
# PASS/FAIL output at all) would otherwise relay zero checks and leave this
# script exit 0, silently invisible.
PROVENANCE_SUBPROCESS_HEALTH_FRAGMENT = "provenance.py subprocess did not crash"


def test_provenance_probe_labels_still_run():
    out = _run_validate().stdout
    for label in PROVENANCE_PROBE_LABELS:
        assert label in out, label


def test_provenance_probes_all_pass_on_the_real_ledger():
    # docs/rule-provenance.md:51's fix (this feature's own reason for
    # existing) has no regression coverage otherwise: the test above only
    # asserts each probe label appears somewhere in stdout, regardless of
    # PASS or FAIL, so a reintroduced drift would go unnoticed here.
    out = _run_validate().stdout
    for label in PROVENANCE_PROBE_LABELS:
        lines = [l for l in out.splitlines()
                 if l.startswith("PASS " + label) or l.startswith("FAIL " + label)]
        assert lines, label
        for line in lines:
            assert line.startswith("PASS "), line


def test_provenance_subprocess_health_check_still_runs():
    assert PROVENANCE_SUBPROCESS_HEALTH_FRAGMENT in _run_validate().stdout


def test_claude_md_does_not_import_the_ledger_check_still_runs():
    assert CLAUDE_MD_IMPORT_FRAGMENT in _run_validate().stdout


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
