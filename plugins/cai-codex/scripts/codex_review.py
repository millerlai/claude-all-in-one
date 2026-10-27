#!/usr/bin/env python3
"""Run one `codex exec review` for verify, but only inside a read-only sandbox.

    codex_review.py --base <ref> [--out <file>] [--project-dir <dir>]

Prints one JSON object. The call comes from resolve_review_command.decide, so
this script decides nothing about whether Codex is usable. Codex prints a
banner with a `sandbox:` line on stderr first; the review is let finish only
when that line says `read-only`, otherwise the whole process tree is stopped.
Exit 0 = ran, 3 = fall back (the `reason` says why), 5 = the inputs cannot be
used, 6 = a process could not be stopped (`left_running` lists the pids).

stdout and stderr go to files under `<top>/.cai/platform-review/` (a Codex
workspace-write sandbox cannot write the system temp dir) and are deleted
afterwards; stderr is never printed, only the sandbox word is taken from it.
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import cai_paths
import local_run
import resolve_review_command as rrc

BANNER_SECONDS = 60
TIMEOUT_SECONDS = 900
POLL_SECONDS = 0.5
BANNER_BYTES = 64 * 1024
GUARD_ENV = "CAI_PLATFORM_REVIEW"
SANDBOX_LINE = re.compile(r"^sandbox:\s*([a-z-]+)", re.M)
EXIT_RAN, EXIT_FALLBACK, EXIT_INVALID, EXIT_LEFT_RUNNING = 0, 3, 5, 6

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_CAPTURE = os.path.join(cai_paths.CAI_DIR, "platform-review")


def _result(call, status, reason, sandbox=None, seconds=0, review=None, left=(), notes=()):
    return {"format": 1, "status": status, "call": (call or {}).get("call"),
            "reason": reason, "sandbox": sandbox, "seconds": int(seconds),
            "review": review, "left_running": list(left), "notes": list(notes)}


def _read(path, limit=None):
    try:
        with open(path, "rb") as fh:
            return fh.read(limit).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _sandbox(stderr_text):
    # Only complete lines: a banner caught mid-write must not read as a shorter word.
    complete = stderr_text[:stderr_text.rfind("\n") + 1]
    found = SANDBOX_LINE.search(_ANSI.sub("", complete))
    return found.group(1) if found else None


def run(call, project_dir, timeout_s=TIMEOUT_SECONDS, banner_s=BANNER_SECONDS, environ=None):
    """Run the review `call` (a `decide` result) in `project_dir`, the repository top."""
    environ = os.environ if environ is None else environ
    if environ.get(GUARD_ENV):
        return _result(call, "fallback", "already inside a platform review")
    if call.get("status") != "run":
        return _result(call, "fallback", call.get("reason"), notes=call.get("notes", ()))
    notes = list(call.get("notes", ()))
    try:
        local_run.install_safety_net()
    except OSError:
        return _result(call, "fallback", "cannot guarantee the review's processes stop",
                       notes=notes)
    cai_paths.ensure_dir(project_dir)
    capture = os.path.join(project_dir, _CAPTURE)
    os.makedirs(capture, exist_ok=True)
    # Its own directory: a second run in the same checkout must not truncate or delete these.
    run_dir = tempfile.mkdtemp(dir=capture)
    out_path, err_path = os.path.join(run_dir, "stdout.txt"), os.path.join(run_dir, "stderr.txt")
    env ={**environ, **call["env"], GUARD_ENV: "1"}
    started = time.monotonic()
    tree = None
    result = None
    try:
        try:
            tree = local_run.start_tree(call["argv"], project_dir, out_path, err_path, env)
        except OSError:
            result = _result(call, "fallback", "codex could not be started", notes=notes)
            return result
        reason = None
        mode = None
        while True:
            elapsed = time.monotonic() - started
            code = tree.popen.poll()
            if mode is None:  # the banner is at the top; once read, stderr is not looked at again
                mode = _sandbox(_read(err_path, BANNER_BYTES))
            if code is not None:
                # Exit code first: a crash can come before any banner (29 ms, exit 1).
                if code != 0:
                    reason = "codex exec review exited %d" % code
                elif mode is None:
                    reason = "no sandbox line from codex"
                elif mode != "read-only":
                    reason = "sandbox was %s" % mode
                break
            if mode is not None and mode != "read-only":
                reason = "sandbox was %s" % mode
            elif mode is None and elapsed > banner_s:
                reason = "no sandbox line from codex"
            elif elapsed > timeout_s:
                reason = "timed out after %d s" % timeout_s
            if reason:
                break
            time.sleep(POLL_SECONDS)
        left = local_run.stop_tree(tree)
        review = _read(out_path)
        if reason is None and not review.strip():
            reason = "no review text"
        seconds = time.monotonic() - started
        if reason:
            result = _result(call, "fallback", reason, mode, seconds, left=left, notes=notes)
        else:
            result = _result(call, "ran", None, mode, seconds, review, left, notes)
        return result
    finally:
        # Windows: a straggler still holding a file makes the delete fail; the
        # result is already built, so say so in its notes rather than raise.
        if tree is not None and tree in local_run._LIVE:  # an exception got us here
            local_run.stop_tree(tree)
        undeleted = False
        for path in (out_path, err_path):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except OSError:
                undeleted = True
                if result is not None:
                    result["notes"].append("could not delete %s" % os.path.basename(path))
        try:
            os.rmdir(run_dir)
        except OSError:
            if result is not None and not undeleted:
                result["notes"].append("could not delete the capture directory")


def _platform_review_file(result):
    return ("# platform review\ncall: %s\nstatus: ran\nreading: pending\nreason: -\n---\n%s"
            % (result["call"], result["review"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="base ref to review against")
    ap.add_argument("--out", help="write the platform review file here when the review ran")
    ap.add_argument("--project-dir", default=".",
                    help="directory inside the repository (default: current directory)")
    args = ap.parse_args(argv)
    if args.out:
        # Only this run's result may be there: a fallback never writes the file,
        # so an earlier round's `status: ran` would otherwise be read as this one's.
        try:
            os.remove(args.out)
        except FileNotFoundError:
            pass
    try:
        top = rrc._git(os.path.abspath(args.project_dir), "rev-parse", "--show-toplevel") \
            .decode("utf-8", errors="replace").strip()
        call = rrc.decide(**rrc.gather("codex", args.base, top))
    except rrc.GatherError as e:
        call = rrc._result("codex", args.base, "invalid", str(e))
    if call["status"] == "invalid":
        result = _result(call, "fallback", call["reason"], notes=call["notes"])
        code = EXIT_INVALID
    else:
        result = run(call, top)
        code = EXIT_RAN if result["status"] == "ran" else EXIT_FALLBACK
        if result["left_running"]:
            code = EXIT_LEFT_RUNNING
    # Exit 6 is a fallback to the caller, which writes the fallback file itself.
    if args.out and result["status"] == "ran" and not result["left_running"]:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_platform_review_file(result), encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    # The review text may be non-ASCII; a piped Windows stdout is not UTF-8.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
