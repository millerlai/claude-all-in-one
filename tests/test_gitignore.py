"""R2: the ledger must not dirty `git status`.

Asserting that `.gitignore` contains a string would not prove this -- a
pattern can be present and still not match the path, or be overridden by a
later rule. Ask git what it actually does with the path instead.
"""
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_ignore(path):
    return subprocess.run(["git", "check-ignore", path], cwd=ROOT,
                          capture_output=True, text=True).returncode


def test_git_ignores_a_tracks_state_and_ledger():
    assert check_ignore(".claude/track/billing-export/ledger.jsonl") == 0
    assert check_ignore(".claude/track/billing-export/state.md") == 0


def test_the_repos_own_shared_settings_stay_tracked():
    # `.claude/settings.json` carries this repo's hooks and is committed. An
    # over-broad `.claude/` rule would silently drop it from everyone's tree.
    assert check_ignore(".claude/settings.json") == 1


def test_the_rule_provenance_ledger_is_tracked_despite_the_docs_ignore():
    """The provenance ledger (docs/rule-provenance.md) is a different thing
    from the attempt ledger this file's own header docstring describes --
    same word, unrelated concept. `.gitignore` ignores docs/ wholesale, so
    this file only stays tracked because someone ran `git add -f` on it.
    `git ls-files` lists tracked paths; that's the semantic R2's acceptance
    criterion and intake already depend on, so this doesn't add a new git
    claim, only a new assertion on it.
    """
    done = subprocess.run(["git", "ls-files", "docs/rule-provenance.md"],
                          cwd=ROOT, capture_output=True, text=True)
    assert done.stdout.strip()
