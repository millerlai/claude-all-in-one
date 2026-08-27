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
    for line in text.splitlines():
        s = line.strip()
        if not (s.startswith("|") and s.endswith("|")):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and cells[0] == stage_id:
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


def not_implemented(stage_id):
    # Registered so the dispatch table stays complete; unit 5 replaces this
    # with the real preflight for each stage.
    def stub(track_dir, project_dir):
        return [(False, "not_implemented (unit 5 fills in the %s preflight)" % stage_id)]
    return stub


STAGES = {"design": design}
for _id in ("intake", "discover", "build", "verify", "ship"):
    STAGES[_id] = not_implemented(_id)


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
