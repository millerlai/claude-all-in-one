"""UC3 for the evals guard: the checks `validate.py` runs over
`plugins/cai/evals/` are themselves unguarded unless something asserts they
still run at all, mirroring `test_guardrail_hardening_checks_still_run.py`'s
reason for existing. Deleting one of the new `check()` calls -- the grader
`type:` frontmatter check, or any of the three secrets aggregates -- would
otherwise leave `validate.py` exit 0 with nobody noticing.

`evals/` is "shipped but not theirs" (CLAUDE.md): it reaches every installed
copy but no shipped component invokes it, so nothing else in this repo reads
it either -- these are the only checks it gets.

Same `_run_validate()` caching pattern as
`test_guardrail_hardening_checks_still_run.py`: a single subprocess run of
validate.py is shared across the tests that don't need to mutate anything,
since the full run takes tens of seconds.
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


# The grader-type check's label fragment -- one check() call per grader file
# under plugins/cai/evals/*/graders/*.md.
GRADER_TYPE_LABEL_FRAGMENT = "frontmatter has an allowed type"

# The three secrets/home-dir aggregate checks' label fragments.
SECRETS_AGGREGATE_LABEL_FRAGMENTS = (
    "sk-ant-",
    "ghp_",
    "home-directory path",
)

GRADER_UNDER_TEST = os.path.join(
    REPO_ROOT, "plugins", "cai", "evals", "track-status-runs-the-script",
    "graders", "names-track-state-script.md")

# R5 in the design doc: a leftover file here ships to every user, so name it
# so an interruption leaves something self-evidently wrong rather than
# something that could pass for a real fixture.
BREACH_FIXTURE = os.path.join(
    REPO_ROOT, "plugins", "cai", "evals", "_breach_test_fake_secret.md")


def test_grader_type_label_still_runs():
    assert GRADER_TYPE_LABEL_FRAGMENT in _run_validate().stdout


def test_secrets_aggregate_labels_still_run():
    out = _run_validate().stdout
    for fragment in SECRETS_AGGREGATE_LABEL_FRAGMENTS:
        assert fragment in out, fragment


def test_grader_type_breach_is_caught():
    """Mirrors test_uc4_report_check_is_anchored_to_the_real_heading's shape:
    read bytes, assert the precondition, mutate/run/assert in a try block,
    restore in finally. `claude plugin eval init --bare` defaults a new
    grader's type to `llm`, which is not in the allowed set -- so this is
    the realistic breach, not a synthetic one.
    """
    with open(GRADER_UNDER_TEST, "rb") as fh:
        original = fh.read()
    assert b"type: regex" in original, "expected the real grader's real type"
    mutated = original.replace(b"type: regex", b"type: llm", 1)
    try:
        with open(GRADER_UNDER_TEST, "wb") as fh:
            fh.write(mutated)
        result = subprocess.run(
            [sys.executable, VALIDATE], cwd=REPO_ROOT,
            capture_output=True, text=True, encoding="utf-8")
        rel = os.path.relpath(GRADER_UNDER_TEST, REPO_ROOT).replace(os.sep, "/")
        grader_lines = [
            l for l in result.stdout.splitlines()
            if rel in l.replace(os.sep, "/")
            and "frontmatter has an allowed type" in l]
        assert grader_lines, result.stdout
        assert all(l.startswith("FAIL") for l in grader_lines), grader_lines
    finally:
        with open(GRADER_UNDER_TEST, "wb") as fh:
            fh.write(original)


def test_secrets_breach_is_caught():
    """A fake ghp_ token dropped anywhere under plugins/cai/evals/ must flip
    the ghp_ aggregate check to FAIL and name the offending file, the same
    way the BOM aggregate check at scripts/validate.py:636-650 names its
    offenders.
    """
    assert not os.path.exists(BREACH_FIXTURE), "fixture already present"
    try:
        with open(BREACH_FIXTURE, "w", encoding="utf-8") as fh:
            fh.write("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\n")
        result = subprocess.run(
            [sys.executable, VALIDATE], cwd=REPO_ROOT,
            capture_output=True, text=True, encoding="utf-8")
        ghp_lines = [l for l in result.stdout.splitlines() if "ghp_" in l]
        assert any(l.startswith("FAIL") for l in ghp_lines), ghp_lines
        rel = os.path.relpath(BREACH_FIXTURE, REPO_ROOT).replace(os.sep, "/")
        assert any(rel in l.replace(os.sep, "/")
                   for l in result.stdout.splitlines()), result.stdout
    finally:
        if os.path.exists(BREACH_FIXTURE):
            os.remove(BREACH_FIXTURE)
