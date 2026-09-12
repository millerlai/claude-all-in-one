#!/usr/bin/env python3
"""Probe layer for docs/rule-provenance.md, the ledger that ties a hard rule
back to the failure that produced it. Zero deps.

The ledger's own writing convention (docs/rule-provenance.md:13-17): keep
each entry's rule sentence on one line; a rule sentence that pastes in a full
line starting with `## ` (quoting a heading, or a fenced code block
containing one) gets misread as a new entry, since `entries()` below splits
the ledger on exactly those lines.

Usage:  provenance.py [--ledger PATH] [--project-dir DIR]
Exit:   0 every probe passed, or the feature is not in use (no ledger, or a
        ledger with no entries); 2 at least one probe failed; 1 usage error.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preflight  # noqa: E402

LEDGER_REL = os.path.join("docs", "rule-provenance.md")
REQUIRED_FIELDS = ("Date", "Failure", "Rule", "Cited by")
# Probes whose FAIL means a quote that used to match no longer does --
# "add an entry" is the wrong fix for these; see main()'s hint below and
# docs/design/2026-09-12-issue78-rule-guards-detail.md's D-8.
DRIFT_LABELS = ("rule_quote_in_cited_section", "restated_quote_in_section",
                "shared_value_in_every_quote")


def entries(text):
    """Parse the ledger's full text into a list of entry dicts. Never raises
    -- a malformed entry is represented with missing/None fields instead, so
    each probe can report its own defect independently rather than one bad
    entry blocking every check (same convention as
    scripts/validate.py:339-368's provenance_entries(), not imported from
    here since this file must not import anything from scripts/)."""
    segments = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    out = []
    for segment in segments:
        heading, _, body = segment.partition("\n")
        heading = heading.strip()
        # U+2014 em dash, one space each side -- not an ASCII hyphen, which
        # the slugs themselves contain.
        id_, sep, _ = heading.partition(" — ")
        entry_id = id_.strip() if sep else heading

        fields = {}
        for label in REQUIRED_FIELDS:
            m = re.search(rf"^- {re.escape(label)}: (.+)$", body, re.MULTILINE)
            if m:
                fields[label] = " ".join(m.group(1).split())

        cited = None
        cited_value = fields.get("Cited by", "")
        if " § " in cited_value:
            path, _, cited_heading = cited_value.partition(" § ")
            cited = (path, cited_heading)

        restated = []
        restated_malformed = []
        for m in re.finditer(r"^- Restated in: (.+)$", body, re.MULTILINE):
            value = m.group(1).strip()
            if " § " in value and " | " in value:
                path, _, rest = value.partition(" § ")
                restated_heading, _, quote = rest.partition(" | ")
                restated.append((path.strip(), restated_heading.strip(), quote.strip()))
            else:
                restated_malformed.append(value)

        shared = None
        m = re.search(r"^- Shared value: (.+)$", body, re.MULTILINE)
        if m:
            shared = m.group(1).strip()

        out.append({
            "id": entry_id,
            "fields": fields,
            "cited": cited,
            "restated": restated,
            "restated_malformed": restated_malformed,
            "shared": shared,
        })
    return out


def normalise(text):
    """String equivalence for comparing a rule sentence against a section's
    prose. Order matters: fold whitespace, strip backticks, then en dash to
    hyphen. U+2014 (em dash) is deliberately left alone -- same reasoning as
    scripts/validate.py:457-462: an em-dash-heavy file's headings would
    otherwise widen this comparison's blast radius for no reason connected
    to what it is checking."""
    text = " ".join(text.split())
    text = text.replace("`", "")
    text = text.replace("–", "-")
    return text


def _fence_ranges(text):
    """(start, end) character ranges of every fenced code block in `text`,
    so section_of() can skip a heading-shaped decoy line inside one."""
    ranges = []
    inside = False
    fence_start = 0
    pos = 0
    for line in text.splitlines(keepends=True):
        if line.strip().startswith("```"):
            if not inside:
                inside = True
                fence_start = pos
            else:
                inside = False
                ranges.append((fence_start, pos + len(line)))
        pos += len(line)
    if inside:
        ranges.append((fence_start, len(text)))
    return ranges


def section_of(text, heading):
    """The slice of `text` from `heading`'s own line up to (not including)
    the next line that is itself a Markdown heading of the same or shallower
    level -- or end-of-file if there is none. `heading` is the heading's own
    full line, `#` characters included (e.g. "## Report"), matching the
    convention scripts/validate.py:1893-1914's verify_section() uses.

    Anchored to the start of a line, same anchoring lesson as verify_section
    (scripts/validate.py:1892-1913): an unanchored search would also match
    the heading text quoted elsewhere, e.g. inline in backticks. That alone
    does not rule out a decoy that is itself a whole line starting with `#`
    at column 0 inside a fenced code block giving an illustrative example
    (plugins/cai/skills/refactor/references/procedure-scan.md:61's
    `# Refactoring scan — <target>` is exactly this shape) -- so matches
    inside a fenced code block are skipped in favour of the first match that
    is not.

    Returns "" when the heading is not found (outside any fence). Never
    raises."""
    fences = _fence_ranges(text)

    def in_fence(offset):
        return any(start <= offset < end for start, end in fences)

    match = None
    for candidate in re.finditer(r"^" + re.escape(heading) + r"[ \t]*$", text, re.MULTILINE):
        if not in_fence(candidate.start()):
            match = candidate
            break
    if match is None:
        return ""

    start = match.start()
    level = len(heading) - len(heading.lstrip("#"))
    end = len(text)
    for candidate in re.finditer(r"^(#+)", text, re.MULTILINE):
        if candidate.start() <= start or in_fence(candidate.start()):
            continue
        if len(candidate.group(1)) <= level:
            end = candidate.start()
            break
    return text[start:end]


def _resolve_heading(path, heading, project_dir):
    """Resolve `path` § `heading` against `project_dir`, the same check both
    `cited_by_resolves` and `restated_quote_in_section` need: file exists, is
    UTF-8-readable, and contains that heading. Returns
    ((file_text, full_heading), None) on success, or (None, reason) with a
    short human-readable reason on failure. Never raises.

    Skips a heading-shaped decoy inside a fenced code block, the same
    fence-awareness section_of() already has (see its docstring) -- without
    this, a decoy at a different `#` level than the real heading would be
    picked here, then correctly rejected by section_of() (which does skip
    fences), turning an intact citation into a false "drifted" report."""
    full_path = os.path.join(project_dir, path)
    if not os.path.isfile(full_path):
        return None, "no such file"
    try:
        with open(full_path, encoding="utf-8") as fh:
            file_text = fh.read()
    except (OSError, UnicodeDecodeError):
        return None, "not readable as UTF-8"
    fences = _fence_ranges(file_text)

    def in_fence(offset):
        return any(start <= offset < end for start, end in fences)

    full_heading = None
    offset = 0
    for line in file_text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        if (stripped.startswith("#") and stripped.lstrip("#").strip() == heading
                and not in_fence(offset)):
            full_heading = stripped.rstrip()
            break
        offset += len(line)
    if full_heading is None:
        return None, "no such heading %r" % heading
    return (file_text, full_heading), None


def probes(entries, project_dir):
    """Yields (ok, label) tuples, one per probe -- same convention as
    plugins/cai/scripts/options_lint.py:201's probes(). Only reads files,
    writes nothing, and never lets an exception escape: an unreadable file
    is a FAIL detail, not a crash."""
    incomplete = [e["id"] or "(untitled)" for e in entries
                  if not e["id"]
                  or not all(e["fields"].get(l, "").strip() for l in REQUIRED_FIELDS)]
    yield not incomplete, "entry_fields_complete (%d incomplete%s)" % (
        len(incomplete), ": " + ", ".join(incomplete[:2]) if incomplete else "")

    seen = {}
    dups = []
    for e in entries:
        if not e["id"]:
            continue
        seen[e["id"]] = seen.get(e["id"], 0) + 1
        if seen[e["id"]] == 2:
            dups.append(e["id"])
    yield not dups, "entry_ids_unique (%d duplicate%s)" % (
        len(dups), ": " + ", ".join(dups[:2]) if dups else "")

    resolved = [None] * len(entries)
    broken = []
    for i, e in enumerate(entries):
        eid = e["id"] or "(untitled)"
        cited_value = e["fields"].get("Cited by", "")
        if e["cited"] is None:
            if cited_value.strip():
                broken.append('%s (%s: Cited by is not "<path> § <heading>")' % (eid, cited_value))
            continue
        path, cited_heading = e["cited"]
        result, reason = _resolve_heading(path, cited_heading, project_dir)
        if reason:
            broken.append("%s (%s: %s)" % (eid, path, reason))
            continue
        file_text, full_heading = result
        resolved[i] = (path, file_text, full_heading)
    yield not broken, "cited_by_resolves (%d broken%s)" % (
        len(broken), ": " + ", ".join(broken[:2]) if broken else "")

    drifted = []
    for i, e in enumerate(entries):
        if resolved[i] is None:
            continue
        eid = e["id"] or "(untitled)"
        path, file_text, full_heading = resolved[i]
        section = section_of(file_text, full_heading)
        rule = e["fields"].get("Rule", "")
        if normalise(rule) not in normalise(section):
            restated_paths = ", ".join(r[0] for r in e["restated"]) or "none"
            drifted.append("%s (%s, restated in: %s)" % (eid, path, restated_paths))
    yield not drifted, "rule_quote_in_cited_section (%d drifted%s)" % (
        len(drifted), ": " + ", ".join(drifted[:2]) if drifted else "")

    restated_broken = []
    for e in entries:
        eid = e["id"] or "(untitled)"
        problems = []
        for path, restated_heading, quote in e["restated"]:
            result, reason = _resolve_heading(path, restated_heading, project_dir)
            if reason:
                problems.append("%s: %s" % (path, reason))
                continue
            file_text, full_heading = result
            section = section_of(file_text, full_heading)
            if normalise(quote) not in normalise(section):
                problems.append("%s: quote not in section" % path)
        for raw in e["restated_malformed"]:
            problems.append("%s: does not parse" % raw)
        if problems:
            restated_broken.append("%s (%s)" % (eid, "; ".join(problems)))
    yield not restated_broken, "restated_quote_in_section (%d broken%s)" % (
        len(restated_broken), ": " + ", ".join(restated_broken[:2]) if restated_broken else "")

    shared_mismatched = []
    for e in entries:
        if not e["shared"]:
            continue
        eid = e["id"] or "(untitled)"
        shared_n = normalise(e["shared"])
        missing = []
        if shared_n not in normalise(e["fields"].get("Rule", "")):
            missing.append("Rule")
        for path, _, quote in e["restated"]:
            if shared_n not in normalise(quote):
                missing.append(path)
        if missing:
            shared_mismatched.append("%s (missing from: %s)" % (eid, ", ".join(missing)))
    yield not shared_mismatched, "shared_value_in_every_quote (%d mismatched%s)" % (
        len(shared_mismatched), ": " + ", ".join(shared_mismatched[:2]) if shared_mismatched else "")


class ArgParser(argparse.ArgumentParser):
    # argparse's own error() exits 2, which this script reserves for "at
    # least one probe failed" -- a usage mistake gets 1 instead, same
    # pattern as plugins/cai/scripts/preflight.py's ArgParser.
    def error(self, message):
        self.print_usage(sys.stderr)
        print("%s: error: %s" % (self.prog, message), file=sys.stderr)
        sys.exit(1)


def main():
    # FAIL lines quote the ledger's own rule sentences, which contain
    # Chinese punctuation and em dashes; a piped Windows stdout defaults to
    # the ANSI codepage. Same reasoning as
    # plugins/cai/scripts/options_lint.py:186-187.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = ArgParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger")
    ap.add_argument("--project-dir", default=".")
    args = ap.parse_args()

    path = args.ledger if args.ledger else preflight.resolve(LEDGER_REL, args.project_dir)
    if path is None or not os.path.isfile(path):
        return 0  # feature not in use: no ledger at the conventional path

    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return 0

    the_entries = entries(text)
    if not the_entries:
        return 0  # feature not in use: a ledger with no entries yet

    failed = 0
    structural = False
    drifted = False
    for ok, label in probes(the_entries, args.project_dir):
        print(("PASS " if ok else "FAIL ") + label)
        if not ok:
            failed += 1
            if label.split(" (", 1)[0] in DRIFT_LABELS:
                drifted = True
            else:
                structural = True

    hints = []
    if structural:
        hints.append("add or complete an entry as `## <id> — <title>` with "
                      "`- Date:`, `- Failure:`, `- Rule:`, `- Cited by:` "
                      "fields, one line each")
    if drifted:
        hints.append("re-confirm the claim before touching any string, "
                      "then update the drifted citation or restatement to "
                      "match")
    hint = " -- " + "; ".join(hints) if hints else ""
    print("-- provenance: %d probe(s) failed%s" % (failed, hint))
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
