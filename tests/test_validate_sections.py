"""#305: validate.py ran top to bottom at import, so a test that cared about
one check -- a breach planted in a copy, a label that must still print --
paid for the whole script: some 380 child processes, a third of a minute
plain and twice that under `pytest --cov`. Naming sections on the command
line runs only those; no name still runs everything, which is what CI, the
PostToolUse hook and a person typing it get.
"""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATE = os.path.join(REPO_ROOT, "scripts", "validate.py")


# The env is built per call: conftest's autouse fixtures set this test's
# CAI_USAGE_LEDGER in os.environ.
def _run(*sections):
    return subprocess.run([sys.executable, VALIDATE, *sections], cwd=REPO_ROOT,
                          capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "CAI_VALIDATE_NESTED": "1"})


def test_a_named_section_runs_only_its_own_checks():
    done = _run("evals")

    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]
    checks = [l for l in done.stdout.splitlines() if l.startswith(("PASS ", "FAIL "))]
    assert checks, done.stdout
    assert any("frontmatter has an allowed type" in l for l in checks), checks
    # The guard cases are the bulk of a full run; none of them belongs here.
    assert not any(l.startswith("PASS guard ") for l in checks), checks


def test_a_selective_run_says_what_it_skipped():
    """Same reason the hook self-tests print their SKIP line: a green run
    must say what it did not check, or a partial run reads as a full one."""
    done = _run("evals", "provenance")

    skip = [l for l in done.stdout.splitlines() if l.startswith("SKIP ")]
    assert len(skip) == 1, done.stdout
    assert "evals" in skip[0] and "provenance" in skip[0], skip


def test_an_unknown_section_fails_before_any_check_runs():
    done = _run("no-such-section")

    assert done.returncode == 2
    assert "no-such-section" in done.stderr
    # The message lists the real names, so a typo can be fixed from it.
    assert "evals" in done.stderr
    assert not [l for l in done.stdout.splitlines() if l.startswith(("PASS ", "FAIL "))]
