<!--
  cai decisions template, filled in by $design in decisions mode.

  This document is a queue, not an essay. Every entry under Tier 1 costs the
  reader a turn, so what reaches it has passed three tests first (see
  `stage-design.md`): the conflict test, the origin test, and the cost test.
  Options that failed the first two never appear as decisions -- they appear
  under `## Ruled out` and `## Requirement gaps`, where they cost a glance
  instead of a turn.

  `design_probe.py --kind decisions <this file>` enforces the counts. Going
  over them is not a document problem to reword around: it means the design
  has not converged, and the fix is upstream.

  Guidance lives in HTML comments and does not count as content. Delete each
  comment as you answer it.
-->

# <topic> — decisions

## Reference

<!--
  The stance document this queue serves, as a path, plus its status line.
  The probe opens it, so the path has to resolve. Decisions mode refuses to
  start unless that document's `## Status` reads `approved <date>`: an open
  stance means these options are being weighed against a trade nobody has
  agreed to yet.
-->

- Stance: `docs/design/<YYYY-MM-DD>-<topic>-stance.md` — status: …

## Feasibility

<!--
  Settled BEFORE any option below was weighed. One row per capability this
  design needs and you have not personally confirmed. Evidence is a file:line
  you opened or a documentation URL you fetched -- never recollection.

  Number every row: options cite these ids, and the probe fails a capability
  that no option cites, and any Tier 2 entry resting on one that is not
  `verified`.

  `infeasible` is a result, not a failure -- it deletes an option before
  someone spends a week inside it. `UNVERIFIED` stays in the finished
  document, where it tells the reader which parts rest on air.

  This table is support material. A person reads the entries below and comes
  here only when an entry cites something they want to check.
-->

| Id | Capability | Verdict | Evidence |
|---|---|---|---|
| C1 | … | verified / UNVERIFIED / infeasible | … |

## Ruled out

<!--
  Options deleted by the conflict test -- each one violates an invariant in
  the stance document, so it was never a choice. One line each: the option,
  and which invariant it hit.

  These are here so that whoever wants to re-open one can see what it would
  cost, and so that Tier 2 is not padded with options nobody may pick. Empty
  is legitimate -- it means no proposed option violated anything.
-->

| Option | Invariant it violates | Evidence |
|---|---|---|

## Requirement gaps

<!--
  Entries the origin test sent back: their failure condition is an assumption
  about user behaviour, not a technical fact. They are not decisions and must
  not be answered here.

  Each row needs one of two exits, and the probe checks the column is filled:

  - a **veto condition** -- the requirement rewritten so it can delete
    options ("the chart must stay visible while a verdict is in flight"),
    plus which options it deletes; or
  - a **verification path** -- who can confirm or refute the assumption, and
    how. An assumption with no way to settle it is a guess, and a guess may
    not be used as grounds.

  The count of rows here is a metric, not a defect. Three or more for three
  rounds running means the requirements stage is what needs fixing, not this
  document.
-->

| # | The behavioural assumption | Veto condition, or verification path | Deletes |
|---|---|---|---|

## Tier 1

<!--
  Decisions a person answers, one at a time. **At most 5.** Over that, stop
  and re-cut: the usual cause is a stance that was never settled (so every
  component re-argues it) or component boundaries that have not converged (so
  one decision split into five).

  Order by dependency: whichever answer changes the *options* available to
  other entries goes first. After each answer, re-run the cost test on what
  remains -- entries routinely drop to Tier 2 or Tier 3 once an earlier answer
  lands. If nothing drops, these decisions are unrelated to each other, which
  is itself worth noticing.

  Each entry carries a diagram. That is not decoration: this is the one place
  a person is asked to hold two designs in their head and compare them, and a
  picture of each does that faster than a table of prose. Small is fine -- the
  two shapes, and what differs.

  `Found out when` is the field that makes a fast read possible: an entry that
  a test would catch tomorrow reads differently from one that surfaces after a
  data migration. Never leave it blank -- unknown counts as late.
-->

### D1 — <the question, ending in a question mark>

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart LR
```

| Option | Rests on | What it costs | Fails when |
|---|---|---|---|
| A — … | C1 | … | … |
| B — … | C2 | … | … |

- **Blast radius:** …
- **Found out when:** …
- **Undo cost:** …
- **Decided:** … — … (who, YYYY-MM-DD)

## Tier 2

<!--
  Cost is high, but the evidence leaves one live option. The person scans
  these; they answer nothing unless they want to overturn something.
  **At most 10, three lines each.**

  The bar for arriving here is a citation, not a preference. If the grounds
  are not a `file:line` or a documentation URL, this entry does not qualify --
  either go and get the evidence, or move it to Tier 1 and let a person
  decide. On a solo project nothing catches what is waved through here.
-->

### D… — <the question>?

Chose …, because <evidence> rules out the rest. **Found out when:** …

## Tier 3

<!--
  Cost is low on all three counts -- one component, caught by the next test
  run, cheap to undo. Recorded so that it is searchable in six months,
  never shown for review. One row each, no options table.

  A row here still names what would have been the alternative: "no
  alternative" is how a decision hides.
-->

| Decision | Chose | Instead of | Found out when |
|---|---|---|---|
