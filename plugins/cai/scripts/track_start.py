#!/usr/bin/env python3
"""Puts a new track on a feature branch before intake's preflight ever runs.
Zero deps.

`/cai:track <feature>` used to create `state.md` and go straight to intake,
which FAILs `not_main_branch` whenever the branch is `main`/`master`
(preflight.intake()) -- `rules/workflow.md` says to branch first, but
nothing in the track procedure did it, so every first attempt on `main` was
recorded `blocked` and the branch was made by hand (#193). This script is
that step: on `main`/`master` it fast-forwards from upstream (skipped, with a
message, when there is none) and switches to `track/<feature>`; on any other
branch, or a detached HEAD, it leaves things alone. Preflight intake is
unchanged and still blocks on `main` as the backstop.

Usage:  track_start.py --track-dir DIR [--project-dir DIR]
Exit:   0 proceed (a branch was created, or none was needed), 2 stop and
        create nothing, 1 usage error.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preflight  # noqa: E402

PULL_TIMEOUT = 60  # preflight.git()'s 5s is sized for a local answer; a real
                    # fetch over the network needs far more room.


def git(cwd, *args, timeout=5):
    """Own copy of preflight.git(), not the import: every call here needs
    GIT_TERMINAL_PROMPT=0 so a credential prompt cannot hang the script, and
    the pull needs a much longer timeout than the rest -- two things
    preflight.git() does not parametrize because none of its own callers
    need them. Decodes as UTF-8 with errors="replace" for the same reason
    preflight.git() does: the console locale is strict, and a name it cannot
    read left stdout None (#190)."""
    if os.name == "nt":
        # Windows looks for a bare "git" in this process's current directory
        # before PATH unless this is set in *this* process: env= below only
        # reaches the child (#272).
        os.environ.setdefault("NoDefaultCurrentDirectoryInExePath", "1")
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        return subprocess.run(["git", *args], cwd=cwd or None, env=env,
                              capture_output=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def first_line(done):
    text = (done.stderr or done.stdout or "").strip()
    return (preflight._escape_control_chars(text.splitlines()[0])
            if text else "no message")


def ref_exists(project_dir, ref):
    done = git(project_dir, "rev-parse", "--verify", "--quiet", ref)
    if done is None:
        return None
    return done.returncode == 0


def write_baseline(track_dir, project_dir):
    """Snapshot every untracked path into `<track-dir>/untracked-at-start.json`,
    read later by `preflight.py`'s `untracked_since_start` (#198) so a Gate 2
    reminder can tell this track's own new files apart from whatever scratch
    was already lying around.

    Called on every exit-0 path below, not only the branch this script just
    created -- most tracks start already on a feature branch
    (`preflight.py intake`'s guidance), and that path used to write nothing,
    which made the common case the one with no baseline instead of the rare
    one (#198 critique).

    Best-effort: git not answering, or the write failing, leaves no baseline
    file, which `untracked_since_start` already reports honestly as "no
    baseline recorded" -- it must never be a reason this script stops."""
    paths = preflight._untracked_paths(project_dir)
    if paths is None:
        return
    try:
        os.makedirs(track_dir, exist_ok=True)
        with open(os.path.join(track_dir, preflight.UNTRACKED_BASELINE_NAME),
                  "w", encoding="utf-8") as fh:
            json.dump(paths, fh)
    except OSError:
        pass


def start(track_dir, project_dir):
    """(exit_code, message) -- never raises, same contract as preflight's
    checks: not knowing is a reason to stop, not to guess."""
    feature = os.path.basename(os.path.normpath(track_dir))

    repo = preflight.is_git_repo(project_dir)
    if repo is preflight.GIT_DID_NOT_ANSWER:
        return 2, "git did not answer -- stopping"
    if not repo:
        return 0, "%s is not a git repository -- leaving branch alone" % project_dir

    branch = preflight.current_branch(project_dir)
    if branch is preflight.UNKNOWN_BRANCH:
        return 2, "git did not answer -- stopping"
    if branch is None:
        write_baseline(track_dir, project_dir)
        return 0, "detached HEAD -- leaving it alone"
    if branch not in ("main", "master"):
        write_baseline(track_dir, project_dir)
        return 0, "already on %s -- leaving it alone" % branch

    name = "track/%s" % feature
    fmt = git(project_dir, "check-ref-format", "--branch", name)
    if fmt is None:
        return 2, "git did not answer -- stopping"
    if fmt.returncode != 0:
        return 2, "%s is not a legal branch name" % name

    local = ref_exists(project_dir, "refs/heads/%s" % name)
    if local is None:
        return 2, "git did not answer -- stopping"
    if local:
        return 2, ("%s already exists locally -- switch to it by hand "
                    "(`git switch %s`) or pick another feature name" % (name, name))

    remote = ref_exists(project_dir, "refs/remotes/origin/%s" % name)
    if remote is None:
        return 2, "git did not answer -- stopping"
    if remote:
        return 2, "%s already exists on origin -- pick another feature name" % name

    upstream = git(project_dir, "rev-parse", "--abbrev-ref",
                   "--symbolic-full-name", "@{u}")
    pulled_note = None
    if upstream is not None and upstream.returncode == 0:
        pull = git(project_dir, "pull", "--ff-only", timeout=PULL_TIMEOUT)
        if pull is None:
            return 2, "git did not answer -- stopping"
        if pull.returncode != 0:
            return 2, "git pull --ff-only failed: %s" % first_line(pull)
        pulled_note = "pulled %s before branching" % upstream.stdout.strip()
    else:
        pulled_note = "no upstream for %s -- skipped the pull" % branch

    switch = git(project_dir, "switch", "-c", name)
    if switch is None:
        return 2, "git did not answer -- stopping"
    if switch.returncode != 0:
        # `git switch -c` on an unborn HEAD (a freshly-init'd repo with no
        # commits) is unverified across git versions; `checkout -b` is the
        # long-standing equivalent and covers that case if switch does not.
        checkout = git(project_dir, "checkout", "-b", name)
        if checkout is None:
            return 2, "git did not answer -- stopping"
        if checkout.returncode != 0:
            return 2, "could not create %s: %s" % (name, first_line(checkout))

    write_baseline(track_dir, project_dir)
    return 0, "%s; created and switched to %s" % (pulled_note, name)


class ArgParser(argparse.ArgumentParser):
    # argparse's own error() exits 2, which this script reserves for "stop,
    # create nothing". A usage mistake is a different failure and gets 1.
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(1)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = ArgParser(description=__doc__.splitlines()[0])
    ap.add_argument("--track-dir", required=True)
    ap.add_argument("--project-dir", default=".")
    args = ap.parse_args()

    code, message = start(args.track_dir, args.project_dir)
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
