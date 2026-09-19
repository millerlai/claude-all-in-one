<!--
  cai stance template, filled in by $design in stance mode.

  This is the short one. It exists to be read in full by a person in one
  sitting, so every heading below has a ceiling as well as a floor.
  `design_probe.py --kind stance <this file>` fails if a heading is missing,
  still empty, or over its ceiling.

  A stance is not a feature list. It is the trade this system makes: what it
  optimises for, and what it gives up to get that. Two systems with the same
  feature list and different stances share no architecture at all.

  Guidance lives in HTML comments and does not count as content. Delete each
  comment as you answer it.
-->

# <topic> — stance

## Status

<!--
  `draft` until the person says otherwise, then `approved YYYY-MM-DD` taken
  from `date +%F`. Decisions mode reads this line and refuses to start on a
  draft, so a status you set yourself is a gate you opened yourself.
-->

draft

## Optimises for

<!--
  One or two sentences. What this design exists to make better, stated so that
  someone could tell whether it succeeded.

  Not "make it faster and cleaner and more maintainable" -- a stance that
  optimises for everything rules out nothing, and a stance that rules out
  nothing cannot delete a single option later.
-->

## Sacrifices

<!--
  What you are knowingly giving up. One bullet each, 2-6 of them.

  This is the heading people skip and the one that decides whether the design
  survives contact with the next person. Without it, whoever reads this in six
  months will "fix" the slowness, the missing view, the extra click -- not
  knowing it was bought deliberately.

  Each bullet says what is lost, not why it is acceptable. The why lives in
  the decision that traded it away.
-->

- …

## Invariants

<!--
  Conditions no later change may violate. These are the only lines in this
  document a machine reads twice: the conflict test in decisions mode checks
  every option against them, and an option that violates one is deleted rather
  than weighed.

  Two lists, and they are not interchangeable:

  - **This system's** -- derived from the trade above. Violating one sends you
    back here to re-open the stance; you are allowed to change your mind.
  - **Cross-project** -- true of every project you run, unchanged by this
    request (the rules file you keep, the platform's limits, what your test
    environment can actually observe). Violating one is not a re-open: that
    road is closed, find another. Reference them, do not restate them.

  An empty invariant list means the conflict test has nothing to check. That
  is not a shortcut -- it is the gate switched off.
-->

**This system's:**

- …

**Cross-project:**

- …

## Rejected stances

<!--
  The other trades you could have made, and why you are not making them.
  At least one. "There was no alternative" is almost never true and is what
  someone writes when they never looked.

  Each entry: the alternative trade in one sentence, then the reason it lost
  -- in terms of the optimise/sacrifice pair above, not in terms of effort.
-->

- …

## Use cases / Issues

<!--
  Numbered UC1, UC2, R1 … `R` is a defect this change removes; `UC` is a flow
  that must still work afterwards. The build spec has to reach every id here
  and the probe checks that it does.

  Each entry says what problem, for whom, and how anyone would know it worked.
  A use case with no way to tell whether it succeeded is a wish.
-->

- UC1 — …
- R1 — …

## Overview

<!--
  One Mermaid diagram, and it is required: a person reads a picture of the
  shape faster than three paragraphs describing it, and this document's whole
  purpose is being read.

  Draw the shape the stance implies -- the main flow, or before/after if this
  changes something that already exists. Not the component graph; that belongs
  to the build spec, which is allowed to be long.

  Per `documentation.md`: elk renderer, labels in double quotes, `classDef`
  colouring wherever something changes (added green, modified amber, existing
  grey). Render it with `mmdc` before shipping -- never write "validated" for
  a diagram you did not render.
-->

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart TD
```

## Out of scope

<!--
  What this deliberately does not do, and anything deferred. Saying it here is
  what stops it being re-litigated one decision at a time later.

  A line here that is really a sacrifice belongs above instead: the difference
  is whether anyone loses something they have today.
-->

- …
