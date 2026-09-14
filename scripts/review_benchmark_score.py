#!/usr/bin/env python3
"""gap03-review-benchmark: schema check plus scorer for the stored-diff
review benchmark. Zero deps -- json and os only.

Reads two things: the case collection under tests/review-benchmark/ (each
case a diff.patch plus an expected.json annotation) and, for one run, a
findings.json transcribed by hand from the four lens agents' prose reports.
Never calls a model, never touches the network (AC10).
"""
import argparse
import json
import os
import sys

LENSES = ("correctness", "conformance", "coverage", "security")
SEVERITIES = ("Blocker", "Major", "Minor")
TOLERANCE = 3  # decision one: a reported line within +-3 of the annotated span counts as a hit


def load_cases(collection_dir):
    """Every case directory under collection_dir, one dict each, holding the
    case name, the diff.patch path and the parsed expected.json. Directory
    order is sorted(), so report rows are deterministic."""
    cases = []
    for name in sorted(os.listdir(collection_dir)):
        case_dir = os.path.join(collection_dir, name)
        if not os.path.isdir(case_dir):
            continue
        with open(os.path.join(case_dir, "expected.json"), encoding="utf-8") as fh:
            expected = json.load(fh)
        cases.append({
            "case": name,
            "diff_path": os.path.join(case_dir, "diff.patch"),
            "expected": expected,
        })
    return cases


def schema_problems(expected):
    """Every reason one annotation is non-compliant, one sentence each;
    empty list when fully compliant. Reads only the dict passed in, never
    touches the filesystem."""
    problems = []

    def require(key, typ):
        if key not in expected:
            problems.append(f"missing {key}")
            return None
        value = expected[key]
        if not isinstance(value, typ):
            problems.append(f"{key} is not a {typ.__name__}")
            return None
        return value

    require("base_sha", str)
    require("base_ref", str)
    require("notes", str)
    expected_list = require("expected", list)
    absent_list = require("expected_absent", list)

    if expected_list is not None:
        for i, item in enumerate(expected_list):
            prefix = f"expected[{i}]"
            if not isinstance(item, dict):
                problems.append(f"{prefix} is not an object")
                continue
            lens = item.get("lens")
            if lens not in LENSES:
                problems.append(f"{prefix}.lens ({lens!r}) not in {LENSES}")
            if not isinstance(item.get("file"), str):
                problems.append(f"{prefix}.file is not a string")
            line_start = item.get("line_start")
            line_end = item.get("line_end")
            if not isinstance(line_start, int):
                problems.append(f"{prefix}.line_start is not an int")
            if not isinstance(line_end, int):
                problems.append(f"{prefix}.line_end is not an int")
            if (isinstance(line_start, int) and isinstance(line_end, int)
                    and line_end < line_start):
                problems.append(
                    f"{prefix}.line_end ({line_end}) < line_start ({line_start})")
            severity = item.get("severity")
            if severity not in SEVERITIES:
                problems.append(f"{prefix}.severity ({severity!r}) not in {SEVERITIES}")
            if not isinstance(item.get("cause"), str):
                problems.append(f"{prefix}.cause is not a string")

    if absent_list is not None:
        for i, lens in enumerate(absent_list):
            if lens not in LENSES:
                problems.append(f"expected_absent[{i}] ({lens!r}) not in {LENSES}")

    return problems


def scored_lenses(expected):
    """The lenses this case has ground truth for: the union of every lens
    named in `expected` and every lens listed in `expected_absent` (D4).
    A lens outside this set contributes only to the `unscored` counter,
    never to TP/FP/FN."""
    lenses = {item["lens"] for item in expected.get("expected", [])}
    lenses |= set(expected.get("expected_absent", []))
    return lenses


def matches(finding, want, tolerance=TOLERANCE):
    """lens equal AND file equal AND the finding's line falls inside
    [want.line_start - tolerance, want.line_end + tolerance]. severity does
    not participate (D3)."""
    if finding["lens"] != want["lens"] or finding["file"] != want["file"]:
        return False
    line = finding["line"]
    return want["line_start"] - tolerance <= line <= want["line_end"] + tolerance


def _rates(counts):
    """Fills precision/recall/f1 into counts in place, using None (not 0.0)
    whenever a formula's own denominator is zero -- 0.0 means "measured,
    and it's zero", None means "nothing to measure"."""
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    if precision is None or recall is None or (precision + recall) == 0:
        f1 = None
    else:
        f1 = 2 * precision * recall / (precision + recall)
    counts["precision"] = precision
    counts["recall"] = recall
    counts["f1"] = f1
    return counts


def score_case(expected, run):
    """One case, one run's counts. Pure: no file reads, no writes, no
    mutation of either argument. `run` is the whole findings.json dict
    (with `lens_runs` at the top level), not just its `findings` list."""
    case_name = run.get("case", "?")
    expected_list = expected.get("expected", [])
    absent_list = expected.get("expected_absent", [])
    if not expected_list and not absent_list:
        raise ValueError(f"case {case_name}: no ground truth "
                          "(expected and expected_absent both empty)")

    scored = scored_lenses(expected)
    findings = run.get("findings", [])
    lens_runs = run.get("lens_runs", {})
    failed_lenses = sorted(lens for lens, info in lens_runs.items()
                            if info.get("status") == "failed")

    per_lens = {lens: {"tp": 0, "fp": 0, "fn": 0,
                        "severity_match": 0, "severity_pairs": 0}
                for lens in LENSES}
    matched = [False] * len(expected_list)
    unscored = 0
    duplicate = 0

    for finding in findings:
        lens = finding.get("lens")
        if lens not in LENSES:
            raise ValueError(f"case {case_name}: unknown lens {lens!r}")
        line = finding.get("line")
        if not isinstance(line, int):
            raise ValueError(f"case {case_name}: finding line is not an int ({line!r})")

        if lens not in scored:
            unscored += 1
            continue

        hit_index = None
        for i, want in enumerate(expected_list):
            if not matched[i] and matches(finding, want):
                hit_index = i
                break

        if hit_index is not None:
            matched[hit_index] = True
            want = expected_list[hit_index]
            per_lens[lens]["tp"] += 1
            per_lens[lens]["severity_pairs"] += 1
            if finding.get("severity") == want.get("severity"):
                per_lens[lens]["severity_match"] += 1
            continue

        already_matched_hit = any(
            matched[i] and matches(finding, want)
            for i, want in enumerate(expected_list)
        )
        if already_matched_hit:
            duplicate += 1
        else:
            per_lens[lens]["fp"] += 1

    for i, want in enumerate(expected_list):
        if not matched[i]:
            per_lens[want["lens"]]["fn"] += 1

    for lens in LENSES:
        _rates(per_lens[lens])

    overall = {"tp": 0, "fp": 0, "fn": 0, "severity_match": 0, "severity_pairs": 0}
    for lens in LENSES:
        for key in ("tp", "fp", "fn", "severity_match", "severity_pairs"):
            overall[key] += per_lens[lens][key]
    _rates(overall)

    return {
        "case": case_name,
        "run": run.get("run"),
        "per_lens": per_lens,
        "overall": overall,
        "unscored": unscored,
        "duplicate": duplicate,
        "failed_lenses": failed_lenses,
        "scored_lenses": sorted(scored),
    }


def score_all(cases, runs):
    """One row per (case, run), case name then run number. A run whose
    `case` field names no known case raises ValueError; a case with no run
    at all still gets exactly one row, flagged, never scored as zero."""
    cases_by_name = {c["case"]: c for c in cases}
    runs_by_case = {}
    for run in runs:
        run_case = run.get("case")
        if run_case not in cases_by_name:
            raise ValueError(f"run names an unknown case {run_case!r}")
        runs_by_case.setdefault(run_case, []).append(run)

    rows = []
    for case_name in sorted(cases_by_name):
        case_runs = sorted(runs_by_case.get(case_name, []),
                            key=lambda r: r.get("run"))
        if not case_runs:
            rows.append({"case": case_name, "run": None, "no_run": True})
            continue
        for run in case_runs:
            rows.append(score_case(cases_by_name[case_name]["expected"], run))
    return rows


def format_report(rows):
    """AC7's report: 2N rows plus an F1 delta column. Pure string, never
    printed here. The delta column is filled only on each case's second run
    row, as that run's overall f1 minus the first run's; `-` whenever either
    f1 is None, never 0."""
    header = ("| case | run | tp | fp | fn | precision | recall | f1 | "
              "f1_delta | unscored | duplicate | failed_lenses |")
    sep = "|---|---|---|---|---|---|---|---|---|---|---|---|"
    lines = [header, sep]

    def fmt(value):
        if value is None:
            return "-"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    by_case = {}
    for row in rows:
        by_case.setdefault(row["case"], []).append(row)

    for case_name in sorted(by_case):
        case_rows = by_case[case_name]
        if len(case_rows) == 1 and case_rows[0].get("no_run"):
            lines.append(f"| {case_name} | - | - | - | - | - | - | - | - | "
                          "- | - | no run for this case |")
            continue
        f1s = [row["overall"]["f1"] for row in case_rows]
        for idx, row in enumerate(case_rows):
            overall = row["overall"]
            if idx == 1 and f1s[0] is not None and f1s[1] is not None:
                delta_str = f"{f1s[1] - f1s[0]:+.4f}"
            else:
                delta_str = "-"
            failed = ",".join(row["failed_lenses"])
            lines.append(
                f"| {row['case']} | {row['run']} | {overall['tp']} | "
                f"{overall['fp']} | {overall['fn']} | {fmt(overall['precision'])} | "
                f"{fmt(overall['recall'])} | {fmt(overall['f1'])} | {delta_str} | "
                f"{row['unscored']} | {row['duplicate']} | {failed} |"
            )
    return "\n".join(lines)


def main(argv=None):
    """Thin CLI: --collection reads the case dir; --findings names one or
    more findings.json files, one per run (repeatable); --run optionally
    restricts to specific run numbers. Prints format_report()'s table."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", required=True)
    parser.add_argument("--findings", required=True, action="append")
    parser.add_argument("--run", type=int, action="append")
    args = parser.parse_args(argv)

    cases = load_cases(args.collection)
    runs = []
    for path in args.findings:
        with open(path, encoding="utf-8") as fh:
            run = json.load(fh)
        if args.run and run.get("run") not in args.run:
            continue
        runs.append(run)

    try:
        rows = score_all(cases, runs)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(format_report(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
