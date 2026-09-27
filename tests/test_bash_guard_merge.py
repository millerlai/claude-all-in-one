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

GUARD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins", "cai", "scripts", "bash_guard.py")


def run(command, tool="Bash", codex=False, cwd=""):
    env = dict(os.environ)
    if codex:
        env["CAI_CODEX_GUARD"] = "1"
    else:
        env.pop("CAI_CODEX_GUARD", None)
    return subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps({"tool_name": tool, "tool_input": {"command": command}, "cwd": cwd}),
        capture_output=True, text=True, env=env,
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
]


def test_claude_path_asks_instead_of_blocking_or_allowing_silently():
    for command in ASK_COMMANDS:
        done = run(command)
        assert done.returncode == 0, (command, done.stdout, done.stderr)
        payload = json.loads(done.stdout)
        out = payload["hookSpecificOutput"]
        assert out["hookEventName"] == "PreToolUse"
        assert out["permissionDecision"] == "ask"
        assert out["permissionDecisionReason"]


def test_codex_signal_denies_and_hands_back_the_command():
    for command in ASK_COMMANDS:
        done = run(command, codex=True)
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
]

# A backtick is a Bash command-substitution boundary, not a PowerShell one --
# so a commit message that merely mentions `gh pr merge` in backticks must
# not be mistaken for a merge on the PowerShell/Codex-Windows path (#194
# follow-up).
BACKTICK_LOOKALIKES = [
    'git commit -m "docs: mention that `gh pr merge` requires review before use"',
]


def test_lookalikes_are_not_treated_as_a_merge():
    for command in NOT_MERGE_COMMANDS:
        done = run(command)
        assert done.returncode == 0, (command, done.stdout, done.stderr)
        assert done.stdout == "", (command, done.stdout)


def test_lookalikes_are_not_treated_as_a_merge_under_codex_either():
    for command in NOT_MERGE_COMMANDS:
        done = run(command, codex=True)
        assert done.returncode == 0, (command, done.stdout, done.stderr)


def test_backtick_lookalike_is_not_a_merge_on_powershell():
    for command in BACKTICK_LOOKALIKES:
        done = run(command, tool="PowerShell")
        assert done.returncode == 0, (command, done.stdout, done.stderr)
        assert done.stdout == "", (command, done.stdout)


def test_backtick_lookalike_is_not_a_merge_on_powershell_under_codex():
    for command in BACKTICK_LOOKALIKES:
        done = run(command, tool="PowerShell", codex=True)
        assert done.returncode == 0, (command, done.stdout, done.stderr)


def test_an_existing_deny_rule_still_wins_over_ask():
    done = run("git push --force origin main && gh pr merge 5")
    assert done.returncode == 2, (done.stdout, done.stderr)
    assert done.stdout == ""
    assert "force push" in done.stderr
