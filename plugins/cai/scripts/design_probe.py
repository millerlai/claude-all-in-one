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

Usage:  design_probe.py --kind hld|detail|delta [--project-dir DIR] <document>
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
# A delta document is written after the change, so its commonest evidence is a
# commit -- which CITE cannot match. The hex run also matches an all-hex English
# word ("defaced"), letting an uncited row through. That is the direction this
# file already prefers: a false reject makes a correct document unpassable,
# which costs more than a miss.
DELTA_CITE = re.compile(r"[\w./\\-]+\.\w+:\d+|https?://|\b[0-9a-f]{7,40}\b")
# `<ref>..HEAD`, `<ref>...HEAD`, or a bare sha.
RANGE = re.compile(r"\.{2,3}HEAD|\b[0-9a-f]{7,40}\b")
# GFM accepts a single dash per cell, so `|-|-|` is a legal separator row.
SEP_CELL = re.compile(r":?-+:?")
COMMENT = re.compile(r"<!--.*?-->", re.S)
FENCE = re.compile(r"^\s*```mermaid", re.M)
STATUS = re.compile(r"^(draft|approved\s+\d{4}-\d{2}-\d{2})", re.I | re.M)
# The field that decides how fast an entry can be read: an entry a test catches
# tomorrow is scanned, one that surfaces after a migration is not. The label
# stays English in every language's document, the same way `## Status` reads
# `draft` whatever the prose around it is -- these are the strings a machine
# reads back, and the templates say so where the author will see it.
FOUND_OUT = re.compile(r"found out when", re.I)
BULLET = ("- ", "* ", "|")

HLD_HEADINGS = ["Status", "Use cases / Issues", "Feasibility",
                "High-level design", "Architecture decisions",
                "Open questions", "Out of scope"]
DETAIL_HEADINGS = ["Reference", "Requirement", "Glossary", "Budgets",
                   "Design decisions", "Diagrams", "Implementation spec",
                   "Naming", "Change points", "Failure modes", "Rollout",
                   "Verification", "Work breakdown"]
# A delta document is written after the fact, so it carries neither a status
# gate nor weighed options -- both are settled by the time it exists. What it
# must carry instead is the range it describes: six months on, that is the one
# thing no amount of rereading the prose recovers.
DELTA_HEADINGS = ["Scope", "Problem", "Before / After", "Decisions",
                  "Impact", "Limits"]
# A stance is read start to finish by a person in one sitting, so its headings
# are the four halves of a trade plus what the trade is for. Splitting the
# trade across four `##` rather than one is deliberate: a missing Sacrifices
# section is then a probe failure rather than a paragraph nobody wrote.
STANCE_HEADINGS = ["Status", "Optimises for", "Sacrifices", "Invariants",
                   "Rejected stances", "Use cases / Issues", "Overview",
                   "Out of scope"]
# The decisions queue. `Ruled out` and `Requirement gaps` come before the tiers
# because what they hold was removed from the queue, and a reader who does not
# know that reads the tiers wondering where an option went.
DECISIONS_HEADINGS = ["Reference", "Feasibility", "Ruled out",
                      "Requirement gaps", "Tier 1", "Tier 2", "Tier 3"]

# Two headings are legitimately short or legitimately empty, and a length rule
# over them makes a correct document unpassable. `## Status` says exactly
# `draft` (5 characters) or `approved 2026-08-25` (19, one short of the
# threshold), and `## Open questions` is empty precisely when everything has
# been answered -- the state the detail design is gated on. Status gets a format
# check instead, which is worth more than a length one because the gate reads it.
SHORT_OK = {"Status"}
# Five of these are empty exactly when things went well, and a length rule over
# them makes a correct document unpassable. `Ruled out` is empty when no option
# violated an invariant; `Requirement gaps` when none rested on a guess about
# user behaviour; and any one tier is empty when every decision landed in the
# others. `Tier 1` empty is the best outcome this design has -- nothing needed
# a person at all.
MAY_BE_EMPTY = {"Open questions", "Ruled out", "Requirement gaps",
                "Tier 1", "Tier 2", "Tier 3"}

# The review budget, in entries per round. Over it, the document is not too
# long -- the design has not converged, and the fix is upstream (a stance that
# was never settled, or boundaries that split one decision into five). These
# are starting values to be calibrated against the one question that settles
# them: did the person actually read it. `stage-design.md` says how.
TIER1_MAX = 5
TIER2_MAX = 10
# What a person reads in one sitting, in lines, ignoring HTML comments, blank
# lines and diagrams. Diagrams are excluded on purpose: a picture is what makes
# the rest readable, so charging the budget for one would push authors to drop
# the cheapest thing that helps.
STANCE_MAX_LINES = 80

# The templates are the shape the design commands write to, so they are the
# source of truth for the lists above. validate.py asserts the two agree.
TEMPLATES = {"hld": "design-high-level.md.tpl", "detail": "design-detail.md.tpl",
             "delta": "design-delta.md.tpl",
             "stance": "design-stance.md.tpl",
             "decisions": "design-decisions.md.tpl"}


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


def entries(body):
    """(title, block) per `### ` heading in a section body. A tier is counted
    by its entries, not by its length: three lines or thirty, one decision
    costs the reader one decision."""
    out, title, buf = [], None, []
    for line in COMMENT.sub("", body).splitlines():
        m = re.match(r"^###\s+(\S.*?)\s*$", line)
        if m:
            if title is not None:
                out.append((title, "\n".join(buf)))
            title, buf = m.group(1), []
        elif title is not None:
            buf.append(line)
    if title is not None:
        out.append((title, "\n".join(buf)))
    return out


def prose_lines(text):
    """Lines a person actually reads. Comments are guidance, blanks are
    spacing, and fenced blocks are diagrams -- charging the budget for a
    diagram would push the author to drop the cheapest thing that helps."""
    body = COMMENT.sub("", text)
    body = re.sub(r"^```.*?^```", "", body, flags=re.S | re.M)
    return [ln for ln in body.splitlines() if ln.strip()]


def feasibility_checks(secs):
    """The three shape checks a feasibility table gets, and the verdict behind
    each capability id. Two kinds carry the table and both need the same
    answers, so the labels live here rather than being written twice and
    drifting."""
    feas = items(secs.get("Feasibility", ""))
    no_id = [r for r in feas if not CAP_ID.search(r)]
    no_ev = [r for r in feas if not CITE.search(r)]
    checks = [
        (bool(feas), "feasibility_has_rows (%d)" % len(feas)),
        (bool(feas) and not no_id,
         "feasibility_ids (%d row(s) carry no C<n>)" % len(no_id)),
        (bool(feas) and not no_ev,
         "feasibility_evidence (%d row(s) cite no file:line or URL)" % len(no_ev)),
    ]
    verdicts = {}
    for row in feas:
        for cid in CAP_ID.findall(row):
            verdicts[cid] = verdict_of(row)
    return checks, verdicts


def hld_probes(secs, text, roots):
    yield probe_headings(secs, HLD_HEADINGS)

    # The detail command's gate reads this line, so its shape is load-bearing.
    ok = bool(STATUS.search(COMMENT.sub("", secs.get("Status", ""))))
    yield ok, "status_is_well_formed (%s)" % (
        "draft or approved <date>" if ok else
        "must read `draft` or `approved YYYY-MM-DD`")

    checks, verdicts = feasibility_checks(secs)
    for check in checks:
        yield check

    # A high-level design is the shape this stage wrote before stance and
    # decisions modes existed, and it is still accepted so that documents
    # already signed off stay passable. What it may not do is grow into the
    # build spec: these headings belong to that document, and a high-level
    # design carrying them has stopped being the short one.
    leaked = [h for h in DETAIL_HEADINGS if h in secs]
    yield not leaked, "no_detail_headings (%s)" % (
        ", ".join(leaked[:4]) if leaked else "none of the build spec's headings")

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


def stance_probes(secs, text, roots):
    yield probe_headings(secs, STANCE_HEADINGS)

    # Decisions mode reads this line and refuses to start on a draft, so its
    # shape is load-bearing rather than cosmetic.
    ok = bool(STATUS.search(COMMENT.sub("", secs.get("Status", ""))))
    yield ok, "status_is_well_formed (%s)" % (
        "draft or approved <date>" if ok else
        "must read `draft` or `approved YYYY-MM-DD`")

    # Three lists that a document can carry as a heading and still not answer.
    # Invariants is the one with teeth: the conflict test checks every option
    # against it, so an empty list is not a short section, it is the gate
    # switched off. Sacrifices is the one people skip, and without it the next
    # reader "fixes" what was given up on purpose.
    for head, label in (("Sacrifices", "sacrifices_listed"),
                        ("Invariants", "invariants_listed"),
                        ("Rejected stances", "rejected_stances_listed")):
        rows = [r for r in items(secs.get(head, ""))
                if len(r) >= 20 and not PLACEHOLDER.match(r)]
        yield bool(rows), "%s (%d)" % (label, len(rows))

    ids = UC_ID.findall(COMMENT.sub("", secs.get("Use cases / Issues", "")))
    yield bool(ids), "use_cases_numbered (%d UC/R id(s))" % len(ids)

    # Required, not encouraged. This document's whole purpose is being read in
    # full, and a reader takes the shape off a picture faster than off three
    # paragraphs describing the same thing.
    count = len(FENCE.findall(text))
    yield count >= 1, "diagram_present (%d mermaid block(s), need 1)" % count

    n = len(prose_lines(text))
    yield n <= STANCE_MAX_LINES, \
        "within_one_page (%d line(s), ceiling %d)" % (n, STANCE_MAX_LINES)


def decisions_probes(secs, text, roots):
    yield probe_headings(secs, DECISIONS_HEADINGS)

    ref = None
    for cand in re.findall(r"[\w./\\-]+\.md",
                           COMMENT.sub("", secs.get("Reference", ""))):
        # A sibling of this document is the likely shape, so look there first.
        ref = resolve(cand, *reversed(roots))
        if ref:
            break
    yield ref is not None, "reference_resolves (%s)" % (
        ref or "## Reference names no readable .md")

    if ref:
        with open(ref, encoding="utf-8") as fh:
            status = COMMENT.sub("", sections(fh.read()).get("Status", ""))
        ok = bool(re.search(r"^approved\s+\d{4}-\d{2}-\d{2}", status.strip(),
                            re.I | re.M))
        # Weighing options against a trade nobody has agreed to is how a
        # stance gets decided one implementation detail at a time.
        yield ok, "stance_is_approved (%s)" % (
            "approved" if ok else "the stance it serves is still draft")

    checks, verdicts = feasibility_checks(secs)
    for check in checks:
        yield check

    t1, t2 = entries(secs.get("Tier 1", "")), entries(secs.get("Tier 2", ""))

    # Over budget is not a formatting problem. It says the design has not
    # converged -- usually a stance that was never settled, so every entry
    # re-argues it, or boundaries that split one decision into five.
    yield len(t1) <= TIER1_MAX, \
        "tier1_within_budget (%d, ceiling %d)" % (len(t1), TIER1_MAX)
    yield len(t2) <= TIER2_MAX, \
        "tier2_within_budget (%d, ceiling %d)" % (len(t2), TIER2_MAX)

    undrawn = [t[:28] for t, b in t1 if not FENCE.search(b)]
    yield not undrawn, "tier1_entries_drawn (%s)" % (
        ", ".join(undrawn[:3]) if undrawn else "every entry carries a diagram")

    nowhen = [t[:28] for t, b in t1 + t2 if not FOUND_OUT.search(b)]
    yield not nowhen, "states_when_found_out (%s)" % (
        ", ".join(nowhen[:3]) if nowhen else "every entry says when it surfaces")

    # The bar for reaching Tier 2 is a citation, not a preference: nobody
    # reviews what is scanned, so "this one looked better" arrives unopposed.
    nocite = [t[:28] for t, b in t2 if not CITE.search(b)]
    yield not nocite, "tier2_entries_cite (%s)" % (
        ", ".join(nocite[:3]) if nocite else "every entry cites its grounds")

    resting = []
    for _, block in t2:
        for cid in CAP_ID.findall(block):
            if verdicts.get(cid, "unstated") != "verified":
                resting.append("%s=%s" % (cid, verdicts.get(cid, "unstated")))
    yield not resting, "tier2_rests_on_verified (%s)" % (
        ", ".join(resting[:5]) or "none rests on an unverified capability")

    gaps = items(secs.get("Requirement gaps", ""))
    noexit = []
    for row in gaps:
        cells = [c.strip() for c in row.split("|")]
        if len(cells) < 3 or not cells[2]:
            noexit.append(cells[0][:20] if cells else row[:20])
    yield not noexit, \
        "gaps_have_an_exit (%d row(s) name neither a veto condition nor a " \
        "verification path)" % len(noexit)

    # Reported, never failed. One round with three gaps is a design doing its
    # job; three rounds running is the requirements stage asking to be fixed,
    # and only a number kept across rounds can say which this is.
    yield True, "requirement_gaps (%d this round)" % len(gaps)

    cited = set()
    for head in ("Ruled out", "Tier 1", "Tier 2", "Tier 3"):
        cited |= set(CAP_ID.findall(COMMENT.sub("", secs.get(head, ""))))
    orphan = sorted(set(verdicts) - cited)
    yield not orphan, "pairs_covered (%d capability id(s) no entry cites%s)" % (
        len(orphan), (": " + ", ".join(orphan[:5])) if orphan else "")


def citation_problem(row, roots):
    """Why one glossary row's `Where it lives` cell does not reach a real line,
    or None when it does."""
    cells = [c.strip() for c in row.split("|")]
    term, where = cells[0][:24], cells[-1]
    # "new" is a file this design creates; "concept" is a term that is not a
    # thing in the code at all. Neither can carry a line number, and forcing
    # one would only teach the author to invent a path.
    if where.lower().startswith(("new", "concept", "`new", "`concept")):
        return None
    m = re.search(r"([\w./\\-]+):(\d+)", where)
    if not m:
        return "%s: no file:line and not marked new" % term
    src = resolve(m.group(1), *roots)
    if src is None:
        return "%s: %s does not exist" % (term, m.group(1))
    with open(src, encoding="utf-8", errors="replace") as fh:
        have = sum(1 for _ in fh)
    if have < int(m.group(2)):
        return "%s: %s has %d line(s)" % (term, m.group(1), have)
    return None


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
    bad = [p for p in (citation_problem(row, roots) for row in glo) if p]
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


def delta_probes(secs, text, roots):
    yield probe_headings(secs, DELTA_HEADINGS)

    # The one fact a delta document cannot be reconstructed without. Prose
    # describing "the new exporter" is worthless once three more land on top.
    scope = COMMENT.sub("", secs.get("Scope", ""))
    ok = bool(RANGE.search(scope))
    yield ok, "scope_names_a_range (%s)" % (
        "found" if ok else "## Scope names no <ref>..HEAD and no commit sha")

    # Before and after. One diagram is a picture of the end state, which is the
    # thing the reader can already get by reading the code.
    count = len(FENCE.findall(text))
    yield count >= 2, "before_after_diagrams (%d mermaid block(s), need 2)" % count

    dec = items(secs.get("Decisions", ""))
    yield bool(dec), "decisions_have_rows (%d)" % len(dec)

    # This command never stops to ask, so a decision whose reason it could not
    # source has to say so. Otherwise silence and evidence read the same to
    # whoever opens this next, and the unsourced half is invisible.
    bare = [r for r in dec
            if not DELTA_CITE.search(r) and "unverified" not in r.lower()]
    yield bool(dec) and not bare, \
        "decisions_evidence (%d row(s) cite nothing and are not UNVERIFIED)" % len(bare)

    imp = items(secs.get("Impact", ""))
    yield bool(imp), "impact_has_rows (%d)" % len(imp)


PROBES = {"stance": stance_probes, "decisions": decisions_probes,
          "hld": hld_probes, "detail": detail_probes, "delta": delta_probes}


def main():
    # The documents are written in the user's own language and the probe quotes
    # them back. A console codepage that cannot encode a quoted character would
    # otherwise replace the report with a traceback.
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:  # Python < 3.7
        pass

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kind", choices=tuple(PROBES), required=True)
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

    run = PROBES[args.kind]
    failed = 0
    for ok, label in run(sections(text), text, roots):
        print(("PASS " if ok else "FAIL ") + label)
        failed += not ok
    print("-- %s: %d probe(s) failed" % (args.kind, failed))
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
