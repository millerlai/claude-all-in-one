#!/usr/bin/env python3
"""PreToolUse guard. Two jobs, and they are not the same kind of rule:

- block destructive git/shell commands unless the user explicitly confirmed them;
- block a commit made directly onto a protected branch, which destroys nothing
  but is the one absolute in rules/workflow.md a hook can actually decide.

Cross-platform (pure stdlib, works on Windows).
Exit codes: 0 = allow, 2 = block (stderr is fed back to Claude).
"""
import json
import re
import subprocess
import sys

CONFIRM = (
    "If the user explicitly requested this, tell them the guard blocked it "
    "and ask them to run it manually or temporarily disable the cai plugin hook."
)

REWRITE = (
    "Rewrite the command instead of asking to run it: write the message to a "
    "file and use `git commit -F <file>`, or pass single-line strings with "
    "repeated -m. A heredoc (<<'EOF') is fine in Bash; @'...'@ is PowerShell "
    "syntax and leaves literal @ characters in the message."
)

BRANCH = (
    "Create a branch first (git checkout -b <name>) and commit there. If the "
    "user explicitly asked to commit on this branch, tell them the guard "
    "blocked it and ask them to run it manually."
)

COMMIT_FIRST = (
    "The working tree has uncommitted changes and this throws them away. "
    "Commit them, or `git stash` so they stay recoverable, and run it again. "
    "If the user explicitly asked to discard them, tell them the guard "
    "blocked it and ask them to run it manually."
)

# git takes global options before the verb, so `git -C <dir> push --force` and
# `git -c k=v reset --hard` walk straight past a pattern anchored on `git push`.
# Tolerating a run of them is the difference between a rule and a suggestion.
GIT = r"git\s+(?:(?:-[cC]\s+\S+|--\S+)\s+)*"

# Argument text, bounded to a single command. Unbounded, `git status && npm
# publish --no-verify` read as git skipping its own hooks -- a false block on a
# command that has nothing to do with git.
ARGS = r"[^\n;&|]*"

# Destructive whichever shell runs them.
BLOCKED = [
    # (pattern, reason, advice)
    (GIT + r"push\b" + ARGS + r"?(\s--force(?!-with-lease)|\s-f\b)", "force push (use --force-with-lease if truly needed)", CONFIRM),
    (GIT + r"reset\s+" + ARGS + r"--hard", "hard reset discards work", CONFIRM),
    (GIT + r"clean\s+(?:-[a-z]*f|--force)", "git clean -f deletes untracked files", CONFIRM),
    (GIT + ARGS + r"--no-verify", "skipping hooks", CONFIRM),
    # Split and long flags delete exactly what -rf does: `rm -r -f`,
    # `rm --recursive --force`. Lookaheads catch any order or spelling.
    (r"\brm\b(?=" + ARGS + r"\s-(?:[a-zA-Z]*[rR]|-recursive))(?=" + ARGS + r"\s-(?:[a-zA-Z]*f|-force))",
     "recursive force delete", CONFIRM),
]

# Discarding uncommitted work is destructive only when there is uncommitted
# work: `git checkout -- .` on a clean tree is a no-op and `git restore
# --staged` merely unstages. So these are checked against `git status` rather
# than blocked outright -- the same reason the commit rule below reads the
# branch instead of refusing every commit.
#
# What this catches is a verification step eating the fix it was meant to
# check: a breach test, a mutation run, or a plain "undo that" reverting edits
# that were never committed. `git reset --hard` above already covers its own
# spelling; these are the two that reach the same files by path.
DISCARD = [
    # Pathspec mode, which is what `--` and a bare `.` both mean here. Without
    # either, `git checkout -b x` and `git checkout main` are branch moves and
    # git refuses them itself rather than overwriting anything.
    (GIT + r"checkout\b" + ARGS + r"(?:\s--(?:\s|$)|\s\.(?:\s|$))",
     "git checkout discards uncommitted changes to those paths", COMMIT_FIRST),
    # `--staged` alone only unstages, so it must go through; `--worktree`
    # alongside it reaches the files again, so the second entry catches the
    # combination the first one lets past.
    (GIT + r"restore\b(?!" + ARGS + r"\s--staged\b)",
     "git restore discards uncommitted changes", COMMIT_FIRST),
    (GIT + r"restore\b" + ARGS + r"\s--worktree\b",
     "git restore --worktree discards uncommitted changes", COMMIT_FIRST),
]

# A here-string is correct PowerShell and garbage in Bash, so this can only be
# judged once you know which shell will run it. Require the opener *and* its
# matching terminator: a real here-string always has both, while a line merely
# ending in @" (a URL with credentials, say) has only one and must go through.
BASH_ONLY = [
    (r"(?ms)@([\"'])\s*$.*^\s*\1@", "PowerShell here-string in a Bash command", REWRITE),
]

# What `rm -rf` looks like in PowerShell; the shared pattern above never sees
# it. PowerShell is case-insensitive, aliases Remove-Item to rm/ri/del/erase/rd,
# and accepts any unambiguous parameter prefix -- so matching only the literal
# `Remove-Item -Recurse -Force` blocks the spelling nobody types and allows the
# one everybody does.
NON_BASH = [
    (r"(?i)(?:remove-item|\brm\b|\bri\b|\bdel\b|\berase\b|\brd\b)"
     r"(?=" + ARGS + r"\s-rec)(?=" + ARGS + r"\s-fo)", "recursive force delete", CONFIRM),
]

# Anchored to a command boundary so `git log --grep='git commit'` stays allowed,
# but the boundary has to admit the shapes a commit really arrives in: an env
# prefix (`GIT_EDITOR=true git commit`), a subshell, a command substitution, and
# git's own global options.
COMMIT = re.compile(r"(?:^|\n|[;&|(`]\s*|\$\()\s*(?:\w+=\S*\s+)*" + GIT + r"commit\b")
PROTECTED = ("main", "master")

# A heredoc body is data the command writes out, not commands it runs. Matched
# as text, a PR body or release note that merely mentions `git commit` reads as
# a commit, and a generated .ps1 containing @'...'@ reads as a here-string in
# Bash. Both are ordinary work, and a guard that blocks ordinary work is a
# guard that gets switched off - see GUIDE.md.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1.*?^\s*\2\s*$", re.DOTALL | re.MULTILINE)


def git(cwd, *args):
    try:
        return subprocess.run(["git", *args], cwd=cwd or None,
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None


def current_branch(cwd):
    """Branch name, or None when git can't answer: no git, no repo, detached
    HEAD, or no commits yet.

    The unborn case has to fail open. symbolic-ref happily names the branch of
    a freshly-init'd repo, so checking it alone blocks the very first commit -
    and the advice to branch first is unfollowable when there is no history to
    branch from."""
    head = git(cwd, "rev-parse", "--verify", "HEAD")
    if head is None or head.returncode != 0:
        return None
    done = git(cwd, "symbolic-ref", "--short", "HEAD")
    return done.stdout.strip() if done and done.returncode == 0 else None


def worktree_dirty(cwd):
    """Whether there is uncommitted work here that these commands could lose.

    `--untracked-files=no` is the whole predicate, not a speed knob. Neither
    `git checkout -- <paths>` nor `git restore` touches an untracked file, so
    counting one as dirty would block both in every repo carrying build
    output or a scratch file -- which is most of them, and is the guard
    blocking work it cannot damage.

    Fails open, like current_branch() above and for the same reason: a git
    that cannot answer -- no repo, no git, a timeout -- must not be what
    starts blocking checkouts. Not knowing is a reason to allow here, where
    the alternative is refusing an operation that discards nothing."""
    done = git(cwd, "status", "--porcelain", "--untracked-files=no")
    return bool(done and done.returncode == 0 and done.stdout.strip())


def deny(reason, command, advice):
    sys.stderr.write(
        f"bash_guard blocked this command: {reason}.\n"
        f"Command: {command}\n"
        f"{advice}\n"
    )
    return 2


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # malformed input: fail open, don't break the session

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        return 0

    # An unknown tool is treated as not-Bash: a wrongly blocked here-string
    # would be a false positive on valid PowerShell, and a guard that blocks
    # legitimate work gets switched off along with the rules that matter.
    shell_rules = BASH_ONLY if payload.get("tool_name") == "Bash" else NON_BASH

    # Match against the command with heredoc bodies removed, but always show
    # the user what they actually typed.
    code = HEREDOC.sub("", command)

    for pattern, reason, advice in BLOCKED + shell_rules:
        if re.search(pattern, code):
            return deny(reason, command, advice)

    # The branch comes from the session's cwd, which is not necessarily where
    # the command runs -- `cd sub && git commit` and `git -C ../other commit`
    # both land elsewhere. Naming the directory makes a wrong verdict
    # diagnosable instead of baffling.
    cwd = payload.get("cwd")

    # Pattern first, git second, and the git call made at most once: `git
    # status` is a subprocess, and asking it on every Bash call would tax
    # every command in the session to decide two of them.
    discard = next(((r, a) for p, r, a in DISCARD if re.search(p, code)), None)
    if discard and worktree_dirty(cwd):
        return deny(discard[0], command, discard[1])

    if COMMIT.search(code) and current_branch(cwd) in PROTECTED:
        return deny("committing directly to a protected branch", command,
                    f"Branch read from {cwd or 'the hook working directory'}. " + BRANCH)

    return 0


if __name__ == "__main__":
    sys.exit(main())
