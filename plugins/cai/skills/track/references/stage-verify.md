# stage-verify — three lenses over one diff, and no claim without evidence

This file is read two ways: by the subagent the track dispatches to run this
stage, and by `/cai:verify` when someone runs the stage standing alone, with
no track underneath it. The procedure below is the same either way.

One reviewer reading a diff finds what that reviewer is tuned to find. The
misses are not random: a reader hunting off-by-one errors is not, in the
same pass, asking whether the feature was worth building. Splitting the
lenses and running them separately is what makes the second question get
asked at all.

## The evidence rule

No completion claim without having just run the command and read its
output. "Should pass" is not evidence, and neither is remembering that it
passed five minutes ago in this conversation — the tree has moved since
then. Every verdict below — the reconciled findings, the fix, the final
report — traces back to a command that was actually run in this pass.

## Step 0 — Fix the scope

Find the base ref, taking the first that works: the ref the user named, or
`git symbolic-ref --short refs/remotes/origin/HEAD`, or `origin/main` (or
`origin/master`). Then, as separate commands:

- `git merge-base HEAD <base-ref>` — the branch point.
- `git diff --stat <branch-point>...HEAD` — the file list.

Carry the values yourself. Do not wire them into one pipeline with shell
variables, `sed`, or `${VAR:-default}` — none of that parses under the
PowerShell tool, and this has to work on Windows.

An empty diff, or one that is entirely generated files, stops here. Say so.

## Step 1 — Dispatch the lenses

Three `reviewer` agents, in parallel, one message. Three and not more —
`model-selection.md` caps parallel subagents at 2–3.

| Lens | What it hunts |
|---|---|
| **correctness** | Off-by-one and boundary errors, state leaking between instances or requests, a `match`/`switch` that silently falls through, a flag set and never cleared, an error swallowed, ordering assumed but not guaranteed |
| **conformance** | What the change does that nothing asked for, and what it was asked for and skipped. Compare against the plan, spec, issue, or the request in this conversation |
| **coverage** | For each behaviour change: is there a test that would **fail if this change were reverted**? Name the tests that are missing, not the coverage percentage |

Give each agent the base ref, the file list, and the requirement it is
reviewing against — the plan, issue, or the user's own words. The
conformance lens is useless without that last one; if no requirement exists
in written form, say so and review the other two.

## Step 2 — Reconcile

Do this inline; it is dedup and ranking over data already gathered, not
worth another subagent run.

- Merge findings that name the same `file:line` and the same cause. Two
  lenses reaching the same defect independently is evidence, not noise.
- Drop anything with no failure scenario, whichever lens produced it.
- Rank `Blocker` → `Major` → `Minor`. Blocker means the change is wrong,
  not that there are many findings.
- **Verify before reporting.** For each surviving Blocker and Major, open
  the file and confirm the line still says what the finding claims — the
  same evidence rule this stage opens with, applied to the reviewers'
  output rather than your own.

## Step 3 — Report

1. **Verdict.** `Ready` / `Revise` / `Rework`, one sentence of why.
2. **Findings**, ranked. Each keeps `file:line`, the failure with concrete
   inputs, and the smallest fix.
3. **Requirement decisions to confirm.** Everything the conformance lens
   found that the requirements do not reach, in either direction — the
   element, the requirement it implies as one sentence, and what follows
   from yes and from no. Not optional and not the findings list: code that
   does more than was asked is a decision someone made silently, and
   deleting it yourself is a second one. Surface it, don't take it.
4. **Not covered.** What the lenses could not check, and why.

## Fixing

Fix `Blocker` and `Major` only. For anything that looks like a bug: write
the failing test first, **run it and read the output showing it fail**,
then fix it and **run it again and read the output showing it pass**. A fix
with no test run you watched is a fix you cannot prove, whatever it looks
like on the screen.

Leave `Minor` documented and unfixed unless asked. Wait for answers on
section 3 before touching anything in it.

## When not to use this

- The artifact is a plan, spec, or design doc, not a diff — that is
  `stage-design.md`'s gate, via `plan-review`.
- The change is one file and a few lines. Read it.

## Closing

Before handing off, write into `state.md`'s `note` cell for `verify`: the
verdict, what was fixed, what section 3 raised and how it was answered, and
what remains unfixed and why.
