#!/usr/bin/env python3
"""Local branches whose work already landed, and which of them are safe to delete.

`git branch --merged` answers this only for repos that merge by fast-forward or
by merge commit. A repo that squash-merges -- as this plugin's own `ship` stage
does -- collapses a branch into one new commit with an unrelated SHA, so ancestry
reports "not merged" about a branch whose every line is already on the base.
Measured on this repo on 2026-09-16: 12 local branches, 8 of them merged through
GitHub, and `git branch --merged main` named none of the 8.

So this reads three independent signals and names the one that fired, because no
single signal covers every repo:

  ancestry  `git branch --merged <base>` -- merge-commit and fast-forward repos.
  pr        a merged pull request whose head was that branch -- squash repos.
  gone      the branch's upstream is no longer on the remote.

Only `ancestry` and `pr` are evidence that the work reached <base>, and only
those -- plus the backup rule below, which leans on `pr` -- are ever reported
`deletable`. `gone` is evidence that someone deleted the remote
branch -- which a merge does by itself where "automatically delete head branches"
is on, but which a person can also do at any time, to a branch that was never
merged. It gets its own status for a human to judge rather than a delete.

A branch carrying commits its upstream never received is reported `ahead` and is
never deletable, whatever the other signals say: a squash-merged branch that was
committed to afterwards holds the only copy of those commits.

A `backup/<source>-<suffix>` branch -- what `ship` leaves behind before it
squashes -- is never pushed and is no pull request's head, so none of the
three signals can fire for it. It is reported `deletable` when <source> is
the head of a merged pull request and the backup's last commit is no later
than that merge. The match is by name only; nothing checks the backup's
contents. The time check is what keeps a backup made in a later round of a
reused branch name from riding on the earlier round's merge.

A branch checked out in a worktree is read for the same signals; git refuses
to delete it, which is no reason to hide that it is merged. One that would
otherwise be `deletable` is reported `detachable`: `--delete --detach` moves
its worktree onto the same commit with no branch, then deletes the branch. The
worktree's directory is never removed and nothing in it is touched. Removing
one stays with a person: `git worktree remove` deletes ignored files unasked
and, measured on git 2.39.2.windows.1 on 2026-10-10, follows a directory
junction inside the worktree and deletes the files it points at.

Prints a table and changes nothing unless `--delete` is passed.

    branch_sweep.py                    # show the table
    branch_sweep.py --delete           # delete only what the table calls deletable
    branch_sweep.py --delete --detach  # and free what it calls detachable
    branch_sweep.py --base develop     # compare against a branch other than the default
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

import tool_path

TIMEOUT_SECONDS = 15

# The test seam, shaped like ticket_backend.CLI_ENV's CAI_TICKET_CLI and for the
# same reason: a subprocess inherits os.environ and nothing else, so a pytest
# monkeypatch of this module cannot reach the CLI it shells out to. A value
# starting with `[` is a JSON argv array; anything else is a single executable.
CLI_ENV = "CAI_GH_CLI"

# One bulk query rather than one per branch. A branch older than this many merged
# PRs reads as `keep`, which is the safe direction to be wrong in -- the table
# says keep, nothing is deleted, and the branch is still there next run.
PR_LIMIT = 200

# What `ship` names the branch it leaves behind before it squashes
# (plugins/cai/skills/track/references/stage-ship.md:112:
# `git branch "backup/${BRANCH}-$(date +%Y%m%d-%H%M%S)"`).
BACKUP_PREFIX = "backup/"

_AHEAD = re.compile(r"ahead (\d+)")

# Classified into a closed set of words, never echoed. `gh`'s 401 message carries
# an api.github.com URL with the credential in it, which is why ticket_backend.py
# classifies rather than prints too (its classify() docstring says so outright).
_AUTH = ("http 401", "bad credentials", "gh auth login", "not logged into")
_NO_REPO = ("could not resolve to a repository", "not a git repository",
            "none of the git remotes", "no git remotes")
_UNREACHABLE = ("error connecting to", "dial tcp", "timeout awaiting",
                "no such host")

STATUS_ORDER = ("deletable", "detachable", "gone", "ahead", "held", "keep")

# What puts a detached worktree back on its branch. `symbolic-ref`, not
# `git switch`: it is the exact inverse of detach() and, like it, reads no
# working tree -- `git switch` exits 128 in a worktree whose `git status` does.
REATTACH = '    git -C "%s" symbolic-ref HEAD refs/heads/%s'


def run(argv, cwd=None):
    """(stdout, stderr, returncode). Never raises; a missing or hung executable
    comes back as returncode -1.

    encoding="utf-8" is explicit rather than `text=True`'s console-locale
    default. Both callees emit UTF-8 whatever the console is set to, and a
    branch name or PR title outside the console codepage -- cp950 here -- makes
    the default raise inside subprocess's own reader thread, where this
    function's `except` cannot see it: the call returns with stdout silently
    None instead of failing (ticket_backend.run(), issue #48)."""
    try:
        # A bare git or gh by full path from a trusted PATH entry (#294).
        done = subprocess.run(tool_path.resolve_argv(argv, cwd), cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=TIMEOUT_SECONDS)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "", "", -1
    out = done.stdout if isinstance(done.stdout, str) else ""
    err = done.stderr if isinstance(done.stderr, str) else ""
    return out, err, done.returncode


def git(args, cwd=None):
    """(stdout, returncode). git's stderr is dropped here rather than returned:
    nothing in this file classifies it, and the one thing it reliably carries
    is a remote URL."""
    out, _, code = run(["git"] + list(args), cwd=cwd)
    return out, code


def gh_prefix():
    raw = os.environ.get(CLI_ENV, "").strip()
    if not raw:
        return ["gh"]
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return ["gh"]
        return [str(a) for a in parsed] if isinstance(parsed, list) else ["gh"]
    return [raw]


def classify_gh(returncode, stderr):
    """One word from a closed set, so the reason a query failed can be shown
    without any of `gh`'s own text reaching the output."""
    if returncode == 0:
        return "ok"
    if returncode == -1:
        return "not-found"
    low = (stderr or "").lower()
    for needles, word in ((_AUTH, "not-authenticated"),
                          (_NO_REPO, "no-github-repo"),
                          (_UNREACHABLE, "unreachable")):
        if any(n in low for n in needles):
            return word
    return "unavailable"


def gh_merged_prs(cwd=None):
    """({branch: (pr number, merged_at or None)}, note). `note` is None when
    the query worked, else the one-word reason, so the caller can say why the
    `pr` signal is missing instead of silently reporting every squash-merged
    branch as `keep`."""
    argv = gh_prefix() + ["pr", "list", "--state", "merged",
                          "--limit", str(PR_LIMIT),
                          "--json", "number,headRefName,mergedAt"]
    out, err, code = run(argv, cwd=cwd)
    if code != 0:
        return {}, classify_gh(code, err)
    try:
        rows = json.loads(out)
    except ValueError:
        return {}, "unreadable"
    if not isinstance(rows, list):
        return {}, "unreadable"
    merged = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        head, number = row.get("headRefName"), row.get("number")
        if not isinstance(head, str) or not head or not isinstance(number, int):
            continue
        merged_at = row.get("mergedAt")
        merged_at = merged_at if isinstance(merged_at, str) else None
        # A branch reused across two PRs keeps the later one: it is the merge
        # that the tip of the local branch could plausibly have reached.
        if number > merged.get(head, (0, None))[0]:
            merged[head] = (number, merged_at)
    return merged, None


def local_branches(cwd=None):
    """[(name, upstream, ahead, gone, committed)] for every local branch, from
    one call. `committed` is the branch tip's ISO commit date, empty when the
    field is absent."""
    fmt = ("%(refname:short)\t%(upstream:short)\t%(upstream:track)\t"
          "%(committerdate:iso-strict)")
    out, rc = git(["for-each-ref", "--format=" + fmt, "refs/heads"], cwd=cwd)
    if rc != 0:
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        name = parts[0]
        upstream = parts[1] if len(parts) > 1 else ""
        track = parts[2] if len(parts) > 2 else ""
        committed = parts[3] if len(parts) > 3 else ""
        found = _AHEAD.search(track)
        rows.append((name, upstream, int(found.group(1)) if found else 0,
                     "gone" in track, committed))
    return rows


def held_branches(cwd=None):
    """{branch: worktree path} for every branch checked out in a worktree, the
    current one included -- the main worktree is a worktree, so this needs no
    separate HEAD check. Deleting one of these fails anyway; naming it, and
    where it is held, is the point."""
    out, rc = git(["worktree", "list", "--porcelain"], cwd=cwd)
    if rc != 0:
        return {}
    held, path = {}, ""
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line.startswith("branch refs/heads/"):
            held[line[len("branch refs/heads/"):]] = path
    return held


def current_branch(cwd=None):
    """The branch checked out where this runs, empty on a detached HEAD."""
    out, _ = git(["symbolic-ref", "-q", "HEAD"], cwd=cwd)
    out = out.strip()
    return out[len("refs/heads/"):] if out.startswith("refs/heads/") else ""


def merged_by_ancestry(base, cwd=None):
    out, rc = git(["branch", "--merged", base, "--format=%(refname:short)"],
                  cwd=cwd)
    if rc != 0:
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def default_base(cwd=None):
    """The branch a PR would target. origin/HEAD names it when the remote has
    been queried at least once; otherwise fall back to whichever conventional
    name exists locally."""
    out, rc = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                  cwd=cwd)
    if rc == 0 and out.strip().startswith("origin/"):
        return out.strip()[len("origin/"):]
    for name in ("main", "master"):
        _, rc = git(["rev-parse", "--verify", "--quiet", "refs/heads/" + name],
                    cwd=cwd)
        if rc == 0:
            return name
    return "main"


def backup_source(name, prs):
    """The merged PR head a `backup/<source>-<suffix>` branch was made from,
    or None if `name` does not match one. `ship` names the suffix with a
    literal `-`, which a source containing `/` (every branch this plugin
    names) would also produce if it were substituted for `/` -- so both
    spellings of each head are tried."""
    if not name.startswith(BACKUP_PREFIX):
        return None
    rest = name[len(BACKUP_PREFIX):]
    best = None
    for head in prs:
        for spelling in (head, head.replace("/", "-")):
            if not rest.startswith(spelling + "-"):
                continue
            if len(rest) <= len(spelling) + 1:
                continue
            candidate = (len(spelling), spelling == head, prs[head][0], head)
            if best is None or candidate > best:
                best = candidate
    return best[3] if best else None


def committed_before(committed, merged_at):
    """Whether `committed` (a branch tip's commit date) is no later than
    `merged_at`. False -- not proven safe -- for anything that fails to
    parse, which is the safe direction to be wrong in."""
    if not committed or not merged_at:
        return False
    try:
        committed_dt = datetime.datetime.fromisoformat(
            committed.replace("Z", "+00:00"))
        merged_dt = datetime.datetime.fromisoformat(
            merged_at.replace("Z", "+00:00"))
        return committed_dt <= merged_dt
    except (ValueError, TypeError):
        return False


def classify(row, base, held, here, ancestry, prs):
    """(status, why) for one branch. A worktree never hides what the signals
    say: it only renames a branch they prove merged, from `deletable` to
    `detachable`. `here` is the one worktree that is not offered -- freeing
    its branch would rewrite the HEAD of the directory this was run from."""
    name = row[0]
    if name == base:
        return None, None
    status, why = signals(row, base, ancestry, prs)
    if name not in held:
        return status, why
    if name == here:
        return "held", why + "; checked out in the current worktree"
    why = "%s; worktree %s" % (why, held[name])
    return ("detachable" if status == "deletable" else "held"), why


def signals(row, base, ancestry, prs):
    """(status, why) from the merge signals alone, as if no worktree held the
    branch. Order is the safety policy: a branch whose delete would lose
    commits is settled before any merge signal is read."""
    name, _upstream, ahead, gone, committed = row
    unproven = None
    if ahead:
        return "ahead", "%d commit(s) not on its upstream" % ahead
    if name in ancestry:
        return "deletable", "ancestry: already on %s" % base
    if name in prs:
        return "deletable", "pr: #%d merged" % prs[name][0]
    source = backup_source(name, prs)
    if source is not None:
        number, merged_at = prs[source]
        if committed_before(committed, merged_at):
            return "deletable", "backup of %s: pr #%d merged" % (source, number)
        unproven = ("backup of %s: pr #%d merged before its last commit"
                   % (source, number))
    if gone:
        return "gone", "upstream deleted on the remote, merge unproven"
    return "keep", unproven or "no merge signal"


def sweep(base, cwd=None):
    """[(name, status, why)] ordered by status then name, plus the gh note."""
    prs, note = gh_merged_prs(cwd=cwd)
    held = held_branches(cwd=cwd)
    here = current_branch(cwd=cwd)
    ancestry = merged_by_ancestry(base, cwd=cwd)
    rows = []
    for row in local_branches(cwd=cwd):
        status, why = classify(row, base, held, here, ancestry, prs)
        if status:
            rows.append((row[0], status, why))
    rows.sort(key=lambda r: (STATUS_ORDER.index(r[1]), r[0]))
    return rows, note


def detach(path, name):
    """Whether the worktree at `path` was moved off branch `name`, onto the
    same commit with no branch. `update-ref` rather than `checkout --detach`:
    it writes that worktree's HEAD and nothing else, so it runs no checkout
    hook and still works where the worktree's own `git status` fails. Passing
    the SHA as the old value too makes it a compare-and-swap -- a worktree
    whose HEAD is anywhere but the branch's tip is left alone."""
    sha, rc = git(["rev-parse", "refs/heads/" + name], cwd=path)
    if rc != 0:
        return False
    sha = sha.strip()
    _, rc = git(["update-ref", "--no-deref", "-m",
                 "branch_sweep: detach from " + name, "HEAD", sha, sha],
                cwd=path)
    return rc == 0


def delete(names, cwd=None, held=None):
    """[(name, sha_or_None, worktree_or_None)] for each attempted delete.
    `worktree` is the path that was detached to free the branch, so a row
    with a worktree and no SHA is one left detached with its branch still
    there. `-D` not `-d`: a squash-merged branch is not an ancestor of
    anything, so `-d` refuses exactly the branches this exists to remove."""
    done = []
    for name in names:
        # refs/heads/ explicitly: a tag sharing the branch's name would win
        # the bare-name lookup, and the SHA printed here is the whole undo.
        sha, rc = git(["rev-parse", "--short", "refs/heads/" + name], cwd=cwd)
        sha = sha.strip() if rc == 0 else None
        path = (held or {}).get(name)
        if path and not detach(path, name):
            done.append((name, None, None))
            continue
        _, rc = git(["branch", "-D", name], cwd=cwd)
        done.append((name, sha if rc == 0 else None, path))
    return done


def render(rows, note, base):
    lines = []
    if note:
        lines.append("note: no merged-pull-request data (%s) -- a squash-merged "
                     "branch can only read as `keep` this run." % note)
    if not rows:
        lines.append("No local branches besides %s." % base)
        return lines
    width = max(len(name) for name, _, _ in rows)
    lines.append("%-*s  %-10s  %s" % (width, "BRANCH", "STATUS", "WHY"))
    for name, status, why in rows:
        lines.append("%-*s  %-10s  %s" % (width, name, status, why))
    counts = {}
    for _, status, _ in rows:
        counts[status] = counts.get(status, 0) + 1
    summary = ", ".join("%d %s" % (counts[s], s)
                        for s in STATUS_ORDER if s in counts)
    lines.append("")
    lines.append(summary + ".")
    if counts.get("deletable"):
        lines.append("Re-run with --delete to remove the deletable ones.")
    if counts.get("detachable"):
        lines.append("Re-run with --delete --detach to free the detachable "
                     "ones too: each worktree stays in place, on the same "
                     "commit with no branch.")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", help="branch the work should have landed on")
    ap.add_argument("--delete", action="store_true",
                    help="delete the branches reported deletable")
    ap.add_argument("--detach", action="store_true",
                    help="with --delete: also move worktrees off the branches "
                         "reported detachable, then delete those branches")
    ap.add_argument("--repo", help="run against this directory")
    args = ap.parse_args(argv)
    if args.detach and not args.delete:
        ap.error("--detach only does something together with --delete")

    cwd = args.repo
    _, rc = git(["rev-parse", "--git-dir"], cwd=cwd)
    if rc != 0:
        print("not a git repository" + (": %s" % cwd if cwd else ""),
              file=sys.stderr)
        return 2

    base = args.base or default_base(cwd=cwd)
    # A base that does not resolve makes `--merged` fail rather than raise, and
    # every branch would then quietly lose its ancestry signal. A mistyped
    # --base has to say so, not return a table that is merely emptier.
    _, rc = git(["rev-parse", "--verify", "--quiet", base + "^{commit}"],
                cwd=cwd)
    if rc != 0:
        print("no such branch: %s" % base, file=sys.stderr)
        return 2

    rows, note = sweep(base, cwd=cwd)
    for line in render(rows, note, base):
        print(line)

    if not args.delete:
        return 0
    wanted = ("deletable", "detachable") if args.detach else ("deletable",)
    targets = [name for name, status, _ in rows if status in wanted]
    if not targets:
        return 0
    print("")
    # Read again, not carried over from the table: this is the moment another
    # worktree's HEAD is rewritten, so it is decided on what is held now.
    held = held_branches(cwd=cwd) if args.detach else {}
    for name, sha, path in delete(targets, cwd=cwd, held=held):
        if sha and path:
            print("Deleted %s (was %s) and detached worktree %s -- undo with:"
                  % (name, sha, path))
            print("    git branch %s %s" % (name, sha))
            print(REATTACH % (path, name))
        elif sha:
            print("Deleted %s (was %s) -- undo with: git branch %s %s"
                  % (name, sha, name, sha))
        elif path:
            print("Could not delete %s -- its worktree %s is detached now; "
                  "put it back with:" % (name, path))
            print(REATTACH % (path, name))
        else:
            print("Could not delete %s" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
