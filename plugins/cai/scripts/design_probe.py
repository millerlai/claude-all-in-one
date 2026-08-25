#!/usr/bin/env python3
"""Deterministic probes for the documents the two design commands produce.
Zero deps.

Those commands state absolutes -- every capability carries evidence, every use
case reaches a component, every glossary term points at a line that exists.
GUIDE.md's diagnostic says a rule enforced only by the model remembering is in
the wrong component: demote it, or promote it to a mechanism. This is the
mechanism. It answers only questions that have one answer, and it costs no
tokens.

The definitions of "filled" and "item" come from the SDD design note under
docs/, so that a probe two people run returns the same number.

Usage:  design_probe.py --kind hld|detail [--project-dir DIR] <document>
Exit:   0 every probe passed, 2 at least one failed.
"""
import argparse
import os
import re
import sys

PLACEHOLDER = re.compile(r"^(TBD|TODO|N/?A|\?+|-{1,3})\.?$", re.I)
CAP_ID = re.compile(r"\bC\d+\b")
UC_ID = re.compile(r"\b(?:UC|R)\d+\b")
CITE = re.compile(r"[\w./\\-]+\.\w+:\d+|https?://")
# GFM accepts a single dash per cell, so `|-|-|` is a legal separator row.
SEP_CELL = re.compile(r":?-+:?")
COMMENT = re.compile(r"<!--.*?-->", re.S)
FENCE = re.compile(r"^\s*```mermaid", re.M)
STATUS = re.compile(r"^(draft|approved\s+\d{4}-\d{2}-\d{2})", re.I | re.M)
BULLET = ("- ", "* ", "|")

HLD_HEADINGS = ["Status", "Use cases / Issues", "Feasibility",
                "High-level design", "Architecture decisions",
                "Open questions", "Out of scope"]
DETAIL_HEADINGS = ["Reference", "Requirement", "Glossary", "Budgets",
                   "Design decisions", "Diagrams", "Implementation spec",
                   "Naming", "Change points", "Failure modes", "Rollout",
                   "Verification", "Work breakdown"]

# Two headings are legitimately short or legitimately empty, and a length rule
# over them makes a correct document unpassable. `## Status` says exactly
# `draft` (5 characters) or `approved 2026-08-25` (19, one short of the
# threshold), and `## Open questions` is empty precisely when everything has
# been answered -- the state the detail design is gated on. Status gets a format
# check instead, which is worth more than a length one because the gate reads it.
SHORT_OK = {"Status"}
MAY_BE_EMPTY = {"Open questions"}

# The templates are the shape both commands write to, so they are the source of
# truth for the lists above. validate.py asserts the two agree.
TEMPLATES = {"hld": "design-high-level.md.tpl", "detail": "design-detail.md.tpl"}


def sections(text):
    """Map each '## ' heading to its body. A '###' line stays in the body."""
    out, cur, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^##\s+(\S.*?)\s*$", line)
        if m:
            if cur is not None:
                out[cur] = "\n".join(buf)
            cur, buf = m.group(1), []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf)
    return out


def _is_separator(s):
    cells = [c.strip() for c in s.strip("|").split("|")]
    return bool(cells) and all(SEP_CELL.fullmatch(c) for c in cells if c)


def items(body):
    """List items and table data rows -- so a section cannot be inflated with
    prose, and neither a table header nor a bullet inside the template's
    guidance is counted as content."""
    lines = [ln.strip() for ln in COMMENT.sub("", body).splitlines()]
    out = []
    for i, s in enumerate(lines):
        if s.startswith(("- ", "* ")):
            out.append(s[2:].strip())
        elif s.startswith("|") and s.endswith("|") and not _is_separator(s):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if nxt.startswith("|") and _is_separator(nxt):
                continue
            out.append(s.strip("|").strip())
    return out


def blocks(body):
    """One chunk per bullet or table row, continuation lines included. An option
    written across two lines keeps its `(recommended)` marker and the C<n> it
    rests on in the same chunk, which scanning line by line does not."""
    out, cur = [], []
    for line in COMMENT.sub("", body).splitlines():
        s = line.strip()
        if s.startswith(BULLET):
            if cur:
                out.append("\n".join(cur))
            cur = [s]
        elif cur:
            if not s:
                out.append("\n".join(cur))
                cur = []
            else:
                cur.append(s)
    if cur:
        out.append("\n".join(cur))
    return out


def resolve(rel, *bases):
    """A citation is written relative to wherever its author was standing.
    Try each base in the order the caller says is likeliest."""
    for base in bases:
        p = os.path.normpath(os.path.join(base or ".", rel))
        if os.path.isfile(p):
            return p
    return None


def filled(body, short_ok=False):
    # The templates carry their guidance as HTML comments. Counting those as
    # content would let an untouched template pass every heading check, which
    # is the one document that must not pass.
    for line in COMMENT.sub("", body).splitlines():
        s = line.strip()
        if s and not PLACEHOLDER.match(s) and (short_ok or len(s) >= 20):
            return True
    return False


def probe_headings(secs, required):
    missing = [h for h in required if h not in secs]
    empty = [h for h in required if h in secs and h not in MAY_BE_EMPTY
             and not filled(secs[h], short_ok=h in SHORT_OK)]
    note = []
    if missing:
        note.append("missing " + ", ".join(missing))
    if empty:
        note.append("empty " + ", ".join(empty))
    return not note, "headings_complete (%s)" % ("; ".join(note) or "all present")


def verdict_of(row):
    low = row.lower()
    if "unverified" in low:
        return "unverified"
    if "infeasible" in low:
        return "infeasible"
    if "verified" in low:
        return "verified"
    return "unstated"


def hld_probes(secs, text, roots):
    yield probe_headings(secs, HLD_HEADINGS)

    # The detail command's gate reads this line, so its shape is load-bearing.
    ok = bool(STATUS.search(COMMENT.sub("", secs.get("Status", ""))))
    yield ok, "status_is_well_formed (%s)" % (
        "draft or approved <date>" if ok else
        "must read `draft` or `approved YYYY-MM-DD`")

    feas = items(secs.get("Feasibility", ""))
    yield bool(feas), "feasibility_has_rows (%d)" % len(feas)

    no_id = [r for r in feas if not CAP_ID.search(r)]
    yield bool(feas) and not no_id, \
        "feasibility_ids (%d row(s) carry no C<n>)" % len(no_id)

    no_ev = [r for r in feas if not CITE.search(r)]
    yield bool(feas) and not no_ev, \
        "feasibility_evidence (%d row(s) cite no file:line or URL)" % len(no_ev)

    verdicts = {}
    for row in feas:
        for cid in CAP_ID.findall(row):
            verdicts[cid] = verdict_of(row)

    arch = COMMENT.sub("", secs.get("Architecture decisions", ""))
    orphan = sorted(set(verdicts) - set(CAP_ID.findall(arch)))
    yield not orphan, "pairs_covered (%d capability id(s) no option cites%s)" % (
        len(orphan), (": " + ", ".join(orphan[:5])) if orphan else "")

    resting = []
    for block in blocks(secs.get("Architecture decisions", "")):
        if "recommend" not in block.lower():
            continue
        for cid in CAP_ID.findall(block):
            if verdicts.get(cid, "unstated") != "verified":
                resting.append("%s=%s" % (cid, verdicts.get(cid, "unstated")))
    yield not resting, "recommendation_is_verified (%s)" % (
        ", ".join(resting[:5]) or "none rests on an unverified capability")


def detail_probes(secs, text, roots):
    yield probe_headings(secs, DETAIL_HEADINGS)

    hld = None
    for cand in re.findall(r"[\w./\\-]+\.md", COMMENT.sub("", secs.get("Reference", ""))):
        # A sibling of this document is the likely shape, so look there first.
        hld = resolve(cand, *reversed(roots))
        if hld:
            break
    yield hld is not None, "reference_resolves (%s)" % (
        hld or "## Reference names no readable .md")

    if hld:
        with open(hld, encoding="utf-8") as fh:
            hsecs = sections(fh.read())
        want = set(UC_ID.findall(hsecs.get("Use cases / Issues", "")))
        missing = sorted(want - set(UC_ID.findall(text)))
        if not want:
            note, ok = "the high-level design numbers no use cases", False
        elif missing:
            note, ok = "%d unreferenced: %s" % (
                len(missing), ", ".join(missing[:5])), False
        else:
            note, ok = "all %d use case(s) reached" % len(want), True
        yield ok, "traceability (%s)" % note

    glo = items(secs.get("Glossary", ""))
    bad = []
    for row in glo:
        cells = [c.strip() for c in row.split("|")]
        term, where = cells[0][:24], cells[-1]
        # "new" is a file this design creates; "concept" is a term that is not a
        # thing in the code at all. Neither can carry a line number, and forcing
        # one would only teach the author to invent a path.
        if where.lower().startswith(("new", "concept", "`new", "`concept")):
            continue
        m = re.search(r"([\w./\\-]+):(\d+)", where)
        src = resolve(m.group(1), *roots) if m else None
        if not m:
            bad.append("%s: no file:line and not marked new" % term)
        elif src is None:
            bad.append("%s: %s does not exist" % (term, m.group(1)))
        else:
            with open(src, encoding="utf-8", errors="replace") as fh:
                have = sum(1 for _ in fh)
            if have < int(m.group(2)):
                bad.append("%s: %s has %d line(s)" % (term, m.group(1), have))
    yield bool(glo) and not bad, "glossary_citations (%s)" % (
        "; ".join(bad[:3]) if bad else
        "%d row(s) resolve" % len(glo) if glo else "no rows at all")

    # Only the number column counts. Checking the whole row would let a row
    # whose sole digit is the date in its provenance pass while its budget
    # still reads "as many as we get".
    budgets = items(secs.get("Budgets", ""))
    wordy = []
    for row in budgets:
        cells = [c.strip() for c in row.split("|")]
        stated = cells[1] if len(cells) > 1 else row
        if not re.search(r"\d", stated):
            wordy.append("%s -> %s" % (cells[0][:20], stated[:20]))
    yield bool(budgets) and not wordy, "budgets_are_numeric (%s)" % (
        "; ".join(wordy[:3]) if wordy else
        "%d row(s) state a number" % len(budgets) if budgets else "no rows at all")

    count = len(FENCE.findall(text))
    yield count >= 4, "diagrams_present (%d mermaid block(s), need 4)" % count

    # Four flowcharts would satisfy the count. A sequence per use case was
    # asked for, and only this says whether one was actually drawn.
    seq = "sequencediagram" in text.lower()
    yield seq, "sequence_diagram_present (%s)" % (
        "found" if seq else "four diagrams but none is a sequenceDiagram")


def main():
    # The documents are written in the user's own language and the probe quotes
    # them back. A console codepage that cannot encode a quoted character would
    # otherwise replace the report with a traceback.
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:  # Python < 3.7
        pass

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kind", choices=("hld", "detail"), required=True)
    ap.add_argument("--project-dir", default=".",
                    help="root the document's file:line citations are relative "
                         "to; pass it when designing against another repo")
    ap.add_argument("document")
    args = ap.parse_args()

    if not os.path.isfile(args.document):
        print("FAIL document not found:", args.document)
        return 2
    with open(args.document, encoding="utf-8") as fh:
        text = fh.read()

    # Citations are repo-root relative, so the project root leads; a path beside
    # the document is the fallback. reference_resolves reverses this, because a
    # sibling .md is the likely shape there.
    roots = (args.project_dir, os.path.dirname(args.document) or ".")

    run = hld_probes if args.kind == "hld" else detail_probes
    failed = 0
    for ok, label in run(sections(text), text, roots):
        print(("PASS " if ok else "FAIL ") + label)
        failed += not ok
    print("-- %s: %d probe(s) failed" % (args.kind, failed))
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
