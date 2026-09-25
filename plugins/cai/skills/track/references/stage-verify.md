# stage-verify — four lenses over one diff, and no claim without evidence

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
- `git rev-parse --show-toplevel` — `<top>`, the directory Step 1's convention
  files live under.

Carry the values yourself. Do not wire them into one pipeline with shell
variables, `sed`, or `${VAR:-default}` — none of that parses under the
PowerShell tool, and this has to work on Windows.

An empty diff, or one that is entirely generated files, stops here. Say so.

## Step 0.5 — Provenance check

Run `python ${CLAUDE_PLUGIN_ROOT}/scripts/provenance.py` once, unconditionally
-- not gated on the diff being empty, unlike Step 0's early-stop. Exit 2 is a
Blocker: report it and stop right there. Never edit the ledger's citations or
a restated file to turn the red green -- a drift needs a person to re-confirm
the claim first, not a string edit that proves nothing.

## Step 1 — Dispatch the lenses

Four agents, in parallel, one message: three `reviewer` agents, one lens
each, plus the `security-reviewer` agent for the fourth. Four and not more —
`model-selection.md` caps parallel subagents at 2–4.

| Lens | What it hunts |
|---|---|
| **correctness** | Off-by-one and boundary errors, state leaking between instances or requests, a `match`/`switch` that silently falls through, a flag set and never cleared, an error swallowed, ordering assumed but not guaranteed |
| **conformance** | What the change does that nothing asked for, and what it was asked for and skipped. Compare against the plan, spec, issue, or the request in this conversation, and against the convention files at `<top>` — `<top>/CLAUDE.md` and `<top>/.claude/CLAUDE.md`, by file rather than by heading |
| **coverage** | For each behaviour change: is there a test that would **fail if this change were reverted**? Name the tests that are missing, not the coverage percentage |
| **security** | The four hunt items in `finding-severity.md`, and no fifth: an external call routed through a shell, who controls what reaches the argument vector, raw error/output/argument text reaching a print or a kept record, and a command shape the repo's own refusal list does not cover |

Give each agent the base ref, the file list, and the requirement it is
reviewing against — the plan, issue, or the user's own words. Before
dispatching, check which of `<top>/CLAUDE.md` and `<top>/.claude/CLAUDE.md`
exist and give the conformance lens only the paths that do. `@path` imports
are not followed, and `CLAUDE.local.md` does not count — only a line inside
one of those two files themselves may be cited, and a convention finding
with no `file:line` in one of them is not a finding.

A written requirement and a convention file are independent inputs to
conformance. With neither, conformance is skipped and the other three
lenses still run, as before. With a requirement but no convention file,
compare only against the requirement, as before. With a convention file but
no requirement, conformance still runs and compares only against the
convention files. With both, compare against both.

The three severity words Step 2 ranks by, and the security lens's four hunt
items, are defined in one place:
`${CLAUDE_PLUGIN_ROOT}/skills/track/references/finding-severity.md`. Read it
before classifying anything, and give `security-reviewer` its four items as the
lens it is reviewing against.

## Step 2 — Reconcile

Do this inline; it is dedup and ranking over data already gathered, not
worth another subagent run.

- Merge findings that name the same `file:line` and the same cause. Two
  lenses reaching the same defect independently is evidence, not noise.
- A convention finding whose `file:line` already appears in a command this
  pass actually ran and read the output of merges into that finding instead
  of standing alone — the repo's own verification command already caught
  it. One the commands run this pass never reached stays as its own
  finding, and Step 3's `Not covered` names which command would have
  covered it.
- Drop anything with no failure scenario, whichever lens produced it.
- Every surviving `Blocker`/`Major` must name what requirement it's based
  on — the original request's own words, a plan/issue paragraph, or an
  existing standing obligation (naming which file, which heading). A
  finding that can name none of those is not a defect this stage may fix —
  reject it or park it as a proposal instead of sending it into Fixing.
- Rank `Blocker` → `Major` → `Minor`. What the three mean is defined in one
  place, and ranking here applies those definitions rather than restating
  them: `${CLAUDE_PLUGIN_ROOT}/skills/track/references/finding-severity.md`.
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
4. **Not covered.** What the lenses could not check, and why — including
   "no written requirement" or "no written conventions" when either was
   missing from conformance's inputs.

## Fixing

Fix `Blocker` and `Major` only. For anything that looks like a bug: write
the failing test first, **run it and read the output showing it fail**,
then fix it and **run it again and read the output showing it pass**. A fix
with no test run you watched is a fix you cannot prove, whatever it looks
like on the screen.

Leave `Minor` documented and unfixed unless asked. Wait for answers on
section 3 before touching anything in it. Fix nothing Step 2 could not
trace to a requirement — a parked proposal stays parked until the user
answers, and must not be swept in together with ordinary `Minor` findings.

## When not to use this

- The artifact is a plan, spec, or design doc, not a diff — that is
  `stage-design.md`'s gate, via `plan-review`.
- The change is one file and a few lines. Read it.

## When this is the wrong tool

- **Checking your own understanding of the diff, rather than its quality** —
  that is `/cai:quiz`, which stops and asks you questions. This stage never
  stops for an answer, because inside a track it has to run to completion.
- **Reviewing a plan rather than code** — that is `plan-review`.

## Report

This is what you hand back to the main session -- not the report this
file's own steps describe. Put these fields in a `## Report` section. The
main session, not you, is the only writer of the track's state table and
of the ledger's `--note`; you write no track file at all.

- the verdict
- what was fixed
- what Step 3's **Requirement decisions to confirm** raised and how it was
  answered
- what remains unfixed and why
- what is left open -- every Minor left unfixed and every parked proposal, one item each
- what got parked as a proposal, and which requirement it would need to
  stop being parked

Evidence goes in the artifact this stage already produces, never pasted
in here. 4000 characters is the ceiling for this section: the largest
note any finished track has written is 1941 characters, measured across
30 rows in five tracks, and a report carries those fields plus what never
reaches that cell. The number is the user's call, 2026-09-08. A
`## Pending questions` section (`references/pending-questions.md`) sits
outside the ceiling -- a decision handed up has to carry its evidence.
