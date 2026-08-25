---
name: diff-review
description: Review a branch diff before merging by dispatching several read-only reviewers in parallel, each with a different lens, then reconciling their findings into one ranked list. Use when the user asks to review a diff, branch, or PR before merging, says "review my changes", "check this before I merge", "審一下這個 diff", "找出這次改動的問題" — and on your own changes before handing them over. For reviewing a plan rather than code, use `plan-review`.
effort: medium
---

# diff-review — three lenses over one diff

One reviewer reading a diff finds what that reviewer is tuned to find. The
misses are not random: a reader hunting off-by-one errors is not, in the same
pass, asking whether the feature was worth building. Splitting the lenses and
running them separately is what makes the second question get asked at all.

Run this on your own changes too, before handing them over.

## Step 0 — Fix the scope

Establish the base and the file list before dispatching anything:

Find the base ref, taking the first that works:

1. the ref the user named, if they named one;
2. `git symbolic-ref --short refs/remotes/origin/HEAD` — if it answers, that is
   the default branch;
3. `origin/main`, or `origin/master` if `main` does not exist.

Then read the two commands' output:

- `git merge-base HEAD <base-ref>` — the branch point, the same detection
  `git-pr-rebase` uses.
- `git diff --stat <branch-point>...HEAD` — the file list.

Run these as separate commands and carry the values yourself. Do not wire them
into one pipeline with shell variables, `sed`, or `${VAR:-default}` — none of
that parses under the PowerShell tool, and this skill has to work on Windows.

An empty diff, or a diff that is entirely generated files, stops here. Say so.

## Step 1 — Dispatch the lenses

Three `reviewer` agents, in parallel, one message. Three and not more:
`model-selection.md` caps parallel subagents at 2–3, and a skill that breaks the
plugin's own rule teaches the wrong thing.

| Lens | What it hunts |
|---|---|
| **correctness** | Off-by-one and boundary errors, state leaking between instances or requests, a `match`/`switch` that silently falls through, a flag set and never cleared, an error swallowed, ordering assumed but not guaranteed |
| **conformance** | What the change does that nothing asked for, and what it was asked for and skipped. Compare against the plan, spec, issue, or the request in this conversation |
| **coverage** | For each behaviour change: is there a test that would **fail if this change were reverted**? Name the tests that are missing, not the coverage percentage |

Give each agent the same three things: the base ref, the file list, and the
requirement it is reviewing against — the plan, issue, or the user's own words.
The conformance lens is useless without that last one; if no requirement exists
in written form, say so and review the other two.

## Step 2 — Reconcile

Do this inline. It is dedup and ranking over data you already have, and it is
not worth another subagent run.

- Merge findings that name the same `file:line` and the same cause. Two lenses
  reaching the same defect from different directions is evidence, not noise —
  keep the clearer scenario and note that both found it.
- Drop anything with no failure scenario, whichever lens produced it.
- Rank `Blocker` → `Major` → `Minor`. Blocker means the change is wrong, not
  that there are many findings.
- **Verify before reporting.** For each surviving Blocker and Major, open the
  file and confirm the line still says what the finding claims. A reviewer
  reading a stale hunk produces findings that are plausible and false; those
  cost more trust than the defect would have.

## Step 3 — Report

**1. Verdict.** `Ready` / `Revise` / `Rework`, one sentence of why.

**2. Findings**, ranked. Each keeps its three parts: `file:line`, the failure
with concrete inputs, and the smallest fix.

**3. Requirement decisions to confirm.** Everything the conformance lens found
that the requirements do not reach — in either direction. Each entry: the
element, the requirement it implies written as one sentence, and what follows
from yes and from no.

This section is not optional and it is not the findings list. Code that does
more than was asked is a decision someone made silently; deleting it yourself is
a second silent decision. Surface it, don't take it — the same discipline
`plan-review` applies to orphans in a plan.

**4. Not covered.** What the lenses could not check, and why.

## Fixing

Fix `Blocker` and `Major` only. For anything that looks like a bug, write the
failing test first, show it failing, then fix it and show it passing — a fix
with no test that would have caught it is a fix you cannot prove.

Leave `Minor` documented and unfixed unless the user asks. Wait for answers on
section 3 before touching anything in it.

## When not to use this

- The artifact is a plan, spec, or design doc → `plan-review`.
- You want to check your *own* understanding of a diff before merging → the
  `/cai:quiz` command; it asks you questions instead of answering them.
- The change is one file and a few lines. Read it.
