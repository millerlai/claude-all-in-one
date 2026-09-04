# stage-build — build the schedule, one verified unit at a time

This file is read two ways: by the subagent the track dispatches to run this
stage, and by `/cai:build` when someone runs the stage standing alone, with
no track underneath it. The procedure below is the same either way.

**Asking is the one thing that is not.** Dispatched by the track you are a
subagent, and the platform removes `AskUserQuestion` from every subagent
whatever `tools:` says. Step 0.5's two answers, and Step 2's row that sends
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
`python ${CLAUDE_PLUGIN_ROOT}/scripts/design_probe.py --kind detail --project-dir <target project dir> <the document>`.
A non-zero exit means building against a document already known to be
wrong — say so and stop.

## Step 0.5 — Say what it will cost, then get two answers

Four lines first, before anything is dispatched: how many units, which of
them can run alongside another, the verify command each will have to pass,
and anything in the document you already know you will have to ask about.
A long pass nobody sized is a long pass nobody agreed to.

Then two answers, once for the whole run and not per unit:

- **Commit per unit.** `workflow.md` says never commit unless asked; this
  procedure needs one commit per verified unit, and the parallel lane below
  cannot work at all without them. Ask once for the whole run. If no, the
  parallel lane is off and an interruption costs a revert — say so plainly.
- **The parallel lane itself.** Buys wall-clock, costs a worktree per lane
  plus a merge. For three or four small units it is not worth it.
  Recommend, let the user decide, default to sequential.

## Step 1 — Turn the schedule into a state table

Copy `## Work breakdown` rows (or the units cut above) into a state table
with three added columns:

| # | Unit | Depends on | Alongside | Verify with | Status | Commit |
|---|---|---|---|---|---|---|
| 1 | collector | nothing | 3 | `pytest tests/test_collector.py` | `pending` | |

**`Verify with` is the actual scoped command**, decided now, before any code
exists — finding what this repo already uses to run tests is mechanical
(dispatch `explorer`); deciding which command gates this unit is not. A
command that takes ten minutes or hangs gets skipped under time pressure,
and then the checkpoints are decoration.

Where the design document is read-only or lives outside this repo, add
these columns to `implementation-notes.md` instead and say which you used.
Otherwise add them to the document's own `## Work breakdown` table, leaving
every existing column untouched — the design and the progress belong in one
file.

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
| Locating files, finding what already exists to reuse | `explorer` (chore) | mechanical |
| Writing a unit's code and its tests | `implementer` (build) | judgement inside the unit's spec |
| Running a unit's verify command, reporting pass/fail | `test-runner` (chore) | mechanical |
| Reviewing the finished diff | `stage-verify.md`'s lenses (build) | judgement |
| Any architecture decision the document didn't make | **the user** | `AskUserQuestion`, never resolved here |

## Step 3 — One unit

For each unit, in schedule order:

1. **Mark it `in progress`.**
2. **Write the brief.** `implementer` starts with no context of this
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
   testing the change. Tell `implementer` to stop and report rather than
   guess when the spec is ambiguous.
4. **Verify.** Dispatch `test-runner` with the unit's `Verify with`
   command. Read the real output.
   - Green → continue.
   - Red → back to `implementer` once with the actual failure text. Still
     red → stop and report. No unbounded fix loop.
5. **Commit**, write the id into the table beside `done`, and re-read the
   table before starting the next unit.

**Never leave the tree uncompilable between units.** A unit that needs a
broken intermediate state is cut in the wrong place — re-cut it and log the
deviation.

## Step 4 — Two units at once

Only when all three hold, otherwise sequential, silently:

1. The schedule's `Alongside` column names the other unit.
2. Their two sides of the ownership map do not intersect — checked by
   reading both sets; the map wins over `Alongside` when they disagree.
3. Commit permission was given in Step 0.5.

Two lanes, never three — `model-selection.md` caps parallel work at 2–3 and
prefers sequential; two is the conservative end of that range.

```bash
git worktree add ../<repo>-<unit-slug> -b <current-branch>-<unit-slug>
```

Each `implementer` gets the worktree's absolute path plus the same brief as
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

`In flight: none` is the goal. Anything else means the stopping point was
wrong — a half-finished unit is the one thing a fresh session cannot recover
from the table alone.

## Step 6 — Close it out

Units all green is not done:

1. **Fill in the traceability table** — every `UC`/`R` id and the `file:line`
   that now satisfies it. A row you cannot point at is unimplemented.
2. **Run `stage-verify.md`** over the whole branch, passing the design
   document as the requirement its conformance lens reviews against. Fix
   Blocker/Major per that stage's rules; leave Minor documented; its
   requirement decisions go to the user.
3. **Report.** What each unit built and where it landed, the traceability
   table, every deviation, the review verdict, and what could not be
   verified automatically as numbered manual steps.

## Closing

Before handing off, write into `state.md`'s `note` cell for `build`: what
was built, which units ran in parallel, every deviation, and anything
skipped.
