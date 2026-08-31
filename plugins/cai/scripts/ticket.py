#!/usr/bin/env python3
"""The local half of the ticket-mirror feature, plus the CLI that wires it to
`ticket_backend.py`. Zero deps beyond the standard library and same-directory
siblings.

`read_config`/`read_pointer`/`write_pointer`/`render_comment` below are still
network-free and exercisable without `gh` on the machine at all (AC22): only
`ticket_backend.py` ever runs an external process. `project()` and `main()`
are the one exception -- they are the CLI layer unit 3 adds, and they call
into `ticket_backend` to actually talk to a ticket, which is why this module
imports it (see `tests/test_ticket_config.py`'s
`test_ticket_py_imports_only_stdlib_and_siblings` for why that import is
allowed under AC22: `ticket_backend` is this feature's other half, not a
third-party dependency).

Where this sits in `ticket` -> `preflight` -> `ledger` -> `usage_collector`
(one direction, no cycle, per `plugins/cai/scripts/ledger.py:15-23`): this
file imports `preflight` for its table parsing and `ticket_backend` for the
capability interface, and nothing here imports back up the chain -- in
particular this file never imports `ledger` (DD2): a projection failure is
recorded in `ticket.json`, never in the ledger.
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preflight  # noqa: E402
import ticket_backend  # noqa: E402

CONFIG_REL = os.path.join(".claude", "cai.json")
POINTER_NAME = "ticket.json"

# state.md's note column, truncated for the mirrored comment: a ticket has no
# obligation to render a wall of text, and 200 keeps every row a glance-sized
# line even when a note was written for a human reading state.md directly.
NOTE_LIMIT = 200
ELLIPSIS = "…"


def read_config(project_dir):
    """This project's ticket-mirror setting, never raising.

    Missing file means the feature was never turned on here -- `problem`
    stays None and nothing is printed (AC1: silence when disabled). A file
    that exists but cannot be read or parsed as the expected shape is a
    different case: it *was* an attempt to turn this on, so it gets a
    problem sentence the caller can print -- one we wrote, never a fragment
    of the file itself, since a `problem` string ends up in whatever the
    caller logs.
    """
    path = preflight.resolve(CONFIG_REL, project_dir)
    if path is None:
        return {"enabled": False, "backend": "", "problem": None}

    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"enabled": False, "backend": "",
                "problem": "%s could not be read as JSON" % CONFIG_REL}

    ticket = data.get("ticket") if isinstance(data, dict) else None
    if not isinstance(ticket, dict):
        return {"enabled": False, "backend": "",
                "problem": "%s has no \"ticket\" object" % CONFIG_REL}

    enabled = ticket.get("enabled")
    backend = ticket.get("backend")
    if not isinstance(enabled, bool) or not isinstance(backend, str):
        return {"enabled": False, "backend": "",
                "problem": ("%s's ticket.enabled must be a bool and "
                            "ticket.backend a string" % CONFIG_REL)}

    return {"enabled": enabled, "backend": backend, "problem": None}


def _pointer_path(track_dir):
    return os.path.join(track_dir, POINTER_NAME)


def read_pointer(track_dir):
    """This track's ticket pointer, or None when there is none to read --
    a missing file, an unreadable one, and a malformed one all read the
    same way: the integration is silently off for this track."""
    try:
        with open(_pointer_path(track_dir), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_pointer(track_dir, pointer):
    """Whole-file overwrite, not append -- ticket.json holds one pointer, not
    a log (unlike ledger.py's append-only file, see its own :306-336 for why
    that file needs a lock and this one does not: read-modify-write here can
    only lose the *other* writer's update, never interleave with it).

    A write that fails must not fail the projection it is part of, so the
    only response to OSError is one printed line."""
    try:
        with open(_pointer_path(track_dir), "w", encoding="utf-8") as fh:
            json.dump(pointer, fh, ensure_ascii=False, indent=2)
    except OSError as exc:
        print("cannot write %s: %s" % (_pointer_path(track_dir), exc))


def marker_for(feature):
    """The delimiter that finds this track's own mirrored comment back among
    everything else on the ticket. The brackets are load-bearing: without
    them `cai track: ticket` is a substring of `cai track: ticket-integration`
    and two tracks would match each other's comments."""
    return "[cai track: %s]" % feature


def _truncate_note(note):
    if len(note) <= NOTE_LIMIT:
        return note
    return note[:NOTE_LIMIT] + ELLIPSIS


def render_comment(track_dir, feature, now):
    """state.md's six stage rows, rendered as the body of the mirrored
    comment. None when there is nothing sane to render -- no state.md, or a
    table that does not have exactly six rows -- so the caller can skip the
    projection instead of writing a comment that lies about the track.

    `artifact` is deliberately left out of the table: it is a `docs/` path
    local to whoever ran the stage, and `docs/` is gitignored (./.gitignore:15),
    so it names nothing a teammate reading the ticket could resolve."""
    path = os.path.join(track_dir, "state.md")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        print("cannot render a comment: no state.md in %s" % track_dir)
        return None

    rows = preflight.data_rows(text)
    if len(rows) != 6:
        print("cannot render a comment: state.md has %d stage row(s), not 6"
              % len(rows))
        return None

    lines = [marker_for(feature),
             "此留言由 cai 就地覆寫，請勿手動編輯",
             "| stage | status | note |",
             "| --- | --- | --- |"]
    for cells in rows:
        stage = cells[0] if len(cells) > 0 else ""
        status = cells[1] if len(cells) > 1 else ""
        note = cells[3] if len(cells) > 3 else ""
        lines.append("| %s | %s | %s |" % (stage, status, _truncate_note(note)))
    lines.append("updated %s" % now)
    return "\n".join(lines)


def _feature_from_track_dir(track_dir):
    """The feature name a marker line and `render_comment` need, taken from
    the directory name rather than passed in separately -- every caller
    already has `track_dir` as `.claude/track/<feature>` (see
    `plugins/cai/scripts/track_state.py:56`), so this avoids a second
    argument that could disagree with the first."""
    return os.path.basename(os.path.normpath(track_dir))


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resend_hint(track_dir, project_dir):
    """The manual-fixup entry point, worded so it can be pasted as-is (per
    the detail design's Observability note for `project`/`transition`)."""
    return ("re-run `ticket.py project --track-dir %s --project-dir %s` "
            "once this clears" % (track_dir, project_dir))


def project(track_dir, project_dir):
    """Runs one projection: config -> pointer -> render -> backend -> record.

    Never raises and never returns anything a caller could mistake for a
    reason to fail the stage -- `main()` always exits 0 from this path. Every
    outcome, success or failure, is recorded in `ticket.json`'s `projection`
    field and nowhere else (DD2): this function never imports or calls
    `ledger`, so a network blip here can never be recorded as `blocked` or
    `failed` and never counts toward the five-attempt lockout.

    `pointer["login"]` is only ever set here on a cache miss (no cached login
    yet) and never overwritten afterwards -- that cache is the sole baseline
    a later 403 gets compared against (DD10); only `point()` may clear or
    replace it. A cache hit costs zero extra round trips: `whoami` is skipped
    entirely once a login is cached, which is what keeps a steady-state
    projection at the two round trips `upsert_comment` itself makes.
    """
    cfg = read_config(project_dir)
    if cfg["problem"]:
        print(cfg["problem"])
    if not cfg["enabled"]:
        return None  # AC1: not one character printed when never turned on

    pointer = read_pointer(track_dir)
    if pointer is None:
        print("this track has no ticket pointer -- run `ticket.py point "
              "--track-dir %s --ref <n>`" % track_dir)
        return None

    backend = ticket_backend.get(pointer.get("backend"))
    if backend is None:
        print("unknown ticket backend %r for %s -- run `ticket.py point "
              "--track-dir %s --ref %s --backend <name>` to fix it"
              % (pointer.get("backend"), track_dir, track_dir, pointer.get("ref")))
        return None

    feature = _feature_from_track_dir(track_dir)
    body = render_comment(track_dir, feature, _now())
    if body is None:
        return None  # render_comment already printed why; nothing to send

    login = pointer.get("login")
    if login is None:
        login, category = backend.whoami(project_dir)
        if category != "ok":
            pointer["projection"] = {"status": category, "at": _now()}
            write_pointer(track_dir, pointer)
            print("project: %s -- %s" % (category, _resend_hint(track_dir, project_dir)))
            return category
        pointer["login"] = login  # first successful whoami, cached from here

    marker = marker_for(feature)
    _, category = backend.upsert_comment(project_dir, pointer["ref"], marker, body, login)
    pointer["projection"] = {"status": category, "at": _now()}
    write_pointer(track_dir, pointer)
    if category == "ok":
        print("project: ok")
    else:
        print("project: %s -- %s" % (category, _resend_hint(track_dir, project_dir)))
    return category


def point(track_dir, ref, backend_name):
    """(Re)points this track at a ticket. The whole pointer is replaced, not
    merged field by field -- an old projection result naming a different
    ticket, or a login cached under a since-switched account, must never
    survive a repoint. Clearing `login` here is the documented way back after
    `gh auth switch` (DD10): the next `project()` call re-fetches identity
    instead of comparing against one that no longer applies."""
    existing = read_pointer(track_dir)
    backend = backend_name or (existing.get("backend") if existing else None) or "github"
    pointer = {"backend": backend, "ref": ref, "login": None, "projection": None}
    write_pointer(track_dir, pointer)
    print("point: %s -> ref %s (backend %s)" % (track_dir, ref, backend))


def show(track_dir, dry_run):
    """Prints this track's pointer -- the sole query entry point for where a
    projection failure landed once DD2 took it out of the ledger, and where a
    user confirms the cached login `point()` set. Never calls a backend, with
    or without `--dry-run`: `--dry-run` only adds the locally rendered body,
    which costs zero external calls of its own."""
    pointer = read_pointer(track_dir)
    if pointer is None:
        print("this track has no ticket pointer -- run `ticket.py point "
              "--track-dir %s --ref <n>`" % track_dir)
        return

    print("ref: %s" % pointer.get("ref"))
    print("login: %s" % (pointer.get("login") or "(none cached)"))
    projection = pointer.get("projection")
    if projection:
        print("last projection: %s at %s" % (projection.get("status"), projection.get("at")))
    else:
        print("last projection: (none yet)")

    if dry_run:
        feature = _feature_from_track_dir(track_dir)
        body = render_comment(track_dir, feature, _now())
        if body is not None:
            print(body)


class ArgParser(argparse.ArgumentParser):
    # argparse's own error() exits 2; this script reserves 2 for nothing --
    # preflight.py uses it to mean "blocked", and a stray 2 from here would
    # eventually be recorded as blocked, counting toward the five-attempt
    # lockout a network blip must never cause. A usage mistake gets 1
    # instead, copying plugins/cai/scripts/ledger.py:515-521.
    def error(self, message):
        self.print_usage(sys.stderr)
        print("%s: error: %s" % (self.prog, message), file=sys.stderr)
        sys.exit(1)


def main():
    # Same reasoning as plugins/cai/scripts/ledger.py:524-532: a piped
    # stdout defaults to the ANSI codepage on Windows, and this script prints
    # whatever alphabet state.md's own notes were written in.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = ArgParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["project", "point", "show"])
    ap.add_argument("--track-dir", required=True)
    ap.add_argument("--project-dir", default=".")
    ap.add_argument("--ref")
    ap.add_argument("--backend")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.command == "point":
        if not args.ref:
            ap.error("point needs --ref")
        point(args.track_dir, args.ref, args.backend)
    elif args.command == "show":
        show(args.track_dir, args.dry_run)
    else:
        project(args.track_dir, args.project_dir)

    # Every path above already printed its own explanation; the exit code
    # itself is never the signal. 0 always, except the usage error
    # ArgParser.error() already exited 1 for, directly.
    return 0


if __name__ == "__main__":
    sys.exit(main())
