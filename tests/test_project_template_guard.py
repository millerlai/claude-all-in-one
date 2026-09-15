"""#90: the project CLAUDE.md template keeps all of its guidance as prose
inside HTML comments, with no `- ` bullet lines -- so a rules-overlap check
that compares bullet lines, the way the user template's check does, sees
nothing in it and stays green whatever the template says. This pins that the
check validate.py runs over the project template actually goes red when a
rule sentence is pasted into it, rewrapped the way prose in a comment would
be.

Same breach shape as test_evals_guard.py's test_grader_type_breach_is_caught:
read bytes, assert the precondition, mutate/run/assert in a try block,
restore in finally.
"""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATE = os.path.join(REPO_ROOT, "scripts", "validate.py")
TEMPLATE = os.path.join(REPO_ROOT, "plugins", "cai", "templates", "CLAUDE-project.md.tpl")
CODING_RULE = os.path.join(REPO_ROOT, "plugins", "cai", "rules", "coding.md")

LABEL = "project template does not restate rules"
RULE_SENTENCE = "Prefer pure functions; avoid hidden global state."
ANCHOR = b"## Conventions\n\n<!--"


def test_a_rule_sentence_pasted_into_the_project_template_is_caught():
    with open(CODING_RULE, encoding="utf-8") as fh:
        assert RULE_SENTENCE in fh.read(), "expected a real rule sentence"
    with open(TEMPLATE, "rb") as fh:
        original = fh.read()
    assert ANCHOR in original, "expected the template's Conventions comment"
    # Wrapped across two lines, as it would be inside a comment block.
    pasted = b" Prefer pure functions;\n     avoid hidden global state."
    mutated = original.replace(ANCHOR, ANCHOR + pasted, 1)
    try:
        with open(TEMPLATE, "wb") as fh:
            fh.write(mutated)
        result = subprocess.run(
            [sys.executable, VALIDATE], cwd=REPO_ROOT,
            capture_output=True, text=True, encoding="utf-8")
        lines = [l for l in result.stdout.splitlines() if LABEL in l]
        assert lines, result.stdout
        assert all(l.startswith("FAIL") for l in lines), lines
    finally:
        with open(TEMPLATE, "wb") as fh:
            fh.write(original)
