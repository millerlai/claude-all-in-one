#!/usr/bin/env python3
"""The capability interface between the track system and an external ticket
CLI, plus the GitHub implementation. Zero deps.

Four semantic capabilities -- whoami, read, upsert_comment, transition_once
-- are kept apart from "which CLI, which subcommands" (Backend/GitHubBackend
below), and every external result is squeezed down to one of six category
words before it leaves this file (classify()). Nothing here raises: a CLI
that is absent or hung is exactly as normal a result as a 401 is, because
this feature must never be the reason a track stage fails (see the detail
design's `## Requirement`).

Where this sits in `ticket` -> `preflight` -> `ledger` -> `usage_collector`
(one direction, no cycle): this file imports nothing from this repo, so
`ticket.py` can import it without closing a loop back to itself.
"""
import json
import os
import subprocess
import tempfile

CATEGORIES = ("ok", "auth-failed", "ticket-not-found",
              "forbidden", "unreachable", "unclassified")
TIMEOUT_SECONDS = 10

# The test seam: a subprocess only sees its own environment, not a
# monkeypatch (tests/conftest.py:56), so this follows CAI_USAGE_LEDGER's
# shape (usage_collector.py:44) rather than reaching for one. A value
# starting with `[` is a JSON argv array; anything else is a single
# executable path.
CLI_ENV = "CAI_TICKET_CLI"

# The four stderr wordings below are captured verbatim from real `gh`
# output (HLD C1-C6, main session 2026-08-31), not invented. `forbidden` is
# deliberately absent here: GitHub answers unauthorized reads with
# "Could not resolve" rather than 403 (to avoid leaking existence), so 403
# only ever shows up on a write path, and upsert_comment checks for it
# itself as the DD10 identity-change signal -- classify() never returns
# "forbidden".
_AUTH_FAILED = ("http 401", "bad credentials")
_TICKET_NOT_FOUND = ("could not resolve to an issue or pull request",
                     "could not resolve to a repository")
_UNREACHABLE_STDERR = ("error connecting to",)


def classify(exc, returncode, stderr):
    """One of CATEGORIES, purifying a subprocess result down to a closed set
    so raw stderr -- which can carry a credential-bearing URL, per the 401
    message's own `https://api.github.com/graphql` -- has no path into any
    saved file. Only the category word may survive past this function."""
    if isinstance(exc, (FileNotFoundError, subprocess.TimeoutExpired, OSError)):
        return "unreachable"
    if returncode == 0:
        return "ok"
    low = (stderr or "").lower()
    if any(needle in low for needle in _AUTH_FAILED):
        return "auth-failed"
    if any(needle in low for needle in _TICKET_NOT_FOUND):
        return "ticket-not-found"
    if any(needle in low for needle in _UNREACHABLE_STDERR):
        return "unreachable"
    # Covers "body is too long" and everything else the caller has not
    # taught this function to recognise -- both are "unclassified" on
    # purpose, per the detail design's classify() decision order.
    return "unclassified"


def _cli_prefix():
    """The argv prefix that invokes the ticket CLI: ["gh"], or CAI_TICKET_CLI's
    override. Measured on Windows: CreateProcess only appends `.exe` to a bare
    name, so a `.cmd` stub given without its extension fails with
    `WinError 2` -- callers must pass the full path, and this warns once when
    that looks like it was forgotten."""
    override = os.environ.get(CLI_ENV)
    if not override:
        return ["gh"]
    if override.startswith("["):
        try:
            argv = json.loads(override)
        except ValueError:
            # Malformed JSON must never raise here -- this feature must
            # never be the reason a track stage fails (module docstring).
            # Falling back to the raw value as a single executable path
            # matches the never-raise shape _load_json_object() already
            # uses below.
            print("warning: %s starts with [ but did not parse as JSON -- "
                  "treating it as a single executable path instead: %r"
                  % (CLI_ENV, override))
            argv = [override]
    else:
        argv = [override]
    if "." not in os.path.basename(argv[0]):
        print("warning: %s's executable %r has no file extension -- on "
              "Windows this fails with WinError 2 unless it is one of the "
              "names CreateProcess resolves on its own" % (CLI_ENV, argv[0]))
    return argv


ARG_SUMMARY_MAX = 40


def _argv_summary(argv):
    """One short line naming the call, never the payload it carries.

    The design asks for `backend argv 摘要 -> 分類詞`, and the summary part
    is load-bearing rather than cosmetic: the comment body handed to
    `-f body=...` is a whole rendered six-row table, so printing argv
    verbatim turns every projection into a screenful and puts whatever the
    table holds on screen. Newlines collapse too -- a multi-line entry
    would break the one-line-per-call contract on its own."""
    parts = []
    for arg in argv:
        flat = " ".join(str(arg).split())
        parts.append(flat if len(flat) <= ARG_SUMMARY_MAX
                     else flat[:ARG_SUMMARY_MAX] + "...")
    return " ".join(parts)


def run(args, cwd=None):
    """Runs the ticket CLI with `args` appended to its configured prefix.
    Returns (CompletedProcess | None, category). Never raises: the two
    exceptions a hung or absent CLI can produce are caught right here and
    turned into "unreachable", matching preflight.py:212-220's shape for
    calling an external process without going through a shell.

    encoding="utf-8" is explicit rather than `text=True`'s console-locale
    default: unlike git (preflight.py's own caller), gh's output is never
    just ASCII -- it echoes back comment bodies, issue titles, and this
    project's own state.md notes, and `gh` itself always emits UTF-8
    regardless of the console's locale. Left to the default, a cp950
    console decoding a Chinese comment raised UnicodeDecodeError inside
    subprocess's own background reader thread (measured against issue #48,
    2026-08-31) -- a thread whose uncaught exception this function's
    `except` clause cannot see, since it never propagates to the caller;
    it left `done.stdout` silently `None` instead. errors="replace" turns
    any byte sequence that still is not valid UTF-8 into mangled-but-
    decodable text rather than raising, so this call itself can never be
    the reason a Backend method raises."""
    argv = _cli_prefix() + list(args)
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=TIMEOUT_SECONDS)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        category = classify(exc, -1, "")
        print("backend %s -> %s" % (_argv_summary(argv), category))
        return None, category
    category = classify(None, done.returncode, done.stderr)
    print("backend %s -> %s" % (_argv_summary(argv), category))
    return done, category


def _text(value):
    """`value` if it is already a string, else "" -- the guard every call
    site needs against `done.stdout`/`done.stderr` coming back None, which
    subprocess.run() can still do even though it did not raise (a reader
    thread's own decode failure is swallowed by Python's default thread
    excepthook rather than surfacing here; see run()'s docstring)."""
    return value if isinstance(value, str) else ""


def _load_json_object(text):
    """Parses `text` as a JSON object. Returns None on anything that is not
    parseable JSON, or parses to something other than a dict -- never
    raises. This is the one place a Backend method's "must not raise"
    requirement would otherwise have a hole: json.loads() raises on
    non-str input and on malformed text alike."""
    if not isinstance(text, str):
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _numeric_comment_id(url):
    """The digits after `#issuecomment-` in a comment's `url` field -- the id
    the REST PATCH endpoint accepts. Not the same value `--json comments`
    calls `id` (a GraphQL node id like `IC_kwDOSxA3Cc8AAAABRjw0GQ`), which
    the endpoint rejects; feeding it the node id is the easiest mistake on
    this path (measured, main session 2026-08-31)."""
    return url.rsplit("#issuecomment-", 1)[-1]


def _is_forbidden(stderr):
    low = (stderr or "").lower()
    return "403" in low or "forbidden" in low


class Backend:
    """Four semantic capabilities a ticket system must offer. Every method
    returns (value, category) and never raises -- classify() is what turns
    an external failure into a category instead of an exception."""
    name = None

    def whoami(self, project_dir):
        raise NotImplementedError

    def read(self, project_dir, ref):
        raise NotImplementedError

    def upsert_comment(self, project_dir, ref, marker, body, login):
        raise NotImplementedError

    def transition_once(self, project_dir, ref):
        raise NotImplementedError


class GitHubBackend(Backend):
    name = "github"

    def whoami(self, project_dir):
        done, category = run(["api", "user", "--jq", ".login"], cwd=project_dir)
        if category != "ok":
            return None, category
        login = _text(done.stdout).strip()
        if not login:
            return None, "unclassified"
        return login, "ok"

    def read(self, project_dir, ref):
        done, category = run(
            ["issue", "view", str(ref), "--json", "number,title,body"],
            cwd=project_dir)
        if category != "ok":
            return None, category
        data = _load_json_object(done.stdout)
        if data is None:
            return None, "unclassified"
        value = {"number": str(data.get("number", "")),
                 "title": data.get("title", ""),
                 "body": data.get("body", "")}
        return value, "ok"

    def upsert_comment(self, project_dir, ref, marker, body, login):
        # Repo resolution is left to `gh` itself, from the project's git
        # remote (see the detail design's `## Requirement`: this version
        # does not support a cross-repo ticket) -- so `{owner}`/`{repo}` are
        # literal placeholders `gh api` fills in from `cwd`, not values this
        # code computes.
        listed, list_category = run(
            ["issue", "view", str(ref), "--json", "comments"], cwd=project_dir)
        if list_category != "ok":
            return None, list_category
        listed_data = _load_json_object(listed.stdout)
        if listed_data is None:
            return None, "unclassified"
        comments = listed_data.get("comments")
        if not isinstance(comments, list):
            comments = []

        # Marker find-back: body contains the marker AND author is the
        # passed-in (cached) login. No up-front identity check -- that is
        # what keeps a cache hit at 2 round trips (DD10).
        match = next(
            (c for c in comments if marker in (c.get("body") or "")
             and (c.get("author") or {}).get("login") == login), None)

        if match is not None:
            endpoint = "repos/{owner}/{repo}/issues/comments/%s" % (
                _numeric_comment_id(match.get("url", "")))
            write_done, write_category = run(
                ["api", "--method", "PATCH", endpoint, "-f", "body=" + body],
                cwd=project_dir)
            url = match.get("url")
        else:
            # Body goes through a file, not argv, so a six-row table's
            # newlines and quotes never touch the command line.
            fd, tmp_path = tempfile.mkstemp(suffix=".md")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(body)
                write_done, write_category = run(
                    ["issue", "comment", str(ref), "--body-file", tmp_path],
                    cwd=project_dir)
            finally:
                os.unlink(tmp_path)
            url = (_text(write_done.stdout).strip() or None
                   if write_done is not None else None)

        if write_category == "ok":
            return url, "ok"

        # 403 (or "forbidden") in a write's stderr is always "forbidden" --
        # classify()'s own decision order has no 403 rule, and the design
        # reserves this category for exactly this signal on a write path
        # (a read never produces it: GitHub answers an unreadable repo with
        # "Could not resolve" instead, precisely to avoid leaking it).
        #
        # DD10's extra whoami only decides which *message* to print, not the
        # category: an identity change gets told apart from a plain
        # permissions problem on the same account, but both are "forbidden".
        stderr = _text(write_done.stderr) if write_done is not None else ""
        if _is_forbidden(stderr):
            current_login, whoami_category = self.whoami(project_dir)
            if whoami_category == "ok" and current_login != login:
                print("identity differs: this track was cached under login "
                      "%r, but the CLI is currently authenticated as %r -- "
                      "the projection was not written, and no second marked "
                      "comment was created; confirm the new identity and "
                      "re-run `ticket.py point --ref %s`"
                      % (login, current_login, ref))
            else:
                print("permission denied updating the mirror comment on "
                      "ticket %s -- the login %r does not currently have "
                      "permission to edit it; the projection was not "
                      "written" % (ref, login))
            return None, "forbidden"
        return None, write_category

    def transition_once(self, project_dir, ref):
        # Idempotent by measurement: `gh issue close` on an already-closed
        # issue still exits 0 (`! Issue ... is already closed`), so a retry
        # never produces an error state.
        done, category = run(["issue", "close", str(ref)], cwd=project_dir)
        return category == "ok", category


class StubBackend(Backend):
    """A no-network backend: every method answers from fixed, in-memory
    values and never touches `subprocess` or the filesystem. This is the
    assertable form of AC23 -- a second backend, registered in BACKENDS,
    costs preflight.py and plugins/cai/skills/track/ zero lines, and this
    one proves it by being incapable of an external call in the first
    place, rather than merely not making one today."""
    name = "local-stub"

    def whoami(self, project_dir):
        return "local-stub-user", "ok"

    def read(self, project_dir, ref):
        return {"number": str(ref), "title": "stub ticket %s" % ref, "body": ""}, "ok"

    def upsert_comment(self, project_dir, ref, marker, body, login):
        return "local-stub://%s/comment" % ref, "ok"

    def transition_once(self, project_dir, ref):
        return True, "ok"


BACKENDS = {"github": GitHubBackend, "local-stub": StubBackend}


def get(name):
    cls = BACKENDS.get(name)
    return cls() if cls else None
