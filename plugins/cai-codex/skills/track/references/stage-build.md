> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.

# stage-build — build the schedule, one verified unit at a time

On this platform, this file is always read directly by the main session —
never handed to a dispatched agent to run as a whole stage — whether under
a track or standing alone via `$build`. The main session dispatches
`cai_explorer`, `cai_test-runner`, and each unit's `cai_implementer` itself;
`cai_implementer` only ever receives one unit's brief and never dispatches
anyone.

**Asking is the one thing that is not.** Dispatched by the track you are a
subagent, and no subagent can ask the person directly here either.
Step 0.5's answers, and Step 2's row that sends
architecture decisions to the user, then mean: finish what the answer does
not block — the four sizing lines are not blocked — and end the report with
the `## Pending questions` section `references/pending-questions.md`
specifies. Standing alone you are the main session — ask directly.

Long runs do not fail gracefully. A session limit, a token limit, or a
dropped connection lands wherever it lands, and the cost is set entirely by
what the tree looks like at that moment — eleven half-edited files means a
revert and a full re-run, one commit later costs nothing. The unit of work
is therefore not the task; it is the largest change that can be verified and
committed on its own.

## Two situations, same discipline

- **A detail design with `## Work breakdown` exists** — that table is the
  schedule. Step 1 below turns it into a state table.
- **No design document, or one with no work breakdown** — cut units
  yourself: roughly five files, or one phase of an approved plan, whichever
  is smaller. Each unit must compile and pass on its own, and be meaningful
  to revert. If it only makes sense together with the next one, it is not a
  unit — merge them or re-cut the boundary.

Everything from Step 0 on applies either way; where a step leans on the
design document, the fallback is noted.

## Step 0 — The gate

1. If a detail design exists: `## Work breakdown` has data rows with
   `Depends on` filled in (a header-only table means there is no schedule —
   just implement directly); `## Verification` reaches those units, each
   with at least one criterion whose `Green before` names it; `##
   Implementation spec` states real signatures, not prose describing an
   interface.
2. **This session is not on `main`/`master`.** `workflow.md` forbids working
   there, and the bash guard reads the branch from the session's working
   directory, so every commit below is blocked on a protected branch,
   worktrees included. Branch first.

If the document came from `stage-design.md`'s Detail mode, run its probe
before reading anything:
`<cai> design_probe --kind detail --project-dir <target project dir> <the document>`.
A non-zero exit means building against a document already known to be
wrong — say so and stop.

## Step 0.5 — Say what it will cost, then get up to three answers

Four lines first, before anything is dispatched: how many units, which of
them can run alongside another, the verify command each will have to pass,
and anything in the document you already know you will have to ask about.
A long pass nobody sized is a long pass nobody agreed to.

Then up to three answers, once for the whole run and not per unit. Up to
three decisions, so up to three menus on as many turns —
`references/approval-gates.md` holds the shape, and none is a sentence the
person types a word back into:

- **Commit per unit.** `workflow.md` says never commit unless asked; this
  procedure needs one commit per verified unit, and the parallel lane below
  cannot work at all without them. Ask once for the whole run. If no, the
  parallel lane is off and an interruption costs a revert — say so plainly.
- **The parallel lane itself.** Buys wall-clock, costs a worktree per lane
  plus a merge. For three or four small units it is not worth it.
  Recommend, let the user decide, default to sequential.
- **Which glossary terms join `CONTEXT.md`.** Only when the document is a
  Detail design and its `## Glossary` has at least one data row that is not
  the template's placeholder. Group the terms into **propose to merge**
  (project-specific concepts) and **leave out** (implementation nouns — file
  names, functions, fields), one line each with a reason; a term already in
  `CONTEXT.md` under the same name shows the existing definition alongside
  the new one. Two options, the whole group at once — "merge as proposed
  (recommended)" or "merge none" — free text moves individual terms between
  groups or drops one. An empty "propose to merge" group means skip the
  question. Fold this into the same `## Pending questions` report as the
  other two.

A Step 0.5 menu that closes on its own leaves that answer unmade, not
defaulted: `references/approval-gates.md`'s new section names the fallback
each of the three takes — commit per unit is treated as no, so the parallel
lane stays off and falls back to sequential, and the glossary question falls
back to merge none. The run states which of the three timed out, by name,
and build proceeds on whichever fallback applies.

## Step 1 — Turn the schedule into a state table

Copy `## Work breakdown` rows (or the units cut above) into a state table
with three added columns:

| # | Unit | Depends on | Alongside | Verify with | Status | Commit |
|---|---|---|---|---|---|---|
| 1 | collector | nothing | 3 | `pytest tests/test_collector.py` | `pending` | |

**`Verify with` is the actual scoped command**, decided now, before any code
exists — finding what this repo already uses to run tests is mechanical
(dispatch `cai_explorer`); deciding which command gates this unit is not. A
command that takes ten minutes or hangs gets skipped under time pressure,
and then the checkpoints are decoration.

This whole table lives in `implementation-notes.md`, never in the design
document itself. `preflight.py`'s `artifact_unchanged` hashes the artifact
the ledger recorded at sign-off, so editing that file makes every later
`preflight.py build` fail with "changed since sign-off" — including the
resumed run this table exists to serve. Standing alone there is no ledger to
compare against and nothing to trip, but keep the table out of the design
document there too — the next run may be a tracked one. Say in the notes
which design document the table belongs to.

Step 0.5's glossary answer belongs here too: once decided, record the terms
that ended up merged, the definition each will write, and any definition
each replaces — a resumed session needs this at Step 6 without re-asking.

Under a track the notes go in `.claude/track/<feature>/`, beside the
`state.md` a cold session resumes from. Check `.gitignore` covers
`.claude/track/` first — `preflight.py`'s `track_ignored` reports when it
does not and never blocks, so an unignored track leaves the notes in the
working tree and `ship` fails later on `clean_tree` instead, naming the
symptom rather than the cause. Standing alone, put them wherever this
project already keeps working notes.

Order the units: riskiest one with no unmet dependency first. Check
upstream blockers here too — a unit waiting on another team's endpoint is
`blocked` now, not on the morning someone starts it.

**Derive the ownership map: which unit owns which paths.** The design does
not contain it — link `## Implementation spec`'s `Where it lives` to unit
names. A path landing under two units is not a mapping problem; it is two
units that cannot run in parallel, and possibly a boundary the design drew
wrong, which goes to the user.

## Step 2 — Who does what

Tiers are named, not versioned: `chore`, `build`, `think` — which model each
resolves to lives only in `plugins/cai/models.json`.

| Work | Runs on | Why |
|---|---|---|
| Reading the document, cutting the schedule, ordering units | this session (build) | judgement |
| Locating files, finding what already exists to reuse | `cai_explorer` (chore) | mechanical |
| Writing a unit's code and its tests | `cai_implementer` (build) | judgement inside the unit's spec |
| Running a unit's verify command, reporting pass/fail | `cai_test-runner` (chore) | mechanical |
| Reviewing the finished diff | `stage-verify.md`'s lenses (build) | judgement |
| Any architecture decision the document didn't make | **the user** | the question tool, never resolved here |

## Step 3 — One unit

For each unit, in schedule order:

1. **Mark it `in progress`.**
2. **Write the brief.** `cai_implementer` starts with no context of this
   conversation, so give it, quoted rather than summarized: what to build
   and what "done" means (`Done when`), the contract it implements
   (Interface/Data/Errors/Concurrency/Observability, verbatim), the
   interfaces its dependencies **actually merged** at `file:line` (not what
   the document said they would be), every name it creates, which files it
   may touch (its side of the ownership map), what proves it (its
   `## Verification` rows), the numbers it is built against (`##
   Budgets`), and **what it must not touch** — every path the ownership map
   gives to another unit, listed explicitly.
3. **Implement, test-first.** No production code without a failing test
   first. Write the test, run it, and watch it actually fail before writing
   the code that makes it pass — a test you did not watch fail proves
   nothing, because a test that would pass against the old code too is not
   testing the change. Tell `cai_implementer` to stop and report rather than
   guess when the spec is ambiguous.
4. **Verify.** Dispatch `cai_test-runner` with the unit's `Verify with`
   command. Read the real output.
   - Green → continue.
   - Red → back to `cai_implementer` once with the actual failure text. Still
     red → stop and report. No unbounded fix loop.
5. **Commit** with a single git commit using `-m` and a single-quoted,
   single-line message (`git commit -m '<type(scope): summary>'`), with
   no message file written. Keep the summary free of apostrophes,
   backticks, and `$`; paraphrase rather than trying to escape one.
   Write the id into the table beside `done`, and re-read the table
   before starting the next unit.

**Never leave the tree uncompilable between units.** A unit that needs a
broken intermediate state is cut in the wrong place — re-cut it and log the
deviation.

The one shape that resists that rule is a **wide refactor** — a rename, a
retyped shared symbol, a moved column — whose blast radius fans across the
codebase, so a single edit breaks every call site at once and no unit can
land green on its own. Re-cut it as **expand, migrate, contract**: an
`expand` unit adds the new form beside the old, so nothing breaks; `migrate`
units move the call sites over in batches sized by blast radius (a package,
a directory), each `Depends on` the expand unit and each green alone because
the old form still exists; a `contract` unit deletes the old form once no
caller remains, `Depends on` every migrate unit. One row per batch, never one
unit that does all three:

| # | Unit | Depends on | Alongside | Verify with | Status | Commit |
|---|---|---|---|---|---|---|
| 1 | expand: add `user_id` beside `uid` | nothing | — | `pytest tests/models` | `pending` | |
| 2 | migrate `api/` to `user_id` | 1 | 3 | `pytest tests/api` | `pending` | |
| 3 | migrate `jobs/` to `user_id` | 1 | 2 | `pytest tests/jobs` | `pending` | |
| 4 | contract: drop `uid` | 2, 3 | — | `pytest` | `pending` | |

## Step 4 — Two units at once

Only when all three hold, otherwise sequential, silently:

1. The schedule's `Alongside` column names the other unit.
2. Their two sides of the ownership map do not intersect — checked by
   reading both sets; the map wins over `Alongside` when they disagree.
3. Commit permission was given in Step 0.5.

Two lanes, never three — `model-selection.md` caps parallel work at 2–4 and
prefers sequential; two is the conservative end of that range.

```bash
git worktree add ../<repo>-<unit-slug> -b <current-branch>-<unit-slug>
```

Each `cai_implementer` gets the worktree's absolute path plus the same brief as
Step 3 — the "must not touch" row especially, since nothing mechanical
enforces the boundary. It commits there.

```bash
git merge --no-ff <current-branch>-<unit-slug>
```

A conflict means condition 2 was judged wrong — resolve it here, log the
deviation, and run every remaining unit sequentially. Once the tree has both
units, run **both** verify commands: each passing alone is not evidence they
pass together.

```bash
git worktree remove ../<repo>-<unit-slug>
git branch -d <current-branch>-<unit-slug>
```

**If `remove` refuses, do not reach for `--force`.** It refuses only on
untracked files — run `git -C ../<repo>-<unit-slug> status` and look. Either
the file belongs to the unit (commit it, merge again) or it's a stray (say
so before forcing).

Run these as separate commands — no shell variables, `sed`, or
`${VAR:-default}` piped together; this has to work on Windows.

## Step 5 — Deviations

The document will be wrong about something; that is what implementation is
for. Log rather than silently re-scope:

```md
- Unit 3 — design said X, built Y.
  Why: <what the design did not anticipate>
  Cost: <what this changes for later units, or "none">
```

Take the conservative option, log it, keep going. A deviation that changes
an interface another unit depends on goes to the user before the dependent
unit starts.

## Step 5.5 — Stopping before you are finished

**No hook fires before a session dies.** `SessionStart`, `SessionEnd`,
`UserPromptSubmit`, `Stop`, `StopFailure`, `PreToolUse`, `PostToolUse` — none
of them warn that the budget is about to run out. Nothing enforces this step;
it holds only because the state table is updated as you go, which is why
Step 3 ends by re-reading it. **The table is the handoff.**

When a run is getting long, stop at a clean commit boundary rather than
starting a unit you may not finish, and append to `state.md`:

```md
## Handoff
- Done: units 1–3 (commits abc123, def456, 789abc)
- Next: unit 4 — <the first concrete action>
- In flight: <uncommitted state, or "none">
- Watch out for: <what the next session would otherwise rediscover>
```

Before appending that block, overwrite this stage's own row in `state.md`:
`status` = `in-progress`, `note` = `unit <N> of <total>` (the same fixture
convention this repo already uses, e.g. `unit 3 of 5`) — the row this stage
is running as, not the one it is about to start next.

`In flight: none` is the goal. Anything else means the stopping point was
wrong — a half-finished unit is the one thing a fresh session cannot recover
from the table alone.

## Step 6 — Close it out

Units all green is not done:

1. **Fill in the traceability table** — every `UC`/`R` id and the `file:line`
   that now satisfies it. A row you cannot point at is unimplemented. It goes
   in `implementation-notes.md` and the report, never back into the design
   document's own `### Traceability`, for the reason Step 1 gives.
2. **Write the merged terms into `<top>/CONTEXT.md`**, before verify. Skip
   entirely — no file created, nothing said about it in the report — when no
   glossary term ended up merged (the third menu was never asked, was
   answered "merge none", or free text moved every term out). Otherwise:
   `<top>` is what `git rev-parse --show-toplevel` prints; find `CONTEXT.md`
   there, and if it does not exist, create it verbatim from
   `<cai-root>/templates/CONTEXT.md.tpl` first. Append each new
   term as one line, `**Term**: definition`, after whatever the file already
   has. A line already starting with that term name (case-insensitive) is
   replaced in place with the new definition instead of appended; any
   hand-written `_Avoid_` line or subheading is left untouched, and no
   `Where it lives` column is written. Replacing by name rather than
   appending a duplicate makes this idempotent — an interrupted rerun lands
   the same file. Commit this write on its own, the same way Step 3's commit
   does, when Step 0.5 answered commit-per-unit yes; otherwise leave it in
   the working tree.
3. **Run `stage-verify.md`** over the whole branch, passing the design
   document as the requirement its conformance lens reviews against, and
   Step 0.5's glossary answer as recorded in `implementation-notes.md`. Fix
   Blocker/Major per that stage's rules; leave Minor documented; its
   requirement decisions go to the user.
4. **Report.** What each unit built and where it landed, the traceability
   table, every deviation, every `CONTEXT.md` definition replaced with the
   old text quoted, the review verdict, and what could not be verified
   automatically as numbered manual steps.

## Report

This is what you hand back to the main session -- not the report this
file's own steps describe. Put these fields in a `## Report` section. The
main session, not you, is the only writer of the track's state table and
of the ledger's `--note`; you write no track file at all.

- what was built
- which units ran in parallel
- every deviation
- anything skipped
- every `CONTEXT.md` definition replaced, old text quoted

The in-flight `unit <N> of <total>` row is still written by Step 5.5
above, not here -- this section is what you hand back once the whole
schedule is done.

Evidence goes in the artifact this stage already produces, never pasted
in here. 4000 characters is the ceiling for this section: the largest
note any finished track has written is 1941 characters, measured across
30 rows in five tracks, and a report carries those fields plus what never
reaches that cell. The number is the user's call, 2026-09-08. A
`## Pending questions` section (`references/pending-questions.md`) sits
outside the ceiling -- a decision handed up has to carry its evidence.
