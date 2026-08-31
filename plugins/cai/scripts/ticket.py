#!/usr/bin/env python3
"""The local, network-free half of the ticket-mirror feature. Zero deps.

`ticket_backend.py` is the only file that ever runs an external process; this
one only reads and writes files under the project and the track directory, so
it can be exercised (and imported) without `gh` on the machine at all -- which
is exactly AC22.

Where this sits in `ticket` -> `preflight` -> `ledger` -> `usage_collector`
(one direction, no cycle, per `plugins/cai/scripts/ledger.py:15-23`): this
file imports `preflight` for its table parsing, and nothing here imports back
up the chain.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preflight  # noqa: E402

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
