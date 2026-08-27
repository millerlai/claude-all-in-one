#!/usr/bin/env python3
"""Zero-token stage gate for the track skill. Zero deps.

A stage's model reads its own reference and decides whether to start; this
script decides whether it is *allowed* to. It answers only what state.md and
the artifact on disk already settle, so a gate that would otherwise cost a
model turn every time a stage begins costs nothing.

Usage:  preflight.py <stage-id> --track-dir DIR [--project-dir DIR]
Exit:   0 passed, 2 blocked, 1 usage error (unknown stage, missing --track-dir).
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STAGES_JSON = os.path.join(HERE, "..", "skills", "track", "stages.json")
DESIGN_PROBE = os.path.join(HERE, "design_probe.py")

# The three suffixes the /cai:design-*-doc commands already write. state.md
# carries no separate field for this -- the filename is the convention.
SUFFIX_KIND = {"-high-level.md": "hld", "-detail.md": "detail", "-delta.md": "delta"}


def resolve(rel, *bases):
    """Same convention as design_probe.resolve(): try each base in the order
    the caller says is likeliest, so a path written relative to the project
    root is found even when the track directory sits elsewhere."""
    for base in bases:
        p = os.path.normpath(os.path.join(base or ".", rel))
        if os.path.isfile(p):
            return p
    return None


def data_rows(text):
    """Every stage row of a state.md table, as lists of trimmed cells. The
    header and the `---` separator are dropped here rather than at each call
    site: two readers that disagree about what counts as a row would disagree
    about how many stages a track has, which is the one number state.md and
    stages.json have to agree on."""
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not (s.startswith("|") and s.endswith("|")):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        first = cells[0] if cells else ""
        if first in ("", "stage") or set(first) <= {"-"}:
            continue
        rows.append(cells)
    return rows


def state_row(track_dir, stage_id):
    """The stage table row in state.md, as a list of trimmed cells, or None
    when state.md is missing or names no such row. Not being able to read it
    is a blocked stage, not a usage error -- a track with no state cannot
    say whether this stage may start."""
    path = os.path.join(track_dir, "state.md")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for cells in data_rows(text):
        if cells[0] == stage_id:
            return cells
    return None


def design(track_dir, project_dir):
    row = state_row(track_dir, "design")
    if row is None:
        return [(False, "state_md (cannot read state.md or find the design row)")]

    artifact = row[2] if len(row) > 2 else ""
    if not artifact or artifact == "—":
        return [(False, "artifact_named (design row names no artifact)")]

    kind = None
    for suffix, k in SUFFIX_KIND.items():
        if artifact.endswith(suffix):
            kind = k
            break
    if kind is None:
        return [(False, "artifact_kind (%s matches none of -high-level.md, "
                         "-detail.md, -delta.md)" % artifact)]

    # Citations inside the document are project-root relative (design_probe's
    # own roots convention), so look there first and fall back to the track
    # directory in case the artifact is tracked alongside state.md instead.
    doc = resolve(artifact, project_dir, track_dir)
    if doc is None:
        return [(False, "artifact_exists (%s not found)" % artifact)]

    done = subprocess.run(
        [sys.executable, DESIGN_PROBE, "--kind", kind, "--project-dir", project_dir, doc],
        capture_output=True, text=True)
    checks = [(line.startswith("PASS "), line[5:])
              for line in done.stdout.splitlines()
              if line.startswith("PASS ") or line.startswith("FAIL ")]
    if not checks:
        checks.append((done.returncode == 0, "design_probe (%s)" % done.stdout.strip()))
    return checks


def git(cwd, *args):
    """Same shape as bash_guard.py's own git() helper -- duplicated rather
    than imported, since bash_guard is out of scope for this change and the
    two would otherwise couple two independently-versioned CLI surfaces."""
    try:
        return subprocess.run(["git", *args], cwd=cwd or None,
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None


def is_git_repo(cwd):
    done = git(cwd, "rev-parse", "--is-inside-work-tree")
    return bool(done and done.returncode == 0)


def current_branch(cwd):
    """Branch name, or None on detached HEAD -- symbolic-ref still answers on
    an unborn HEAD (a freshly-init'd repo with no commits), which is exactly
    what intake needs before the first commit exists."""
    done = git(cwd, "symbolic-ref", "--short", "HEAD")
    return done.stdout.strip() if done and done.returncode == 0 else None


def active_tracks(track_root):
    """The track root's own subdirectories, minus `done`. Active means exactly
    this: `done/` is the archive and never counts, or a user who finished five
    features could never start a sixth. track_state.py calls this one rather
    than keeping its own copy -- both compare the answer against the 5-track
    cap, and two definitions of "active" would disagree at the boundary."""
    if not os.path.isdir(track_root):
        return []
    return sorted(n for n in os.listdir(track_root)
                  if n != "done" and os.path.isdir(os.path.join(track_root, n)))


def intake(track_dir, project_dir):
    if not is_git_repo(project_dir):
        branch_check = (False, "not_main_branch (%s is not a git repository)" % project_dir)
    else:
        branch = current_branch(project_dir)
        branch_check = (branch not in ("main", "master"),
                         "not_main_branch (branch is %s)" % (branch or "detached HEAD"))

    track_root = os.path.dirname(os.path.normpath(track_dir))
    active = active_tracks(track_root)
    active_check = (len(active) < 5,
                     "active_tracks (%d active: %s)" % (len(active), ", ".join(active) or "none"))

    feature = os.path.basename(os.path.normpath(track_dir))
    name_check = (feature not in ("current", "done"), "reserved_name (%s)" % feature)

    return [branch_check, active_check, name_check]


def discover(track_dir, project_dir):
    row = state_row(track_dir, "intake")
    if row is None:
        return [(False, "state_md (cannot read state.md or find the intake row)")]
    status = row[1] if len(row) > 1 else ""
    ok = bool(status)
    return [(ok, "intake_status (intake row's status is %s)" % (status if ok else "empty"))]


def build(track_dir, project_dir):
    row = state_row(track_dir, "design")
    if row is None:
        return [(False, "state_md (cannot read state.md or find the design row)")]

    artifact = row[2] if len(row) > 2 else ""
    if not artifact or artifact == "—":
        return [(False, "artifact_named (design row names no artifact)")]

    doc = resolve(artifact, project_dir, track_dir)
    if doc is None:
        return [(False, "artifact_exists (%s not found)" % artifact)]

    with open(doc, encoding="utf-8") as fh:
        has_breakdown = "## Work breakdown" in fh.read()
    label = ("work_breakdown (%s)" % artifact if has_breakdown else
             "work_breakdown (%s has no ## Work breakdown heading)" % artifact)
    return [(has_breakdown, label)]


def find_base_ref(cwd):
    """The first usable base ref: the remote's default branch if origin
    answers, else a local main or master. diff-review's SKILL.md walks the
    same chain to pick a ref a human would review against; this only needs to
    know whether a base exists at all, so it stops at the first hit."""
    done = git(cwd, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if done and done.returncode == 0:
        return done.stdout.strip()
    for ref in ("origin/main", "origin/master", "main", "master"):
        done = git(cwd, "rev-parse", "--verify", "--quiet", ref)
        if done and done.returncode == 0:
            return ref
    return None


def verify(track_dir, project_dir):
    if not is_git_repo(project_dir):
        return [(False, "has_changes (%s is not a git repository)" % project_dir)]

    status = git(project_dir, "status", "--porcelain")
    dirty = bool(status and status.stdout.strip())

    base = find_base_ref(project_dir)
    diff = False
    if base:
        done = git(project_dir, "diff", "--quiet", "%s...HEAD" % base)
        diff = bool(done and done.returncode == 1)

    ok = dirty or diff
    if dirty:
        detail = "uncommitted changes"
    elif diff:
        detail = "diff from %s" % base
    else:
        detail = "nothing to review"
    return [(ok, "has_changes (%s)" % detail)]


def ship(track_dir, project_dir):
    row = state_row(track_dir, "verify")
    if row is None:
        return [(False, "state_md (cannot read state.md or find the verify row)")]
    status = row[1] if len(row) > 1 else ""
    status_check = (bool(status), "verify_status (verify row's status is %s)" % (status or "empty"))

    if not is_git_repo(project_dir):
        clean_check = (False, "clean_tree (%s is not a git repository)" % project_dir)
        branch_check = (False, "not_main_branch (%s is not a git repository)" % project_dir)
    else:
        working = git(project_dir, "status", "--porcelain")
        clean = bool(working and not working.stdout.strip())
        clean_check = (clean, "clean_tree (working tree %s)" %
                        ("is clean" if clean else "has uncommitted changes"))
        branch = current_branch(project_dir)
        branch_check = (branch not in ("main", "master"),
                         "not_main_branch (branch is %s)" % (branch or "detached HEAD"))

    return [status_check, clean_check, branch_check]


STAGES = {"design": design, "intake": intake, "discover": discover,
          "build": build, "verify": verify, "ship": ship}


class ArgParser(argparse.ArgumentParser):
    # argparse's own error() exits 2, which this script reserves for "blocked".
    # A usage mistake is a different failure and gets exit 1 instead.
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(1)


def main():
    ap = ArgParser(description=__doc__.splitlines()[0])
    ap.add_argument("stage")
    ap.add_argument("--track-dir", required=True)
    ap.add_argument("--project-dir", default=".")
    args = ap.parse_args()

    if args.stage not in STAGES:
        print("unknown stage: %s" % args.stage, file=sys.stderr)
        return 1

    failed = 0
    for ok, label in STAGES[args.stage](args.track_dir, args.project_dir):
        print(("PASS " if ok else "FAIL ") + label)
        failed += not ok
    print("-- %s: %d probe(s) failed" % (args.stage, failed))
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
