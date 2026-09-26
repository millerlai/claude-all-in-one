#!/usr/bin/env python3
"""Lists every annotated case under this repo's tests/review-benchmark/,
one line per expected finding. Run from the repo root:

    python plugins/cai/scripts/review_benchmark_cases.py
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_UP3 = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
COLLECTION_DIR: str = os.path.join(_UP3, "tests", "review-benchmark")


def case_rows(collection_dir: str) -> list[str]:
    """One line per case: its expected findings, or "(none)" when empty."""
    rows = []
    for name in sorted(os.listdir(collection_dir)):
        case_dir = os.path.join(collection_dir, name)
        if not os.path.isdir(case_dir):
            continue
        with open(os.path.join(case_dir, "expected.json"), encoding="utf-8") as fh:
            items = json.load(fh).get("expected", [])
        if not items:
            rows.append(f"{name}  (none)")
        for item in items:
            span = f"{item['line_start']}-{item['line_end']}"
            rows.append(f"{name}  {item['lens']}  {item['file']}:{span}")
    return rows


def main() -> int:
    for row in case_rows(COLLECTION_DIR):
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
