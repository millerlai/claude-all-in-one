#!/usr/bin/env python3
"""Deterministic shape check for an option list, before it is sent. Zero deps.

`rules/option-explainer.md` says which six fields every option carries. It
never said what the block looks like on the page, so a reply that runs all six
into one paragraph per option satisfied every word of it -- and a reader who
has to find "how reversible" inside a 90-word sentence is back where the rule
started (#73). This file holds the half a rule cannot: the shape.

It checks shape and nothing else. Whether the ELI5 is really an analogy, or
whether "what actually changes" names something observable, has no one answer
and stays with the self-check in the rules file. What is here has one answer,
costs no tokens, and fails the same way twice.

How it tells the parts apart, since the field labels are written in whatever
language the reply is in: dimensions are a bulleted list, an option's six
fields are a numbered one. That is why the rule asks for bullets there -- a
list numbered from 1 is then unambiguous evidence of an option block, in any
language, and the line above it is that option's title.

The title is any line, not a `##` heading: the example the issue calls correct
writes `選項 A — ...` as plain text, and a check that failed it would be
arguing with the thing it was asked to enforce.

Usage:  options_lint.py <draft>
Exit:   0 every probe passed, 2 at least one failed.
"""
import argparse
import re
import sys

HEADING = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")
ORDERED = re.compile(r"^(\d+)\.\s+(\S.*)$")
BULLET = re.compile(r"^[-*]\s+(\S.*)$")
BOLD_LED = re.compile(r"^\*\*[^*]+\*\*")
# The label carries the field's name; what the probe weighs is what follows it.
LABEL = re.compile(r"^\*\*[^*]+\*\*\s*[:：\-—–]*\s*")
PLACEHOLDER = re.compile(r"^(TBD|TODO|N/?A|\?+|-{1,3})\.?$", re.I)
SEP_CELL = re.compile(r":?-+:?")
# Matched the way design_probe.py already matches it in a high-level design's
# options, so one marker means the same thing in both places.
RECOMMENDED = re.compile(r"recommend", re.I)
FIELDS = 6
# The closing pick plus the condition that voids it. Shorter than this is the
# one-word "Option B" that the rule already refuses ("never end on it depends"
# has a twin: never end on a name with no reason beside it).
PICK_MIN = 40


def run_of_items(lines, start):
    """(number, text, line index) for the ordered list beginning at `start`.

    A blank line between two items does not end the list; any other non-item
    line does. Wrapped continuation lines are deliberately not folded in: the
    shape asks for label and content in the same item, so an item whose line
    is a bare `**ELI5**:` is a finding, not a parse to repair -- and folding
    is also how a check like this swallows the paragraph after the list.
    """
    out = []
    for i in range(start, len(lines)):
        s = lines[i].strip()
        m = ORDERED.match(s)
        if m:
            out.append((int(m.group(1)), m.group(2), i))
        elif s:
            break
    return out


def title_before(lines, at):
    """(text, line index) of the nearest non-blank line above `at` that is not
    itself list or table content -- the option's title."""
    for i in range(at - 1, -1, -1):
        s = lines[i].strip()
        if not s:
            continue
        if ORDERED.match(s) or BULLET.match(s) or s.startswith("|"):
            return "", at
        m = HEADING.match(s)
        return (m.group(2) if m else s), i
    return "", at


def option_blocks(lines):
    """(title, title line, items) per ordered list that starts at 1 -- the
    shape a filled-in option has."""
    out, i = [], 0
    while i < len(lines):
        m = ORDERED.match(lines[i].strip())
        if m and int(m.group(1)) == 1:
            items = run_of_items(lines, i)
            title, at = title_before(lines, i)
            out.append((title, at, items))
            i = items[-1][2] + 1
        else:
            i += 1
    return out


def bullets(lines):
    return [BULLET.match(ln.strip()).group(1)
            for ln in lines if BULLET.match(ln.strip())]


def has_table(lines):
    """A GFM table: a row of cells with a separator row under it."""
    for i, ln in enumerate(lines[:-1]):
        s, nxt = ln.strip(), lines[i + 1].strip()
        if not (s.startswith("|") and nxt.startswith("|")):
            continue
        cells = [c.strip() for c in nxt.strip("|").split("|")]
        if cells and all(SEP_CELL.fullmatch(c) for c in cells if c):
            return True
    return False


def content(item_text):
    """What is left of a field once its label is taken off."""
    return LABEL.sub("", item_text).strip()


def tail(lines, after):
    """The prose that closes the list: everything past the blank line that ends
    the last option's fields. Starting at the blank line rather than at the
    item keeps a field's own wrapped second line out of the pick's length."""
    i = after + 1
    while i < len(lines) and lines[i].strip():
        i += 1
    kept = [ln.strip() for ln in lines[i:]
            if ln.strip() and not HEADING.match(ln.strip())
            and not ln.strip().startswith("|")]
    return " ".join(kept)


def probes(text):
    lines = text.splitlines()
    blocks = option_blocks(lines)
    first = blocks[0][1] if blocks else len(lines)

    dims = [b for b in bullets(lines[:first]) if BOLD_LED.match(b)]
    yield len(dims) >= 2, \
        "dimensions_declared (%d bold-led bullet(s) before the first option, need 2)" % len(dims)

    yield len(blocks) >= 2, \
        "options_found (%d numbered field list(s) found, need 2)" % len(blocks)

    wrong = ["%s -> %s" % (title[:24] or "(untitled)", ",".join(str(n) for n, _, _ in items))
             for title, _, items in blocks
             if [n for n, _, _ in items] != list(range(1, FIELDS + 1))]
    yield bool(blocks) and not wrong, "six_fields (%s)" % (
        "; ".join(wrong[:3]) if wrong else
        "every option runs 1-%d" % FIELDS if blocks else "no option to check")

    empty = ["%s field %d" % (title[:20] or "(untitled)", n)
             for title, _, items in blocks for n, body, _ in items
             if not content(body) or PLACEHOLDER.match(content(body))]
    yield bool(blocks) and not empty, "fields_filled (%s)" % (
        "; ".join(empty[:3]) if empty else
        "%d field(s) carry content" % sum(len(i) for _, _, i in blocks)
        if blocks else "no option to check")

    # The marker, not the closing sentence, is what says which option was
    # picked: it is the same literal stage-design.md and stage-intake.md
    # already ask for, and it survives being read in any language.
    marked = [title[:24] for title, _, _ in blocks if RECOMMENDED.search(title)]
    yield len(marked) == 1, "one_recommended (%s)" % (
        "; ".join(marked) if marked else "no option title carries `(recommended)`")

    close = tail(lines, blocks[-1][2][-1][2]) if blocks else ""
    yield len(close) >= PICK_MIN, \
        "pick_closes (%d character(s) after the last option, need %d)" % (
            len(close), PICK_MIN)

    if len(blocks) >= 3:
        yield has_table(lines[:first]), "table_for_three_or_more (%s)" % (
            "found" if has_table(lines[:first]) else
            "%d options and no side-by-side table before them" % len(blocks))


def main():
    # The draft is written in the user's own language and every FAIL line
    # quotes an option's title back. Same reason track_state.py and ledger.py
    # do this, and pinned by the same test file: on Windows a piped stdout
    # defaults to the ANSI codepage, so a title the caller then cannot decode
    # names nothing. The console path is already UTF-8 (PEP 528).
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("draft", help="the option list, as Markdown")
    args = ap.parse_args()

    try:
        with open(args.draft, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print("FAIL draft not readable:", exc)
        return 2

    failed = 0
    for ok, label in probes(text):
        print(("PASS " if ok else "FAIL ") + label)
        failed += not ok
    print("-- options: %d probe(s) failed" % failed)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
