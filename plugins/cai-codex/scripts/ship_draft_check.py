#!/usr/bin/env python3
"""Mechanical checks on ship's drafted commit message and PR body, run by the
main session before either menu in references/approval-gates.md's Gate 2 --
so what has one answer (a title's length, a closing keyword, whether `Refs
#N` appears exactly once) is caught here instead of by the main session
re-deriving every claim by hand (stage-ship.md's grounding rule). Zero deps.

A first-step sample of 60 merged PRs (measured for issue 196, numbers in the
PR description) found no real path:line or file/line-count mismatch once a
path was resolved the way `preflight.resolve()` already does -- every
apparent mismatch was a bare filename or an unrelated number in prose, not a
drafted claim that was actually wrong. Those two checks are left unbuilt for
that reason; the sample is a lower bound (merged text already survived one
round of correction), so a later, better-targeted sample could still turn one
up.

The attribution-trailer check named in the original proposal is dropped:
this script never writes, rewrites or checks that trailer. A dispatched
draft carries no trailer lines at all -- the main session adds its own
before showing the message (`stage-ship.md`'s Step 4, `approval-gates.md`'s
squash bullet) -- so there is nothing here for this script to check.

Usage:  ship_draft_check.py --message-file F [--body-file F] [--ticket N]
                             [--track-dir D]
Exit:   0 every check passed, 2 any FAIL, 1 usage error (a missing required
        argument, or a file that could not be read).
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ticket  # noqa: E402

TITLE_TYPES = ("feat", "fix", "docs", "refactor", "test", "chore", "perf",
               "build", "ci", "style", "revert")
TITLE_RE = re.compile(r"^(?:%s)(\([^)]*\))?!?: .+$" % "|".join(TITLE_TYPES))
TITLE_MAX_LEN = 72

# ticket-mirror.md's own wording for the rule this mirrors: "close(s|d)",
# "fix(es|ed)", "resolve(s|d)", any case, with or without a colon, followed
# by an issue reference -- #N, an owner/repo#N cross-repo reference, or an
# issues URL. The keyword must sit directly against the reference (only an
# optional colon and whitespace between them) so a title's own
# `type(scope): summary` prefix, or an unrelated later "#N", never matches.
CLOSING_KEYWORD_RE = re.compile(
    r"\b(close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s*"
    r"(#\d+|[\w.-]+/[\w.-]+#\d+|https?://\S*/issues/\d+)",
    re.IGNORECASE)


def _read(path):
    """A file's text, or None when it could not be read -- the caller turns
    that into a usage error, since a message or body file that is missing or
    unreadable means this run cannot check anything, not that the draft
    failed a check."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def title_checks(message):
    """The first line of the drafted message against stage-ship.md Step 4's
    own rule: a conventional-commit type and at most 72 characters. Split
    into two checks, as preflight.py's own checks are, so a FAIL names which
    half of the rule broke."""
    title = message.splitlines()[0] if message else ""
    format_ok = bool(TITLE_RE.match(title))
    yield (format_ok, "title_format (%r is %sa type(scope)?!?: summary line)"
           % (title, "" if format_ok else "not "))
    length_ok = len(title) <= TITLE_MAX_LEN
    yield (length_ok, "title_length (title is %d character(s), max %d)"
           % (len(title), TITLE_MAX_LEN))


def closing_keyword_check(label, text):
    """FAIL when a closing keyword sits directly against an issue reference
    -- closing a ticket is `$track done`'s close menu, never a side
    effect of merging (issue 195)."""
    match = CLOSING_KEYWORD_RE.search(text)
    ok = match is None
    detail = ("no closing keyword found" if ok else
              "%r closes an issue -- use Refs #<number> instead" % match.group(0))
    return ok, "%s (%s)" % (label, detail)


def refs_check(label, text, ticket_number):
    """`Refs #<number>` must appear exactly once -- zero means the ticket
    went unnamed, more than one is copy-paste drift, either way the wrong
    number of pointers for one ticket. A trailing digit boundary keeps a
    longer number (`Refs #196`) from satisfying a shorter one (`Refs #19`),
    since the two share a prefix."""
    needle = "Refs #%s" % ticket_number
    count = len(re.findall(r"Refs #%s(?!\d)" % re.escape(str(ticket_number)), text))
    ok = count == 1
    return ok, "%s (%r appears %d time(s), need exactly 1)" % (label, needle, count)


def has_ticket_pointer(track_dir):
    """Whether this track has a ticket pointer at all -- a pointer with no
    resolved number still forbids a closing keyword (acceptance: "ticket
    checks apply only with --ticket or a ticket.json in --track-dir"), since
    resolving the number takes a network call this script does not make."""
    if not track_dir:
        return False
    return ticket.read_pointer(track_dir) is not None


def run_checks(message, body, ticket_number, track_dir):
    checks = list(title_checks(message))

    if ticket_number is not None or has_ticket_pointer(track_dir):
        checks.append(closing_keyword_check("closing_keyword_message", message))
        if body is not None:
            checks.append(closing_keyword_check("closing_keyword_body", body))

    if ticket_number is not None:
        checks.append(refs_check("refs_message", message, ticket_number))
        if body is not None:
            checks.append(refs_check("refs_body", body, ticket_number))

    return checks


class ArgParser(argparse.ArgumentParser):
    # argparse's own error() exits 2, which this script reserves for "a
    # check failed" -- a usage mistake is a different failure and gets exit
    # 1 instead, matching preflight.py's own ArgParser.
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(1)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = ArgParser(description=__doc__.splitlines()[0])
    ap.add_argument("--message-file", required=True)
    ap.add_argument("--body-file")
    ap.add_argument("--ticket")
    ap.add_argument("--track-dir")
    args = ap.parse_args()

    message = _read(args.message_file)
    if message is None:
        print("cannot read --message-file %s" % args.message_file, file=sys.stderr)
        return 1

    body = None
    if args.body_file is not None:
        body = _read(args.body_file)
        if body is None:
            print("cannot read --body-file %s" % args.body_file, file=sys.stderr)
            return 1

    checks = run_checks(message, body, args.ticket, args.track_dir)

    failed = 0
    for ok, label in checks:
        print(("PASS " if ok else "FAIL ") + label)
        failed += not ok
    print("-- ship draft: %d check(s) failed" % failed)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
