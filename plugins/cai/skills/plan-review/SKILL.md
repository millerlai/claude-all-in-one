---
name: plan-review
description: Review an implementation plan, architecture design, or technical spec the way a senior architect would — trace every design element back to a requirement, surface over-engineering, and check the software-engineering consequences the plan glossed over. Use when the user asks to review a plan, design doc, spec, RFC, or ADR, says "審一下這份計畫", "is this over-engineered", "does this match the requirements", "poke holes in this design" — and also on your own implementation plans before handing them over.
---

# plan-review — read the plan the way a senior architect would

The expensive mistake in a plan is rarely a wrong detail. It is building
something the requirements never asked for, and discovering the requirement it
actually missed after the code exists.

So this review runs in one direction first: **from the requirements**. Anything
the requirements don't reach is not automatically wrong — but it is a decision
someone made silently, and silent decisions are what this skill exists to
surface.

Review your own plans with it too, before handing them over. That is the harder
case and the more valuable one.

## Step 0 — Is it reviewable?

Two things must be present. Nothing else gates the review:

1. **The requirement** — what problem this solves, for whom.
2. **The acceptance criteria** — how anyone will know it worked.

Missing either one, stop. Say which is missing and ask for it, or offer the
skeleton at the bottom of this file. Reviewing a plan with no stated requirement
means inventing the requirement yourself — and every finding after that is your
opinion wearing a suit.

Everything else being thin (no diagrams, no file list, rough steps) is a
finding, not a blocker.

## Step 1 — Trace it both ways

Build the table before forming any opinion. Read the plan and the code it
touches; a traceability claim you cannot point at a line for is a guess.

| Direction | The question | What it finds |
|---|---|---|
| requirement → design | Which element of the design satisfies this? | **Gaps** — a requirement nothing implements |
| design → requirement | Which requirement asked for this element? | **Orphans** — an element no requirement reaches |

Render it as a table: requirement / design element / `file:line` or plan section
/ status. One row per requirement, plus one row per orphan.

**Orphans are the point of this skill, and they are not a delete list.** An
orphan means the author had a requirement in their head and did not write it
down. Your job is to recover that requirement as one sentence and hand it back
for a yes/no — not to decide it for them. See *The reviewer's discipline*.

## Step 2 — Run the lenses

Seven lenses, in this order. Requirement fit outranks engineering detail:
a beautifully engineered answer to the wrong question is still the wrong answer.

| # | Lens | Ask |
|---|---|---|
| 1 | **Over-engineering** | Which elements are orphans? Which exist for a caller that doesn't exist yet? |
| 2 | **Boundaries** | Is it split along reasons-to-change, or along nouns? Where is the contract between the pieces stated? Who owns which data? Any cycle? |
| 3 | **Data & state** | What is the source of truth? What schema change does this imply, and what happens to the rows already there? What is assumed about concurrency? |
| 4 | **Failure modes** | Which steps can fail halfway? What is retried, and is retrying it safe? What happens on timeout, and what does the caller see? |
| 5 | **Testability** | For each acceptance criterion, what exactly proves it? Is anything here unreachable from a test, and why? |
| 6 | **Delivery & operations** | Can this ship in pieces? What is the rollback? What breaks for data or callers already in flight? When it misbehaves at 3am, what is there to look at? |
| 7 | **The plan itself** | Is the riskiest, least-understood part first or last? Which steps can be verified on their own? Is this one deliverable or three pretending to be one? |

Lens 1 is where the requirement discipline earns its keep, so be concrete about
what to look at: an abstraction with one implementation, an extension point with
one extension, a config value nobody varies, a cache before a measurement, a
queue before a load problem, a service boundary before a team boundary, a
generic parameter with one instantiation, an interface introduced for a test
that a direct call would pass just as well.

None of these is wrong on its own. Each is a claim that something will vary,
and the review asks the author to name the requirement that makes it vary.

Lenses 3–6 exist because they are where plans are silently thin. A plan that
only describes the happy path is not a small plan, it is an unfinished one —
say so as a finding, with the specific call that can fail.

## Step 3 — Write the review

Five sections, in this order:

**1. Verdict.** `Ready` / `Revise` / `Rework`, plus one sentence of why. Rework
means the requirement fit is wrong, not that there are many findings.

**2. Traceability table.** From Step 1. Gaps and orphans marked.

**3. Findings.** Ordered `Blocker` → `Major` → `Minor`. Each one needs three
parts, and a finding missing any of them is not ready to ship:

- **where** — the section of the plan, or the `file:line` it contradicts;
- **the failure it causes** — a concrete scenario with real inputs. "This may
  cause problems" is not a finding. "Two requests arriving in the same second
  both pass the check and both insert, and the unique index throws instead of
  the second one seeing the first" is;
- **the smallest fix** — the least that makes it correct, not the best version
  you can imagine.

**4. Requirement decisions to confirm.** Orphans and any out-of-scope
suggestions land here — never in the findings, and never quietly folded into the
plan. Each entry:

- the element;
- **the requirement it implies**, written as one sentence the user can accept or
  reject;
- the question;
- what follows from *yes* (write the requirement down, keep the design) and from
  *no* (drop it, and what that simplifies).

**5. Open questions.** Anything else that blocks progress until the user
decides. Ordered by how much work the answer changes.

## The reviewer's discipline

A multi-lens review fails in two symmetric ways. It adds a little something from
every lens until the plan is twice the size. Or, in the name of "no
over-engineering", it quietly deletes things worth keeping. **Both are the
reviewer making a requirements decision that was never theirs to make.**

The rule: **surface the decision, don't take it.**

- Backed by a stated requirement or a concrete failure scenario → a finding.
  Say what to change.
- Driven by best practice, future extensibility, or how you'd have built it →
  **raise it anyway**, explicitly flagged as outside the current requirements,
  as a question in section 4. Never write it into the design yourself. Withheld
  expertise is as much a silent decision as unrequested scope.
- An orphan → recover its implied requirement and ask. Do not delete it for
  them.
- Pure taste → `Minor`, or leave it out.

The test before you write any recommendation: *can I name the requirement or the
failure scenario behind this?* If not, it belongs in section 4 as a question, in
the user's hands.

## Escalating

Run the whole review inline by default. Dispatch `architect` (Opus, read-only —
see `model-selection.md`) only when the plan spans several subsystems, or turns
on a concurrency, consistency, or migration-ordering decision that the lenses
surfaced and could not settle. It is an escalation, not a step.

When you do escalate, hand over the traceability table and the finding that
stalled, so it starts from the open question instead of paying Opus rates to
redo Step 1.

## Minimum reviewable plan skeleton

When a plan is missing too much to review, or is being written from scratch:

```md
## Requirement          what problem, for whom, and how we know it worked
## Design decisions     what we chose, and the requirement each choice serves
## Change points        the files/modules that change, at file granularity
## Failure modes        what can fail, and what happens when it does
## Verification         what proves each acceptance criterion
## Sequence             the order, riskiest and least understood first
```

Six headings. Anything a plan needs beyond this, the plan should justify.

## Folding it back

- Findings → fix the plan, then re-run Step 1 on the fixed version. A fix that
  adds an element adds a row to the traceability table too.
- Reviewing your own plan → say what you found and what you changed, in the same
  breath as handing it over. A finding you spotted and quietly fixed is still a
  decision the user never got to see.
- Section 4 → wait for the answers. Accepted ones become **requirements**, not
  design notes; that is what stops the same orphan being re-litigated later.
- Rejected suggestions worth remembering → say so once, in the review. Don't
  carry them into the next round.

## When not to use this

- There is no plan, and the task is small enough not to need one. Write the
  code.
- The plan is already agreed and the question is whether the *code* matches it
  — that is a code review.
- The requirements themselves are the unknown. That is `finding-unknowns`;
  come back here once there is something to trace against.
