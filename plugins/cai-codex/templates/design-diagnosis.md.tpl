<!--
  cai diagnosis template, filled in by $design in diagnosis mode.

  This is the stance's counterpart for something that is broken rather than
  missing. It is short for the same reason: what a person signs here is the
  root cause, and a root cause nobody read is a fix aimed at nothing.

  The entry condition is not "someone called it a bug". It is a test that
  fails right now and would pass if an existing promise held -- a promise
  being an existing test, the documentation, a spec, or an invariant, never
  anyone's expectation. Write that test first. If you cannot, this is not a
  diagnosis: nothing was promised, so nothing is broken, and the work belongs
  in stance mode.

  `design_probe.py --kind diagnosis <this file>` enforces the shape.

  Guidance lives in HTML comments and does not count as content. Delete each
  comment as you answer it.
-->

# <topic> — diagnosis

## Status

<!--
  `draft` until the person says otherwise, then `approved YYYY-MM-DD` from
  `date +%F`. What they are approving is the root cause below, not the fix:
  a wrong root cause makes every fix downstream of it wrong too, and that is
  the one judgement a person can make better than the evidence alone.
-->

draft

## Symptom

<!--
  What is observed, and the exact steps that produce it every time. Not "it
  sometimes fails under load" -- that is a report, not a reproduction, and a
  fix aimed at it is aimed at nothing.

  Not reproducible yet? Stop here and gather more: logs, a smaller case, the
  exact input. An unreproducible bug is a discovery task, not a diagnosis.
-->

## Failing test

<!--
  The test that fails now and would pass if the promise held. Give its path
  and name, and what it prints when it fails.

  This is the entry condition for this whole mode, so it is not optional and
  it is not written afterwards: `stage-build.md`'s test-first discipline
  starts here, and the probe looks for a path.

  Name the promise it tests against, too -- which existing test, which
  documented behaviour, which invariant. "It should obviously work" is an
  expectation, and an expectation that was never written down is a
  requirement, which means this is stance mode's problem, not this one's.
-->

## Root cause

<!--
  One sentence saying why it happens, then the evidence: `file:line` for
  every claim about how the code behaves, a URL plus the sentence relied on
  for a library or platform.

  Then answer the question that separates a cause from a symptom: **what
  would still be true if you fixed the line the stack trace points at?**
  If the answer is "the same thing could happen again through another path",
  you have a symptom and the cause is further up.

  Cannot get there? Write UNVERIFIED and say what evidence would settle it.
  A plausible-sounding cause is worse than a blank, because it ends the
  search.
-->

## Blast radius

<!--
  Who else is affected by this same cause -- other call sites, other inputs,
  other environments. A cause that reaches exactly one place is possible, but
  say so and say why, because it is also what a symptom looks like.

  This section is what turns one fix into the right fix: the second caller
  found here is the one that would otherwise come back as a new ticket in
  three weeks.
-->

## Fix

<!--
  What changes, where, and why that is the cause rather than the symptom.

  Keep it to the cause. No unrelated cleanup riding along -- that is
  `refactor`'s job on a separate pass, and mixing them means nobody can tell
  afterwards which change fixed the bug.

  If the fix needs an architecture-level choice, or two approaches survive
  the evidence, stop: that is the escalation this mode hands to stance mode
  (`stage-design.md`). A diagnosis that has to weigh options is a design
  wearing a diagnosis's clothes.
-->

## Invariants preserved

<!--
  What this fix must not break, and how anyone would know it did not.
  Reference the stance document's invariants when one exists rather than
  restating them.

  A fix that repairs the symptom by violating something the system promised
  elsewhere is not a fix; it is the next ticket.
-->

## Picture

<!--
  One Mermaid diagram, required. Draw the path and mark where it goes wrong
  -- that is what a reader checks the root cause against, and it is faster
  than the same thing in prose.

  Per `documentation.md`: elk renderer, labels in double quotes. Colour the
  faulty node so the claim is visible at a glance. Render it with `mmdc`
  before shipping, and put a sentence under it saying what to look at.
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
  What this deliberately does not fix, including anything the blast radius
  turned up and you are choosing to leave. Saying it here is what stops it
  being discovered again as a surprise.
-->

- …
