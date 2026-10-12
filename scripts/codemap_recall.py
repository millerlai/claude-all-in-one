#!/usr/bin/env python3
"""Recall@5 and Recall@10 of the codemap index against a plain-Grep baseline.

    python scripts/codemap_recall.py --project-dir DIR --tasks FILE

FILE holds one JSON object per line: {"query": str, "expected_files": [str]}.
The tool prints the numbers side by side and no verdict: whether the index has
fallen far enough behind to need a better approach is the person's call.

Maintainer-side only (not shipped): it assumes this repository's layout.
"""
import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "plugins", "cai", "scripts"))
import codemap_index  # noqa: E402
import codemap_query  # noqa: E402
import codemap_store  # noqa: E402

NS = (5, 10)
INDEX_LIMIT = 1000


def recall(ranked: list, expected: list, n: int) -> float:
    want = set(expected)
    return len(set(ranked[:n]) & want) / len(want)


def grep_baseline(top: str, text: str) -> list:
    """Paths ranked as `grep -i` over every term would: by how many lines match,
    most first, then path. Files with no matching line are left out."""
    words = codemap_query.terms(text)
    scored = []
    for path, body in codemap_query.tracked_texts(top):
        count = sum(1 for line in body.splitlines()
                    if any(w in line.lower() for w in words))
        if count:
            scored.append((-count, path))
    return [path for _, path in sorted(scored)]


def _index_ranked(top, index, text):
    seen = []
    for hit in codemap_query.query(top, index, text, INDEX_LIMIT):
        if hit.path not in seen:
            seen.append(hit.path)
    return seen


def _read_tasks(path):
    tasks = []
    with open(path, encoding="utf-8") as fh:
        for number, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                query, expected = row["query"], row["expected_files"]
                ok = isinstance(query, str) and isinstance(expected, list) and expected \
                    and all(isinstance(p, str) for p in expected)
            except (ValueError, KeyError, TypeError):
                ok = False
            if not ok:
                raise ValueError("line %d: need {\"query\": str, \"expected_files\": "
                                 "[str, ...]}" % number)
            tasks.append((query, expected))
    return tasks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="codemap_recall.py")
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--tasks", required=True)
    args = parser.parse_args(argv)
    try:
        tasks = _read_tasks(args.tasks)
    except (OSError, ValueError) as exc:
        print("tasks file: %s" % exc, file=sys.stderr)
        return 1
    if not tasks:
        print("tasks file: no tasks", file=sys.stderr)
        return 1
    top = os.path.abspath(args.project_dir)
    status = codemap_index.status(top)
    print(codemap_index.state_line(status))   # a stale or absent index still counts
    index = codemap_store.load(top) if status.word not in ("absent", "unsupported") \
        else None
    sums = {("index", n): 0.0 for n in NS}
    sums.update({("grep", n): 0.0 for n in NS})
    for query, expected in tasks:
        ranked = {"index": _index_ranked(top, index, query) if index else [],
                  "grep": grep_baseline(top, query)}
        for which, files in ranked.items():
            for n in NS:
                sums[(which, n)] += recall(files, expected, n)
    print("tasks %d" % len(tasks))
    for which in ("index", "grep"):
        for n in NS:
            print("%s recall@%d %.2f" % (which, n, sums[(which, n)] / len(tasks)))
    return 0


if __name__ == "__main__":
    # The state line can name a non-ASCII file; a piped Windows stdout is not UTF-8.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
