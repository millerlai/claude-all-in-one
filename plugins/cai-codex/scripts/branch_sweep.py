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

Only `ancestry` and `pr` are evidence that the work reached <base>, and only those
are ever reported `deletable`. `gone` is evidence that someone deleted the remote
branch -- which a merge does by itself where "automatically delete head branches"
is on, but which a person can also do at any time, to a branch that was never
merged. It gets its own status for a human to judge rather than a delete.

A branch carrying commits its upstream never received is reported `ahead` and is
never deletable, whatever the other signals say: a squash-merged branch that was
committed to afterwards holds the only copy of those commits.

Prints a table and changes nothing unless `--delete` is passed.

    branch_sweep.py                 # show the table
    branch_sweep.py --delete        # delete only what the table calls deletable
    branch_sweep.py --base develop  # compare against a branch other than the default
"""
import argparse
import json
import os
import re
import subprocess
import sys

TIMEOUT_SECONDS = 15

# The test seam, shaped like ticket_backend.py:32's CAI_TICKET_CLI and for the
# same reason: a subprocess inherits os.environ and nothing else, so a pytest
# monkeypatch of this module cannot reach the CLI it shells out to. A value
# starting with `[` is a JSON argv array; anything else is a single executable.
CLI_ENV = "CAI_GH_CLI"

# One bulk query rather than one per branch. A branch older than this many merged
# PRs reads as `keep`, which is the safe direction to be wrong in -- the table
# says keep, nothing is deleted, and the branch is still there next run.
PR_LIMIT = 200

_AHEAD = re.compile(r"ahead (\d+)")

# Classified into a closed set of words, never echoed. `gh`'s 401 message carries
# an api.github.com URL with the credential in it, which is why ticket_backend.py
# classifies rather than prints too (its classify() docstring says so outright).
_AUTH = ("http 401", "bad credentials", "gh auth login", "not logged into")
_NO_REPO = ("could not resolve to a repository", "not a git repository",
            "none of the git remotes", "no git remotes")
_UNREACHABLE = ("error connecting to", "dial tcp", "timeout awaiting",
                "no such host")

STATUS_ORDER = ("deletable", "gone", "ahead", "held", "keep")


def run(argv, cwd=None):
    """(stdout, stderr, returncode). Never raises; a missing or hung executable
    comes back as returncode -1.

    encoding="utf-8" is explicit rather than `text=True`'s console-locale
    default. Both callees emit UTF-8 whatever the console is set to, and a
    branch name or PR title outside the console codepage -- cp950 here -- makes
    the default raise inside subprocess's own reader thread, where this
    function's `except` cannot see it: the call returns with stdout silently
    None instead of failing (ticket_backend.py:127-141, issue #48)."""
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
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
    """({branch: pr number}, note). `note` is None when the query worked, else
    the one-word reason, so the caller can say why the `pr` signal is missing
    instead of silently reporting every squash-merged branch as `keep`."""
    argv = gh_prefix() + ["pr", "list", "--state", "merged",
                          "--limit", str(PR_LIMIT),
                          "--json", "number,headRefName"]
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
        if not isinstance(head, str) or not isinstance(number, int):
            continue
        # A branch reused across two PRs keeps the later one: it is the merge
        # that the tip of the local branch could plausibly have reached.
        if number > merged.get(head, 0):
            merged[head] = number
    return merged, None


def local_branches(cwd=None):
    """[(name, upstream, ahead, gone)] for every local branch, from one call."""
    fmt = "%(refname:short)\t%(upstream:short)\t%(upstream:track)"
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
        found = _AHEAD.search(track)
        rows.append((name, upstream, int(found.group(1)) if found else 0,
                     "gone" in track))
    return rows


def held_branches(cwd=None):
    """Branches checked out in any worktree, the current one included -- the
    main worktree is a worktree, so this needs no separate HEAD check. Deleting
    one of these fails anyway; naming it is the point."""
    out, rc = git(["worktree", "list", "--porcelain"], cwd=cwd)
    if rc != 0:
        return set()
    return {line[len("branch refs/heads/"):]
            for line in out.splitlines()
            if line.startswith("branch refs/heads/")}


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


def classify(row, base, held, ancestry, prs):
    """(status, why) for one branch. Order is the safety policy: anything a
    delete would fail on or lose is settled before any merge signal is read."""
    name, _upstream, ahead, gone = row
    if name == base:
        return None, None
    if name in held:
        return "held", "checked out in a worktree"
    if ahead:
        return "ahead", "%d commit(s) not on its upstream" % ahead
    if name in ancestry:
        return "deletable", "ancestry: already on %s" % base
    if name in prs:
        return "deletable", "pr: #%d merged" % prs[name]
    if gone:
        return "gone", "upstream deleted on the remote, merge unproven"
    return "keep", "no merge signal"


def sweep(base, cwd=None):
    """[(name, status, why)] ordered by status then name, plus the gh note."""
    prs, note = gh_merged_prs(cwd=cwd)
    held = held_branches(cwd=cwd)
    ancestry = merged_by_ancestry(base, cwd=cwd)
    rows = []
    for row in local_branches(cwd=cwd):
        status, why = classify(row, base, held, ancestry, prs)
        if status:
            rows.append((row[0], status, why))
    rows.sort(key=lambda r: (STATUS_ORDER.index(r[1]), r[0]))
    return rows, note


def delete(names, cwd=None):
    """[(name, sha_or_None)] for each attempted delete. `-D` not `-d`: a
    squash-merged branch is not an ancestor of anything, so `-d` refuses
    exactly the branches this exists to remove."""
    done = []
    for name in names:
        # refs/heads/ explicitly: a tag sharing the branch's name would win
        # the bare-name lookup, and the SHA printed here is the whole undo.
        sha, rc = git(["rev-parse", "--short", "refs/heads/" + name], cwd=cwd)
        sha = sha.strip() if rc == 0 else None
        _, rc = git(["branch", "-D", name], cwd=cwd)
        done.append((name, sha if rc == 0 else None))
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
    lines.append("%-*s  %-9s  %s" % (width, "BRANCH", "STATUS", "WHY"))
    for name, status, why in rows:
        lines.append("%-*s  %-9s  %s" % (width, name, status, why))
    counts = {}
    for _, status, _ in rows:
        counts[status] = counts.get(status, 0) + 1
    summary = ", ".join("%d %s" % (counts[s], s)
                        for s in STATUS_ORDER if s in counts)
    lines.append("")
    lines.append(summary + ".")
    if counts.get("deletable"):
        lines.append("Re-run with --delete to remove the deletable ones.")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", help="branch the work should have landed on")
    ap.add_argument("--delete", action="store_true",
                    help="delete the branches reported deletable")
    ap.add_argument("--repo", help="run against this directory")
    args = ap.parse_args(argv)

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
    targets = [name for name, status, _ in rows if status == "deletable"]
    if not targets:
        return 0
    print("")
    for name, sha in delete(targets, cwd=cwd):
        if sha:
            print("Deleted %s (was %s) -- undo with: git branch %s %s"
                  % (name, sha, name, sha))
        else:
            print("Could not delete %s" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
