<!--
  cai detail design template, filled in by
  /cai:design in detail mode.

  Every heading below is required. `design_probe.py --kind detail <this file>`
  fails if one is missing or still empty, so this template does not pass its
  own probe until it has been filled in — which is the point.

  Guidance lives in HTML comments and does not count as content. Delete each
  comment as you answer it.

  The bar for the whole document: hand it to an engineer who was not in the
  conversation. Anything they have to come back and ask about is a gap.
-->

# <topic> — detail design

## Reference

<!--
  The high-level design this elaborates, and the status line it was gated on.
  The path is load-bearing: the probe follows it, reads that document, and
  checks that every use case in it is reached below.
-->

High Level Design doc: docs/design/<YYYY-MM-DD>-<topic>-high-level.md
Status: approved <YYYY-MM-DD>

### Traceability

<!--
  Every UC/R id from the referenced document, and what here satisfies it. A row
  with nothing against it is a gap found now instead of three weeks into the
  build — report it, never quietly drop the row.
-->

| From the high-level design | Satisfied by | Status |
|---|---|---|
| UC1 | … | covered |

## Requirement

<!-- What problem, for whom, and how we know it worked. One short section. -->

## Glossary

<!--
  Every noun the prose below leans on: component names, states, roles, data
  shapes, and any ordinary word this project uses in a non-obvious way. One
  definition per term — two meanings means two entries under two names, and the
  collision gets reported rather than smoothed over.

  `Where it lives` is a file:line for something that exists today, `new — path`
  for something this design creates, or `concept` for a term that genuinely is
  not a thing in the code. The probe checks that every file:line resolves and
  that the file really has that many lines, so never invent a path to fill the
  column — `concept` is what that case is for.
-->

| Term | Definition | Where it lives |
|---|---|---|
| … | one sentence, no synonyms | file:line / new — path / concept |

## Budgets

<!--
  Every quantity the implementation has to be built against: volume, rate,
  latency, payload size, concurrent callers, timeouts, retry counts, retention.
  Whichever of those this design actually has to satisfy — not a checklist.

  The Number column must contain a number; the probe reads only that column, so
  a date in the provenance will not rescue a budget reading "as many as we get".
  A collector built for 400 records a night and one built for 100,000 a second
  share no code.

  Unknown number → ask the user; an estimate they own beats one you invented.
  Knowable from the existing system → measure it and cite the measurement.
-->

| What | Number | Where it comes from |
|---|---|---|
| … | … | … |

## Design decisions

<!-- What we chose, and the requirement each choice serves. -->

## Diagrams

<!--
  Four, in Mermaid, per documentation.md: elk renderer, labels in double
  quotes, classDef colouring where something changes. Render them with `mmdc`
  before shipping.

    Architecture — the layers or services, and what crosses each boundary
    Component    — each component and the contract with its neighbours
    Flow         — the main path end to end, including where it branches
    Sequence     — one per use case, with the real call order

  Past six use cases, draw sequences only where the call order is not already
  obvious from the flow diagram, and say which you skipped and why.
-->

### Architecture

### Component

### Flow

### Sequence — UC1

## Implementation spec

<!--
  One block per component in the Glossary:

    Responsibility — one sentence; needing two means it is two components
    Interface      — the real signature, parameter and return types included
    Data           — shape in and shape out, field by field, types, optionality
    Errors         — what fails, what the caller sees, what state is left behind
    Concurrency    — safe to run twice? safe to retry? does order matter? what
                     state is shared? this is where a team's integration bugs
                     live, because each engineer believes theirs is the only
                     writer and each is right in isolation
    Observability  — what it emits working, and what it emits failing
    Where it lives — the path, and whether that file exists today
    What it reuses — the existing function or module, at file:line

  Prose describing an interface is not an interface.
-->

### <component>

## Naming

<!--
  Every name the implemented system creates: files, directories, config keys,
  environment variables, CLI flags, database columns, API fields, and the values
  of any state or enum.

  Spelled out, always — `phase-5` not `p5`, `user-tier-3` not `u3`. An
  abbreviation already standard in the domain (http, id, url) is fine; one
  coined an hour ago is not.

  `Chosen by` is either the user's decision or a convention already in this
  codebase with the line that shows it. A row that is neither is a name someone
  invented, and it belongs in Open decisions until the user has answered.
-->

| Name | What it is | Chosen by |
|---|---|---|
| … | … | the user, YYYY-MM-DD / follows <convention> at file:line |

## Change points

<!--
  The files and modules that change, at file granularity — plus every new
  dependency with its version, and why an existing one would not do.
-->

| Path | Change | Exists today |
|---|---|---|
| … | … | yes / no |

## Failure modes

<!--
  What can fail, and what happens when it does. A document describing only the
  happy path is not a short one, it is unfinished.
-->

| Situation | What happens | What the caller sees |
|---|---|---|
| … | … | … |

## Rollout

<!--
  All four of these get an answer, even when the answer is "nothing":

    - can it ship in pieces, and what is the smallest useful first piece?
    - what happens to data that already exists — migration, backfill, or nothing
    - what breaks for callers already in flight when this lands
    - what the rollback is

  "Revert the commit, nothing was written" is a real answer. Write it rather
  than leaving the question open.
-->

## Verification

<!--
  Acceptance criteria are the start, not the whole thing.

    Level        — unit / integration / end-to-end. Three engineers left to
                   choose pick three different levels, and the seams between
                   their components end up tested by nobody.
    What it needs — fixtures, test data, fakes, what is mocked at each seam
    Green before  — the merge gate for that unit; this is what "done" means
-->

| Criterion | Level | What it needs | Green before |
|---|---|---|---|
| UC1 | unit | … | unit 1 merges |

## Work breakdown

<!--
  Cut the units where the Implementation spec's interfaces already cut them — a
  stated interface is what makes two units safe to build at the same time. Then
  start with the riskiest unit that has no unmet dependency.

  Record anything OUTSIDE this repo that must exist first — another team's
  endpoint, a provisioned queue, a credential. An upstream blocker nobody wrote
  down is found by the engineer assigned the unit that needs it, that morning.

  When implementation finds this document wrong, workflow.md requires the
  deviation logged rather than silently re-scoped, and stage-build.md
  already defines the format. Point the team at that one; do not invent a second.
-->

| Unit | Depends on | Can run alongside | Done when |
|---|---|---|---|
| 1 … | nothing | … | … |

### Upstream blockers

| What | Owned by | Needed before |
|---|---|---|
| … | … | unit … |
