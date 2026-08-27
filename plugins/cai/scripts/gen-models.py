#!/usr/bin/env python3
"""
Apply models.json's role assignments to each component's `model:` frontmatter.

Components carry a model family alias (haiku/sonnet/opus); models.json says
which ROLE each component plays, and roles map to aliases. Editing a role's
alias there and re-running this script re-tiers every component in that role.

    python3 gen-models.py             # apply; rewrites files that differ
    python3 gen-models.py --check     # report drift, write nothing, exit 1 if any
    python3 gen-models.py --list      # print the resolved table

Only the value on the `model:` line inside the frontmatter is touched. The rest
of every file - including the body and every other frontmatter key - is left
byte for byte alone, which is why this is a line edit and not the whole-file
rewrite gen-commands.py does: those 72 files are generated, these are written
by hand and only their tier is managed.

Single source of truth: plugins/cai/models.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models.json"

# Only inside the frontmatter, only at the start of a line. A `model:` mentioned
# in prose (build-from-design's tier table quotes one) must not be rewritten.
MODEL_LINE = re.compile(r"^model:[ \t]*(\S+)[ \t]*$", re.MULTILINE)


def load():
    spec = json.loads(MODELS.read_text(encoding="utf-8"))
    roles, assignments = spec["roles"], spec["assignments"]
    unknown = sorted({r for r in assignments.values() if r not in roles})
    if unknown:
        sys.exit(f"models.json assigns unknown role(s): {', '.join(unknown)}")
    return roles, assignments


def split_frontmatter(text):
    """(frontmatter, rest) or (None, text) when there is no frontmatter."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    return text[: end + 4], text[end + 4 :]


def current_model(path):
    """The component's declared model, or None when it declares none."""
    fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    if fm is None:
        return None
    m = MODEL_LINE.search(fm)
    return m.group(1) if m else None


def retier(path, alias):
    """Rewrite the frontmatter's model line. Returns the previous value, or
    None when the file already agreed and nothing was written."""
    text = path.read_text(encoding="utf-8")
    fm, rest = split_frontmatter(text)
    if fm is None:
        sys.exit(f"{path}: no frontmatter to place `model:` in")
    m = MODEL_LINE.search(fm)
    if m is None:
        sys.exit(f"{path}: no `model:` line in frontmatter — add one, then re-run")
    was = m.group(1)
    if was == alias:
        return None
    path.write_text(fm[: m.start(1)] + alias + fm[m.end(1) :] + rest, encoding="utf-8")
    return was


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report drift, write nothing")
    ap.add_argument("--list", action="store_true", help="print the resolved table")
    args = ap.parse_args()

    roles, assignments = load()

    if args.list:
        for role, spec in roles.items():
            members = sorted(p for p, r in assignments.items() if r == role)
            print(f"\n{role} -> {spec['alias']}\n  {spec['criterion']}")
            for p in members:
                print(f"    {p}")
        return 0

    missing = [p for p in assignments if not (ROOT / p).is_file()]
    if missing:
        sys.exit("models.json names files that do not exist:\n  " + "\n  ".join(missing))

    drift, changed = [], 0
    for rel, role in sorted(assignments.items()):
        path, alias = ROOT / rel, roles[role]["alias"]
        if args.check:
            have = current_model(path)
            if have != alias:
                drift.append(f"{rel}: has {have!r}, {role} wants {alias!r}")
        else:
            was = retier(path, alias)
            if was is not None:
                print(f"  {rel}: {was} -> {alias}  ({role})")
                changed += 1

    if args.check:
        for line in drift:
            print(f"  DRIFT {line}")
        print(f"{len(drift)} file(s) drifted from models.json")
        return 1 if drift else 0

    print(f"{changed} file(s) re-tiered, {len(assignments) - changed} already correct")
    return 0


if __name__ == "__main__":
    sys.exit(main())
