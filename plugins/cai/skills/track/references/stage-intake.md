# stage-intake — turn a request into an acceptance-testable problem statement

This file is read two ways: by the subagent the track dispatches to run this
stage, and by `/cai:intake` when someone runs the stage standing alone, with
no track underneath it. The procedure below is the same either way.

The failure this stage exists to catch is starting to build before anyone
agreed on what "done" means. A request arrives as a sentence; this stage
turns it into a problem statement precise enough that a later stage can
check whether the acceptance criteria were actually met.

## Step 1 — Explore the context

Before asking anything, look. Dispatch `explorer` (read-only) to map the
area the request touches — related code, existing conventions, anything that
already half-solves this. A question asked without having looked first
spends the person's time on something you could have found yourself.

## Step 2 — Ask one question at a time

Whatever is still ambiguous after exploring goes to the user, following the
interview move (`finding-unknowns`, move C):

- Open with the count and the ordering — "4 open questions, ordered by
  blast radius."
- **Ask one question at a time and wait.** A numbered list of questions is
  not an interview; it gets one vague answer covering none of them.
- Order by whether the answer changes the shape of the work, not by what is
  easiest to answer. Cheap cosmetic questions go last or get dropped.
- Offer a default with each question ("I'd assume X — correct me"), so a
  shrug still moves things forward.

Skip this step when the request already reads unambiguous — interviewing
someone who already answered is noise.

## Step 3 — Propose 2–3 approaches

Once the request is unambiguous, propose 2–3 approaches. Each one carries:

- what it does, concretely;
- its trade-offs — what it costs, what it constrains later;
- how it fails — the situation where this would be the wrong choice.

Mark at most one **(recommended)**, and say why from the trade-offs above —
never from preference alone. This is the same option-weighing
`design-high-level-doc` runs before an architecture choice, sized for a raw
request rather than a full feasibility table.

## Step 4 — Wait for approval

**Do not start implementing.** Hand back the problem statement, the
acceptance criteria it implies, and the recommended approach, then stop.
The next stage — `discover` when the solution space is still unclear, or
`design` when it is not — only starts once the user has said yes to this
one. Typing the request is not agreement to whatever was inferred from it.

## Closing

Before handing off, write into `state.md`'s `note` cell for `intake`: the
problem statement that was agreed, which questions were skipped and why, and
any deviation from this procedure. A track resuming in a fresh session with
no memory of this conversation reads that cell, not this file, to find out
what happened.
