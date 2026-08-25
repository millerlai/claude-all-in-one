---
description: "Write a detail design document an engineering team can implement from — grounded in the real code, every term defined, four validated diagrams, then a strict review. Usage: /cai:design-implementation-detail-doc <approved high-level design doc> [target project dir]"
argument-hint: "<approved high-level design doc> [target project dir]"
model: opus
effort: high
---

Turn an approved high-level design into a document an engineering team can build
from without coming back to ask what you meant: $ARGUMENTS

The failure this exists to catch is a specification that reads well and cannot be
implemented — where every sentence is defensible on its own and two engineers
still build different things.

## Step 0 — The gate

Open the high-level design named above and check three things **in the file**,
not in this conversation. A fresh session has no conversation to check, and a
fresh session days later is when this command actually gets run:

1. **`## Status` reads `approved`** with a date. `draft` means stop.
2. **`## Open questions` is empty, or every entry carries the answer it got.**
   An open architecture question is a decision this document would otherwise
   make by accident, one implementation detail at a time — which is the thing
   the two-document split exists to prevent.
3. **`## Use cases / Issues` numbers its entries** (`UC1`, `R1`, …). Step 2's
   traceability table has nothing to trace without them.

If any of the three fails, stop and say which. For a missing document or one
still in `draft`, point at `/cai:design-high-level-doc`.

Reading the file instead of asking is the whole point. "Did you approve this?"
is a question whose answer is always yes, put to someone who wants the work to
start.

## Step 0.5 — Say what it will cost, then wait

`finding-unknowns:29-36` requires this of any long pass, and this is the longer
of the two. Four lines:

- **what you will write** — the document path, and the headings it will carry;
- **what it will take** — how many areas of the target directory to read, how
  many documentation sources to fetch, how many diagrams the use-case count
  implies;
- **what is already unclear** enough that you will have to ask about it;
- **what this will not decide** — anything the high-level design left open.

Then wait for a go.

## The two rules everything below obeys

**The evidence rule.** Every sentence about how something currently behaves —
this codebase, a library, a platform API — carries its source: a `file:line`, or
a documentation URL plus the sentence you are relying on.

Gathering and judging are different jobs and they get different models, per
`model-selection.md`: fetching is mechanical, deciding what it means is not.
Three sources count, and nothing else does:

- **This project** — dispatch `explorer` (Haiku, read-only) to locate and quote
  the relevant lines, then read those files yourself and decide what they mean.
  A scout's summary is a pointer, not evidence.
- **Official documentation** — for any tool, framework, or platform this design
  stands on, fetch the vendor's own docs. `explorer` cannot do this (its tools
  are Read, Grep, and Glob), so dispatch a Haiku subagent with web access to
  fetch and quote the passages, then interpret them yourself. Record the URL and
  the sentence you took.
- **Neither** — write `UNVERIFIED`, and name the design decision that stops
  standing up if the guess turns out wrong.

What does not count: what you remember about the library, what a function's name
implies, what a similar project usually does, and what is "standard practice".
Catching yourself writing *typically*, *generally*, *should be able to*, or
*presumably* means you are writing `UNVERIFIED` in a longer form.

**The decision rule.** Four situations stop you and send you to
`AskUserQuestion`, with real options and what each costs here:

- an architecture-level choice — component boundaries, source of truth, sync or
  async, where state lives, which way a dependency points;
- a requirement not clear enough to design against;
- evidence that does not settle it, and two or more approaches both survive;
- anything touching credentials, personal data, or who is allowed to do what.
  These are architecture-level whether or not they look it, and the two costs
  are not symmetrical: asking costs a question, choosing wrong costs an
  incident. There is no heading for this precisely so that it cannot be
  discharged by filling one in.

Never resolve one silently in either direction. Writing your preference in is a
decision the user never made; leaving something out because they did not ask for
it is the same decision with the opposite sign. This is `plan-review`'s "surface
the decision, don't take it", applied to writing rather than reviewing.

These two rules appear word for word in `/cai:design-high-level-doc`. A command's
text is only loaded when that command runs, so a cross-reference would point at
something the model cannot see — the duplication is deliberate. Edit both.

## Step 1 — Ground it in the real directory

Name the target project directory: the one given above, or the repo you are in.
Say which you used and, if you had to choose, why.

Then read it. Everything the document later claims about existing code — a
function to call, a table to extend, a hook that fires, a config key that is
honoured — must resolve to a real `file:line` you have opened. Under the
evidence rule, an implementation reference you have not read is `UNVERIFIED`,
even when you are confident.

Unless the user named a path, write the document to:

```
docs/design/<YYYY-MM-DD>-<topic>-detail.md
```

Same `<topic>` as the high-level design it elaborates, so the pair sorts
together. Take the date from the system (`date +%F`), never from memory. Write
the document in whatever language `communication.md` sets for responses.

Start from the shipped template rather than from a blank file — that is what
stops two runs producing two different shapes. Find `<plugin-root>` by taking
the first of these that exists, the same way `/cai:setup` does:

1. `~/.claude/plugins/cache/claude-all-in-one/cai/*/` — highest version if
   several are present;
2. `./plugins/cai/` — a local checkout, if the working directory is one.

Copy `<plugin-root>/templates/design-detail.md.tpl` to that path and fill it in. Its
guidance lives in HTML comments; delete each one as you answer it. Those
comments do not count as content, so a section still holding only its comment
fails `design_probe.py` — an untouched template is not a document.

Do not add or rename headings. `design_probe.py` checks for exactly the set the
template ships, and `validate.py` keeps the two in step.

Four of its headings are what turn a component specification into something a
*team* can work from. Without `## Budgets` two engineers build for different
scales; without `## Rollout` nobody knows what happens to the rows already in
the database; without a `## Verification` naming test levels the seams between
components get tested by nobody; and without `## Work breakdown` there is a
de-risking order but no way for four people to start at once.

## Step 2 — Four tables, before any prose

Write no design prose until all four exist.

**1 — the Reference block.** `## Reference` names the high-level design this
elaborates, and the status line it was gated on:

```md
## Reference
High Level Design doc: docs/design/2026-08-25-session-log-collector-high-level.md
Status: approved 2026-08-25
```

The path is load-bearing, not a courtesy: `design_probe.py` follows it, reads
that document, and compares its use-case numbers against this one. A
`## Reference` naming nothing readable fails the probe.

**2 — the traceability table.** Every `UC`/`R` id in the high-level design, and
what in *this* document satisfies it:

| From the high-level design | Satisfied by | Status |
|---|---|---|
| `UC1` | the Collector component, under Implementation spec | covered |
| `UC4` | — | **not covered** |

The high-level design numbers its use cases so that something downstream can
consume the numbers; this is that consumer. A `UC` with nothing against it is a
gap found now instead of three weeks into the build — report the row, never
quietly drop it.

**3 — the glossary.** Every term the prose later leans on:

| Term | Definition | Where it lives |
|---|---|---|
| … | one sentence, no synonyms | `file:line`, `new — path/to/file.py`, or `concept` |

- Every noun the prose leans on is in here — component names, states, roles,
  data shapes, and any ordinary word this project uses in a non-obvious way.
- One definition per term. If two parts of the system mean different things by
  the same word, they get two entries under two names, and the collision is
  reported rather than smoothed over.
- **A term used in the prose but absent from the table is a defect.** No probe
  can catch that one — deciding which words are load-bearing needs a reader — so
  it falls to `plan-review`'s precision lens, and to you first.
- `Where it lives` takes a `file:line` for something that exists today,
  `new — path` for something this design creates, or `concept` for a term that
  genuinely is not a thing in the code: a state name, a consistency model, a
  role. The probe checks that every `file:line` resolves and that the file
  really has that many lines, so a citation you guessed will be caught. Never
  invent a path to fill the column — `concept` is what that case is for.

**4 — the budgets.** Every quantity the implementation has to be built against:

| What | Number | Where it comes from |
|---|---|---|
| runs per night | up to 400 | the operator's estimate, 2026-08-25 |
| render latency | under 2s at 400 runs | UC1 is read interactively |
| record size | under 4 KB | the existing rows average 1.2 KB, db/schema.sql:88 |

Volume, rate, latency, payload size, concurrent callers, timeouts, retry counts,
retention. Whichever of those the design actually has to satisfy — not a
checklist to fill.

**The `Number` column must contain a number.** `design_probe.py` fails the
document otherwise, and it reads only that column, so a date in the provenance
will not rescue a budget that reads "as many as we get". A collector built for
400 records a night and one built for 100,000 a second share no code; picking
between them is what this table is for, and it is not a decision you get to make
by leaving it out.

Where a number is genuinely unknown, it comes from the user under the decision
rule — an estimate they own beats a figure you invented. Where it is knowable
from the existing system, measure it and cite the measurement.

## Step 3 — Four diagrams

All four, in Mermaid, following `documentation.md`: `elk` renderer, labels in
double quotes rather than hand-escaped entities, `classDef` colouring wherever
the diagram shows a change.

| Diagram | Shows |
|---|---|
| **Architecture** | the layers or services, and what crosses each boundary |
| **Component** | each component, and the contract between it and its neighbours |
| **Flow** | the main path end to end, including where it branches |
| **Sequence** | one per use case in the high-level design, with the real call order |

"One per use case" has a ceiling. Past six, draw sequences only for the use
cases whose call order is not already obvious from the flow diagram, and name in
the document which ones you skipped and why. Twelve near-identical sequence
diagrams are twelve things to keep in sync and one thing nobody reads.

Then validate them by rendering, not by reading:

```bash
mmdc -i <the document> -o <scratchpad>/check.md
```

Every block must render. If `mmdc` is not installed, say plainly that the
diagrams are unvalidated and offer the install line — never write "validated"
for a diagram you did not render.

## Step 4 — The implementation spec

For each component in the glossary, in this order:

- **Responsibility** — one sentence. Needing two means it is two components.
- **Interface** — the actual signature, parameter and return types included.
  Prose describing an interface is not an interface.
- **Data** — the shape in and the shape out, field by field, with types and
  which fields are optional.
- **Errors** — what can fail, what the caller sees, and what state is left
  behind.
- **Concurrency** — is running two of these at once safe, is retrying one safe,
  does call order matter, and what state does it share with anything else. This
  is where a team's integration bugs live: each engineer builds their component
  believing it is the only writer, and every one of them is right in isolation.
- **Observability** — what it emits when it works, and what it emits when it
  does not. `plan-review`'s lens 6 asks what there is to look at when this
  misbehaves at 3am; the answer has to be designed here, because nobody adds it
  afterwards under pressure.
- **Where it lives** — the path, and whether that file exists today.
- **What it reuses** — the existing function or module it builds on, at
  `file:line`. Something you are about to write that already exists in this
  project is the most expensive detail-design defect and the cheapest to catch.

The bar: hand this to an engineer who was not in the conversation. Anything they
would have to come back and ask about is a gap, and it is your gap.

## Step 5 — Every name this design puts into the world

`## Naming` lists every name the implemented system creates: files, directories,
config keys, environment variables, CLI flags, database columns, API fields, and
the values of any state or enum.

Two rules, and it is the second that gets broken:

- **Spelled out, always.** `phase-5` not `p5`, `user-tier-3` not `u3`,
  `retry_count` not `rc`. A name is read a hundred times for every time it is
  typed, and the reader does not have your table of abbreviations in their head.
  An abbreviation already standard in the domain (`http`, `id`, `url`) is fine;
  one you coined an hour ago is not.
- **A name you invent is a decision, so ask for it.** Catching yourself choosing
  what a directory, a config key, or a status value will be called means it goes
  to `AskUserQuestion` with your suggestions — not into the document. These
  names outlive the design: they end up in scripts, dashboards, other people's
  code, and support conversations years later. Renaming one afterwards costs a
  migration; asking now costs one question.

| Name | What it is | Chosen by |
|---|---|---|
| `docs/design/` | where design documents live | the user, 2026-08-25 |
| `retry_count` | attempts made so far | follows the `*_count` fields at db/schema.sql:88 |

`Chosen by` is what makes this checkable by a reader: every row is either the
user's decision or a convention already in the codebase, with the line that
shows it. A row that is neither is a name you invented, and it belongs in the
next step's questions instead of in this table.

## Step 6 — From written to shipped

Three sections a component specification does not contain, and a team cannot
work without.

**`## Rollout` — how this reaches production, and how it comes back.**
`plan-review`'s lens 6 asks four questions; all four get answered here:

- Can it ship in pieces, and what is the smallest useful first piece?
- What happens to the data that already exists — a migration, a backfill, or
  nothing. Say which.
- What breaks for callers already in flight when this lands.
- What the rollback is. "Revert the commit, nothing was written" is a real
  answer — write it rather than leaving the question open.

If the design persists no state and has no live callers, say that in one
sentence and move on. The heading is not there to be padded; it is there so the
case where it matters cannot be skipped by forgetting the question existed.

**`## Verification` — what proves it, at which level, and what must be green.**
Acceptance criteria are the start, not the whole thing:

| Criterion | Level | What it needs | Green before |
|---|---|---|---|
| `UC1` | unit | a fixture log with three runs | unit 1 merges |
| `UC2` | integration | collector and reporter together, on real files | unit 2 merges |

- **Level** — unit, integration, or end to end. Three engineers left to choose
  will pick three different levels, and the seams between their components end
  up tested by nobody.
- **What it needs** — fixtures, test data, fakes, and what gets mocked at each
  seam. A test needing data nobody generated is a test nobody writes.
- **Green before** — the merge gate for that unit. This is what "done" means.
  Without it, "done" means whatever the person who did it thought it meant.

**`## Work breakdown` — who can start, and on what.**

| Unit | Depends on | Can run alongside | Done when |
|---|---|---|---|
| 1 collector | nothing | unit 3 | its unit test is green |
| 2 reporter | unit 1's record shape | — | `UC1` passes end to end |

Cut the units where Step 4's interfaces already cut them — a stated interface is
exactly what makes two units safe to build at the same time. Then start with the
riskiest unit that has no unmet dependency: front-loading the unknown is what
stops a late surprise invalidating work already finished.

Record here anything **outside this repo** that has to exist first — another
team's endpoint, a provisioned queue, a credential. An upstream blocker nobody
wrote down gets discovered by the engineer assigned the unit that needs it, on
the morning they start it.

Last line of this section: when an engineer finds the specification wrong
mid-build, `workflow.md` requires the deviation logged rather than silently
re-scoped, and `checkpointed-execution` already defines the format. Point the
team at that one. Do not invent a second.

## Step 7 — What you could not pin down

Anything the evidence would not settle goes to `AskUserQuestion` under the
decision rule — options spelled out, each carrying what it costs in this
codebase specifically. Wait for the answers, then write them in as decisions
with the reason attached.

Every name Step 5 could not source to the user or to an existing convention
belongs in here too, and so does every budget in Step 2 you could not measure.

**One at a time, biggest blast radius first** — the ordering
`finding-unknowns:71-73` uses. A numbered list of seven questions is not an
interview; it gets one vague answer covering none of them.

A confident guess is worse than an open question. The open question gets
answered; the guess gets implemented.

## Step 8 — Check it mechanically, then review it

Run the probe first. It costs nothing and it settles the questions that have one
answer, so no reading is spent on them:

```bash
python <plugin-root>/scripts/design_probe.py --kind detail \n    --project-dir <the target project directory> <the document>
```

It checks that all thirteen headings are present and filled, that `## Reference`
names a document that exists, that **every use case in that document is reached
by this one**, that every glossary `file:line` resolves to a file with that many
lines, that every `## Budgets` row states an actual number, and that four
diagrams are there — one of them an actual `sequenceDiagram`, since four
flowcharts would otherwise satisfy the count.

Pass `--project-dir` whenever the design targets a directory other than the one
you are standing in, or every citation relative to that project reads as
missing. Fix what it reports and re-run
until it exits 0.

Then invoke `plan-review` against the document, using its **detail design**
skeleton and running lens 8 (**Precision**) first, as that skill's Step 2 says
to for a document meant to be implemented from.

- Blocker and Major findings → fix the document, then re-run the probe *and*
  `plan-review`'s Step 1 on the fixed version, per its own "Folding it back"
  rule. A fix that changed a citation has to be re-probed, not assumed.
- Its section 4, requirement decisions to confirm → `AskUserQuestion`. Never
  resolve those yourself; that section exists so scope decisions are not made
  silently.
- Minor findings → leave them documented and unfixed unless the user asks.

**At most three rounds.** If findings remain after the third, stop and report
what is still open, with a recommendation: fix by hand, accept the Majors on
record, or go back and change the high-level design. A fix loop with no stopping
rule spends the user's budget until something else interrupts it —
`goal.md:39-41` caps the same shape for the same reason.

Be clear about what this review is: you wrote the document you are now
reviewing, so you are the reader least able to see what it quietly assumes.
Weigh a finding you are inclined to dismiss twice.

## When not to use this

- The high-level design is still `draft`, or its open questions are unanswered.
  Step 0 already stops you; this is the same rule, said before you start.
- The change touches one or two files. A thirteen-heading document with four
  diagrams over that is ceremony, and ceremony is what makes someone skip the
  command the time it would have mattered.
- The design is agreed and what you actually want is the code. That is
  `/cai:goal <the high-level design>` — it reviews, then implements against
  the whole document, since a high-level design carries no work breakdown to
  schedule from.
- Nothing is being designed; something is broken. That is debugging.

## When you are done

Report where the document is, what `plan-review` returned, what is still open,
and every claim still marked `UNVERIFIED` — the last one especially, because it
is the list of things that will surprise the implementer.

Then stop. Implementing it is `/cai:goal <this document>` — it reviews the
document, finds the `## Work breakdown` you just wrote, and hands it to
`build-from-design` to be built unit by unit rather than in one pass. Starting
that is the user's call, not yours.
