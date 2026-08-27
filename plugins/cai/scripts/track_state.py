#!/usr/bin/env python3
"""Zero-token state resolver for the track skill. Zero deps.

A new session has no memory of the conversation that started a track, so
resuming it must answer from files alone -- this script is that answer. It
never writes state.md; overwriting a row is the track's job, this only reads.

Usage:  track_state.py status  [--track-root DIR]
        track_state.py resolve [--track-root DIR]   (prints only the feature name)
Exit:   0 an active track exists, 2 no active track (or a state.md that
        disagrees with stages.json), 1 usage error.
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
# table_row_count() below, and the report, for why.)
sys.path.insert(0, HERE)
import preflight  # noqa: E402


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


def table_row_count(state_path):
    """How many stage rows state.md's table actually has. The definition of
    "a row" lives in preflight.data_rows() and only there -- this count is
    compared against stages.json, so a second opinion about what counts would
    turn a healthy track into a reported mismatch."""
    with open(state_path, encoding="utf-8") as fh:
        return len(preflight.data_rows(fh.read()))


def format_status(feature, track_dir, order):
    rows = {sid: preflight.state_row(track_dir, sid) for sid in order}
    lines = ["current: %s" % feature]
    next_stage = None
    skipped = []
    for sid in order:
        row = rows[sid]
        status = row[1] if row and len(row) > 1 else ""
        note = row[3] if row and len(row) > 3 else ""
        line = "%-10s %s" % (sid, status)
        if status == "skipped":
            skipped.append((sid, note))
            line += "  (reason: %s)" % note
        lines.append(line)
        if next_stage is None and status not in ("done", "skipped"):
            next_stage = sid
    lines.append("")
    lines.append("next: %s" % (next_stage or "none -- every stage is done or skipped"))
    if skipped:
        lines.append("skipped:")
        for sid, note in skipped:
            lines.append("  %s: %s" % (sid, note))
    others = [t for t in preflight.active_tracks(os.path.dirname(track_dir)) if t != feature]
    lines.append("other active tracks: %s" % (", ".join(others) if others else "none"))
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
    actual = table_row_count(state_path)
    if actual != len(order):
        print("state.md has %d stage row(s), stages.json has %d"
              % (actual, len(order)), file=sys.stderr)
        return 2

    print(format_status(feature, track_dir, order))
    return 0


def resolve_cmd(track_root):
    feature, info = resolve(track_root)
    if feature is None:
        print(info, file=sys.stderr)
        return 2
    print(feature)
    return 0


class ArgParser(argparse.ArgumentParser):
    # argparse's own error() exits 2, which this script reserves for "no
    # active track". A usage mistake is a different failure and gets 1.
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(1)


def main():
    ap = ArgParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["status", "resolve"])
    ap.add_argument("--track-root", default=DEFAULT_TRACK_ROOT)
    args = ap.parse_args()

    if args.command == "status":
        return status(args.track_root)
    return resolve_cmd(args.track_root)


if __name__ == "__main__":
    sys.exit(main())
