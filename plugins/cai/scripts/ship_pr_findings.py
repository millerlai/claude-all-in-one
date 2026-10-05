#!/usr/bin/env python3
"""What a track's pull request is carrying: wait for its checks, then list its findings.

Gate 2 used to run straight through to `gh pr merge`, so a review thread or a
check annotation nobody had read could be merged along with the PR. After the
PR opens, the main session runs this once per call: it waits for the head
commit's check runs, reads the two places a finding can sit -- unresolved
review threads and the annotations of finished check runs -- drops what both
sides say twice, and prints the list for the main session to triage, along with
how many fix rounds this track has already used.

    ship_pr_findings.py --track-dir DIR [--project-dir DIR] [--sha SHA]
                        [--started-at SECONDS]

Exit 0: the list was printed, unreachable sources included, as `unchecked`.
Exit 8: checks are still running -- call again with the same arguments plus
        `--started-at` set to the `wait_started_at` this call printed.
Exit 1: the command line was wrong.

Read-only: every `gh` call is `pr view` or a GET (`api`, or `api graphql` with a
query), nothing is written to GitHub or to disk. One call never runs past about
two minutes, so a tool that kills a command at 120 seconds never kills this one.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ledger  # noqa: E402
import preflight  # noqa: E402
import tool_path  # noqa: E402

# The same seam as branch_sweep.CLI_ENV, same name on purpose: a test sets it
# once and both scripts read it. A value starting with `[` is a JSON argv
# array; anything else is a single executable.
CLI_ENV = "CAI_GH_CLI"
TIMEOUT_SECONDS = 15
# One call waits at most this long, then exits 8 and is called again: the Bash
# tool's default timeout is 120 s.
WAIT_SLICE_SECONDS = 90
WAIT_TOTAL_SECONDS = 600
POLL_INTERVAL_SECONDS = 10
# Fetching starts no later than this far into a call: 120 s tool timeout, minus
# one more gh call's TIMEOUT_SECONDS, minus 5 s of slack.
FETCH_DEADLINE_SECONDS = 100
# If the first poll of a call lists no check runs at all, sleep this long and
# list once more -- a push can come before GitHub creates its check runs.
# One re-look per call, never more. 30 is an estimate, not a measurement
# (person's answer, 2026-10-04); still none after it means "no checks".
SETTLE_SECONDS = 30
# Conclusions of a completed run that say nothing about the code.
NO_RESULT_CONCLUSIONS = ("timed_out", "cancelled", "startup_failure",
                         "action_required", "stale")
FIX_ROUND_CAP = 2
PAGE_SIZE = 100
CATEGORIES = ("ok", "not-found", "not-authenticated", "no-github-repo",
              "unreachable", "unreadable", "timed-out", "no-pull-request")
# any other non-zero exit is "exit-N", N being gh's exit code

# Classified into a closed set of words, never echoed (branch_sweep.py:71-78):
# gh's 401 message carries a URL with the credential in it.
_AUTH = ("http 401", "bad credentials", "gh auth login", "not logged into")
_NO_REPO = ("could not resolve to a repository", "not a git repository",
            "none of the git remotes", "no git remotes")
_UNREACHABLE = ("error connecting to", "dial tcp", "timeout awaiting",
                "no such host")
_NO_PR = ("no pull requests found",)

_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")

_QUERY = (
    "query($owner:String!,$repo:String!,$number:Int!,$endCursor:String){"
    "repository(owner:$owner,name:$repo){pullRequest(number:$number){"
    "reviewThreads(first:%d,after:$endCursor){"
    "pageInfo{hasNextPage endCursor} "
    "nodes{isResolved isOutdated path line "
    "comments(first:%d){totalCount nodes{author{__typename login} body url}}}}}}}"
    % (PAGE_SIZE, PAGE_SIZE))


def gh_prefix():
    # Same shape as branch_sweep.gh_prefix(); not imported because
    # branch_sweep.run() cannot tell a timeout from a missing executable.
    raw = os.environ.get(CLI_ENV, "").strip()
    if not raw:
        return ["gh"]
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return ["gh"]
        return [str(a) for a in parsed] if isinstance(parsed, list) else ["gh"]
    return [raw]


def classify(exc, returncode, stderr):
    """One word from CATEGORIES, or `exit-N`; gh's own text never leaves here."""
    if isinstance(exc, subprocess.TimeoutExpired):
        return "timed-out"
    if exc is not None:
        return "not-found"
    if returncode == 0:
        return "ok"
    low = (stderr or "").lower()
    for needles, word in ((_AUTH, "not-authenticated"),
                          (_NO_REPO, "no-github-repo"),
                          (_UNREACHABLE, "unreachable"),
                          (_NO_PR, "no-pull-request")):
        if any(n in low for n in needles):
            return word
    return "exit-%d" % returncode


def run_gh(args, cwd):
    """(stdout, category). Never raises; stderr is only ever classified."""
    try:
        # encoding is explicit for the reason branch_sweep.run() gives: a
        # comment body outside the console codepage must not break the reader.
        # A bare gh by full path from a trusted PATH entry (#294).
        done = subprocess.run(tool_path.resolve_argv(gh_prefix() + list(args), cwd), cwd=cwd,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as exc:
        return "", classify(exc, 0, "")
    category = classify(None, done.returncode, done.stderr)
    out = done.stdout if isinstance(done.stdout, str) else ""
    return (out if category == "ok" else ""), category


def _json(args, cwd):
    out, category = run_gh(args, cwd)
    if category != "ok":
        return None, category
    try:
        return json.loads(out), "ok"
    except ValueError:
        return None, "unreadable"


def _pages(data):
    """`--paginate --slurp` gives a list of pages; accept a single page too."""
    return data if isinstance(data, list) else [data]


def pull_request(cwd):
    data, category = _json(["pr", "view", "--json",
                            "number,url,headRefOid,state"], cwd)
    if data is None:
        return None, category
    if (not isinstance(data, dict)
            or not isinstance(data.get("number"), int)
            or not all(isinstance(data.get(k), str)
                       for k in ("url", "headRefOid", "state"))):
        return None, "unreadable"
    return {k: data[k] for k in ("number", "url", "headRefOid", "state")}, "ok"


def list_check_runs(sha, cwd):
    data, category = _json(
        ["api", "--paginate", "--slurp",
         "repos/{owner}/{repo}/commits/%s/check-runs?per_page=%d"
         % (sha, PAGE_SIZE)], cwd)
    if data is None:
        return None, category
    runs = []
    for page in _pages(data):
        rows = page.get("check_runs") if isinstance(page, dict) else None
        if not isinstance(rows, list):
            return None, "unreadable"
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get("id"), int)
                    or not isinstance(row.get("name"), str)):
                return None, "unreadable"
            runs.append({"id": row["id"], "name": row["name"],
                         "status": str(row.get("status")),
                         "conclusion": str(row.get("conclusion"))})
    return runs, "ok"


def wait_for_checks(sha, started_at, cwd, now=None, sleep=None):
    """Poll until every listed check run is completed, the call's slice or the
    whole budget is spent, or listing fails. `waited` is whole seconds since
    `started_at`.

    state "done" with nothing completed and nothing running can only come from
    the re-look: the first poll listed none, so did the re-look after it.
    now/sleep resolve at call time so a test can swap this module's `time`."""
    now = now or time.time
    sleep = sleep or time.sleep
    call_start = now()
    first = True
    relooked = False
    while True:
        runs, category = list_check_runs(sha, cwd)
        waited = int(now() - started_at)
        if runs is None:
            return {"state": "done", "completed": [], "running": [],
                    "waited": waited, "category": category}
        completed = [r for r in runs if r["status"] == "completed"]
        # Anything but "completed" counts as still running, so this never
        # depends on the full list of status words GitHub may use.
        running = [r for r in runs if r["status"] != "completed"]
        if first and not runs:
            sleep(SETTLE_SECONDS)
            first, relooked = False, True
            continue
        just_relooked, relooked = relooked, False
        result = {"completed": completed, "running": running,
                  "waited": waited, "category": "ok"}
        if not running:
            # Fetch only when this call's first poll, or its re-look, saw
            # everything done: that keeps the fetch at the start of a call.
            state = "done" if first or just_relooked else "waiting"
            return dict(result, state=state)
        if waited >= WAIT_TOTAL_SECONDS:
            return dict(result, state="done")
        if (now() - call_start) + POLL_INTERVAL_SECONDS > WAIT_SLICE_SECONDS:
            return dict(result, state="waiting")
        sleep(POLL_INTERVAL_SECONDS)
        first = False


def check_annotations(run, cwd):
    data, category = _json(
        ["api", "--paginate", "--slurp",
         "repos/{owner}/{repo}/check-runs/%d/annotations?per_page=%d"
         % (run["id"], PAGE_SIZE)], cwd)
    if data is None:
        return None, category
    found = []
    for page in _pages(data):
        if not isinstance(page, list):
            return None, "unreadable"
        for row in page:
            if not isinstance(row, dict):
                return None, "unreadable"
            line = row.get("start_line")
            text = row.get("message") if isinstance(row.get("message"),
                                                    str) else ""
            found.append({
                "source": "check_annotation",
                "path": str(row.get("path") or ""),
                "line": line if isinstance(line, int) else None,
                "text": text, "key": text.strip(),
                "outdated": None, "url": None, "check": run["name"],
                "title": row.get("title") if isinstance(
                    row.get("title"), str) else None,
                "level": row.get("annotation_level") if isinstance(
                    row.get("annotation_level"), str) else None,
                "more": 0})
    return found, "ok"


def review_threads(number, cwd, expired=None):
    """Unresolved threads, GraphQL paged by cursor (`--slurp` is documented for
    REST only). `expired`, when given, is asked before every page."""
    found = []
    cursor = None
    while True:
        if expired is not None and expired():
            return None, "timed-out"
        args = ["api", "graphql", "-F", "owner={owner}", "-F", "repo={repo}",
                "-F", "number=%d" % number]
        if cursor:
            args += ["-F", "endCursor=%s" % cursor]
        data, category = _json(args + ["-f", "query=" + _QUERY], cwd)
        if data is None:
            return None, category
        try:
            block = data["data"]["repository"]["pullRequest"]["reviewThreads"]
            nodes, info = block["nodes"], block["pageInfo"]
            for node in nodes:
                if node["isResolved"] is not False:
                    continue
                comments = node["comments"]
                texts = ["@%s: %s" % ((c.get("author") or {}).get("login"),
                                      c.get("body") or "")
                         for c in comments["nodes"]]
                first = (comments["nodes"][0].get("body") or "") \
                    if comments["nodes"] else ""
                line = node.get("line")
                # __typename, not a "[bot]" login suffix: the scan bot's login
                # is plain "github-advanced-security". A null author (deleted
                # account) is not a bot.
                first_author = (comments["nodes"][0].get("author")
                                if comments["nodes"] else None) or {}
                found.append({
                    "bot": first_author.get("__typename") == "Bot",
                    "source": "review_thread",
                    "path": str(node.get("path") or ""),
                    "line": line if isinstance(line, int) else None,
                    "text": "\n".join(texts), "key": first.strip(),
                    "outdated": bool(node.get("isOutdated")),
                    "url": (comments["nodes"][0].get("url")
                            if comments["nodes"] else None),
                    "check": None, "title": None, "level": None,
                    "more": max(0, int(comments["totalCount"]) - PAGE_SIZE)})
            more_pages, cursor = info["hasNextPage"], info["endCursor"]
        except (KeyError, TypeError, ValueError, AttributeError):
            return None, "unreadable"
        if not more_pages or not cursor:
            return found, "ok"


def dedupe(threads, annotations):
    """(findings kept, how many dropped). A bot posts one scan result as a
    thread and as an annotation; the thread is kept, it carries the link.
    The thread's first comment wraps the scan message in a heading and a link,
    so the annotation matches when its message is a substring of that text;
    it removes itself only, never another thread on the same line. Only a
    thread whose first comment is a bot's counts: a person quoting the text
    does not make the annotation a duplicate."""
    by_line = {}
    for t in threads:
        if t["bot"]:
            by_line.setdefault((t["path"], t["line"]), []).append(t["key"])
    kept = [a for a in annotations
            if not any(a["key"] == k or (a["key"] and a["key"] in k)
                       for k in by_line.get((a["path"], a["line"]), []))]
    return list(threads) + kept, len(annotations) - len(kept)


def fix_rounds(track_dir):
    """Verify attempts since the first `ship passed`: the first PR is not a
    round. `unavailable` and `skipped` are not attempts at fixing."""
    shipped = False
    rounds = 0
    for record in ledger.records(track_dir):
        if record.get("malformed"):
            continue
        if not shipped:
            shipped = (record.get("stage") == "ship"
                       and record.get("outcome") == "passed")
        elif (record.get("stage") == "verify"
              and record.get("outcome") in ("passed", "failed", "blocked")):
            rounds += 1
    return rounds


def _names(runs):
    return ", ".join('"%s"' % preflight._escape_control_chars(r["name"])
                     for r in runs)


def _body(text):
    return ["    " + preflight._escape_control_chars(ln)
            for ln in (text.split("\n") if text else [""])]


def render(report):
    """The stdout lines. Every line that carries someone else's text is
    escaped, and the body of a finding is indented, so no comment can forge a
    `finding` or `source` line."""
    esc = preflight._escape_control_chars
    out = []
    pr = report.get("pr")
    if pr:
        out.append("pr %d %s %s" % (pr["number"], esc(pr["url"]),
                                    esc(pr["state"])))
        out.append("sha %s pr-head %s" % (report["sha"], pr["headRefOid"]))
    if report.get("wait_started_at") is not None:
        out.append("wait_started_at %d" % report["wait_started_at"])
    waiting = report.get("waiting")
    if waiting:
        running = waiting["running"]
        total = len(running) + len(waiting["completed"])
        head = "waiting %d of %d checks running after %d s (%d s of %d)" % (
            len(running), total, report["elapsed"], waiting["waited"],
            WAIT_TOTAL_SECONDS)
        out.append(head + (": " + _names(running) if running else ""))
        return out
    out.append("fix_rounds %d of %d" % (report["fix_rounds"], FIX_ROUND_CAP))
    checks = report.get("checks")
    if checks is not None:
        if checks["category"] != "ok":
            out.append("checks unknown %s" % checks["category"])
        else:
            done, running = checks["completed"], checks["running"]
            tail = (_names(done + running) if done or running else
                    "still no check runs after a %d s re-look"
                    % SETTLE_SECONDS)
            out.append("checks %d completed, %d running, waited %d s of %d: "
                       "%s" % (len(done), len(running), checks["waited"],
                               WAIT_TOTAL_SECONDS, tail))
    for name in ("review_thread", "check_annotation"):
        count, category = report["sources"][name]
        out.append("source %s ok %d" % (name, count) if category == "ok"
                   else "source %s unchecked %s" % (name, category))
    if checks is not None:
        for run in checks["running"]:
            if checks["state"] == "done":
                out.append('unchecked check "%s" still running after %d s'
                           % (esc(run["name"]), WAIT_TOTAL_SECONDS))
        # A finished run that produced no verdict is as unread as a running
        # one. `failure` is deliberately absent: CI red is not this script's.
        for run in checks["completed"]:
            if run["conclusion"] in NO_RESULT_CONCLUSIONS:
                out.append('unchecked check "%s" concluded %s'
                           % (esc(run["name"]), run["conclusion"]))
    if report.get("findings") is not None:
        out.append("findings %d after de-duplication, %d dropped"
                   % (len(report["findings"]), report["dropped"]))
    for number, f in enumerate(report.get("findings") or [], 1):
        where = esc(f["path"]) + (":%d" % f["line"] if f["line"] is not None
                                  else "")
        head = "finding %d %s %s" % (number, f["source"], where)
        if f["source"] == "review_thread":
            head += " outdated=%s" % ("yes" if f["outdated"] else "no")
            if f["url"]:
                head += " url=%s" % esc(f["url"])
        else:
            if f["check"]:
                head += ' check="%s"' % esc(f["check"])
            if f["level"]:
                head += " level=%s" % esc(f["level"])
        out.append(head)
        out.extend(_body(f["text"]))
        if f["more"]:
            out.append("    %d more comments not listed" % f["more"])
    return out


def _started_at(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "--started-at must be a whole number of epoch seconds")
    if number < 0:
        raise argparse.ArgumentTypeError(
            "--started-at must not be negative")
    return number


def _sha(value):
    if not _SHA.match(value):
        raise argparse.ArgumentTypeError(
            "--sha must be 40 hexadecimal characters")
    return value


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = preflight.ArgParser(description=__doc__.splitlines()[0])
    ap.add_argument("--track-dir", required=True)
    ap.add_argument("--project-dir", default=".")
    ap.add_argument("--sha", type=_sha)
    ap.add_argument("--started-at", type=_started_at)
    args = ap.parse_args(argv)
    if not os.path.isdir(args.track_dir):
        ap.error("--track-dir is not a directory: %s" % args.track_dir)

    cwd = args.project_dir
    call_start = time.time()

    def expired():
        return time.time() - call_start > FETCH_DEADLINE_SECONDS

    report = {"fix_rounds": fix_rounds(args.track_dir)}
    pr, category = pull_request(cwd)
    if pr is None:
        report["sources"] = {"review_thread": (0, category),
                             "check_annotation": (0, category)}
        print("\n".join(render(report)))
        return 0

    sha = args.sha or pr["headRefOid"]
    started_at = args.started_at
    report.update(pr=pr, sha=sha)
    if started_at is None:
        started_at = int(time.time())
        report["wait_started_at"] = started_at

    wait = wait_for_checks(sha, started_at, cwd)
    if wait["state"] == "waiting":
        report.update(waiting=wait, elapsed=int(time.time() - call_start))
        print("\n".join(render(report)))
        return 8

    annotations, ann_category = [], wait["category"]
    if wait["category"] == "ok":
        for run in wait["completed"]:
            if expired():
                ann_category = "timed-out"
                break
            found, ann_category = check_annotations(run, cwd)
            if found is None:
                break
            annotations += found
        # The first failing read marks the whole source, but what was already
        # read stays listed: a partial result is not passed off as clean.
    threads, thr_category = review_threads(pr["number"], cwd, expired)
    kept, dropped = dedupe(threads or [], annotations)
    report.update(
        checks=wait,
        sources={"review_thread": (len(threads or []), thr_category),
                 "check_annotation": (len(annotations), ann_category)},
        findings=kept, dropped=dropped)
    print("\n".join(render(report)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
