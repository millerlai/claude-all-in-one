<!--
  cai single design document template, filled in by /cai:design on the long
  path. One file per track: `docs/design/<YYYY-MM-DD>-<topic>-design.md`.

  It holds, in this order, up to four sections, each written by the mode of
  the same name and edited in place by the next mode, never rewritten:

    ## Diagnosis   optional -- only when a bug escalated into a feature, and
                   the root cause becomes this section
    ## Stance      the trade, read in full by a person
    ## Decisions   the queue of choices that trade implies
    ## Detail      the build spec; it is for the builder, not for sign-off

  Inside a section, every heading is one level deeper than the template of
  the same mode (`design-stance.md.tpl`, `design-decisions.md.tpl`,
  `design-detail.md.tpl`, `design-diagnosis.md.tpl`), whose guidance comments
  apply here unchanged. `design_probe.py --kind design <this file>` promotes
  each section's headings back up one level and runs that mode's own probe on
  it, so a section is checked as the page it would have been alone.

  Only Diagnosis and Stance carry a `### Status`. Decisions is complete when
  every Tier 1 entry has a `Decided:` line. Detail has no status of its own:
  Gate 1 fingerprints the whole file, so an edit to any section after
  sign-off re-opens the gate.

  Write only the sections the current mode owns; delete the HTML comments as
  you answer them, and delete a section you do not need (Diagnosis) outright.
-->

# <topic> — design

## Diagnosis

<!-- Optional. Delete this whole section unless a bug escalated into a feature. -->

### Status

<!--
  `draft` until the person says otherwise, then `approved YYYY-MM-DD` from
  `date +%F`. What they are approving is the root cause below, not the fix:
  a wrong root cause makes every fix downstream of it wrong too, and that is
  the one judgement a person can make better than the evidence alone.
-->

draft

### Symptom

<!--
  What is observed, and the exact steps that produce it every time. Not "it
  sometimes fails under load" -- that is a report, not a reproduction.
-->

### Failing test

<!--
  The test that fails now and would pass if the promise held. Give its path
  and name, and what it prints when it fails. Name the promise it tests
  against: which existing test, which documented behaviour, which invariant.
-->

### Root cause

<!--
  One sentence saying why it happens, then the evidence: `file:line` for
  every claim about how the code behaves, a URL plus the sentence relied on
  for a library or platform. Cannot get there? Write UNVERIFIED and say what
  evidence would settle it.
-->

### Blast radius

<!--
  Who else is affected by this same cause -- other call sites, other inputs,
  other environments.
-->

### Fix

<!--
  What changes, where, and why that is the cause rather than the symptom.
  Keep it to the cause; no unrelated cleanup riding along.
-->

### Invariants preserved

<!--
  What this fix must not break, and how anyone would know it did not.
-->

### Picture

<!--
  One Mermaid diagram, required. Draw the path and mark where it goes wrong.
  Per `documentation.md`: elk renderer, labels in double quotes, colour the
  faulty node. Render it with `mmdc` before shipping, and put a sentence under
  it saying what to look at.
-->

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart TD
```

### Out of scope

<!-- What this deliberately does not fix, including anything the blast radius turned up. -->

- …

## Stance

### Status

<!--
  `draft` until the person says otherwise, then `approved YYYY-MM-DD` taken
  from `date +%F`. Decisions mode reads this line and refuses to start on a
  draft, so a status you set yourself is a gate you opened yourself.
-->

draft

### Optimises for

<!--
  One or two sentences. What this design exists to make better, stated so that
  someone could tell whether it succeeded.

  Not "make it faster and cleaner and more maintainable" -- a stance that
  optimises for everything rules out nothing, and a stance that rules out
  nothing cannot delete a single option later.
-->

### Sacrifices

<!--
  What you are knowingly giving up. One bullet each, 2-6 of them.

  This is the heading people skip and the one that decides whether the design
  survives contact with the next person. Each bullet says what is lost, not
  why it is acceptable. The why lives in the decision that traded it away.
-->

- …

### Invariants

<!--
  Conditions no later change may violate. These are the only lines in this
  section a machine reads twice: the conflict test in Decisions checks every
  option against them, and an option that violates one is deleted rather than
  weighed.

  Two lists, and they are not interchangeable:

  - **This system's** -- derived from the trade above. Violating one sends you
    back here to re-open the stance; you are allowed to change your mind.
  - **Cross-project** -- true of every project you run, unchanged by this
    request. Violating one is not a re-open: that road is closed, find
    another. Reference them, do not restate them.

  An empty invariant list means the conflict test has nothing to check. That
  is not a shortcut -- it is the gate switched off.
-->

**This system's:**

- …

**Cross-project:**

- …

### Rejected stances

<!--
  The other trades you could have made, and why you are not making them.
  At least one. Each entry: the alternative trade in one sentence, then the
  reason it lost -- in terms of the optimise/sacrifice pair above, not in
  terms of effort.
-->

- …

### Use cases / Issues

<!--
  Numbered UC1, UC2, R1 … `R` is a defect this change removes; `UC` is a flow
  that must still work afterwards. The Detail section has to reach every id
  here and the probe checks that it does, looking only inside Detail.
-->

- UC1 — …
- R1 — …

### Overview

<!--
  One Mermaid diagram, and it is required. Draw the shape the stance implies --
  the main flow, or before/after if this changes something that already
  exists. Not the component graph; that belongs to Detail.

  Per `documentation.md`: elk renderer, labels in double quotes, `classDef`
  colouring wherever something changes. Render it with `mmdc` before shipping.
-->

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart TD
```

### Out of scope

<!--
  What this deliberately does not do, and anything deferred. A line here that
  is really a sacrifice belongs above instead: the difference is whether
  anyone loses something they have today.
-->

- …

## Decisions

### Reference

<!--
  The Stance section of this same file, plus its status. Decisions mode
  refuses to start unless that section's `### Status` reads
  `approved <date>`: an open stance means these options are being weighed
  against a trade nobody has agreed to yet.
-->

The `## Stance` section of this file — status: …

### Feasibility

<!--
  Settled BEFORE any option below was weighed. One row per capability this
  design needs and you have not personally confirmed. Evidence is a file:line
  you opened or a documentation URL you fetched -- never recollection.

  Number every row: options cite these ids, and the probe fails a capability
  that no option cites, and any Tier 2 entry resting on one that is not
  `verified`. `infeasible` is a result, not a failure.
-->

| Id | Capability | Verdict | Evidence |
|---|---|---|---|
| C1 | … | verified / UNVERIFIED / infeasible | … |

### Ruled out

<!--
  Options deleted by the conflict test -- each one violates an invariant in
  the Stance section, so it was never a choice. One line each: the option, and
  which invariant it hit. Empty is legitimate.
-->

| Option | Invariant it violates | Evidence |
|---|---|---|

### Requirement gaps

<!--
  Entries the origin test sent back: their failure condition is an assumption
  about user behaviour, not a technical fact. Each row needs one of two exits:
  a **veto condition** or a **verification path**.
-->

| # | The behavioural assumption | Veto condition, or verification path | Deletes |
|---|---|---|---|

### Tier 1

<!--
  Decisions a person answers, one at a time. **At most 5.** Over that, stop
  and re-cut. Order by dependency: whichever answer changes the *options*
  available to other entries goes first.

  Each entry carries a diagram, and `Found out when` is never blank -- unknown
  counts as late. Each entry's `Decided:` line is written when the person
  answers; the Detail section does not start until every entry has one.
  Entries are `####` headings here, one level deeper than the stand-alone
  decisions template's `###`.
-->

#### D1 — <the question, ending in a question mark>

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

### Tier 2

<!--
  Cost is high, but the evidence leaves one live option. The person scans
  these; they answer nothing unless they want to overturn something.
  **At most 10, three lines each.** The bar for arriving here is a citation
  (`file:line` or a documentation URL), not a preference.
-->

#### D… — <the question>?

Chose …, because <evidence> rules out the rest. **Found out when:** …

### Tier 3

<!--
  Cost is low on all three counts -- one component, caught by the next test
  run, cheap to undo. Recorded so that it is searchable in six months, never
  shown for review. One row each, no options table.
-->

| Decision | Chose | Instead of | Found out when |
|---|---|---|---|

## Detail

### Reference

<!--
  What this elaborates: the Stance and Decisions sections above, in this same
  file. The probe reads the use cases from the Stance section and looks for
  each only inside this Detail section.

  The `AC:` line is written by the main session, not by the designer: after
  the designer reports, the main session writes the track's `intake.md`,
  computes its sha256, and replaces the placeholder below with the real path
  and hex digest -- all before Gate 1 fingerprints this file.
  `preflight.py build`'s `intake_unchanged` compares it with `intake.md` as it
  stands then.
-->

The `## Stance` and `## Decisions` sections of this file
AC: <intake.md path> sha256 <hex>

#### Traceability

<!--
  Every UC/R id from the Stance section, and what here satisfies it. A row
  with nothing against it is a gap found now instead of three weeks into the
  build -- report it, never quietly drop the row.
-->

| From the referenced document | Satisfied by | Status |
|---|---|---|
| UC1 | … | covered |

### Requirement

<!-- What problem, for whom, and how we know it worked. One short section. -->

### Glossary

<!--
  Every noun the prose below leans on: component names, states, roles, data
  shapes, and any ordinary word this project uses in a non-obvious way. One
  definition per term.

  `Where it lives` is a file:line for something that exists today, `new — path`
  for something this design creates, or `concept` for a term that genuinely is
  not a thing in the code. The probe checks that every file:line resolves.
-->

| Term | Definition | Where it lives |
|---|---|---|
| … | one sentence, no synonyms | file:line / new — path / concept |

### Budgets

<!--
  Every quantity the implementation has to be built against: volume, rate,
  latency, payload size, concurrent callers, timeouts, retry counts, retention.
  The Number column must contain a number; the probe reads only that column.
  Unknown number → ask the user; knowable from the existing system → measure
  it and cite the measurement.
-->

| What | Number | Where it comes from |
|---|---|---|
| … | … | … |

### Design decisions

<!-- What we chose, and the requirement each choice serves. -->

### Diagrams

<!--
  Four, in Mermaid, per documentation.md: elk renderer, labels in double
  quotes, classDef colouring where something changes. Render them with `mmdc`
  before shipping.

    Architecture — the layers or services, and what crosses each boundary
    Component    — each component and the contract with its neighbours
    Flow         — the main path end to end, including where it branches
    Sequence     — one per use case, with the real call order

  **Every diagram carries a sentence under it** saying what to look at.
-->

#### Architecture

#### Component

#### Flow

#### Sequence — UC1

### Implementation spec

<!--
  One block per component in the Glossary:

    Responsibility — one sentence; needing two means it is two components
    Interface      — the real signature, parameter and return types included
    Data           — shape in and shape out, field by field, types, optionality
    Errors         — what fails, what the caller sees, what state is left behind
    Concurrency    — safe to run twice? safe to retry? does order matter? what
                     state is shared?
    Observability  — what it emits working, and what it emits failing
    Where it lives — the path, and whether that file exists today
    What it reuses — the existing function or module, at file:line

  Prose describing an interface is not an interface.
-->

#### <component>

### Naming

<!--
  Every name the implemented system creates: files, directories, config keys,
  environment variables, CLI flags, database columns, API fields, and the values
  of any state or enum. Spelled out, always. `Chosen by` is either the user's
  decision or a convention already in this codebase with the line that shows it.
-->

| Name | What it is | Chosen by |
|---|---|---|
| … | … | the user, YYYY-MM-DD / follows <convention> at file:line |

### Change points

<!--
  The files and modules that change, at file granularity -- plus every new
  dependency with its version, and why an existing one would not do.
-->

| Path | Change | Exists today |
|---|---|---|
| … | … | yes / no |

### Failure modes

<!--
  What can fail, and what happens when it does. Boundary inputs belong here
  too, even when nothing fails: an empty list, a value exactly at a Budgets
  limit, the first run with no existing state.
-->

| Situation | What happens | What the caller sees |
|---|---|---|
| … | … | … |

### Rollout

<!--
  All four of these get an answer, even when the answer is "nothing": can it
  ship in pieces; what happens to data that already exists; what breaks for
  callers already in flight; what the rollback is.
-->

### Verification

<!--
  Acceptance criteria are the start, not the whole thing: Level (unit /
  integration / end-to-end), What it needs, Green before.
-->

| Criterion | Level | What it needs | Green before |
|---|---|---|---|
| UC1 | unit | … | unit 1 merges |

### Work breakdown

<!--
  Cut the units where the Implementation spec's interfaces already cut them,
  then start with the riskiest unit that has no unmet dependency. Record
  anything OUTSIDE this repo that must exist first under Upstream blockers.
  When implementation finds this document wrong, log the deviation in the
  format stage-build.md defines.
-->

| Unit | Depends on | Can run alongside | Done when |
|---|---|---|---|
| 1 … | nothing | … | … |

#### Upstream blockers

| What | Owned by | Needed before |
|---|---|---|
| … | … | unit … |
