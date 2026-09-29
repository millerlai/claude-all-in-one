#!/usr/bin/env python3
"""PreToolUse guard. Four jobs, and they are not the same kind of rule:

- block destructive git/shell commands unless the user explicitly confirmed them;
- block a commit made directly onto a protected branch, or a push that lands
  one there, which destroys nothing but is the one absolute in
  rules/workflow.md a hook can actually decide;
- block a backtick Bash would run as a command, or a $(...) a stray
  apostrophe left unquoted, which rewrites a commit message or PR body -- or
  runs something -- without an error.
- ask, rather than block or silently allow, before `gh pr merge` -- merging is
  a human's call, not something to run unattended or refuse outright (#194
  maintainer decision, 2026-09-27).

Cross-platform (pure stdlib, works on Windows).
Exit codes: 0 = allow (or ask, on Claude Code -- see ask() below), 2 = block
(stderr is fed back to the model).
"""
import json
import os
import re
import shlex
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
    "Commit them so they stay recoverable -- a WIP commit on this branch is "
    "fine -- and run it again. Use `git stash` only if `git worktree list` "
    "shows a single worktree: every worktree of a repo shares one stash, so "
    "another one can pop yours (#230). "
    "If the user explicitly asked to discard them, tell them the guard "
    "blocked it and ask them to run it manually."
)

# A -C/-c value quoted because it holds a space -- an ordinary Windows user
# directory ("C:\Users\Jane Doe\project") is exactly this shape -- must not
# stop matching at that space and drop the rest of the pattern (#194 review).
OPT_VALUE = r'"[^"]*"|\'[^\']*\'|\S+'

# git takes global options before the verb, so `git -C <dir> push --force` and
# `git -c k=v reset --hard` walk straight past a pattern anchored on `git push`.
# Tolerating a run of them is the difference between a rule and a suggestion.
GIT = r"git\s+(?:(?:-[cC]\s+(?:" + OPT_VALUE + r")|--\S+)\s+)*"

# Argument text, bounded to a single command. Unbounded, `git status && npm
# publish --no-verify` read as git skipping its own hooks -- a false block on a
# command that has nothing to do with git.
ARGS = r"[^\n;&|]*"

# Destructive whichever shell runs them.
BLOCKED = [
    # (pattern, reason, advice)
    # A `+refspec` (`git push origin +HEAD:main`) forces exactly like --force/-f
    # do, just spelled differently -- #194. Blocked on every target, matching
    # those two, not only main/master: leaving it a hole on other branches
    # would make "force push" in the reason above a half-truth.
    (GIT + r"push\b" + ARGS + r"?(\s--force(?!-with-lease)|\s-f\b|\s\+[^\s+])", "force push (use --force-with-lease if truly needed)", CONFIRM),
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
COMMIT = re.compile(r"(?:^|\n|[;&|(`]\s*|\$\()\s*(?:\w+=\S*\s+)*(?P<git>" + GIT + r")commit\b")
PROTECTED = ("main", "master")

# Same command boundary as COMMIT, but captures the push's own arguments (to
# read its destination). Which directory's branch a bare push sends is
# target_dir()'s job, shared with the commit and discard rules.
# Args stop at `)` too, on top of ARGS's `;&|` and newline: a push scrubbed
# out of a `$(...)` substitution keeps that closing paren in the same line,
# and reading it as part of a refspec would corrupt the destination.
PUSH_ARGS = r"[^\n;&|)]*"
PUSH = re.compile(
    r"(?:^|\n|[;&|(`]\s*|\$\()\s*(?:\w+=\S*\s+)*(?P<git>" + GIT + r")"
    r"push\b(?P<args>" + PUSH_ARGS + r")"
)


# Merging a PR is decided by a person, not blocked outright: `gh pr merge`
# itself, plus the one other door to the same effect this guard can see --
# `gh api` writing straight to the REST endpoint the CLI wraps
# (POST/PUT .../pulls/<n>/merge). Same command-boundary anchor as
# COMMIT/PUSH above, so a mention inside a commit message or PR body (a
# quoted argument, not preceded by `;&|(`` or `$(`) does not match -- except
# the backtick itself, which is Bash-only: unlike COMMIT/PUSH (whose backtick
# false positive only bites on a protected-branch target), this check fires
# on every branch, so a backtick-quoted mention on the PowerShell/Codex path
# would otherwise ask or hard-deny an ordinary commit. `-R`/`--repo` before
# the verb is threaded through the same way GIT's own global options are, so
# `gh -R owner/repo pr merge 5`, `gh -Rowner/repo pr merge 5` and
# `gh --repo=owner/repo pr merge 5` are all still caught -- ahead of `api`
# too, so the same forms in front of `gh api ... /pulls/<n>/merge` are caught.
GH_OPT = r"(?:(?:-R\s*|--repo[= ])(?:" + OPT_VALUE + r")\s*)*"
GH_BOUNDARY = r"(?:^|\n|[;&|(]\s*|\$\()"
GH_BOUNDARY_BASH = r"(?:^|\n|[;&|(`]\s*|\$\()"


def _gh_merge_patterns(boundary):
    pr_merge = re.compile(
        boundary + r"\s*(?:\w+=\S*\s+)*gh\s+" + GH_OPT + r"pr\s+merge\b")
    api_merge = re.compile(
        boundary + r"\s*(?:\w+=\S*\s+)*gh\s+" + GH_OPT + r"api\b"
        r"(?=" + ARGS + r"\s(?:-X\s*(?:POST|PUT)\b|--method[= ]?(?:POST|PUT)\b))"
        r"(?=" + ARGS + r"/pulls/\d+/merge\b)",
        re.IGNORECASE)
    return pr_merge, api_merge


GH_PR_MERGE, GH_API_MERGE = _gh_merge_patterns(GH_BOUNDARY)
GH_PR_MERGE_BASH, GH_API_MERGE_BASH = _gh_merge_patterns(GH_BOUNDARY_BASH)

# Set only by plugins/cai-codex/scripts/launcher.py (hand-written) before it
# invokes this same file -- an explicit signal from the one component that
# knows which host it is running under, rather than this guard guessing from
# the payload shape. Claude Code never sets it, so that is the default path.
CODEX_GUARD_ENV = "CAI_CODEX_GUARD"

MERGE_REASON = "merging a pull request"

# https://learn.chatgpt.com/docs/hooks: "permissionDecision: 'ask', legacy
# 'decision: approve', continue: false, stopReason, and suppressOutput are
# parsed but not supported yet." An "ask" JSON on this host would be parsed
# and then ignored, silently letting the merge through -- worse than blocking
# it -- so Codex gets a deny, with the command repeated for the person to run.
MERGE_CODEX_ADVICE = (
    "Codex's hook host parses a PreToolUse \"ask\" permission decision but "
    "does not yet act on one, so this guard cannot put up a prompt here. "
    "Tell the person the exact command above and let them run it themselves."
)


def _unquote(value):
    """Strip one layer of matching quotes from a -C value the regex matched
    quoted (a path with a space in it); a bare value passes through as-is."""
    if value and len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


# A directory change at a command boundary, the way COMMIT/PUSH anchor git.
# PowerShell spells it Set-Location/sl/Push-Location as well, in any case.
CD = re.compile(
    r"(?:^|\n|[;&|(`]\s*|\$\()\s*"
    r"(?i:cd|pushd|popd|set-location|sl|push-location|pop-location)"
    r"(?=[\s;&|)]|$)(?P<args>[^\n;&|)]*)")

GIT_C = re.compile(r"-([cC])\s+(" + OPT_VALUE + r")|--\S+")

# A directory this guard cannot know without running the shell: `cd "$DIR"`,
# `cd -`, `popd`. Kept apart from None, which already means "the hook's own
# working directory" to git().
UNRESOLVED = object()


def _resolve(base, path):
    if not path or path == "-" or any(c in path for c in "$`%"):
        return UNRESOLVED
    path = os.path.expanduser(path)
    if os.path.isabs(path):
        return path
    if base is UNRESOLVED:
        return UNRESOLVED
    return os.path.join(base, path) if base else path


def target_dir(cwd, code, git_start):
    """The directory the git invocation starting at `code[git_start]` acts on
    (#233): its own `-C <dir>`s, applied on top of the last `cd`s before it
    on the line, applied on top of the session `cwd`. Judging the session cwd
    alone let `cd <main-checkout> && git commit` through from a feature
    worktree and blocked `git -C <worktree> commit` from a session on main.

    Anything that cannot be read statically falls back to `cwd` -- the
    guard's behaviour before #233 -- and every rule names the directory it
    read, so a wrong verdict stays diagnosable."""
    prefix = code[:git_start]
    # A group that closed before this git ran in a subshell of its own, so
    # a cd inside it moved nothing here: `(cd x && make); git commit`.
    while True:
        stripped = re.sub(r"\([^()]*\)", " ", prefix)
        if stripped == prefix:
            break
        prefix = stripped
    where = cwd
    for m in CD.finditer(prefix):
        tokens = [_unquote(t) for t in re.findall(OPT_VALUE, m.group("args"))]
        # `-` alone is `cd -`, not an option; `-P`, `-Path` and the like are.
        paths = [t for t in tokens if t == "-" or not t.startswith("-")]
        where = _resolve(where, paths[0] if paths else None)
    opts = re.match(GIT, code[git_start:]).group(0)
    for m in GIT_C.finditer(opts):
        if m.group(1) == "C":
            where = _resolve(where, _unquote(m.group(2)))
    return cwd if where is UNRESOLVED else where


# Options that take a separate value, so that value is not misread as the
# remote or a refspec.
PUSH_VALUE_OPTS = ("-o", "--push-option", "--repo", "--receive-pack", "--exec")

PUSH_PROTECTED_ADVICE = (
    "Changes reach main/master only through a merged pull request. " + CONFIRM
)


def push_targets(args):
    """The destination branch name(s) `git push <args>` would write to. None
    stands for "whatever the current branch is" -- a bare push, a push naming
    only a remote, or an explicit HEAD refspec -- which the caller resolves
    with current_branch(). `--tags` alone leaves no branch destination at all
    and is the one case that adds nothing. `--all`/`--mirror` push every
    local branch regardless of which one is checked out, so they always
    include every protected branch as a target rather than falling back to
    "whatever the current branch is" (#194 review).

    Best-effort, like the rest of this guard: unbalanced quotes fall back to
    a plain split, and an option this does not recognise is skipped as a flag
    rather than misread as the remote -- a missed protected push is the
    failure this guard exists to prevent, but a false block on an ordinary
    push is the failure that gets it switched off."""
    try:
        tokens = shlex.split(args)
    except ValueError:
        tokens = args.split()

    positional = []
    skip_value = False
    tags_only = False
    all_or_mirror = False
    skip_redirect_target = False
    for tok in tokens:
        if skip_value:
            skip_value = False
            continue
        if skip_redirect_target:
            skip_redirect_target = False
            continue
        if tok in ("--all", "--mirror"):
            all_or_mirror = True
            continue
        if tok == "--tags":
            tags_only = True
            continue
        if tok in PUSH_VALUE_OPTS:
            skip_value = True
            continue
        if any(tok.startswith(o + "=") for o in PUSH_VALUE_OPTS):
            continue
        if tok.startswith("-"):
            continue
        redirect = re.fullmatch(r"\d*(?P<op>>{1,2})(?P<dup>&?\d*)", tok)
        if redirect:
            # `2>&1` duplicates a file descriptor and names no file; a bare
            # `>`/`>>`/`2>` does, and that filename is the *next* token, not
            # the remote or a refspec (#194 review).
            if not redirect.group("dup"):
                skip_redirect_target = True
            continue
        if re.fullmatch(r"\d*<", tok):
            continue  # input redirection has no target to skip
        positional.append(tok)

    targets = []
    for spec in positional[1:]:  # positional[0], if present, is the remote
        spec = spec.lstrip("+")
        dst = spec.split(":", 1)[1] if ":" in spec else spec
        if dst.startswith("refs/heads/"):
            dst = dst[len("refs/heads/"):]
        targets.append(None if dst in ("", "HEAD") else dst)
    if all_or_mirror:
        targets.extend(PROTECTED)
    elif not targets and not tags_only:
        targets.append(None)
    return targets


def has_remote_ref(cwd, branch):
    """Whether some remote is already tracked as having `branch` --
    `refs/remotes/*/<branch>`. Only used to exempt a non-force push that
    would create the branch on a remote that has none: the unborn-commit
    exemption above (:407-410) mirrored for push, since "open a PR" is
    unfollowable when the remote has no main yet to open one into."""
    done = git(cwd, "for-each-ref", f"refs/remotes/*/{branch}")
    return bool(done and done.returncode == 0 and done.stdout.strip())

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

# The same silent rewrite through the other substitution syntax (#130). A
# deliberate $(...) is how BACKTICK substitutes on purpose, so only the shape
# a stray apostrophe makes is judged: a $( between a single quote that closed
# and the next that opens, with a letter touching either quote (`it's`,
# `owners'`) -- the one mark that tells English text from shell code.
SUBSTITUTED = "a $(...) that an apostrophe left outside its single quotes, which Bash runs"
UNPARSED_SUBSTITUTION = (
    "a $(...) after shell syntax this guard does not parse ($'...', a # "
    "comment, a quote inside \"$(...)\", or an unusual heredoc delimiter)"
)

SUBSTITUTION = (
    "A single-quoted argument ends at the next apostrophe, so text after a "
    "stray one is live shell and its $(...) runs before the command does. "
    "Pass a message as a file (git commit -F <file>, gh pr create "
    "--body-file <file>) or through a heredoc with a quoted delimiter "
    "(<<'EOF'). To substitute a command's output on purpose, write "
    "\"$(command)\"; if a # comment or $'...' before it holds an apostrophe, "
    "take that apostrophe out, since the guard cannot tell where those end."
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
    EXPANDED, UNPARSED, SUBSTITUTED or UNPARSED_SUBSTITUTION) is the first
    backtick, or $(...) a stray apostrophe left unquoted, this scan saw, for
    main() to act on."""
    n = len(command)
    i = 0
    state = "normal"  # normal, single, double
    walk_depth = 0  # >0 while walking a $( ... ) inside a double-quoted string
    unmodelled = False
    # Between a single quote that closed and the next that opens: the stretch
    # a stray apostrophe leaves unquoted. `glued` is whether a letter touches
    # the quote that closed it, `subst` whether a $( sits in it.
    bridge = glued = subst = False
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
                if i + 1 < n and command[i + 1] == "\n":
                    # Bash removes a backslash-newline pair entirely before
                    # word-splitting, joining the two lines -- so a command
                    # split across a continuation (`gh pr \` / `merge 123`)
                    # must read the same as the unwrapped form, not slip
                    # past GH_PR_MERGE/COMMIT/PUSH because `\s+` never
                    # crosses the backslash.
                    i += 2
                    continue
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
                    if bridge and subst and (glued or (i > 0 and command[i - 1].isalpha())):
                        record(UNPARSED_SUBSTITUTION if unmodelled else SUBSTITUTED)
                    bridge = False
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
            if walk_depth == 0 and bridge and c == "$" and i + 1 < n and command[i + 1] == "(":
                subst = True
            out.append(c)
            i += 1
            continue

        if state == "single":
            if c == "'":
                state = "normal"
                bridge = True
                glued = i + 1 < n and command[i + 1].isalpha()
                subst = False
                out.append(c)
                i += 1
                continue
            if c == "`" and unmodelled:
                record(UNPARSED)
            if c == "$" and i + 1 < n and command[i + 1] == "(" and unmodelled:
                record(UNPARSED_SUBSTITUTION)
            out.append(c)
            i += 1
            continue

        # state == "double"
        if c == "\\":
            if i + 1 < n and command[i + 1] == "\n":
                # Same line-continuation removal as the normal-state branch
                # above -- Bash also strips a backslash-newline pair inside
                # double quotes.
                i += 2
                continue
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


def ask(reason, command):
    """Claude Code path for `reason`: print the permission-decision JSON
    PreToolUse reads and exit 0, so the person sees a prompt instead of a
    silent allow or a hard block. Verified against
    https://code.claude.com/docs/en/permission-modes: "Claude Code doesn't
    add the option to prompts forced by one of your ask rules or by a hook,
    because auto mode still shows you those prompts" -- so this fires even
    when the session is otherwise running unattended."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": f"bash_guard: {reason}. Command: {command}",
        }
    }))
    return 0


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
        advice = SUBSTITUTION if verdict in (SUBSTITUTED, UNPARSED_SUBSTITUTION) else BACKTICK
        return deny(verdict, command, advice)

    # The session's cwd is only where the command starts -- `cd sub && git
    # commit` and `git -C ../other commit` both land elsewhere, so each rule
    # below reads target_dir() of the invocation it matched (#233). Naming
    # that directory makes a wrong verdict diagnosable instead of baffling.
    cwd = payload.get("cwd")

    # Pattern first, git second: `git status` is a subprocess, and asking it
    # on every Bash call would tax every command in the session to decide
    # two of them.
    for pattern, reason, advice in DISCARD:
        for m in re.finditer(pattern, code):
            if worktree_dirty(target_dir(cwd, code, m.start())):
                return deny(reason, command, advice)

    # A push that reaches main/master bypasses the same PR the commit rule
    # below protects, just one step later -- #194. `--force`/`-f`/`+refspec`
    # are already denied above regardless of target; what is left is a lease
    # or a plain push whose destination resolves to a protected branch.
    for m in PUSH.finditer(code):
        push_args = m.group("args")
        where = target_dir(cwd, code, m.start("git"))
        lease = bool(re.search(r"(?:^|\s)--force-with-lease\b", push_args))
        branch = None
        for target in push_targets(push_args):
            if target is None:
                if branch is None:
                    branch = current_branch(where) or ""
                target = branch
            if target not in PROTECTED:
                continue
            if lease or has_remote_ref(where, target):
                return deny(f"push to protected branch '{target}'", command,
                            f"Branch read from {where or 'the hook working directory'}. "
                            + PUSH_PROTECTED_ADVICE)

    for m in COMMIT.finditer(code):
        where = target_dir(cwd, code, m.start("git"))
        if current_branch(where) in PROTECTED:
            return deny("committing directly to a protected branch", command,
                        f"Branch read from {where or 'the hook working directory'}. " + BRANCH)

    # Checked last: every rule above is a deny, and a command that trips one
    # of them stays denied even if it also merges -- ask never weakens a
    # deny.
    pr_merge, api_merge = ((GH_PR_MERGE_BASH, GH_API_MERGE_BASH)
                            if payload.get("tool_name") == "Bash"
                            else (GH_PR_MERGE, GH_API_MERGE))
    if pr_merge.search(code) or api_merge.search(code):
        if os.environ.get(CODEX_GUARD_ENV) == "1":
            return deny(MERGE_REASON, command, MERGE_CODEX_ADVICE)
        return ask(MERGE_REASON, command)

    return 0


if __name__ == "__main__":
    sys.exit(main())
