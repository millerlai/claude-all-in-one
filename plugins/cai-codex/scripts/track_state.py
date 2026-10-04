#!/usr/bin/env python3
"""Zero-token state resolver for the track skill. Zero deps.

A new session has no memory of the conversation that started a track, so
resuming it must answer from files alone -- this script is that answer. It
never writes state.md; overwriting a row is the track's job, this only reads.

Usage:  track_state.py status    [--track-root DIR]
        track_state.py resolve   [--track-root DIR]   (prints only the feature name)
        track_state.py left-open [--track-root DIR]   (prints what state.md marks "Left open:")
Exit:   0 an active track exists, 2 no active track (or a state.md that
        disagrees with stages.json or the status vocabulary), 1 usage error.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STAGES_JSON = os.path.join(HERE, "..", "skills", "track", "stages.json")
DEFAULT_TRACK_ROOT = os.path.join(".claude", "track")

# preflight.py already implements "find this stage's row in state.md"; reuse
# it rather than writing that lookup a second time. (Its own inline loop is
# the one piece of table parsing this script could not fold into a single
# shared implementation -- preflight.py is out of scope for this change. See
# table_stage_ids() below, and the report, for why.)
sys.path.insert(0, HERE)
import preflight  # noqa: E402
import ledger  # noqa: E402
import pending  # noqa: E402


def stage_ids():
    with open(STAGES_JSON, encoding="utf-8") as fh:
        return [row["id"] for row in json.load(fh)["stages"]]


def current_feature(track_root):
    path = os.path.join(track_root, "current")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def resolve(track_root):
    """(feature, track_dir) on success, or (None, message) on failure. Both
    `resolve` and `status` print the same message on the exit-2 path, so it
    is built once here rather than in each command."""
    feature = current_feature(track_root)
    if not feature:
        msg = "no active track (no %s)" % os.path.join(track_root, "current")
        others = preflight.active_tracks(track_root)
        return None, msg + (
            "; tracks that do exist: %s" % ", ".join(others) if others else "")

    track_dir = os.path.join(track_root, feature)
    if not os.path.isdir(track_dir):
        others = preflight.active_tracks(track_root)
        msg = "current names %s, which does not exist" % track_dir
        return None, msg + (
            "; tracks that do exist: %s" % ", ".join(others) if others else "; no tracks exist")

    return feature, track_dir


def table_stage_ids(state_path):
    """The stage id in each of state.md's table rows, in file order. The
    definition of "a row" lives in preflight.data_rows() and only there."""
    with open(state_path, encoding="utf-8") as fh:
        return [cells[0] for cells in preflight.data_rows(fh.read())]


def bad_statuses(track_dir, order):
    """(stage id, the offending value) for every row whose status is outside
    ledger.STATUSES, in stages.json order. An empty list means the table is
    written in the vocabulary state.md actually has."""
    out = []
    for sid in order:
        row = preflight.state_row(track_dir, sid)
        status = row[1] if row and len(row) > 1 else ""
        if status not in ledger.STATUSES:
            out.append((sid, status))
    return out


def next_unfinished(track_dir, order):
    """The first stage in stages.json order whose status is not done or
    skipped, as (stage id, status), or None when every stage is done or
    skipped. One definition, shared by the current track's `next:` line and
    by every other active track's status line below (#204) -- two readers of
    "unfinished" would eventually disagree about where a track stands."""
    for sid in order:
        row = preflight.state_row(track_dir, sid)
        status = row[1] if row and len(row) > 1 else ""
        if status not in ("done", "skipped"):
            return sid, status
    return None


def head_line(project_dir):
    """`on: <branch> at <short sha>`, asked of git now: pending.md stores
    neither, because a stored value would be out of date by the time anyone
    reads it. Says so when git cannot answer instead of guessing."""
    branch = preflight.git(project_dir, "rev-parse", "--abbrev-ref", "HEAD")
    sha = preflight.git(project_dir, "rev-parse", "--short", "HEAD")
    if branch is None or sha is None:
        return "  on: unknown (git did not answer)"
    if branch.returncode != 0 or sha.returncode != 0:
        return "  on: unknown (not a git repository)"
    name = branch.stdout.strip()
    if name == "HEAD":
        name = "(detached HEAD)"
    return "  on: %s at %s" % (name, sha.stdout.strip())


def pending_lines(track_dir):
    """The `pending:` section for what a stage handed up and nobody finished
    answering, or [] when the track has none. Without pending.md this does
    nothing and asks git nothing; a file that cannot be used costs one line,
    never the exit code."""
    path = os.path.join(track_dir, pending.FILE_NAME)
    if not os.path.isfile(path):
        return []
    try:
        data = pending.load(path)
    except pending.PendingError as exc:
        return ["pending: %s; ignored" % exc]
    row = preflight.state_row(track_dir, data["stage"])
    status = row[1] if row and len(row) > 1 else ""
    if status in ("done", "skipped"):
        return ["pending: %s is for %s, which is already %s; stale, ignored"
                % (pending.FILE_NAME, data["stage"], status)]
    answered = sum(1 for q in data["questions"] if q["status"] == "answered")
    lines = ["pending: %s, round %d, %d of %d answered"
             % (data["stage"], data["round"], answered, len(data["questions"])),
             "  file: %s" % path]
    for q in data["questions"]:
        # text starts "N. <the decision>"; the number is printed by us.
        lines.append("  %d. [%s] %s" % (q["n"], q["status"],
                                        q["text"].split("\n")[0].split(". ", 1)[-1]))
    # This script runs from the project root (DEFAULT_TRACK_ROOT's assumption).
    track_root = os.path.abspath(os.path.dirname(track_dir))
    project_dir = os.path.dirname(os.path.dirname(track_root))
    lines.append(head_line(project_dir))
    lines.append("  resume: $track")
    return lines


def format_status(feature, track_dir, order, show_next=True):
    rows = {sid: preflight.state_row(track_dir, sid) for sid in order}
    lines = ["current: %s" % feature]
    skipped = []
    for sid in order:
        row = rows[sid]
        status = row[1] if row and len(row) > 1 else ""
        note = row[3] if row and len(row) > 3 else ""
        line = "%-10s %s" % (sid, status)
        if status == "skipped":
            skipped.append((sid, note))
            line += "  (reason: %s)" % note
        # Who let this one through, from the ledger record that says it passed
        # -- not from state.md, which has no column for it. A stage that has
        # not passed, or a track with no ledger at all, adds nothing here, so
        # every existing track's output is byte-for-byte what it was.
        passed = ledger.last_passed(track_dir, sid)
        if passed:
            gate = passed.get("gate", "unknown")
            if sid == "design":
                # Gate 1 is not whoever passed last: its Approve may land
                # before the stage's own pass, or carry no sha, and build
                # decides by design_signed_off -- so ask that, from the
                # project root this script runs in (DEFAULT_TRACK_ROOT's
                # assumption), rather than tell a person the opposite of what
                # build will do (#139).
                gate = ("human" if preflight.design_signed_off(track_dir, ".")[0]
                        else "not signed off")
            line += "  (gate: %s)" % gate
        lines.append(line)
    lines.append("")
    if show_next:
        next_stage = next_unfinished(track_dir, order)
        lines.append("next: %s"
                     % (next_stage[0] if next_stage
                        else "none -- every stage is done or skipped"))
        lines.extend(pending_lines(track_dir))
    if skipped:
        lines.append("skipped:")
        for sid, note in skipped:
            lines.append("  %s: %s" % (sid, note))
    track_root = os.path.dirname(track_dir)
    others = [t for t in preflight.active_tracks(track_root) if t != feature]
    lines.append("other active tracks: %s" % (", ".join(others) if others else "none"))
    for other in others:
        other_dir = os.path.join(track_root, other)
        other_state = os.path.join(other_dir, "state.md")
        if not os.path.isfile(other_state):
            lines.append("  %s  (no state.md)" % other)
            continue
        actual = table_stage_ids(other_state)
        if len(actual) != len(order) or set(actual) != set(order):
            lines.append("  %s  (state.md disagrees with stages.json)" % other)
            continue
        other_next = next_unfinished(other_dir, order)
        if other_next is None:
            lines.append("  %s  every stage done or skipped" % other)
        else:
            stage, status = other_next
            lines.append("  %s  stopped at: %s (%s)"
                         % (other, stage, status or "not started"))
    return "\n".join(lines)


def status(track_root):
    feature, info = resolve(track_root)
    if feature is None:
        print(info, file=sys.stderr)
        return 2

    track_dir = info
    state_path = os.path.join(track_dir, "state.md")
    if not os.path.isfile(state_path):
        print("no state.md in %s" % track_dir, file=sys.stderr)
        return 2

    order = stage_ids()
    actual = table_stage_ids(state_path)
    if len(actual) != len(order):
        print("state.md has %d stage row(s), stages.json has %d"
              % (len(actual), len(order)), file=sys.stderr)
        return 2
    unexpected = [sid for sid in actual if sid not in order]
    missing = [sid for sid in order if sid not in actual]
    if unexpected or missing:
        print("state.md stage ids disagree with stages.json: unexpected %s; "
              "missing %s" % (", ".join(unexpected) or "none",
                              ", ".join(missing) or "none"), file=sys.stderr)
        return 2

    bad = bad_statuses(track_dir, order)
    print(format_status(feature, track_dir, order, show_next=not bad))
    if bad:
        legal = ", ".join(s or "(empty)" for s in ledger.STATUSES)
        for sid, value in bad:
            print("unknown status for %s: %s (expected one of %s)"
                  % (sid, value, legal), file=sys.stderr)
        return 2
    return 0


def resolve_cmd(track_root):
    feature, info = resolve(track_root)
    if feature is None:
        print(info, file=sys.stderr)
        return 2
    print(feature)
    return 0


def left_open(track_root):
    feature, info = resolve(track_root)
    if feature is None:
        print(info, file=sys.stderr)
        return 2
    track_dir = info
    state_path = os.path.join(track_dir, "state.md")
    if not os.path.isfile(state_path):
        print("no state.md in %s" % track_dir, file=sys.stderr)
        return 2
    with open(state_path, encoding="utf-8") as fh:
        items = preflight.left_open_items(fh.read())
    if not items:
        print('Left open by %s: no "Left open:" marker in %s -- read it if '
              'this track predates the marker' % (feature, state_path))
        return 0
    print("Left open by %s:" % feature)
    for stage, item in items:
        print("- [%s] %s" % (stage, item))
    return 0


class ArgParser(argparse.ArgumentParser):
    # argparse's own error() exits 2, which this script reserves for "no
    # active track". A usage mistake is a different failure and gets 1.
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(1)


def main():
    # state.md's note column is prose a person wrote -- a skip reason, a
    # sentence about what is still open -- so this script prints whatever
    # alphabet they used, and `—` is state.md's own "no artifact" cell. On
    # Windows a piped stdout defaults to the ANSI codepage and the caller
    # cannot decode what comes back. The console path is already UTF-8
    # (PEP 528), so only the pipe changes.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = ArgParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["status", "resolve", "left-open"])
    ap.add_argument("--track-root", default=DEFAULT_TRACK_ROOT)
    args = ap.parse_args()

    if args.command == "status":
        return status(args.track_root)
    if args.command == "left-open":
        return left_open(args.track_root)
    return resolve_cmd(args.track_root)


if __name__ == "__main__":
    sys.exit(main())
