#!/usr/bin/env python3
"""What $fix is pointed at, whether it may start, and what it may push.

The skill's main session makes every commit, push and reply itself; this
script holds the decisions that must not rest on a model's reading of prose:
which kind of target an argument is, whether the repository is in a state to
begin, whether a subagent's reported paths are the paths that changed, whether
a branch may be pushed, and whether the final report is complete.

    fix_target.py classify --project-dir DIR [ARGUMENT]
    fix_target.py ready --project-dir DIR
    fix_target.py changes --project-dir DIR --expect-head SHA --expect-branch NAME
                          --reported-file FILE --pathspec-out FILE [--ready-file FILE]
    fix_target.py pushable --project-dir DIR --base REF
    fix_target.py report --results-file FILE [--expect-file FILE]

Exit 0: carry on. Exit 2: the run stops; the first line is
`stopped <reason>: <sentence>` or `rejected <reason>: <sentence>`. Exit 3: this
one item cannot go the usual way (`changes` and `pushable`). Exit 1: the
command line was wrong.

Nothing here pushes, commits or merges, and nothing writes into the repository:
the only file written is the one `changes` is told to with --pathspec-out.
`ready` fetches, which updates remote-tracking branches and nothing else.
"""
import fnmatch
import json
import os
import re
import subprocess
import sys
from typing import NamedTuple, Optional
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preflight  # noqa: E402
import resolve_test_command  # noqa: E402
import ship_pr_findings  # noqa: E402
import tool_path  # noqa: E402

GIT_TIMEOUT = 15
# One call may run about 100 s: this fetch, then two gh calls of 15 s each,
# leaving 10 s of slack (the Bash tool kills a command at 120 s).
FETCH_TIMEOUT = 60

_escape = preflight._escape_control_chars

REASONS = {
    "no-remote": "No origin remote with a recognised GitHub URL was found; run this "
                 "inside a clone of the repository.",
    "unrecognised": "Not recognised. Give an issue URL (https://<host>/<owner>/<repo>/"
                    "issues/<number>), the issues list URL (https://<host>/<owner>/<repo>/"
                    "issues, with no query: filters are not supported and the list is "
                    "always every open issue), a pull request URL (https://<host>/<owner>/"
                    "<repo>/pull/<number>), or a Jira ticket URL (https://<site>/browse/"
                    "<KEY>-<number>); with no argument, the current branch's pull request "
                    "is used.",
    "other-repository": "That URL belongs to a different repository than origin; run "
                        "this inside a clone of that repository.",
    "not-a-repository": "The project directory is not inside a git repository.",
    "dirty-tree": "The working tree has uncommitted changes to tracked files; commit "
                  "them first.",
    "pre-existing-untracked": "A pre-existing untracked path now has tracked changes; "
                              "nothing was added or committed. Resolve this conflict "
                              "before continuing.",
    "no-default-branch": "origin/HEAD is not set, so the default branch is unknown; run "
                         "`git remote set-head origin --auto`.",
    "no-github-repo": "gh cannot see this repository on GitHub.",
    "fetch-failed": "`git fetch origin` failed.",
    "test-command-several": "Several test commands were found; declare the one to use "
                            "with record_test_command.py.",
    "test-command-unknown": "No test command was found; declare one with "
                            "record_test_command.py.",
    "test-command-invalid": "The declared test command cannot be used; correct it with "
                            "record_test_command.py.",
    "git-failed": "git could not read the repository.",
    "results-invalid": "The results file does not meet the report's rules.",
}
GH_REASONS = {
    "not-found": "gh was not found on a trusted PATH entry.",
    "not-authenticated": "gh is not signed in; run `gh auth login`.",
    "unreachable": "GitHub could not be reached.",
    "timed-out": "gh did not answer in time.",
}

# word -> the one sentence the report prints for it. `too-large` carries the
# command the person can run instead.
OUTCOMES = {
    "pr-opened": "A pull request was opened for this item.",
    "replied-fixed": "The fix was pushed and the thread was answered and resolved.",
    "replied-not-fixed": "Not fixed: a reply gave the reason and the thread stays unresolved.",
    "cannot-reproduce": "The problem could not be reproduced, so nothing was pushed.",
    "needs-decision": "This needs a decision from you, not a code change.",
    "too-large": "Too large or too unclear for a quick fix; start a track with "
                 "$track <url> instead.",
    "failed-three-attempts": "Three fix attempts failed; any changes stay on a local branch.",
    "waiting-for-pr": "Waiting for the pull request named in the detail.",
    "held-path": "The change touches a path that is never pushed automatically; it stays "
                 "on a local branch.",
    "dependency-not-fixed": "A dependency was not fixed, so this item was not worked on.",
    "dependency-cycle": "The dependencies form a cycle, so no member of it was worked on.",
    "committed-not-pushed": "The fix is committed on a local branch but the push did not "
                            "succeed.",
    "pushed-no-pr": "The branch was pushed but the pull request could not be opened.",
    "replied-not-resolved": "The reply was posted but the thread could not be resolved.",
    "pushed-not-replied": "The fix was pushed but the reply could not be posted.",
    "paths-mismatch": "The reported paths did not match the real changes, or HEAD moved; "
                      "nothing was pushed.",
    "not-selected": "Not selected, so it was not worked on.",
    "has-open-pr": "A pull request is already open, so it was skipped.",
    "dependency-not-selected": "A dependency was not selected, so this item was not "
                               "worked on.",
    "local-branch-kept": "A local branch from an earlier run was kept, not overwritten.",
    "claimed-elsewhere": "Another session on this machine is working on it; once that "
                         "session has ended, $fix-unclaim with this URL and the "
                         "detail's values clears its claim.",
}
# the fields an item must carry besides id and outcome
REQUIRED = {
    "pr-opened": ("url", "branch", "paths"),
    "replied-fixed": ("detail",),
    "replied-not-fixed": ("detail",),
    "too-large": ("url",),
    "waiting-for-pr": ("detail",),
    "held-path": ("branch", "paths"),
    "dependency-not-fixed": ("detail",),
    "dependency-cycle": ("detail",),
    "committed-not-pushed": ("branch",),
    "pushed-no-pr": ("branch",),
    "replied-not-resolved": ("detail",),
    "pushed-not-replied": ("detail",),
    "paths-mismatch": ("branch",),
    "has-open-pr": ("url",),
    "dependency-not-selected": ("detail",),
    "local-branch-kept": ("branch",),
    "claimed-elsewhere": ("url", "detail"),
}

# File names (any depth, any case) a fix may never push: dependency manifests
# and lock files, the code form of the held-path list in the track skill's
# approval-gates reference. Its prose says "package.json and its lockfiles"
# without naming them; the six lock names here are this list's own.
HELD_NAMES = frozenset(n.lower() for n in (
    "pyproject.toml", "setup.py", "package.json", "package-lock.json",
    "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb",
    "go.mod", "go.sum", "Cargo.toml", "Cargo.lock", "Gemfile", "Gemfile.lock",
    "pom.xml"))


class Remote(NamedTuple):
    host: str
    owner: str
    repo: str


class Target(NamedTuple):
    kind: str
    host: str
    owner: str
    repo: str
    number: Optional[int]
    key: Optional[str]
    url: Optional[str]


class Rejection(NamedTuple):
    reason: str
    message: str


class Changes(NamedTuple):
    verdict: str
    held: list
    unreported: list
    missing: list


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------

_HTTPS = re.compile(r"https://(?:[^@/]+@)?([^/:@]+)(?::\d+)?/([^/]+)/([^/]+)")
_SCP = re.compile(r"git@([^/:@]+):([^/]+)/([^/]+)")
_SSH = re.compile(r"ssh://git@([^/:@]+)(?::\d+)?/([^/]+)/([^/]+)")
_ISSUE = re.compile(r"/([^/]+)/([^/]+)/issues/(\d+)(?:/.*)?")
_ISSUE_LIST = re.compile(r"/([^/]+)/([^/]+)/issues")
_PULL = re.compile(r"/([^/]+)/([^/]+)/pull/(\d+)(?:/.*)?")
_JIRA = re.compile(r".*/browse/([A-Za-z][A-Za-z0-9_]*-[0-9]+)")
_JIRA_HOST = re.compile(r"[a-z0-9.-]+")
_JIRA_PATH = re.compile(r"[A-Za-z0-9._~/-]+")


def parse_remote(url):
    """The host, owner and repo of an origin URL, or None for any other shape."""
    text = (url or "").strip().rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    for shape in (_HTTPS, _SCP, _SSH):
        m = shape.fullmatch(text)
        if m:
            return Remote(m.group(1).lower(), m.group(2), m.group(3))
    return None


def _reject(reason):
    return Rejection(reason, REASONS[reason])


def classify(argument, remote):
    """Pure: the Target an argument means for this origin, or a Rejection."""
    if remote is None:
        return _reject("no-remote")
    text = (argument or "").strip()
    if not text:
        return Target("review-threads", remote.host, remote.owner, remote.repo,
                      None, None, None)
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return _reject("unrecognised")
    path = parts.path.rstrip("/")
    if parts.hostname.lower() == remote.host.lower():
        kind, m, number = None, _ISSUE.fullmatch(path), None
        if m:
            kind = "issue"
        elif _ISSUE_LIST.fullmatch(path) and not parts.query and not parts.fragment:
            kind, m = "issue-list", _ISSUE_LIST.fullmatch(path)
        else:
            m = _PULL.fullmatch(path)
            kind = "review-threads" if m else None
        if kind is None:
            return _reject("unrecognised")
        if (m.group(1).lower(), m.group(2).lower()) != (remote.owner.lower(),
                                                       remote.repo.lower()):
            return _reject("other-repository")
        if kind != "issue-list":
            number = int(m.group(3))
        return Target(kind, remote.host, remote.owner, remote.repo, number, None, text)
    m = _JIRA.fullmatch(path)
    try:
        port = parts.port
    except ValueError:
        port = None
        m = None
    host = parts.hostname.lower()
    # The host and url go on a shell command line in jira-ticket.md, so only
    # shapes with no shell character survive, and the query and fragment are
    # dropped: the PR body needs the ticket's address, not the pasted tail.
    if m and _JIRA_HOST.fullmatch(host) and _JIRA_PATH.fullmatch(path):
        url = f"{parts.scheme}://{host}{f':{port}' if port else ''}{path}"
        return Target("jira-ticket", host, "", "", None, m.group(1).upper(), url)
    return _reject("unrecognised")


# ---------------------------------------------------------------------------
# running git and gh
# ---------------------------------------------------------------------------

def git(args, cwd, timeout=GIT_TIMEOUT):
    """git's stdout, or None when it could not run, timed out or exited non-zero.

    Decoded here from bytes: text mode would turn a CR inside a file name into
    a newline, and these are file names."""
    try:
        done = subprocess.run(tool_path.resolve_argv(["git"] + list(args), cwd), cwd=cwd,
                              capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.decode("utf-8", "replace")


def stop(reason, sentence=None, word="stopped"):
    print(f"{word} {reason}: {sentence or REASONS[reason]}")
    return 2


def usage_error(message):
    print(f"fix_target.py: error: {message}", file=sys.stderr)
    return 1


def origin_remote(cwd):
    url = git(["remote", "get-url", "origin"], cwd)
    return parse_remote(url) if url is not None else None


def default_branch_name(cwd):
    ref = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd)
    if ref and "/" in ref.strip():
        return ref.strip().split("/", 1)[1]
    return None


def _gh_stop(category):
    return stop(category, GH_REASONS.get(category) or "gh failed with exit code %s."
                % category.split("-", 1)[-1])


def cmd_classify(args):
    result = classify(args.argument, origin_remote(args.project_dir))
    if isinstance(result, Rejection):
        return stop(result.reason, result.message, word="rejected")
    print(json.dumps(result._asdict()))
    return 0


# ---------------------------------------------------------------------------
# ready
# ---------------------------------------------------------------------------

def cmd_ready(args):
    cwd = args.project_dir
    top = git(["rev-parse", "--show-toplevel"], cwd)
    if top is None or not top.strip():
        return stop("not-a-repository")
    root = top.strip()
    remote = origin_remote(root)
    if remote is None:
        return stop("no-remote")
    status = git(["status", "--porcelain", "--untracked-files=no"], root)
    if status is None:
        return stop("git-failed")
    if status.strip():
        return stop("dirty-tree")
    untracked = git(["ls-files", "--others", "--exclude-standard", "-z"], root)
    if untracked is None:
        return stop("git-failed")
    default = default_branch_name(root)
    if default is None:
        return stop("no-default-branch")
    login, category = ship_pr_findings.run_gh(["api", "user", "--jq", ".login"], root)
    if category != "ok":
        return _gh_stop(category)
    _, category = ship_pr_findings.run_gh(["api", f"repos/{remote.owner}/{remote.repo}"], root)
    if category != "ok":
        # gh's 404 for a repository it cannot see is a plain exit 1
        return (_gh_stop(category) if category in GH_REASONS
                else stop("no-github-repo"))
    if git(["fetch", "origin"], root, FETCH_TIMEOUT) is None:
        return stop("fetch-failed")
    base_ref = f"origin/{default}"
    base_sha = git(["rev-parse", base_ref], root)
    if base_sha is None:
        return stop("no-default-branch")
    test = resolve_test_command.resolve(root)
    if test["status"] != "resolved":
        return stop(f"test-command-{test['status']}")
    branch = git(["symbolic-ref", "--short", "HEAD"], root)
    facts = {"root": root, "untracked_paths": [p for p in untracked.split("\0") if p]}
    if branch is not None:
        facts["start_ref"] = branch.strip()
    else:
        facts["start_ref"] = (git(["rev-parse", "HEAD"], root) or "").strip()
        facts["start_detached"] = True
    facts.update(default_branch=default, base_ref=base_ref, base_sha=base_sha.strip(),
                 login=login.strip(), owner=remote.owner, repo=remote.repo, test=test)
    print(json.dumps(facts))
    return 0


# ---------------------------------------------------------------------------
# changes
# ---------------------------------------------------------------------------

def is_held(path):
    """Whether a path may never be pushed by this skill (case-insensitive)."""
    p = path.replace("\\", "/").lower()
    while p.startswith("./"):
        p = p[2:]
    if p.startswith(".github/"):
        return True
    name = p.rsplit("/", 1)[-1]
    return name in HELD_NAMES or fnmatch.fnmatchcase(name, "requirements*.txt")


def parse_porcelain(raw, ignored_untracked=()):
    """Every path in `git status --porcelain -z --untracked-files=all` output;
    a rename or copy counts for both its new and its old path.
    Only still-untracked paths from the readiness snapshot are excluded."""
    fields = raw.split("\0")
    paths, i = [], 0
    while i < len(fields):
        field = fields[i]
        i += 1
        if len(field) < 4:
            continue
        if field[:2] == "??" and field[3:] in ignored_untracked:
            continue
        paths.append(field[3:])
        if ("R" in field[:2] or "C" in field[:2]) and i < len(fields) and fields[i]:
            paths.append(fields[i])
            i += 1
    return paths


def compare_changes(actual, reported):
    """How the paths a subagent reported compare with the ones that changed."""
    a, r = set(actual), set(reported)
    held = sorted(p for p in a if is_held(p))
    verdict = "none" if not a else "match" if a == r else "mismatch"
    return Changes(verdict, held, sorted(a - r), sorted(r - a))


def _reported_paths(path):
    with open(path, encoding="utf-8-sig") as fh:
        lines = [line.strip().replace("\\", "/") for line in fh]
    out = []
    for line in lines:
        while line.startswith("./"):
            line = line[2:]
        if line:
            out.append(line)
    return out


def cmd_changes(args):
    cwd = args.project_dir
    head = git(["rev-parse", "HEAD"], cwd)
    raw = git(["status", "--porcelain", "-z", "--untracked-files=all"], cwd)
    if head is None or raw is None:
        return stop("git-failed")
    branch = git(["symbolic-ref", "--short", "HEAD"], cwd)
    try:
        reported = _reported_paths(args.reported_file)
    except OSError:
        return usage_error("cannot read --reported-file: %s" % args.reported_file)
    ignored_untracked = set()
    if args.ready_file:
        try:
            with open(args.ready_file, encoding="utf-8-sig") as fh:
                facts = json.load(fh)
            paths = facts["untracked_paths"]
            if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
                raise ValueError
            ignored_untracked = set(paths)
        except (OSError, ValueError, KeyError, TypeError):
            return usage_error("cannot read untracked_paths from --ready-file")
    actual = parse_porcelain(raw, ignored_untracked)
    if ignored_untracked.intersection(actual):
        return stop("pre-existing-untracked")
    result = compare_changes(actual, reported)
    try:
        with open(args.pathspec_out, "wb") as fh:
            fh.write("\0".join(actual).encode("utf-8"))
    except OSError:
        return usage_error("cannot write --pathspec-out: %s" % args.pathspec_out)
    moved = (head.strip() != args.expect_head
             or branch is None or branch.strip() != args.expect_branch)
    verdict = "head-moved" if moved else result.verdict
    print(f"changes {verdict}")
    for label, paths in (("held", result.held), ("unreported", result.unreported),
                         ("missing", result.missing)):
        for path in paths:
            print(f"{label} {_escape(path)}")
    return 0 if verdict == "match" and not result.held else 3


# ---------------------------------------------------------------------------
# pushable
# ---------------------------------------------------------------------------

def cmd_pushable(args):
    cwd = args.project_dir
    branch = git(["symbolic-ref", "--short", "HEAD"], cwd)
    if branch is None:
        # `git symbolic-ref` fails on a detached HEAD and outside a repository
        # alike; only the first is a reason to refuse rather than a git failure.
        if git(["rev-parse", "--git-dir"], cwd) is None:
            return stop("git-failed")
        return _not_pushable("detached-head")
    branch = branch.strip()
    if branch in (default_branch_name(cwd), "main", "master"):
        return _not_pushable("default-branch")
    status = git(["status", "--porcelain", "--untracked-files=no"], cwd)
    log = git(["log", "--format=", "--name-only", "--no-renames", "-z",
               f"{args.base}..HEAD"], cwd)
    count = git(["rev-list", "--count", f"{args.base}..HEAD"], cwd)
    if status is None or log is None or count is None:
        return stop("git-failed")
    if status.strip():
        return _not_pushable("dirty-tree")
    # Per commit, not first-to-last: a file added and deleted again is still in
    # the history that would go out.
    paths = sorted({p for p in log.split("\0") if p.strip("\n")})
    if not paths:
        return _not_pushable("nothing-to-push")
    held = [p for p in paths if is_held(p)]
    if held:
        return _not_pushable("held-path", held)
    print(f"pushable {_escape(branch)} {count.strip()}")
    return 0


def _not_pushable(reason, held=()):
    print(f"not-pushable {reason}")
    for path in held:
        print(f"held {_escape(path)}")
    return 3


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def check_results(results, expected):
    """The problems that keep a results object from being a report; empty means
    every item has exactly one known outcome and what that outcome needs."""
    if not isinstance(results, dict) or not isinstance(results.get("items"), list):
        return ["the results file must be an object with an `items` list"]
    problems, seen = [], set()
    for n, row in enumerate(results["items"], 1):
        if (not isinstance(row, dict) or row.get("id") is None
                or not str(row["id"]).strip()):
            problems.append(f"item {n} has no id")
            continue
        ident = str(row["id"])
        if ident in seen:
            problems.append(f"{ident}: duplicate id")
        seen.add(ident)
        outcome = row.get("outcome")
        if outcome not in OUTCOMES:
            problems.append(f"{ident}: unknown outcome {outcome!r}")
            continue
        for field in REQUIRED.get(outcome, ()):
            if not row.get(field):
                problems.append(f"{ident}: outcome {outcome} needs {field}")
    if expected is not None:
        problems += [f"{i}: missing from the results" for i in expected if i not in seen]
        problems += [f"{i}: not expected" for i in sorted(seen - set(expected))]
    return problems


def render_report(results):
    """The final report as lines; every third-party string is escaped."""
    items = results["items"]
    if not items:
        return ["no items"]
    lines, kept, touched = [], [], {}
    for row in items:
        ident, outcome = _escape(str(row["id"])), row["outcome"]
        where = row.get("url") or row.get("branch")
        head = f"{ident} {outcome}" + (f" {_escape(where)}" if where else "")
        lines.append(head + (" checks not waited for" if outcome == "pr-opened" else ""))
        lines.append("  " + OUTCOMES[outcome])
        if row.get("detail"):
            lines.append("  detail: " + _escape(str(row["detail"])))
        lines += ["  " + _escape(str(note)) for note in row.get("notes") or []]
        if row.get("branch") and not row.get("url"):
            kept.append(f"  {ident} {_escape(row['branch'])}")
        if outcome == "pr-opened":
            for path in set(row.get("paths") or []):
                touched.setdefault(path, []).append(ident)
    if kept:
        lines += ["local branches kept:"] + kept
    shared = [f"  {_escape(path)}: {', '.join(ids)}"
              for path, ids in sorted(touched.items()) if len(ids) > 1]
    if shared:
        lines += ["same file touched by:"] + shared
    return lines


def cmd_report(args):
    try:
        with open(args.results_file, encoding="utf-8-sig") as fh:
            results = json.load(fh)
        expected = None
        if args.expect_file:
            with open(args.expect_file, encoding="utf-8-sig") as fh:
                expected = [line.strip() for line in fh if line.strip()]
    except (OSError, ValueError) as exc:
        return stop("results-invalid", "cannot read the file (%s)" % type(exc).__name__)
    problems = check_results(results, expected)
    if problems:
        print("stopped results-invalid: " + _escape(problems[0]))
        for problem in problems[1:]:
            print("  " + _escape(problem))
        return 2
    print("\n".join(render_report(results)))
    return 0


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = preflight.ArgParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)

    def command(name, fn, *required, optional=(), project_dir=True):
        p = sub.add_parser(name)
        if project_dir:
            p.add_argument("--project-dir", default=".")
        for flag in required:
            p.add_argument(flag, required=True)
        for flag in optional:
            p.add_argument(flag)
        p.set_defaults(run=fn)
        return p

    command("classify", cmd_classify).add_argument("argument", nargs="?")
    command("ready", cmd_ready)
    command("changes", cmd_changes, "--expect-head", "--expect-branch",
            "--reported-file", "--pathspec-out", optional=("--ready-file",))
    command("pushable", cmd_pushable, "--base")
    command("report", cmd_report, "--results-file", optional=("--expect-file",),
            project_dir=False)
    args = ap.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
