<!--
  cai high-level design template, filled in by /cai:design in high-level mode.

  Every heading below is required. `design_probe.py --kind hld <this file>`
  fails if one is missing or still empty, so this template does not pass its
  own probe until it has been filled in — which is the point.

  Guidance lives in HTML comments and does not count as content. Delete each
  comment as you answer it.
-->

# <topic> — high-level design

## Status

<!--
  `draft` until the user says otherwise, then `approved YYYY-MM-DD` taken from
  `date +%F`. /cai:design in detail mode reads this line and refuses
  to start on a draft, so a status you set yourself is a gate you opened
  yourself.
-->

draft

## Use cases / Issues

<!--
  Numbered UC1, UC2, R1 … The detail design has to reach every id here, and
  the probe checks that it does. Each entry says what problem, for whom, and
  how anyone would know it worked — a use case with no way to tell whether it
  succeeded is a wish.
-->

- UC1 — …
- UC2 — …

## Feasibility

<!--
  Settled BEFORE any option below was weighed. One row per capability this
  design needs and you have not personally confirmed. Evidence is a file:line
  you opened or a documentation URL you fetched — never recollection. Number
  every row: Architecture decisions must cite these ids, and the probe fails a
  capability that no option cites.

  infeasible is a result, not a failure — it deletes an option before someone
  spends a week inside it. UNVERIFIED stays in the finished document, where it
  tells the reviewer which parts of this design rest on air.
-->

| Id | Capability | Verdict | Evidence |
|---|---|---|---|
| C1 | … | verified / UNVERIFIED / infeasible | … |

## High-level design

<!--
  The main flow and the components, as two Mermaid diagrams: elk renderer,
  labels in double quotes, classDef colouring wherever something changes.
  Render with `mmdc` before shipping — never write "validated" for a diagram
  you did not render.

  No signatures, no schemas, no file paths for code that does not exist yet.
  Those belong to the detail design, and settling them here in prose is what
  the two-document split exists to prevent.
-->

## Architecture decisions

<!--
  At least two real options per choice. Each option names:
    - the C<n> ids from Feasibility that it rests on;
    - what it costs — what changes, what it constrains later, what it rules out;
    - how it fails — the situation in which this is the wrong choice.

  At most one option marked (recommended), and only when every capability it
  cites is `verified`. The probe enforces that: recommending something built on
  UNVERIFIED is how an unchecked assumption quietly becomes the architecture.

  The choice itself goes to the user, one decision at a time, biggest blast
  radius first. Do not pick first and justify afterwards.
-->

### Decision 1 — …

| Option | Rests on | Costs | Fails when |
|---|---|---|---|
| A … | C1 | … | … |
| B … | C2 | … | … |

**Chosen:** … — because …

## Open questions

<!--
  What the user still has to decide. /cai:design in detail mode
  refuses to start unless this is empty or every entry carries the answer it
  got, so leaving something here is a real stop, not a note.
-->

## Out of scope

<!--
  What this deliberately does not do, and anything deferred to a later version.
  Saying it here is what stops it being re-litigated in the detail design.
-->
