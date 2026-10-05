"""bash_guard.py's `gh pr merge` handling (#194 follow-up).

Maintainer decision (2026-09-27): merging a PR is a human action, so the
guard neither blocks it nor lets it through silently -- it asks. Claude Code
supports a PreToolUse "ask" permission decision (a JSON blob on stdout, exit
0); Codex's hook host parses but does not yet act on one
(https://learn.chatgpt.com/docs/hooks: "permissionDecision: 'ask' ... parsed
but not supported yet"), so under Codex the guard denies instead (exit 2)
and hands the exact command back for the person to run themselves. The
launcher sets CAI_CODEX_GUARD=1 before invoking bash_guard.py so the guard
can tell which host it is running under without sniffing the payload.
"""
import json
import os
import subprocess
import sys

import pytest

GUARD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins", "cai", "scripts", "bash_guard.py")


@pytest.fixture
def feature_repo(tmp_path):
    """A throwaway repo sitting on a feature branch, used as the cwd of every
    guard call. Without it the guard judged each command against whatever
    branch this test run's own checkout was on: a PR's detached merge ref
    passed, but main's push CI runs on `main`, where the `git commit`
    look-alikes tripped the commit-on-a-protected-branch rule (#228 merged
    red)."""
    subprocess.run(["git", "init", "-b", "feat", str(tmp_path)],
                   capture_output=True, text=True)
    return str(tmp_path)


def run(command, cwd, tool="Bash", codex=False):
    env = dict(os.environ)
    if codex:
        env["CAI_CODEX_GUARD"] = "1"
    else:
        env.pop("CAI_CODEX_GUARD", None)
    return subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps({"tool_name": tool, "tool_input": {"command": command}, "cwd": cwd}),
        capture_output=True, text=True, env=env, cwd=cwd,
    )


ASK_COMMANDS = [
    "gh pr merge 123",
    "gh pr merge 123 --squash",
    "gh pr merge --auto 123",
    "gh pr merge --admin 123",
    "gh pr merge -R owner/repo 123",
    "gh pr merge --repo owner/repo 123",
    "gh pr merge --repo=owner/repo 123",
    "gh -Rowner/repo pr merge 123",
    "gh pr merge https://github.com/owner/repo/pull/123",
    "gh pr merge feature-branch",
    "gh api -X PUT repos/owner/repo/pulls/123/merge",
    "gh api --method POST repos/owner/repo/pulls/123/merge",
    "gh api repos/owner/repo/pulls/123/merge -X PUT",
    "gh --repo owner/repo api -X PUT repos/owner/repo/pulls/5/merge",
    "gh -R owner/repo api -X PUT repos/owner/repo/pulls/5/merge",
    "gh pr \\\n merge 123",
    # A merge the shell runs from a position other than the start of a
    # segment (l1c-interactive.md: all ten were let through unasked).
    "if true; then gh pr merge 1; fi",
    "if false; then :; else gh pr merge 1; fi",
    "for i in 1; do gh pr merge 1; done",
    "while false; do gh pr merge 1; done",
    "{ gh pr merge 1; }",
    "! gh pr merge 1",
    "time gh pr merge 1",
    "bash -c 'gh pr merge 1'",
    'sh -c "gh pr merge 1"',
    "bash -lc 'gh pr merge 1'",
    "bash -lc gh pr merge 1",
    "zsh -c 'gh pr merge 1'",
    "dash -c 'gh pr merge 1'",
    "bash -c \"bash -c 'gh pr merge 1'\"",
    "eval gh pr merge 1",
    'eval "gh pr merge 1"',
    "env gh pr merge 1",
    "env FOO=1 gh pr merge 1",
    "nohup gh pr merge 1",
    "command gh pr merge 1",
    "exec gh pr merge 1",
    "echo x | xargs gh pr merge",
    "echo x | xargs -n1 gh pr merge",
    # A wrapper's option may take its value as the next word (S1: wrappers
    # "with their options"): `{}` or `1` must not end the walk to `gh`.
    "gh pr list --json number -q '.[].number' | xargs -I {} gh pr merge {}",
    "echo x | xargs -n 1 gh pr merge",
    "env -u VAR gh pr merge 1",
    "bash -o pipefail -c 'gh pr merge 1'",
    'powershell -NoProfile -ExecutionPolicy Bypass -Command "gh pr merge 1"',
    "pwsh -Command 'gh pr merge 1'",
    "powershell -c \"gh pr merge 1\"",
    "Invoke-Expression 'gh pr merge 1'",
    "bash -c 'gh api -X PUT repos/o/r/pulls/5/merge'",
    "if true; then gh api -X PUT repos/o/r/pulls/5/merge; fi",
]


def test_claude_path_asks_instead_of_blocking_or_allowing_silently(feature_repo):
    for command in ASK_COMMANDS:
        done = run(command, feature_repo)
        assert done.returncode == 0, (command, done.stdout, done.stderr)
        payload = json.loads(done.stdout)
        out = payload["hookSpecificOutput"]
        assert out["hookEventName"] == "PreToolUse"
        assert out["permissionDecision"] == "ask"
        assert out["permissionDecisionReason"]


def test_codex_signal_denies_and_hands_back_the_command(feature_repo):
    for command in ASK_COMMANDS:
        done = run(command, feature_repo, codex=True)
        assert done.returncode == 2, (command, done.stdout, done.stderr)
        assert done.stdout == ""
        assert command in done.stderr
        assert "run it themselves" in done.stderr or "run it manually" in done.stderr


NOT_MERGE_COMMANDS = [
    "gh pr view 123",
    "gh pr list",
    "gh pr create --title x --body y",
    "gh pr checks 123",
    "git merge feature-branch",
    'git commit -m "please gh pr merge later"',
    'gh pr create --title x --body "run gh pr merge after CI"',
    # A GET (gh's default) or an explicit read-only method against the same
    # endpoint checks merge status; only POST/PUT actually merges.
    "gh api repos/owner/repo/pulls/123/merge",
    "gh api -X GET repos/owner/repo/pulls/123/merge",
    "gh api -X DELETE repos/owner/repo/pulls/123/merge",
    # Quoted text that only mentions a merge stays a look-alike (#194).
    "bash -c 'echo gh pr merge'",
    'git commit -m "then gh pr merge"',
    'git commit -m "if x then gh pr merge 1"',
    "bash -c 'gh pr view 1'",
    "eval echo gh pr merge",
    "echo 'xargs gh pr merge'",
]

# A backtick is a Bash command-substitution boundary, not a PowerShell one --
# so a commit message that merely mentions `gh pr merge` in backticks must
# not be mistaken for a merge on the PowerShell/Codex-Windows path (#194
# follow-up).
BACKTICK_LOOKALIKES = [
    'git commit -m "docs: mention that `gh pr merge` requires review before use"',
]


def test_lookalikes_are_not_treated_as_a_merge(feature_repo):
    for command in NOT_MERGE_COMMANDS:
        done = run(command, feature_repo)
        assert done.returncode == 0, (command, done.stdout, done.stderr)
        assert done.stdout == "", (command, done.stdout)


def test_lookalikes_are_not_treated_as_a_merge_under_codex_either(feature_repo):
    for command in NOT_MERGE_COMMANDS:
        done = run(command, feature_repo, codex=True)
        assert done.returncode == 0, (command, done.stdout, done.stderr)


def test_backtick_lookalike_is_not_a_merge_on_powershell(feature_repo):
    for command in BACKTICK_LOOKALIKES:
        done = run(command, feature_repo, tool="PowerShell")
        assert done.returncode == 0, (command, done.stdout, done.stderr)
        assert done.stdout == "", (command, done.stdout)


def test_backtick_lookalike_is_not_a_merge_on_powershell_under_codex(feature_repo):
    for command in BACKTICK_LOOKALIKES:
        done = run(command, feature_repo, tool="PowerShell", codex=True)
        assert done.returncode == 0, (command, done.stdout, done.stderr)


def test_ask_docstring_states_what_the_evidence_shows():
    # R9: the prompt appears in an interactive auto mode, is denied outright
    # under dontAsk and a `-p` run with no prompt tool, and cannot be silenced
    # by bypassPermissions or an allow rule. "Unattended" claimed more.
    with open(GUARD, encoding="utf-8") as fh:
        source = fh.read()
    start = source.index("def ask(")
    doc = source[start:source.index("print(json.dumps", start)]
    assert "unattended" not in doc
    assert "dontAsk" in doc and "bypassPermissions" in doc and "allow rule" in doc


POWERSHELL_ASK_COMMANDS = [
    "gh pr merge 1",
    "pwsh -Command 'gh pr merge 1'",
    'powershell -c "gh pr merge 1"',
    'powershell -NoProfile -ExecutionPolicy Bypass -Command "gh pr merge 1"',
    "Invoke-Expression 'gh pr merge 1'",
    # What the Codex launcher produces from ["bash", "-lc", script]: one line.
    "bash -lc echo x | xargs -I {} gh pr merge {}",
    "bash -c env FOO=1 gh pr merge 123",
]


def test_the_non_bash_path_asks_and_denies_too(feature_repo):
    # The PowerShell tool uses the non-Bash regex pair; nothing else exercised
    # it with a merge (only look-alikes).
    for command in POWERSHELL_ASK_COMMANDS:
        done = run(command, feature_repo, tool="PowerShell")
        assert done.returncode == 0, (command, done.stdout, done.stderr)
        assert json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask", command
        done = run(command, feature_repo, tool="PowerShell", codex=True)
        assert done.returncode == 2, (command, done.stdout, done.stderr)


def test_a_long_run_of_wrapper_options_does_not_hang_the_guard(feature_repo):
    # EXEC_WORDS nests quantifiers: if one token could be read two ways, a
    # command with no `gh` at the end would take exponential time to reject.
    for token in ("-n a=b", "-n if", "-n x", "env", "if"):
        command = "xargs " + (token + " ") * 40 + "echo hi"
        done = subprocess.run(
            [sys.executable, GUARD],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                              "cwd": feature_repo}),
            capture_output=True, text=True, cwd=feature_repo, timeout=20)
        assert done.returncode == 0 and done.stdout == "", (token, done.stdout, done.stderr)


def test_an_existing_deny_rule_still_wins_over_ask(feature_repo):
    done = run("git push --force origin main && gh pr merge 5", feature_repo)
    assert done.returncode == 2, (done.stdout, done.stderr)
    assert done.stdout == ""
    assert "force push" in done.stderr
