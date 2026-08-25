---
name: build-from-design
description: Build a detail design document unit by unit — its Work breakdown table is the schedule, each unit gets a Sonnet implementer briefed from the document's own spec sections, Haiku runs the verification, and nothing starts until the one before it is green and committed. Use when an approved detail design exists and the user asks to build it, says "implement this design", "按這份設計實作", "照 work breakdown 做", "把這份 detail design 做出來", or invokes /cai:build-from-design. A design with no work breakdown is `/cai:goal` instead.
---

# build-from-design — the work breakdown is the schedule

A detail design already did the hard scheduling. `## Work breakdown` says which
units exist, which depend on which, and which two are safe to build at once;
`## Verification` says what has to be green before each one merges;
`## Implementation spec` states every interface those units meet at. Handing the
whole document to one implementer throws all of that away and gets back one
large diff nobody can verify against one row of anything.

This skill is that table's consumer. It reads the schedule, briefs one engineer
per unit from the sections that unit actually needs, and does not start the next
one until the last is green.

Two tiers, and the split is the point: **deciding runs on Sonnet, fetching and
running run on Haiku.** Locating a file and executing a test command are
mechanical; choosing where a unit's boundary sits, ranking a review finding, or
resolving a merge conflict is not, and neither is a design decision the document
turns out not to have made — that one goes back to the user.

## Step 0 — The gate

Four things, checked **in the file** — not in this conversation. A fresh session
days later is when this actually gets run, and it has no conversation to check.

1. **`## Work breakdown` has data rows.** Units, with `Depends on` filled in.
   No table, or a table with only its header, means there is no schedule to run
   and this skill has nothing to do — that case is `/cai:goal <the document>`.
2. **`## Verification` reaches those units.** Each unit needs at least one
   criterion whose `Green before` names it. A unit with no gate has no
   definition of done, and "done" then means whatever the implementer thought it
   meant.
3. **`## Implementation spec` states real signatures.** Prose describing an
   interface is not an interface, and two units meeting at a described interface
   is exactly the integration bug this ordering exists to prevent.
4. **This session is not on `main`/`master`.** `workflow.md` forbids working
   there, and the guard reads the branch from the *session's* working directory
   (`bash_guard.py:145-152`) — so on a protected branch every commit below is
   blocked, including the ones inside a worktree. Branch first.

If the document is one `/cai:design-implementation-detail-doc` wrote, run its
probe before reading anything. It costs nothing and settles the mechanical half:

```bash
python <plugin-root>/scripts/design_probe.py --kind detail --project-dir <target project dir> <the document>
```

Find `<plugin-root>` the way `/cai:setup` does — the highest-versioned
`~/.claude/plugins/cache/claude-all-in-one/cai/*/`, or `./plugins/cai/` in a
local checkout. A non-zero exit means build against a document already known to
be wrong; say so and stop. A document from somewhere else will fail the probe on
its headings — that is expected, and gates 1–3 above are what stand in for it.

## Step 0.5 — Say what it will cost, then get two answers

`finding-unknowns:29-36` requires this of any long pass. Four lines: the unit
count, which of them can run alongside another, the verify command each will
have to pass, and anything in the document you already know you will have to
ask about.

Then get both of these settled **once, up front**, not per unit:

- **Commit per unit.** `workflow.md` says never commit unless asked; this
  procedure needs one commit per verified unit, and the parallel lane cannot
  work at all without them — a worktree's output comes back by merge or not at
  all. Ask once for the whole run. If the answer is no, the parallel lane is off
  and an interruption costs a revert; say that plainly and continue sequentially.
- **The parallel lane itself.** It buys wall-clock and costs a worktree per lane
  plus a merge. For three or four small units it is not worth it. Recommend, let
  the user decide, and default to sequential when they have no preference.

## Step 1 — Turn the schedule into a state table

Copy the `## Work breakdown` rows into a state table and add three columns the
document does not have:

| # | Unit | Depends on | Alongside | Verify with | Status | Commit |
|---|---|---|---|---|---|---|
| 1 | collector | nothing | 3 | `pytest tests/test_collector.py` | `pending` | |

**`Verify with` is the actual command**, scoped to that unit. The document's
`## Verification` gives the criterion and the level, never the command — turning
"a unit test over a fixture log" into the line that runs it is work this step
has to do, and it has to be done before any code exists. Finding what this repo
already uses to run tests is mechanical: dispatch `explorer` (Haiku). Deciding
which of those commands gates this unit is not.

A verify command that takes ten minutes or hangs gets skipped under time
pressure, and then the checkpoints are decoration — `checkpointed-execution`
makes the same point about the same column. Scope it to the unit.

**Where this table lives.** Add those three columns to the document's own
`## Work breakdown` table, leaving every existing column untouched. The design
and the progress belong in one file, because the table *is* the handoff — a
fresh session opens the document and knows exactly where the last one stopped,
and which command proves it.
Where the document is read-only or lives outside this repo, start
`implementation-notes.md` beside the code instead and say which you used.

Then order the units: the riskiest one with no unmet dependency first. Front-
loading the unknown is what stops a late surprise invalidating finished work.
`### Upstream blockers` gets checked here too — a unit waiting on another team's
endpoint is `blocked` now, not on the morning someone starts it.

**Then derive the ownership map: which unit owns which paths.** The document
does not contain it. `## Change points` lists paths without saying whose they
are, and `## Work breakdown` names units without listing files — the link
between them runs through `## Implementation spec`, whose `Where it lives` gives
each component its path, and through unit names that are usually component
names. Write the map down next to the state table.

Everything downstream leans on it: it is what a unit's brief says it may touch,
what its brief forbids, and the only real test of whether two units are safe to
run at once. A path that lands under two units is not a mapping problem, it is
two units that cannot run in parallel — and possibly a boundary the design drew
in the wrong place, which goes to the user.

## Step 2 — Who does what

| Work | Runs on | Why that tier |
|---|---|---|
| Reading the document, cutting the schedule, ordering units | this session (Sonnet) | judgement |
| Locating the files a unit touches, finding what already exists to reuse | `explorer` (Haiku) | finding a location is mechanical |
| Writing a unit's code and its tests | `implementer` (Sonnet) | the main tier |
| Running a unit's verify command, reporting pass/fail | `test-runner` (Haiku) | executing and reporting is mechanical |
| Reviewing the finished diff, three lenses | `reviewer` ×3 (Sonnet) | via `diff-review` |
| Ranking findings, resolving a merge conflict, judging a deviation | this session (Sonnet) | judgement |
| Any architecture decision the document turns out not to have made | **the user** | `AskUserQuestion`, never resolved here |

The last row is the one that gets broken. A detail design missing a decision is
not an invitation to make it — the document went through review specifically so
that these were settled in front of the user. Writing your preference into the
code is a decision they never made.

## Step 3 — One unit

For each unit in schedule order:

**1. Mark it `in progress`.**

**2. Write the brief.** `implementer` starts with no context of this
conversation, so a path and "see the design" gets you a guess. Give it, quoted
from the document rather than summarized:

| What it gets | From which section |
|---|---|
| what to build, and what "done" means | the `## Work breakdown` row, `Done when` included |
| the contract it implements | the `## Implementation spec` block for its component — signature, data shape, errors, concurrency, observability, verbatim |
| the interfaces it meets | what its `Depends on` units **actually merged**, at `file:line` — not what the document said they would be |
| every name it creates | the `## Naming` rows that apply, spelled exactly |
| which files it may touch | its side of Step 1's ownership map, with the matching `## Change points` rows for what the change is |
| what proves it | its `## Verification` rows — criterion, level, and what that test needs |
| the numbers it is built against | the whole `## Budgets` table |
| **what it must not touch** | every path the ownership map gives to another unit, listed explicitly |

That last row is load-bearing in both lanes: sequential it stops scope creep,
parallel it is the entire reason two lanes do not collide.

**3. Implement.** Dispatch `implementer` (Sonnet) with that brief. It is told to
stop and report rather than guess when a spec is ambiguous — when it does, that
is Step 2's last row, not something to smooth over.

**4. Verify.** Dispatch `test-runner` (Haiku) with the unit's `Verify with`
command. Read the real output.

- Green → continue.
- Red → back to `implementer` once, with the actual failure text. Still red
  after that, stop and report. A fix loop with no stopping rule spends the
  budget until something else interrupts it, and `goal.md:39-41` caps the same
  shape for the same reason.

**5. Commit**, write the id into the table beside `done`, and re-read the table
before starting the next unit — so a session that dies here resumes from exactly
this row.

**Never leave the tree uncompilable between units.** A unit that needs a broken
intermediate state is cut in the wrong place; re-cut it and log that as a
deviation.

## Step 4 — Two units at once

Only when all three hold. Any one missing means this unit runs sequentially —
silently, no announcement needed, it is the default.

1. The document's `Alongside` column names the other unit.
2. **Their two sides of the ownership map do not intersect** — checked by you,
   by reading both sets. `Alongside` is a claim the design made before the code
   existed; the map is derived from where the components actually live. When the
   two disagree, the map wins and the units run sequentially. Finding this out
   during a merge is the expensive way to learn it.
3. Commit permission was given in Step 0.5.

Two lanes, never three. `model-selection.md` allows 2–3 and prefers sequential
execution with worktrees for exactly this shape, so two is the conservative end
of a range it already narrows — and the right end here. Each extra lane costs
another worktree, another merge, and one more chance that the ownership map was
wrong, while the wall-clock it saves is bounded by the slowest lane either way.

One worktree per lane, off the current branch:

```bash
git worktree add ../<repo>-<unit-slug> -b <current-branch>-<unit-slug>
```

Each `implementer` is given the worktree's **absolute path** as its working
directory, plus the same brief as Step 3 — the "must not touch" row especially,
since nothing mechanical is enforcing the boundary. It commits there.

Bring them back one at a time, on the main worktree:

```bash
git merge --no-ff <current-branch>-<unit-slug>
```

A conflict means condition 2 was judged wrong. Resolve it here — that is
judgement, not something to hand back down — log it as a deviation, and run
every remaining unit sequentially. Once the tree has both units, run **both**
verify commands: each passed alone in isolation, which is not evidence that they
pass together, and the seam between two components is where a team's integration
bugs live.

Then clean up, so an interrupted run does not leave worktrees behind:

```bash
git worktree remove ../<repo>-<unit-slug>
git branch -d <current-branch>-<unit-slug>
```

**If `remove` refuses, do not reach for `--force`.** It refuses on untracked
files and nothing else — build output and caches that `.gitignore` covers do not
trigger it — so the refusal means the lane produced a file that never got
committed, and forcing it deletes that file along with the worktree. Run
`git -C ../<repo>-<unit-slug> status` and look. Either the file belongs to the
unit, in which case commit it and merge again, or it is a stray, in which case
say so before forcing. This is `checkpointed-execution`'s `In flight: none`
being enforced by git rather than by memory; a lane cleaned up with `--force` on
reflex is a unit reported `done` that is missing part of itself.

Run these as separate commands. Do not wire them into one pipeline with shell
variables, `sed`, or `${VAR:-default}` — none of that parses under the PowerShell
tool, and this has to work on Windows.

## Step 5 — Deviations

The document will be wrong about something; that is what implementation is for.
`workflow.md` requires the deviation logged rather than silently re-scoped, and
`checkpointed-execution` already defines the format. Use that one — do not
invent a second:

```md
- Unit 3 — design said X, built Y.
  Why: <what the design did not anticipate>
  Cost: <what this changes for later units, or "none">
```

Take the conservative option, log it, keep going. Report every deviation at the
end, not only the ones that turned out to matter. A deviation that changes an
interface another unit depends on is not a log entry — it goes to the user
before the dependent unit starts.

## Step 6 — Close it out

Units all green is not done. Three things, in order:

**1. Fill in the traceability table.** Every `UC`/`R` id in the document's
`### Traceability`, and the `file:line` that now satisfies it. A row you cannot
point at is unimplemented, whatever the unit statuses say — this is the check
that catches a schedule that was complete and a design that was not.

**2. Run `diff-review`** over the whole branch, passing the design document as
the requirement its `conformance` lens reviews against. Fix `Blocker` and
`Major` per that skill's own rules — failing test first, then the fix, then show
it passing. Leave `Minor` documented and unfixed unless asked. Its section 4,
requirement decisions to confirm, goes to the user; never resolve those here.

**3. Report.** What each unit built and where it landed, the traceability table
with every row pointing at real code, every deviation from Step 5, the review
verdict with any open `Minor`, and what could not be verified automatically as
numbered manual steps.

Do not call it done until that report exists, and do not claim something works
without having run it.

## When not to use this

- **No `## Work breakdown`** in the document → `/cai:goal <the document>`,
  which reviews it, implements it in one pass, and verifies.
- **The document is still a high-level design** → it has no implementation spec
  to brief anyone from. That is `/cai:design-implementation-detail-doc` first.
- **Nobody has reviewed the design** → `/cai:goal` opens with `plan-review` for
  this reason. Building from an unreviewed design means finding its gaps one
  unit at a time, at implementation prices.
- **One or two small units.** The schedule, the state table, and the per-unit
  briefs cost more than the work. Just build it.
