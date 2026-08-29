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
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STAGES_JSON = os.path.join(HERE, "..", "skills", "track", "stages.json")
DESIGN_PROBE = os.path.join(HERE, "design_probe.py")

# The attempt ledger is read here, not shelled out to: this script already
# opens state.md itself, and counting integers does not need a process
# boundary. ledger.py imports nothing back, which is what keeps the
# track_state -> preflight -> ledger chain from closing into a cycle.
sys.path.insert(0, HERE)
import ledger  # noqa: E402

DEFAULT_MAX_ATTEMPTS = 5
MAX_ATTEMPTS_ENV = "CAI_TRACK_MAX_ATTEMPTS"

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


def max_attempts():
    """The retry cap: CAI_TRACK_MAX_ATTEMPTS, or 5. `0` means no cap.

    Anything unusable -- not a number, negative -- is the default rather than
    an error. This variable exists to let someone out of a stage that has
    stopped letting them in; it must never become the reason they are stuck."""
    try:
        value = int(os.environ.get(MAX_ATTEMPTS_ENV, ""))
    except ValueError:
        return DEFAULT_MAX_ATTEMPTS
    return value if value >= 0 else DEFAULT_MAX_ATTEMPTS


def ledger_attempts(track_dir, stage):
    """How many times this stage has failed since it last passed or was
    skipped, and whether that is still under the cap.

    Blocking is only half the job. A caller who is told "5 of 5" and nothing
    else has to go and read the ledger, which is the trip this whole design
    exists to remove -- so the failing label carries every attempt's reason
    and all three ways out."""
    limit = max_attempts()
    count = ledger.attempts(track_dir, stage)
    if limit == 0:
        return True, "ledger_attempts (%d so far, no cap -- %s=0)" % (count, MAX_ATTEMPTS_ENV)
    if count < limit:
        return True, "ledger_attempts (%d of %d)" % (count, limit)

    history = "\n".join(
        "       %d. %s -- %s" % (r.get("attempt"), r.get("outcome"),
                                 r.get("note") or "no note given")
        for r in ledger.streak(track_dir, stage))
    return False, (
        "ledger_attempts (%d of %d since %s last passed)\n%s\n"
        "       clear it with any one of:\n"
        "         /cai:track skip %s --reason \"<why>\"\n"
        "         %s=<a bigger number, or 0 for no cap>\n"
        "         delete %s"
        % (count, limit, stage, history, stage, MAX_ATTEMPTS_ENV,
           os.path.join(track_dir, ledger.LEDGER_NAME)))


def ledger_intact(track_dir):
    """Reports broken ledger lines. Never blocks on them.

    R5 says one unparseable line must not stop the track, and a FAIL here
    hangs off all six stages -- which is precisely stopping the track. So a
    corrupt ledger is loud and harmless: every stage says so, none refuses."""
    lines = ledger.malformed_lines(track_dir)
    if not lines:
        return True, "ledger_intact (0 malformed)"
    return True, "ledger_intact (%d malformed line(s) at %s)" % (
        len(lines), ", ".join(str(n) for n in lines))


def artifact_unchanged(track_dir, project_dir):
    """UC5: prove build is reading the document a person actually signed off.

    Both the path and the digest come from the ledger record, not from
    state.md. The cell in state.md can be overwritten by any later stage; the
    record of what passed cannot."""
    record = ledger.last_passed(track_dir, "design")
    if record is None or not record.get("sha256"):
        return True, "artifact_unchanged (no signed-off design recorded)"

    artifact = record.get("artifact") or ""
    doc = resolve(artifact, project_dir, track_dir)
    if doc is None:
        return False, ("artifact_unchanged (%s was signed off and is not there now)"
                       % artifact)
    with open(doc, "rb") as fh:
        now = hashlib.sha256(fh.read()).hexdigest()
    if now != record["sha256"]:
        return False, ("artifact_unchanged (%s changed since sign-off: %s now, %s then)"
                       % (artifact, now[:12], record["sha256"][:12]))
    return True, "artifact_unchanged (%s)" % artifact


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


UNKNOWN_BRANCH = object()


def current_branch(cwd):
    """The branch name, None on a genuinely detached HEAD, or UNKNOWN_BRANCH
    when git could not be asked at all.

    Those last two have to stay apart. Both used to be None, and both callers
    read "not main" as permission to proceed -- so a git that timed out or
    could not be executed silently passed the guard that exists to keep work
    off a protected branch. Not knowing is a reason to block, not to continue.

    symbolic-ref still answers on an unborn HEAD (a freshly-init'd repo with
    no commits), which is what intake needs before the first commit exists."""
    done = git(cwd, "symbolic-ref", "--short", "HEAD")
    if done is None:
        return UNKNOWN_BRANCH
    return done.stdout.strip() if done.returncode == 0 else None


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
        branch_check = (branch is not UNKNOWN_BRANCH and branch not in ("main", "master"),
                         "not_main_branch (branch is %s)" % (
                             "unknown -- git did not answer" if branch is UNKNOWN_BRANCH
                             else branch or "detached HEAD"))

    # abspath, not normpath: a bare `--track-dir feature-a` -- which is what a
    # caller already sitting in .claude/track/ passes -- leaves dirname() empty,
    # os.path.isdir("") is False, and the cap then counts zero tracks and lets
    # a sixth one through.
    track_root = os.path.dirname(os.path.abspath(track_dir))
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
    # Computed first so it survives the early returns below: it answers from
    # the ledger, so it is just as valid when state.md is the thing that is
    # broken -- and "the design changed after sign-off" is worth saying even
    # then.
    unchanged = artifact_unchanged(track_dir, project_dir)

    row = state_row(track_dir, "design")
    if row is None:
        return [unchanged, (False, "state_md (cannot read state.md or find the design row)")]

    artifact = row[2] if len(row) > 2 else ""
    if not artifact or artifact == "—":
        return [unchanged, (False, "artifact_named (design row names no artifact)")]

    doc = resolve(artifact, project_dir, track_dir)
    if doc is None:
        return [unchanged, (False, "artifact_exists (%s not found)" % artifact)]

    with open(doc, encoding="utf-8") as fh:
        has_breakdown = "## Work breakdown" in fh.read()
    label = ("work_breakdown (%s)" % artifact if has_breakdown else
             "work_breakdown (%s has no ## Work breakdown heading)" % artifact)
    return [unchanged, (has_breakdown, label)]


def find_base_ref(cwd):
    """The first usable base ref: the remote's default branch if origin
    answers, else a local main or master. stage-verify.md walks the
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
        branch_check = (branch is not UNKNOWN_BRANCH and branch not in ("main", "master"),
                         "not_main_branch (branch is %s)" % (
                             "unknown -- git did not answer" if branch is UNKNOWN_BRANCH
                             else branch or "detached HEAD"))

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
    # ledger_attempts quotes the notes a person wrote, so this script now
    # prints whatever alphabet they used. On Windows a piped stdout defaults
    # to the ANSI codepage and the caller cannot decode what comes back; the
    # console path is already UTF-8 (PEP 528), so only the pipe changes.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = ArgParser(description=__doc__.splitlines()[0])
    ap.add_argument("stage")
    ap.add_argument("--track-dir", required=True)
    ap.add_argument("--project-dir", default=".")
    args = ap.parse_args()

    if args.stage not in STAGES:
        print("unknown stage: %s" % args.stage, file=sys.stderr)
        return 1

    # The two ledger checks are added here rather than inside each of the six
    # stage functions: several of those return a single failing check early,
    # and UC8 asks for the ledger's condition on every stage, including the
    # ones that are already blocked for another reason.
    checks = list(STAGES[args.stage](args.track_dir, args.project_dir))
    checks.append(ledger_attempts(args.track_dir, args.stage))
    checks.append(ledger_intact(args.track_dir))

    failed = 0
    for ok, label in checks:
        print(("PASS " if ok else "FAIL ") + label)
        failed += not ok
    print("-- %s: %d probe(s) failed" % (args.stage, failed))
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
