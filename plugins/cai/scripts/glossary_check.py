#!/usr/bin/env python3
"""Deterministic check of a glossary file's entries. Zero deps.

A glossary line is `**Term**: definition`. What may be written into it has one
answer per kind of defect, so it is decided here and not left to a model's
reading of a rule: a decision id, a track-document path, a number with a unit
and a definition of more than two sentences are all copies of something that
lives somewhere else and goes stale there (#326), and a second entry under a
name already used makes one term mean two things.

Build runs this on a candidate file before it offers a term, and again on the
final lines before it writes them; `scripts/validate.py` runs it on the whole
file. All three hand it one UTF-8 file, so there is one set of patterns.

Usage:  glossary_check.py <file>
Exit:   0 nothing flagged, 2 at least one entry flagged or the file unreadable.
"""
import argparse
import re
import sys
from typing import NamedTuple

ENTRY = re.compile(r"^\*\*(?P<term>[^*\n]+?)\*\*:[ \t]*(?P<definition>\S.*?)\s*$")
DECISION_ID = re.compile(r"(?<![A-Za-z0-9_-])(?:AC|UC|[CDGIRSU])\d{1,3}(?![A-Za-z0-9_-])")
TRACK_PATH = re.compile(
    r"(?:\.claude/track/|docs/design/)[^\s`'\")）]*?\.md(?![A-Za-z0-9_-])"
    r"|(?<![A-Za-z0-9_./-])(?:intake|discover|decisions|stance|implementation-notes|state|pending)\.md(?![A-Za-z0-9_-])"
    r"|-(?:stance|decisions|detail|diagnosis|delta|high-level)\.md(?![A-Za-z0-9_-])")
# A number then a unit, with no letter after the unit so `5 more` and `2 ftp`
# are not units. A bare `A` (amperes) is taken only glued to its number, `12A`,
# because "3 A" is also a way to start a sentence; `in` and `us` are left out
# for the same reason. A `/` after the unit is not a letter, so `km/h` and
# `MB/s` are caught by their first half.
NUMBER_UNIT = re.compile(
    r"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?[ \t]?"
    r"(?:(?:"
    # time
    r"ms|s|secs?|seconds?|mins?|minutes?|h|hrs?|hours?|days?|weeks?|months?|years?|yrs?"
    r"|ns|[µμ]s|(?:milli|micro|nano)seconds?"
    # length
    r"|[nmck]?m|(?:nano|micro|milli|centi|kilo)?(?:meter|metre)s?|inch(?:es)?|f(?:ee|oo)t|ft|yards?|yd"
    r"|miles?|mi"
    # mass
    r"|m?g|kg|(?:milli|kilo)?grams?|tonnes?|tons?|lbs?|pounds?|oz|ounces?"
    # volume
    r"|m?[Ll]|(?:milli)?lit(?:re|er)s?|gal|gallons?|pints?|quarts?|cups?|cc"
    # temperature
    r"|degrees?|kelvin|celsius|fahrenheit|°[CFK]?|℃|℉"
    # electricity, frequency
    r"|[mk]?V|volts?|mAh?|Ah|amps?|amperes?|[mkMG]?Wh?|watts?|[kM]?(?:ohms?|Ω)"
    r"|[kMGT]?(?:Hz|hertz)"
    # speed
    r"|mph|kph|fps|rpm|knots?"
    # data, data rates
    r"|[KMGTP]i?B|kB|[kKMGT]?bits?|[kKMGT]?bps"
    r"|bytes?|lines?|rows?|chars?|characters?|tokens?|rounds?|times)(?![A-Za-z])"
    r"|(?<=\d)A(?![A-Za-z])"
    r"|%|秒|毫秒|分鐘|小時|天|週|年|月|位元組|字元|行|列|輪|次|個"
    r"|公斤|公克|克|公里|公尺|公分|毫米|公升|毫升|瓦|伏特|伏|安培|赫茲|度|英里|英寸|英吋|磅|盎司|哩|呎|吋)")
CODE_SPAN = re.compile(r"`[^`]*`")
ABBREVIATION = re.compile(r"\b(?:e\.g|i\.e|etc|vs|cf)\.", re.I)
SENTENCE_END = re.compile(r"[。！？]|[.!?](?=\s|$)")
MAX_SENTENCES = 2


class Finding(NamedTuple):
    line: int
    term: str
    reasons: tuple


def sentences(definition):
    # Code spans and abbreviations carry full stops that end nothing.
    flat = ABBREVIATION.sub("x", CODE_SPAN.sub("x", definition))
    return sum(1 for part in SENTENCE_END.split(flat) if part.strip())


def reasons(definition):
    """Why one definition may not be written, in a fixed order."""
    out = []
    for label, pattern in (("decision id", DECISION_ID),
                           ("track-document path", TRACK_PATH),
                           ("number with a unit", NUMBER_UNIT)):
        m = pattern.search(definition)
        if m:
            out.append("%s %s" % (label, m.group(0)))
    n = sentences(definition)
    if n > MAX_SENTENCES:
        out.append("%d sentences, at most %d" % (n, MAX_SENTENCES))
    return out


def name_key(term):
    return " ".join(term.replace("`", "").split()).casefold()


def check_text(text):
    """(entry count, findings in line order) for a whole file's text."""
    entries, findings, seen = 0, [], {}
    for number, line in enumerate(text.splitlines(), 1):
        m = ENTRY.match(line)
        if not m:
            if line.startswith("**"):
                findings.append(Finding(number, line[:40],
                                        ("not a **Term**: definition line",)))
            continue
        entries += 1
        why = reasons(m.group("definition"))
        key = name_key(m.group("term"))
        if key in seen:
            why.append("name already used on line %d" % seen[key])
        else:
            seen[key] = number
        if why:
            findings.append(Finding(number, m.group("term"), tuple(why)))
    return entries, findings


def main(argv=None):
    # Terms are written in the user's own language and every FAIL line quotes
    # one back; a piped stdout on Windows defaults to the ANSI codepage.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", help="the glossary file, UTF-8")
    args = ap.parse_args(argv)

    try:
        with open(args.file, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        print("FAIL %s: not readable: %s" % (args.file, exc))
        return 2

    entries, findings = check_text(text)
    for f in findings:
        print("FAIL line %d: %s: %s" % (f.line, f.term, "; ".join(f.reasons)))
    print("-- glossary: %d entries checked, %d flagged" % (entries, len(findings)))
    return 2 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
