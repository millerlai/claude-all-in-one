---
description: Quiz yourself on a diff before merging — a report on what changed and the non-obvious behaviours, then questions you have to answer correctly. Usage: /cai:quiz [base-ref]
argument-hint: "[base-ref — defaults to the branch point]"
---

Quiz the user on the changes in this branch before they merge: $ARGUMENTS

The failure mode this exists to catch is merging code you did not actually
understand. **You wrote it, so you know the answers — the point is finding out
whether the user does.**

## Step 1 — Determine the base

If a ref was given above, use it. Otherwise:

```bash
DEFAULT=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|origin/||')
git merge-base HEAD "origin/${DEFAULT:-main}"
```

If `origin/HEAD` is unset, fall back to `origin/main`, then `origin/master`,
then local `main` — the same detection `/cai:git-pr-rebase` uses. If the range
is empty, say so and stop.

## Step 2 — Read the diff

```bash
git log --oneline <BASE>..HEAD
git diff <BASE>..HEAD
```

Read it properly. Open the surrounding files where the diff alone doesn't show
what a change implies.

## Step 3 — Write the report

Four sections, no more:

**The mental model** — how data flowed before and how it flows now. Use a
Mermaid flowchart per `documentation.md`: `elk` renderer, labels in double
quotes, and `classDef` colouring so added/modified/unchanged nodes are
distinguishable at a glance. Validate that it parses before showing it.

**Three non-obvious behaviours** — deliberate choices whose reasoning is not
visible in the diff. Not a restatement of what changed: why *this* way, and what
the alternative would have cost.

**What this depends on** — assumptions the change makes about code it doesn't
touch. This is where the merge-day surprises live.

**Where it can fail** — the failure modes, and what happens when each fires.

## Step 4 — Ask the questions

Five or six, **one at a time, waiting for each answer**. Do not print the
questions as a list, and do not reveal any answer before the user has committed
to theirs.

The hard constraint: **a question whose answer is stated in the report above is
a reading test, not a comprehension test.** Every question must require
reasoning from the diff to something the report did not spell out. Good shapes:

- "What happens to an in-flight request when X goes down mid-write?"
- "Why doesn't this just do Y — it would be half the code?"
- "Which existing caller breaks if Z's default changes?"
- "Where would you look first if this shipped and error rates doubled?"

Bad shapes: "What does the new `export()` function do?", "Which files changed?"

## Step 5 — Grade

For each answer: correct, partially correct, or wrong. For anything not fully
correct, explain it and point at `file:line`. Be straight about it — a quiz that
passes everyone is worse than no quiz.

## Step 6 — Merge readiness

Only after the grading, give a short checklist of what is left before merging,
and say plainly whether the user demonstrated they understand the change. If
they missed something material, name it as a blocker rather than a note.

Do not merge, push, or commit anything. This command only reads and asks.
