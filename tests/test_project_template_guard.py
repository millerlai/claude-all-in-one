"""#90: the project CLAUDE.md template keeps all of its guidance as prose
inside HTML comments, with no `- ` bullet lines -- so a rules-overlap check
that compares bullet lines, the way the user template's check does, sees
nothing in it and stays green whatever the template says. This pins that the
check validate.py runs over the project template actually goes red when a
rule sentence is pasted into it, rewrapped the way prose in a comment would
be.

Same breach shape as test_evals_guard.py's test_grader_type_breach_is_caught:
copy the repo, read bytes, assert the precondition, mutate the copy, run,
assert. The copy keeps the breach away from anything else reading the real
tree at the same time, such as another pytest-xdist worker (#221).
"""
import os
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join("plugins", "cai", "templates", "CLAUDE-project.md.tpl")
CODING_RULE = os.path.join(REPO_ROOT, "plugins", "cai", "rules", "coding.md")

LABEL = "project template does not restate rules"
RULE_SENTENCE = "Prefer pure functions; avoid hidden global state."
ANCHOR = b"## Conventions\n\n<!--"


def _copy_repo(tmp_path):
    dest = os.path.join(str(tmp_path), "repo")
    shutil.copytree(REPO_ROOT, dest, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", ".coverage*"))
    return dest


def test_a_rule_sentence_pasted_into_the_project_template_is_caught(tmp_path):
    with open(CODING_RULE, encoding="utf-8") as fh:
        assert RULE_SENTENCE in fh.read(), "expected a real rule sentence"
    repo = _copy_repo(tmp_path)
    template = os.path.join(repo, TEMPLATE)
    with open(template, "rb") as fh:
        original = fh.read()
    assert ANCHOR in original, "expected the template's Conventions comment"
    # Wrapped across two lines, as it would be inside a comment block.
    pasted = b" Prefer pure functions;\n     avoid hidden global state."
    mutated = original.replace(ANCHOR, ANCHOR + pasted, 1)
    with open(template, "wb") as fh:
        fh.write(mutated)
    # Skips the hook self-tests, which re-run validate.py twice -- two thirds
    # of a run -- and which this test does not read. The env is built here,
    # not at import: conftest's autouse fixtures set CAI_USAGE_LEDGER.
    result = subprocess.run(
        [sys.executable, os.path.join("scripts", "validate.py")], cwd=repo,
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "CAI_VALIDATE_NESTED": "1"})
    lines = [l for l in result.stdout.splitlines() if LABEL in l]
    assert lines, result.stdout
    assert all(l.startswith("FAIL") for l in lines), lines
