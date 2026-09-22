#!/usr/bin/env python3
"""PreToolUse guard. Three jobs, and they are not the same kind of rule:

- block destructive git/shell commands unless the user explicitly confirmed them;
- block a commit made directly onto a protected branch, which destroys nothing
  but is the one absolute in rules/workflow.md a hook can actually decide;
- block a backtick Bash would run as a command, which rewrites a commit
  message or PR body without an error.

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

# A quoted heredoc body is data the command writes out, not commands it runs.
# Matched as text, a PR body or release note that merely mentions `git commit`
# would read as a commit, and a generated .ps1 containing @'...'@ would read as
# a here-string in Bash. Both are ordinary work, and a guard that blocks
# ordinary work is a guard that gets switched off - see GUIDE.md.
HEREDOC_OPEN = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(?:'(\w+)'|\"(\w+)\"|\\(\w+)|(\w+))(?=[ \t\r\n]|$)")

EXPANDED = "a backtick Bash would run as a command"
UNPARSED = (
    "a backtick after shell syntax this guard does not parse ($'...', a # "
    "comment, a quote inside \"$(...)\", or an unusual heredoc delimiter)"
)

BACKTICK = (
    "Bash runs the text between backticks as a command and pastes in its "
    "output. For literal text use single quotes ('fix `x`'), pass a file "
    "(git commit -F <file>, gh pr create --body-file <file>), or feed it "
    "through a heredoc with a quoted delimiter (<<'EOF'). To substitute a "
    "command's output on purpose, write $(command)."
)


def _heredoc_terminator(command, start, delim):
    """First line at or after `start` whose stripped text is `delim`, as
    (line_start, line_end) with line_end past its trailing newline (or at the
    end of the string, if that line has none). None if no such line exists."""
    n = len(command)
    pos = start
    while pos <= n:
        nl = command.find("\n", pos)
        content_end = nl if nl != -1 else n
        if command[pos:content_end].strip() == delim:
            return pos, (nl + 1 if nl != -1 else n)
        if nl == -1:
            return None
        pos = nl + 1
    return None


def substitutions(body):
    """The $(...) and `...` segments of one unquoted heredoc body, left to
    right. Quotes inside `body` are literal here -- an unquoted body
    contributes only its segments, nothing else."""
    n = len(body)
    i = 0
    segments = []
    while i < n:
        c = body[i]
        if c == "\\" and i + 1 < n and body[i + 1] in "$`\\\n":
            i += 2
            continue
        if c == "\\":
            i += 1
            continue
        if c == "$" and i + 1 < n and body[i + 1] == "(":
            start = i
            depth = 1
            i += 2
            while i < n and depth > 0:
                if body[i] == "(":
                    depth += 1
                elif body[i] == ")":
                    depth -= 1
                i += 1
            segments.append(body[start:i])
            continue
        if c == "`":
            start = i
            i += 1
            while i < n and not (body[i] == "`" and body[i - 1] != "\\"):
                i += 1
            if i < n:
                i += 1
            segments.append(body[start:i])
            continue
        i += 1
    return segments


def scan_command(command):
    """Read `command` once, left to right, replacing each heredoc opener with
    a space and each unquoted body with its substitution segments -- a quoted
    body is data and is dropped entirely. Returns (code, verdict): `code` is
    what the BLOCKED/COMMIT rules match against, and `verdict` (None,
    EXPANDED or UNPARSED) is the first backtick this scan saw, for main() to
    act on."""
    n = len(command)
    i = 0
    state = "normal"  # normal, single, double
    walk_depth = 0  # >0 while walking a $( ... ) inside a double-quoted string
    unmodelled = False
    queue = []  # pending (delim, quoted, term_start, term_end), oldest first
    out = []
    verdict = [None]

    def record(v):
        if verdict[0] is None:
            verdict[0] = v

    while i < n:
        c = command[i]

        if walk_depth > 0 or state == "normal":
            if c == "\\":
                out.append(c)
                if i + 1 < n:
                    out.append(command[i + 1])
                    i += 2
                else:
                    i += 1
                continue
            if c == "'":
                if walk_depth > 0:
                    unmodelled = True
                else:
                    state = "single"
                out.append(c)
                i += 1
                continue
            if c == '"':
                if walk_depth > 0:
                    unmodelled = True
                else:
                    state = "double"
                out.append(c)
                i += 1
                continue
            if walk_depth == 0 and c == "$" and i + 1 < n and command[i + 1] == "'":
                unmodelled = True
                out.append(c)
                i += 1
                continue
            if c == "#" and (i == 0 or command[i - 1] in " \t\n;&|()<>"):
                unmodelled = True
                out.append(c)
                i += 1
                continue
            if c == "<" and i + 1 < n and command[i + 1] == "<":
                m = None if unmodelled else HEREDOC_OPEN.match(command, i)
                term = None
                delim = None
                if m:
                    delim = m.group(2) or m.group(3) or m.group(4) or m.group(5)
                    quoted = m.group(2) is not None or m.group(3) is not None or m.group(4) is not None
                    if queue:
                        search_from = queue[-1][3]
                    else:
                        nl = command.find("\n", i)
                        search_from = (nl + 1) if nl != -1 else None
                    if search_from is not None:
                        term = _heredoc_terminator(command, search_from, delim)
                if m and term:
                    out.append(" ")
                    queue.append((delim, quoted, term[0], term[1]))
                    i = m.end()
                else:
                    out.append("<<")
                    unmodelled = True
                    i += 2
                continue
            if c == "\n":
                out.append(c)
                i += 1
                if queue:
                    for delim, quoted, term_start, term_end in queue:
                        body = command[i:term_start]
                        if not quoted:
                            segs = substitutions(body)
                            out.append("\n".join(segs))
                            for seg in segs:
                                if "`" in seg:
                                    record(UNPARSED if unmodelled else EXPANDED)
                        i = term_end
                    queue = []
                continue
            if c == "`":
                record(UNPARSED if unmodelled else EXPANDED)
                out.append(c)
                i += 1
                continue
            if walk_depth > 0 and c == "(":
                walk_depth += 1
                out.append(c)
                i += 1
                continue
            if walk_depth > 0 and c == ")":
                walk_depth -= 1
                out.append(c)
                i += 1
                if walk_depth == 0:
                    state = "double"
                continue
            out.append(c)
            i += 1
            continue

        if state == "single":
            if c == "'":
                state = "normal"
                out.append(c)
                i += 1
                continue
            if c == "`" and unmodelled:
                record(UNPARSED)
            out.append(c)
            i += 1
            continue

        # state == "double"
        if c == "\\":
            out.append(c)
            if i + 1 < n:
                out.append(command[i + 1])
                i += 2
            else:
                i += 1
            continue
        if c == '"':
            state = "normal"
            out.append(c)
            i += 1
            continue
        if c == "$" and i + 1 < n and command[i + 1] == "(":
            out.append(command[i:i + 2])
            walk_depth = 1
            i += 2
            continue
        if c == "`":
            record(UNPARSED if unmodelled else EXPANDED)
            out.append(c)
            i += 1
            continue
        if c == "<" and i + 1 < n and command[i + 1] == "<":
            out.append("<<")
            i += 2
            continue
        out.append(c)
        i += 1

    return "".join(out), verdict[0]


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
    code, verdict = scan_command(command)

    for pattern, reason, advice in BLOCKED + shell_rules:
        if re.search(pattern, code):
            return deny(reason, command, advice)

    if verdict and payload.get("tool_name") == "Bash":
        return deny(verdict, command, BACKTICK)

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
