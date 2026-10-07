#!/usr/bin/env python3
"""Read an intake's `## Verification levels` table, read-only.

One parser for the intake: later subcommands (plan, check, merge-list) are added
to this same file. `levels --intake <path>` prints one `AC3 local-run GET /health
200` line per row. Exit 0 ok, 4 legacy (no heading -- not an error), 5 invalid
table or unreadable intake; 1 and 2 are left to uncaught exceptions and argparse.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shlex
import sys

import record_test_command
import resolve_start_command
import resolve_test_command
import tool_path

TABLE_HEADING = "## Verification levels"
TABLE_HEADER = "| AC | level | check |"
LEVELS = ("test", "local-run", "deployed", "manual")
EXIT_OK, EXIT_LEGACY, EXIT_INVALID = 0, 4, 5

FENCE = re.compile(r"^\s*```")
SECTION_END = re.compile(r"^#{1,2}\s")
# Optional list marker, optional bold, then the id: covers the five spellings
# earlier intakes used (`- AC1:`, `- AC1：`, `- **AC1** `, `- **AC1（…）**`,
# `**AC1 …**`). A line that merely starts with a reference to another AC is
# caught too and reported, rather than letting a real id slip through.
PROSE_ID = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?(AC\d+)")
AC_ID = re.compile(r"AC\d+$")
SEPARATOR = re.compile(r"^\|[\s:\-|]+\|$")
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def _ac_number(ac):
    return int(ac[2:])


def _split(lines):
    """(table lines, prose ids) -- the lines of the levels section, and the AC ids
    defined outside it. Fenced blocks count as neither."""
    table, prose, in_fence, in_section = [], [], False, False
    for line in lines:
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.strip() == TABLE_HEADING:
            in_section = True
            continue
        if in_section and SECTION_END.match(line):
            in_section = False
        if in_section:
            table.append(line)
            continue
        match = PROSE_ID.match(line)
        if match:
            prose.append(match.group(1))
    return table, prose


def _has_heading(lines):
    in_fence = False
    for line in lines:
        if FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and line.strip() == TABLE_HEADING:
            return True
    return False


def _cells(line):
    """The cells of one table row (`\\|` is a literal pipe), or None when the row
    is not pipe-delimited on both ends."""
    parts = UNESCAPED_PIPE.split(line.strip())
    if len(parts) < 3 or parts[0] != "" or parts[-1] != "":
        return None
    return [p.replace("\\|", "|").strip() for p in parts[1:-1]]


def read_levels(text):
    lines = text.splitlines()
    if not _has_heading(lines):
        return {"status": "legacy", "rows": [], "problems": []}
    section, prose = _split(lines)
    table = [ln for ln in section if ln.strip().startswith("|")]
    if not table or table[0].strip() != TABLE_HEADER:
        return {"status": "invalid", "rows": [],
                "problems": ['table header is not exactly "%s"' % TABLE_HEADER]}

    rows, problems, seen = [], [], set()
    for line in table[1:]:
        if SEPARATOR.match(line.strip()):
            continue
        cells = _cells(line)
        if cells is None or len(cells) != 3:
            problems.append("row is not three cells (AC | level | check): %s" % line.strip())
            continue
        ac, level, check = cells
        if not AC_ID.match(ac):
            problems.append("row id %r is not of the form AC<number>" % ac)
        elif ac in seen:
            problems.append("%s: duplicate row in Verification levels" % ac)
        else:
            seen.add(ac)
            if level not in LEVELS:
                problems.append("%s: level %r is not one of %s" % (ac, level, ", ".join(LEVELS)))
            rows.append({"ac": ac, "level": level, "check": check})

    body = set(prose)
    for ac in sorted(body - seen, key=_ac_number):
        problems.append("%s: no row in Verification levels" % ac)
    for ac in sorted(seen - body, key=_ac_number):
        problems.append("%s: row in Verification levels has no AC in the body" % ac)
    return {"status": "invalid" if problems else "ok", "rows": rows, "problems": problems}


METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
INTAKE_NAME = "intake.md"
CONFIG_LABEL = ".claude/cai.json"  # as the person writes it, whatever the OS separator


def _none(problem):
    return {"kind": "none", "problem": problem}


def parse_check(cell):
    """A check cell as {"kind": "http"|"e2e"|"none", ...}; "none" carries a problem."""
    try:
        words = shlex.split(cell)
    except ValueError as exc:
        return _none("check is not parseable: %s" % exc)
    if not words:
        return _none("check is empty")
    if words[0] == "e2e":
        if len(words) != 2:
            return _none("e2e takes exactly one name")
        return {"kind": "e2e", "name": words[1]}
    if words[0] not in METHODS:
        return _none("first word %r is neither e2e nor an HTTP method" % words[0])
    if len(words) not in (3, 4):
        return _none("HTTP check is <METHOD> <path> <status> [\"text\"]")
    method, path, status = words[:3]
    if not path.startswith("/"):
        return _none("path %r does not start with /" % path)
    if not (status.isascii() and status.isdigit()):
        return _none("status %r is not a number" % status)
    text = words[3] if len(words) == 4 else None
    if text is not None and method == "HEAD":
        return _none("HEAD has no body to match")
    return {"kind": "http", "method": method, "path": path, "status": int(status), "text": text}


def _missing_tool(argv, root):
    """argv[0] when it is a bare name absent from the trusted PATH, else None."""
    try:
        tool_path.resolve_argv(argv[:1], root)
    except FileNotFoundError:
        return argv[0]
    return None


def _local_run_route(row, parsed, start, root):
    """(route, reason, detail) for one local-run row."""
    status = start["status"]
    if status == "candidates":
        return "not-covered", "start-candidates", "no start declaration; package.json offers candidates"
    if status == "unknown":
        return "not-covered", "no-start-declaration", "no start declaration in %s" % CONFIG_LABEL
    if status == "invalid":
        return "not-covered", "invalid-start-declaration", start["problem"]
    declaration = start["declaration"]
    missing = _missing_tool(declaration["start"], root)
    if missing:
        return "not-covered", "start-not-on-path", "%s is not on the trusted PATH" % missing
    head = "start: %s (declared in %s)" % (" ".join(declaration["start"]), CONFIG_LABEL)
    if parsed["kind"] == "http":
        tail = "%s %s expect %d" % (parsed["method"], parsed["path"], parsed["status"])
        if parsed["text"] is not None:
            tail += ' containing "%s"' % parsed["text"]
        return "local-run", None, "%s; %s" % (head, tail)
    if parsed["kind"] == "e2e":
        name = parsed["name"]
        words = declaration["e2e"].get(name)
        if words is None:
            return ("not-covered", "e2e-not-declared",
                    "e2e name %s is not a key of run.e2e in %s" % (name, CONFIG_LABEL))
        missing = _missing_tool(words, root)
        if missing:
            return "not-covered", "e2e-not-on-path", "%s is not on the trusted PATH" % missing
        return "local-run", None, "%s; e2e %s: %s" % (head, name, " ".join(words))
    return "not-covered", "no-check-data", "no HTTP check and no declared e2e name"


def _test_detail(commands):
    shown = ["%s %s" % (c["command"], c["whole"]) if c["whole"] else c["command"]
             for c in commands]
    return "tests: %s (verifier maps the tests)" % ("; ".join(shown) if shown else
                                                    "no test command resolved")


def _skipped(reason):
    return {"status": "skipped", "reason": reason, "acs": []}


def _runtime(rows, start):
    if not any(r["level"] == "local-run" for r in rows):
        return _skipped("no-local-run-ac")
    acs = [r["ac"] for r in rows if r["route"] == "local-run"]
    if acs:
        return {"status": "will-run", "reason": None, "acs": acs}
    if start["status"] == "invalid":
        return _skipped("invalid-start-declaration")
    if start["status"] != "declared":
        return _skipped("no-start-declaration")
    return _skipped("no-runnable-ac")


def build_plan(track_dir, project_root):
    """Where each AC goes, as a dict; reads files and PATH, writes and starts nothing."""
    start = resolve_start_command.resolve(project_root)
    plan = {"source": "track" if track_dir else "standalone", "intake": None,
            "intake_status": "missing", "problems": [], "runtime": _skipped("standalone"),
            "start": start, "test_commands": [], "rows": []}
    if not track_dir:
        return plan
    plan["intake"] = os.path.join(track_dir, INTAKE_NAME)
    text = resolve_test_command._read(track_dir, INTAKE_NAME, [])
    if text is None:
        return plan  # a track with no readable intake reads as having no intake to plan from
    levels = read_levels(text)
    plan["intake_status"] = {"ok": "ok", "legacy": "legacy", "invalid": "invalid"}[levels["status"]]
    plan["problems"] = levels["problems"]
    if levels["status"] == "legacy":
        plan["runtime"] = _skipped("legacy-intake")
        return plan
    if levels["status"] == "invalid":
        plan["runtime"] = _skipped("invalid-intake")
        return plan
    plan["test_commands"] = resolve_test_command.resolve(project_root)["commands"]
    for row in levels["rows"]:
        parsed = parse_check(row["check"])
        level, detail, reason = row["level"], None, None
        if level == "test":
            route, detail = "test", _test_detail(plan["test_commands"])
        elif level == "local-run":
            route, reason, detail = _local_run_route(row, parsed, start, project_root)
        else:
            route = "merge"
        plan["rows"].append({"ac": row["ac"], "level": level, "route": route,
                             "check": row["check"], "parsed": parsed,
                             "reason": reason, "detail": detail})
    plan["runtime"] = _runtime(plan["rows"], start)
    return plan


def _row_line(row):
    if row["route"] == "not-covered":
        what = "Not covered (%s): %s; not dispatched" % (row["reason"], row["detail"])
    elif row["route"] == "merge":
        what = "The merge: %s" % row["check"]
    else:
        what = row["detail"]
    return "%s %-10s -> %s" % (row["ac"], row["level"], what)


def _print_plan(plan):
    print("verify plan -- %d AC (source: %s)" % (len(plan["rows"]), plan["intake"] or "standalone"))
    for row in plan["rows"]:
        print(_row_line(row))
    runtime = plan["runtime"]
    if runtime["status"] == "will-run":
        print("runtime: will run %d AC (%s)" % (len(runtime["acs"]), ", ".join(runtime["acs"])))
    else:
        print("runtime: skipped (%s)" % runtime["reason"])
    # Only when a `local-run` AC is waiting on one: the line is what makes the
    # verifier ask (AC15), and every other case must read as it does today (AC9).
    waiting = any(r["reason"] == "start-candidates" for r in plan["rows"])
    candidates = plan["start"]["candidates"][:3] if waiting else []
    if candidates:
        print("start candidates: " + "; ".join(
            "%d) %s (%s scripts.%s)" % (i, " ".join(c["start"]), c["origin"], c["script"])
            for i, c in enumerate(candidates, 1)))


def _plan(args):
    root = resolve_test_command.find_root(os.path.abspath(args.project_dir))
    plan = build_plan(args.track_dir, root)
    if plan["intake_status"] == "invalid":
        for problem in plan["problems"]:
            print(problem, file=sys.stderr)
        return EXIT_INVALID
    _print_plan(plan)
    return EXIT_OK


def merge_list(track_dir):
    """`- AC4 (deployed): <check>` per deployed/manual row; [] when legacy or no intake.
    Raises ValueError(list of problems) when the table is invalid."""
    text = resolve_test_command._read(track_dir, INTAKE_NAME, [])
    if text is None:
        return []
    levels = read_levels(text)
    if levels["status"] == "invalid":
        raise ValueError(levels["problems"])
    return ["- %s (%s): %s" % (r["ac"], r["level"], r["check"])
            for r in levels["rows"] if r["level"] in ("deployed", "manual")]


def _merge_list(args):
    try:
        lines = merge_list(args.track_dir)
    except ValueError as exc:
        for problem in exc.args[0]:
            print(problem, file=sys.stderr)
        return EXIT_INVALID
    for line in lines:
        print(line)
    return EXIT_OK


# --- check: assemble and verify the evidence manifest (DD10, DD11) -----------------

OUTCOMES = ("verified-by-test", "verified-at-runtime", "confirm-before-merge", "not-covered")
EXIT_PROBLEMS = 3
SEVERITIES = ("Blocker", "Major", "Minor")
BLOCKING = ("Blocker", "Major")
MANIFEST_NAME = "manifest.json"
EVIDENCE_BASE = ("evidence", "verify")


class CheckError(Exception):
    """A refusal to assemble or verify: `code` is the exit code, `problems` the lines."""

    def __init__(self, code, problems):
        super().__init__(problems)
        self.code, self.problems = code, problems


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rel(path, track_dir):
    return os.path.relpath(path, track_dir).replace(os.sep, "/")


def _inside(path, base):
    """True when `path` resolves to somewhere strictly under `base`."""
    base, path = os.path.realpath(base), os.path.realpath(path)
    return path != base and os.path.commonpath([path, base]) == base


def _fingerprint_problem(track_dir, evidence, sha):
    """Why the evidence file no longer matches `sha`, or None when it does."""
    path = os.path.join(track_dir, *evidence.split("/"))
    if not _inside(path, track_dir):
        return "is outside the track directory"
    try:
        return None if _sha256(path) == sha else "fingerprint does not match"
    except OSError:
        return "is missing or unreadable"


def _load_json(path, what):
    try:
        with open(path, "rb") as fh:
            data = fh.read(resolve_test_command.READ_LIMIT + 1)
        if len(data) > resolve_test_command.READ_LIMIT:
            raise ValueError("larger than %d bytes" % resolve_test_command.READ_LIMIT)
        return json.loads(data.decode("utf-8-sig"))
    except (OSError, ValueError) as exc:  # UnicodeDecodeError is a ValueError
        raise CheckError(EXIT_INVALID, ["%s %s could not be read as JSON: %s" % (what, path, exc)])


def _check_synthesis(syn, ac_ids):
    """The problems in a synthesis file, as lines; [] when it is well formed."""
    if not isinstance(syn, dict):
        return ["synthesis must be a JSON object"]
    problems = []
    if syn.get("format") != 1 or isinstance(syn.get("format"), bool):
        problems.append("synthesis format must be 1")
    commands = syn.get("test_commands", [])
    if not isinstance(commands, list) or not all(
            isinstance(c, dict) and isinstance(c.get("failed", 0), int)
            and not isinstance(c.get("failed", 0), bool) for c in commands):
        problems.append("synthesis test_commands must be a list of objects with a numeric failed")
    acs = syn.get("acs", {})
    if not isinstance(acs, dict):
        return problems + ["synthesis acs must be an object"]
    for ac, entry in acs.items():
        if ac not in ac_ids:
            problems.append("%s: synthesis names an AC the intake does not have" % ac)
        if not isinstance(entry, dict):
            problems.append("%s: synthesis entry must be an object" % ac)
            continue
        if not isinstance(entry.get("tests", []), list):
            problems.append("%s: tests must be a list" % ac)
        findings = entry.get("findings", [])
        if not isinstance(findings, list) or not all(isinstance(f, dict) for f in findings):
            problems.append("%s: findings must be a list of objects" % ac)
            continue
        for f in findings:
            if f.get("severity") not in SEVERITIES:
                problems.append("%s: finding severity %r is not one of %s"
                                % (ac, f.get("severity"), ", ".join(SEVERITIES)))
            if not isinstance(f.get("fixed"), bool):
                problems.append("%s: finding fixed must be true or false" % ac)
    return problems


def _unfixed(findings):
    return [f for f in findings if f.get("severity") in BLOCKING and f.get("fixed") is False]


def _runtime_row(ac, record, run_dir, track_dir):
    """(outcome, reason, detail, evidence, sha256) for one local-run AC (rules 8-9)."""
    entry = next((c for c in (record or {}).get("checks", []) if c.get("ac") == ac), None)
    if entry is None or not entry.get("outcome"):
        return "not-covered", "not-run", None, None, None
    outcome, reason = entry["outcome"], entry.get("reason")
    evidence = sha = None
    if entry.get("evidence") and entry.get("sha256"):
        evidence = _rel(os.path.join(run_dir, entry["evidence"]), track_dir)
        sha = entry["sha256"]
    if outcome == "PASS":
        if evidence is None:
            return "not-covered", "no-evidence", None, None, None
        if _fingerprint_problem(track_dir, evidence, sha):
            return "not-covered", "evidence-changed", None, evidence, sha
        return "verified-at-runtime", None, None, evidence, sha
    if outcome == "NOT-RUN":
        return "not-covered", reason or "not-run", None, evidence, sha
    # FAIL and TIMEOUT keep one code each; the runner's own text (for a start that
    # exited before ready: "start-exited (exit code N)") rides along as `detail`
    # rather than becoming a code of its own.
    return "not-covered", "runtime-%s" % outcome, reason, evidence, sha


def _new_dir(base):
    os.makedirs(base, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    n = 1
    while True:
        path = os.path.join(base, stamp if n == 1 else "%s-%d" % (stamp, n))
        try:
            os.mkdir(path)  # mkdir, not exists-then-make: two checks may race here
        except FileExistsError:
            n += 1
            continue
        return path


def _plan_ok(track_dir, project_root):
    plan = build_plan(track_dir, project_root)
    if plan["intake_status"] == "invalid":
        raise CheckError(EXIT_INVALID, plan["problems"])
    if plan["intake_status"] != "ok":
        raise CheckError(EXIT_LEGACY, ["no manifest for a legacy or standalone verify"])
    return plan


def _row(ac, level, outcome, reason, check, evidence, sha, tests, findings, detail=None):
    return {"ac": ac, "level": level, "outcome": outcome, "reason": reason, "detail": detail,
            "check": check, "evidence": evidence, "sha256": sha, "tests": tests,
            "findings": findings}


def assemble(track_dir, project_root, synthesis_path, run_dir):
    """Write the evidence manifest; (its path, the manifest dict). Raises CheckError
    (exit 4 legacy/standalone, 5 bad input) before writing anything."""
    plan = _plan_ok(track_dir, project_root)
    syn = _load_json(synthesis_path, "synthesis")
    problems = _check_synthesis(syn, {r["ac"] for r in plan["rows"]})
    if run_dir is not None and not (
            _inside(run_dir, os.path.join(track_dir, *EVIDENCE_BASE)) and os.path.isdir(run_dir)):
        problems.append("--run must be an existing directory under %s"
                        % "/".join(("<track-dir>",) + EVIDENCE_BASE))
    if problems:
        raise CheckError(EXIT_INVALID, problems)

    record = run_path = None
    if run_dir is not None and os.path.isfile(os.path.join(run_dir, "run.json")):
        run_path = os.path.join(run_dir, "run.json")
        record = _load_json(run_path, "run record")
    commands = syn.get("test_commands", [])
    rows = []
    for p in plan["rows"]:
        ac, level = p["ac"], p["level"]
        entry = syn.get("acs", {}).get(ac, {})
        tests, findings = entry.get("tests", []), entry.get("findings", [])
        make = lambda outcome, reason=None, detail=None, ev=None, sha=None: _row(  # noqa: E731
            ac, level, outcome, reason, p["check"], ev, sha, tests, findings, detail)
        if p["route"] == "not-covered":                                  # 1
            rows.append(make("not-covered", p["reason"], p["detail"]))
        elif _unfixed(findings):                                         # 2
            rows.append(make("not-covered", "unfixed-finding"))
        elif p["route"] == "merge":                                      # 3
            rows.append(make("confirm-before-merge"))
        elif p["route"] == "test":
            if not tests:                                                # 4
                rows.append(make("not-covered", "no-matching-test"))
            elif not commands:                                           # 5
                rows.append(make("not-covered", "tests-not-run"))
            elif any(c.get("failed", 0) > 0 for c in commands):          # 6
                rows.append(make("not-covered", "tests-failed"))
            else:                                                        # 7
                rows.append(make("verified-by-test"))
        else:                                                            # 8, 9
            rows.append(make(*_runtime_row(ac, record, run_dir, track_dir)))

    manifest = {"format": 1, "intake": INTAKE_NAME,
                "intake_sha256": _sha256(os.path.join(track_dir, INTAKE_NAME)),
                "run": _rel(run_path, track_dir) if run_path else None,
                "run_sha256": _sha256(run_path) if run_path else None,
                "synthesis": syn, "rows": rows}
    target = run_dir or _new_dir(os.path.join(track_dir, *EVIDENCE_BASE))
    path, n = os.path.join(target, MANIFEST_NAME), 1
    while os.path.exists(path):  # a manifest is only ever added, never overwritten
        n += 1
        path = os.path.join(target, "manifest-%d.json" % n)
    record_test_command.write_config(path, manifest)
    return path, manifest


def _problems(manifest, plan, track_dir):
    if not isinstance(manifest, dict) or not isinstance(manifest.get("rows"), list) or not all(
            isinstance(r, dict) for r in manifest["rows"]):
        return ["manifest has no rows list"]
    problems = []
    planned = {r["ac"]: r for r in plan["rows"]}
    ids = [r.get("ac") for r in manifest["rows"]]
    for ac in sorted(set(planned) - set(ids), key=_ac_number):                    # AC5
        problems.append("%s: no row in the manifest" % ac)
    for ac in sorted({a for a in ids if a not in planned}, key=str):
        problems.append("%s: row is not an AC of the intake" % ac)
    for ac in sorted({a for a in ids if ids.count(a) > 1}, key=str):
        problems.append("%s: more than one row" % ac)
    synthesis_acs = (manifest.get("synthesis") or {}).get("acs", {})
    for row in manifest["rows"]:
        ac, outcome = row.get("ac"), row.get("outcome")
        if outcome not in OUTCOMES:
            problems.append("%s: outcome %r is not one of %s" % (ac, outcome, ", ".join(OUTCOMES)))
        if row.get("evidence"):                                                   # AC4
            why = (_fingerprint_problem(track_dir, row["evidence"], row.get("sha256"))
                   if isinstance(row["evidence"], str) else "is not a path")
            if why:
                problems.append("%s: evidence %s %s" % (ac, row["evidence"], why))
        if not str(outcome).startswith("verified-"):
            continue
        findings = (row.get("findings") or []) + ((synthesis_acs.get(ac) or {}).get("findings") or [])
        if _unfixed([f for f in findings if isinstance(f, dict)]):                # AC14 rule 1
            problems.append("%s: %s with an unfixed Blocker or Major finding" % (ac, outcome))
        if ac in planned and planned[ac]["route"] == "not-covered":               # AC14 rule 2
            problems.append("%s: %s but the plan says not-covered (%s)"
                            % (ac, outcome, planned[ac]["reason"]))
        if outcome == "verified-by-test" and not row.get("tests"):                # AC14 rule 3
            problems.append("%s: verified-by-test with no matching test" % ac)
    return problems


def verify_manifest(manifest_path, track_dir, project_root):
    """The problems with an existing manifest, one line each; [] when clean. The one
    checking function both `check` modes use (DD11); the plan is recomputed (D6)."""
    try:
        manifest = _load_json(manifest_path, "manifest")
        plan = _plan_ok(track_dir, project_root)
    except CheckError as exc:
        return exc.problems
    return _problems(manifest, plan, track_dir)


def _command_text(entry):
    entry = entry if isinstance(entry, dict) else {}
    return "%s (%s passed, %s failed)" % (entry.get("command"), entry.get("passed", "?"),
                                         entry.get("failed", 0))


def _manifest_line(row, commands=()):
    parts = [str(row.get("ac")), str(row.get("level")), str(row.get("outcome"))]
    if row.get("outcome") == "verified-by-test":
        # AC5: a test-verified AC is reported with its tests, command and counts
        parts.append("tests=%s" % ",".join(str(t) for t in row.get("tests") or []))
        parts.append("commands=%s" % "; ".join(_command_text(c) for c in commands))
    if row.get("outcome") == "not-covered":
        parts.append("(%s)" % row.get("reason"))
    if row.get("evidence"):
        parts += [str(row["evidence"]), "sha256=%s" % row.get("sha256")]
    return " ".join(parts)


def _check(args):
    root = resolve_test_command.find_root(os.path.abspath(args.project_dir))
    try:
        if args.manifest:
            path = args.manifest
            _plan_ok(args.track_dir, root)  # legacy/standalone/invalid exit before reading it
        else:
            run = os.path.abspath(args.run_dir) if args.run_dir else None
            path, _ = assemble(args.track_dir, root, args.synthesis, run)
        manifest = _load_json(path, "manifest")
    except CheckError as exc:
        for problem in exc.problems:
            print(problem, file=sys.stderr)
        return exc.code
    print("manifest: %s" % path)
    rows = manifest.get("rows") if isinstance(manifest, dict) else None
    synthesis = manifest.get("synthesis") if isinstance(manifest, dict) else None
    commands = synthesis.get("test_commands") if isinstance(synthesis, dict) else None
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            print(_manifest_line(row, commands if isinstance(commands, list) else []))
    # Both modes end in the same function, on the file as it now sits on disk (DD11).
    problems = verify_manifest(path, args.track_dir, root)
    for problem in problems:
        print(problem, file=sys.stderr)
    return EXIT_PROBLEMS if problems else EXIT_OK


def _levels(args):
    notes = []
    # An absolute or relative path passes through os.path.join("", path) unchanged.
    text = resolve_test_command._read("", args.intake, notes)
    if text is None:
        print("; ".join(notes), file=sys.stderr)
        return EXIT_INVALID
    result = read_levels(text)
    if result["status"] == "legacy":
        print('legacy: no "%s" heading' % TABLE_HEADING)
        return EXIT_LEGACY
    if result["status"] == "invalid":
        for problem in result["problems"]:
            print(problem, file=sys.stderr)
        return EXIT_INVALID
    for row in result["rows"]:
        print("%s %s %s" % (row["ac"], row["level"], row["check"]))
    return EXIT_OK


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    levels = sub.add_parser("levels", help="print each AC's level and check")
    levels.add_argument("--intake", required=True, help="path to intake.md")
    levels.set_defaults(run=_levels)
    plan = sub.add_parser("plan", help="print where each AC goes; starts nothing")
    plan.add_argument("--track-dir", help="the track directory holding intake.md "
                                          "(omit for a standalone run)")
    plan.add_argument("--project-dir", default=".", help="project directory (default: .)")
    plan.set_defaults(run=_plan)
    merge = sub.add_parser("merge-list", help="print the deployed/manual ACs for The merge")
    merge.add_argument("--track-dir", required=True, help="the track directory")
    merge.set_defaults(run=_merge_list)
    check = sub.add_parser("check", help="assemble the evidence manifest, or verify one")
    check.add_argument("--track-dir", required=True, help="the track directory")
    check.add_argument("--project-dir", default=".", help="project directory (default: .)")
    mode = check.add_mutually_exclusive_group(required=True)
    mode.add_argument("--synthesis", help="the verifier's synthesis file (assemble a manifest)")
    mode.add_argument("--manifest", help="an existing manifest (verify only)")
    check.add_argument("--run", dest="run_dir", help="the run directory to write the manifest into "
                                     "(with --synthesis; default: a new evidence/verify/<UTC>/)")
    check.set_defaults(run=_check)
    args = ap.parse_args(argv)
    if args.command == "check" and args.manifest and args.run_dir:
        ap.error("--run goes with --synthesis, not --manifest")
    return args.run(args)


if __name__ == "__main__":
    # Check cells may be non-ASCII; a piped Windows stdout is not UTF-8.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
