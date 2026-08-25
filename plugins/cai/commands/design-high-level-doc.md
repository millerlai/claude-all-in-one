---
description: "Write a high-level design for a human to review — use cases, a feasibility analysis grounded in real evidence, the main flow and components as diagrams, and the architecture choices put to the user rather than decided for them. Stops before implementation detail. Usage: /cai:design-high-level-doc <what to design>"
argument-hint: "<what to design — a description, an issue, or a path to notes>"
model: opus
effort: high
---

Produce a high-level design for review, and stop before any implementation
detail: $ARGUMENTS

The failure this exists to catch is a design document that arrives already
committed — plausible, detailed, and resting on an architecture nobody was asked
about and a capability nobody checked was actually available.

## Step 0 — Which kind of design is this?

Decide, and say what you decided it from:

- **A new system** — nothing exists yet, so the design stands on tools,
  frameworks, or platforms whose behaviour has to come from their documentation.
- **A change to an existing system** — the design stands on code that is already
  here, and its options are constrained by that code.

Most real work is the second. For it, establish the target project directory
before going further; if which repo or directory is meant is not obvious, ask
rather than assume the one you happen to be in.

## Step 0.5 — Say what it will cost, then wait

`finding-unknowns:29-36` requires this of any long discovery pass, and this is
one. Four lines, no more:

- **what you will write** — the document path, and the headings it will carry;
- **what it will take** — roughly how many areas of code to read, how many
  documentation sources to fetch, how many decisions you expect to bring back;
- **what is already unclear** enough that you will have to ask about it;
- **what you will not do** — no implementation detail, no code.

Then wait for a go. Typing the command is not agreement to the scope you
inferred from it, and an unwanted long pass is worse than none: the next one
gets refused too.

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

These two rules appear word for word in
`/cai:design-implementation-detail-doc`. A command's text is only loaded when
that command runs, so a cross-reference would point at something the model
cannot see — the duplication is deliberate. Edit both.

## Step 1 — Feasibility, before the document

This is what stops the document being a guess in a suit, and it runs before a
word of the document is written.

List every capability the design would need — each thing the system must be able
to do that you have not personally confirmed it can. Then settle each one under
the evidence rule:

| Id | Capability | Verdict | Evidence |
|---|---|---|---|
| `C1` | … | `verified` / `UNVERIFIED` / `infeasible` | `file:line`, or a doc URL and the line from it |

**Number every row `C1`, `C2`, …** The ids are not decoration. Step 3 cites
them, and `design_probe.py` fails the document if a capability you researched is
cited by no option, or if a recommended option rests on one that is not
`verified`. Without the ids that check cannot exist, and the feasibility table
goes back to being a disclaimer.

`infeasible` is a result, not a failure — it deletes an option before someone
spends a week inside it. `UNVERIFIED` is honest, and it stays in the finished
document, where it tells the reviewer which parts of the design rest on air.

Do not start Step 3 with an empty table. Options weighed without this are
preferences.

## Step 2 — Use cases and issues

Number them (`UC1`, `R1`, …) so `plan-review`'s traceability table can point at
them, and so the detail design later has something concrete to satisfy.

Each says what problem, for whom, and how anyone would know it worked. A use
case with no way to tell whether it succeeded is a wish.

Any requirement you would otherwise have to invent goes to `AskUserQuestion`
under the decision rule. Inventing one is the cheapest mistake available here
and the most expensive to find later, because everything downstream traces back
to it.

## Step 3 — Compare the options, then ask

For each architecture-level choice, at least two real options. Real means each
one carries:

- **which capabilities it rests on** — the `C<n>` ids from Step 1's table,
  written into the option itself;
- **why it is possible here** — the existing code it builds on at `file:line`,
  or the documented capability at its URL, taken from Step 1's table;
- **what it costs** — what changes, what it constrains later, what it rules out;
- **how it fails** — the situation in which this is the wrong choice.

An option citing no `C<n>` is not an option. Drop it, or go back and verify
what it needs. Comparison against this specific project is the whole point of
the step — a list of architectures recited from general practice is exactly
what it exists to replace.

**Mark at most one option `(recommended)`, and only if every capability it
cites is `verified`.** Recommending something that rests on `UNVERIFIED` is how
an unchecked assumption becomes the architecture: the user reasonably takes the
recommendation, and nobody revisits the row that was never confirmed.

Then put the choice to the user with `AskUserQuestion`. Do not pick first and
justify afterwards.

**One decision at a time, biggest blast radius first** — the ordering
`finding-unknowns:71-73` uses, and for the same reason: four architecture
questions in one call gets one vague answer covering none of them. Order by
whether the answer changes what the other decisions even are, not by what is
easiest to ask.

Escalate to `architect` (Opus, read-only) only when a choice genuinely spans
several subsystems, or turns on concurrency, consistency, or migration ordering
that the evidence could not settle. Per `model-selection.md` that is an
escalation and not a step — and hand it Step 1's table, so it does not pay Opus
rates to redo the research.

## Step 4 — Write it

Unless the user named a path, write it to:

```
docs/design/<YYYY-MM-DD>-<topic>-high-level.md
```

Take the date from the system (`date +%F`), never from memory — a wrong date
sorts the document into the wrong place forever, and nothing later corrects it.
`<topic>` is lowercase words joined by hyphens and **spelled out**:
`session-log-collector`, never `slc`.

Write the document itself in whatever language `communication.md` sets for
responses. This command's prose is English because every component shipped in
this plugin is; what you produce is for the user to read.

Start from the shipped template rather than from a blank file — that is what
stops two runs producing two different shapes. Find `<plugin-root>` by taking
the first of these that exists, the same way `/cai:setup` does:

1. `~/.claude/plugins/cache/claude-all-in-one/cai/*/` — highest version if
   several are present;
2. `./plugins/cai/` — a local checkout, if the working directory is one.

Copy `<plugin-root>/templates/design-high-level.md.tpl` to that path and fill it in. Its
guidance lives in HTML comments; delete each one as you answer it. Those
comments do not count as content, so a section still holding only its comment
fails `design_probe.py` — an untouched template is not a document.

Do not add or rename headings. `design_probe.py` checks for exactly the set the
template ships, and `validate.py` keeps the two in step.

`## Status` starts as `draft`. Only Step 6 turns it into `approved`, and only
after the user says so — the next command gates on that line.

Two diagrams, in Mermaid per `documentation.md` — `elk` renderer, labels in
double quotes rather than hand-escaped entities, `classDef` colouring wherever
something changes:

- **the main flow** — end to end, including where it branches;
- **the components** — what each is responsible for, and what passes between
  them.

Validate by rendering, not by reading:

```bash
mmdc -i <the document> -o <scratchpad>/check.md
```

If `mmdc` is not installed, say so and offer the install line rather than
claiming the diagrams were checked.

## Step 5 — Check it mechanically, then review it

Run the probe before reading anything:

```bash
python <plugin-root>/scripts/design_probe.py --kind hld <the document>
```

It answers only questions with one answer: are the seven headings present and
filled, does `## Status` read `draft` or `approved YYYY-MM-DD`, does every
capability row carry a `C<n>` and a citation, is every capability cited by some
option, does any recommendation rest on something not `verified`. It reads a
whole option, not a line, so splitting `(recommended)` from the `C<n>` it rests
on does not get past it. Fix what it reports and re-run until it exits 0. Nothing below is
worth doing while it still fails — reading cannot close a hole this has already
named.

Then invoke `plan-review` against the document, using the high-level design
skeleton. Lens 8 (**Precision**) runs last here rather than first: this document
is not supposed to carry signatures and schemas yet, and treating their absence
as vagueness produces findings that are all true and all premature.

Fix objective errors, re-run its Step 1 on the fixed version, and take its
section 4 to `AskUserQuestion`.

**At most three rounds of fix-and-recheck.** If findings remain after the
third, stop and report what is still open rather than looping — an
unbounded fix loop spends the user's budget without a stopping rule, and
`goal.md:39-41` caps the same shape for the same reason.

## Step 6 — Stop

Hand the document over with `## Status` still reading `draft`, and stop. Say in
as many words that no implementation detail has been decided, and that the next
step is `/cai:design-implementation-detail-doc <this document>` once the user
has approved this one.

**Only the user's approval changes `## Status`.** When they give it, write
`approved <YYYY-MM-DD>` — again from `date +%F` — and say that you did. Never
set it because the document looks finished to you: the next command gates on
that line, and a status you wrote yourself is a gate you opened yourself.

Before handing it over, check your draft for what does not belong in a
high-level design. Each of these settles in prose what the detail design exists
to settle with evidence:

- a function or method signature;
- a table schema, or a field list with types;
- a file path for code that does not exist yet;
- a pinned library version, config key, or CLI flag;
- pseudocode.

Nothing mechanical stops you writing these. A command is prose, and prose is
followed until it becomes inconvenient — so this list is what makes that failure
visible instead of silent, and finding one means cutting it, not defending it.

## When not to use this

- The change is small enough that a code review would settle it. A feasibility
  table and two diagrams over a three-file fix is ceremony, and ceremony is
  what makes someone skip the command the time it would have mattered.
- The decisions are already made and the user wants them written down. That is
  dictation — write the document, skip the option-weighing, and say you did.
- Nothing is being designed; something is broken. That is debugging: reproduce
  it, find the cause, fix it.
- The requirements themselves are the unknown. `finding-unknowns` first; come
  back when there is something to design against.
