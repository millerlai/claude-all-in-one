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
validate.py's `evals` section is shared across the tests that don't need to
mutate anything.

The tests that do mutate work on a copy of the repo, never the real tree:
another pytest-xdist worker, or a validate.py run started by hand, reads the
real tree at the same time and would see the breach (#221).
"""
import os
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATE = os.path.join(REPO_ROOT, "scripts", "validate.py")

_VALIDATE_RESULT = []


def _copy_repo(tmp_path):
    dest = os.path.join(str(tmp_path), "repo")
    shutil.copytree(REPO_ROOT, dest, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", ".coverage*"))
    return dest


# Both runs name the one section these checks live in (#305); the rest of
# validate.py is some 380 child processes nothing here reads. The env is built
# per call: conftest's autouse fixtures set this test's CAI_USAGE_LEDGER in
# os.environ.
def _run_validate_in(repo):
    return subprocess.run(
        [sys.executable, os.path.join("scripts", "validate.py"), "evals"], cwd=repo,
        capture_output=True, text=True, encoding="utf-8")


def _run_validate():
    if not _VALIDATE_RESULT:
        _VALIDATE_RESULT.append(subprocess.run(
            [sys.executable, VALIDATE, "evals"], cwd=REPO_ROOT,
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
    "plugins", "cai", "evals", "track-status-runs-the-script",
    "graders", "names-track-state-script.md")

# R5 in the design doc: a leftover file here ships to every user, so name it
# so an interruption leaves something self-evidently wrong rather than
# something that could pass for a real fixture. It is written into a copy
# now, so an interruption leaves nothing in the real tree either way.
BREACH_FIXTURE = os.path.join(
    "plugins", "cai", "evals", "_breach_test_fake_secret.md")


def test_grader_type_label_still_runs():
    assert GRADER_TYPE_LABEL_FRAGMENT in _run_validate().stdout


def test_secrets_aggregate_labels_still_run():
    out = _run_validate().stdout
    for fragment in SECRETS_AGGREGATE_LABEL_FRAGMENTS:
        assert fragment in out, fragment


def test_grader_type_breach_is_caught(tmp_path):
    """Mirrors test_uc4_report_check_is_anchored_to_the_real_heading's shape:
    copy the repo, read bytes, assert the precondition, mutate the copy, run,
    assert. `claude plugin eval init --bare` defaults a new
    grader's type to `llm`, which is not in the allowed set -- so this is
    the realistic breach, not a synthetic one.
    """
    repo = _copy_repo(tmp_path)
    grader = os.path.join(repo, GRADER_UNDER_TEST)
    with open(grader, "rb") as fh:
        original = fh.read()
    assert b"type: regex" in original, "expected the real grader's real type"
    mutated = original.replace(b"type: regex", b"type: llm", 1)
    with open(grader, "wb") as fh:
        fh.write(mutated)
    result = _run_validate_in(repo)
    rel = GRADER_UNDER_TEST.replace(os.sep, "/")
    grader_lines = [
        l for l in result.stdout.splitlines()
        if rel in l.replace(os.sep, "/")
        and "frontmatter has an allowed type" in l]
    assert grader_lines, result.stdout
    assert all(l.startswith("FAIL") for l in grader_lines), grader_lines


def test_grader_type_quoted_value_still_passes(tmp_path):
    """`frontmatter_value()` must strip quotes the same way its sibling
    `frontmatter_description()` already does (scripts/validate.py:113-114):
    `type: "regex"` is a plainly valid, semantically identical YAML scalar to
    `type: regex`, and the same file's own `pattern:` fields are already
    quoted (e.g. design-gate-is-a-menu/graders/label-changes-requested.md's
    `pattern: "Changes requested"`), so a contributor quoting `type:` too is
    a realistic edit, not a synthetic one. Without stripping, a legitimate
    grader would FAIL UC1's check.
    """
    repo = _copy_repo(tmp_path)
    grader = os.path.join(repo, GRADER_UNDER_TEST)
    with open(grader, "rb") as fh:
        original = fh.read()
    assert b"type: regex" in original, "expected the real grader's real type"
    mutated = original.replace(b"type: regex", b'type: "regex"', 1)
    with open(grader, "wb") as fh:
        fh.write(mutated)
    result = _run_validate_in(repo)
    rel = GRADER_UNDER_TEST.replace(os.sep, "/")
    grader_lines = [
        l for l in result.stdout.splitlines()
        if rel in l.replace(os.sep, "/")
        and "frontmatter has an allowed type" in l]
    assert grader_lines, result.stdout
    assert all(l.startswith("PASS") for l in grader_lines), grader_lines


def test_secrets_breach_is_caught(tmp_path):
    """A fake ghp_ token dropped anywhere under plugins/cai/evals/ must flip
    the ghp_ aggregate check to FAIL and name the offending file, the same
    way the BOM aggregate check at scripts/validate.py:636-650 names its
    offenders.
    """
    repo = _copy_repo(tmp_path)
    fixture = os.path.join(repo, BREACH_FIXTURE)
    assert not os.path.exists(fixture), "fixture already present"
    with open(fixture, "w", encoding="utf-8") as fh:
        fh.write("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\n")
    result = _run_validate_in(repo)
    ghp_lines = [l for l in result.stdout.splitlines() if "ghp_" in l]
    assert any(l.startswith("FAIL") for l in ghp_lines), ghp_lines
    rel = BREACH_FIXTURE.replace(os.sep, "/")
    assert any(rel in l.replace(os.sep, "/")
               for l in result.stdout.splitlines()), result.stdout
