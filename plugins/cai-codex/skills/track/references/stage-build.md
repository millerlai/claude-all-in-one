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
not block and end the report with the `## Pending questions` section
`references/pending-questions.md` specifies. Step 0.5 blocks every unit, so
under a track the first pass stops there when it has a question to hand up:
no unit starts until the answers come back; with none, it does not stop.
Standing alone you are the main session — ask directly.

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
3. **The test command is settled, or skipped — never a stop.**
   `test-command.md`'s `## Before build` runs before this stage does. Under a
   track the main session ran it before dispatching you: your brief carries a
   `Test command: skipped` line, or carries none and Step 1's resolver run
   finds the command. Standing alone you are the main session: run that
   section now.

If the document came from `stage-design.md`'s Detail mode, run its probe
before reading anything:
`<cai> design_probe --kind detail --project-dir <target project dir> <the document>`.
A non-zero exit means building against a document already known to be
wrong — say so and stop.

## Step 0.5 — Say what it will cost, then get up to two answers

Four lines first, before anything is dispatched: how many units, which of
them can run alongside another, the verify command each will have to pass,
and anything in the document you already know you will have to ask about.
A long pass nobody sized is a long pass nobody agreed to.

Then up to two answers standing alone and at most one under a track, once for the
whole run and not per unit, before anything is started. Under a track the
first pass is Step 0, those four lines, and Step 1's state table (the lane
question needs its `Alongside` column); when there is a lane question to ask
it then ends with that question in one `## Pending questions` report and
nothing else done: no unit starts, no commit is made.
With no question to hand up, the first pass does not stop: it carries on from
Step 1 and puts the four lines in its report. That is one hand-up, a stop that
`references/pending-questions.md` does not count as one of its three rounds,
and the main session re-dispatches you with the answer. Up to two decisions
standing alone and at most one under a track, one menu per turn —
`references/approval-gates.md` holds the shape, and none is a sentence the
person types a word back into:

- **Commit per unit.** `workflow.md` says never commit unless asked; this
  procedure needs one commit per verified unit, and the parallel lane below
  cannot work at all without them. Under a track this is never asked: the
  person answered it at Gate 1, and the answer is the `commit_answer` line
  `preflight.py build` printed for this build — quoted in your brief when
  the track dispatched you, or in the preflight output you read yourself
  when you, the main session, run this file under a track. `yes, ledger
  line <n>` is yes; `no, …`, `unreadable: …`, or no `commit_answer` line
  at all is no, and the report says which. A saved report carried in your brief repeats the line its own pass acted on: that is a trace, and the line you act on is the one the dispatch quotes outside that report. Repeat that line verbatim, on a
  line of its own, in every report you hand back — in a report that ends
  with `## Pending questions`, above that section. That answer
  covers the verify stage's changes too, and the person is not asked again
  there: if yes, the main session commits verify's changes by the paths
  verify reports (`references/approval-gates.md`, "Verify's changes").
  Standing alone, ask once for the whole run. Either way, if the answer is
  no, the parallel lane is off and an interruption costs a revert — say so
  plainly — and every change stays in the working tree, build's and
  verify's: `ship`'s Step 1 stops on the tracked ones (`clean_tree`) and
  the person commits.
- **The parallel lane itself.** Asked only when the `Alongside` column names a
  pair of units whose sides of the ownership map do not intersect, and the
  commit answer is yes; with no
  such pair there is no menu, and the four lines say "sequential" in one
  line. Buys wall-clock, costs a worktree per lane plus a merge. For three or
  four small units it is not worth it. Recommend, let the user decide,
  default to sequential.

A Step 0.5 menu that closes on its own leaves that answer unmade, not
defaulted: `references/approval-gates.md`'s new section names the fallback
each takes — commit per unit, asked only standing alone, is treated as no,
so the parallel lane stays off and falls back to sequential. The run states
which menus timed out, by name, and build proceeds on whichever fallback
applies.

## Step 1 — Turn the schedule into a state table

Copy `## Work breakdown` rows (or the units cut above) into a state table
with three added columns:

| # | Unit | Depends on | Alongside | Verify with | Status | Commit |
|---|---|---|---|---|---|---|
| 1 | collector | nothing | 3 | `pytest tests/test_collector.py` | `pending` | |

**`Verify with` is the actual scoped command**, decided now, before any code
exists. The test command comes from the resolver, never from a guess: run
`<cai> resolve_test_command` and follow
`<cai-root>/skills/track/references/test-command.md` for every exit
code — unless Step 0 left a `Test command: skipped` line. Then run no resolver,
since a person declined whatever it would find, and every row's `Verify with`
reads `skipped: no test command`. A command whose `narrow` is `paths` or
`packages` gets this unit's own paths appended; one whose `narrow` is `none` goes in whole and the row says
"not narrowed". Deciding which paths gate this unit is judgement; finding the
command is not. A command that takes ten minutes or hangs gets skipped under
time pressure, and then the checkpoints are decoration.

This whole table lives in `implementation-notes.md`, never in the design
document itself. `preflight.py`'s `artifact_unchanged` hashes the artifact
the ledger recorded at sign-off, so editing that file makes every later
`preflight.py build` fail with "changed since sign-off" — including the
resumed run this table exists to serve. Standing alone there is no ledger to
compare against and nothing to trip, but keep the table out of the design
document there too — the next run may be a tracked one. Say in the notes
which design document the table belongs to.

Step 0.5's answers belong here too, so a resumed session needs none of them
again: whether a lane was approved, and
the commit answer — under a track, the `commit_answer` line this build acted
on, copied verbatim; standing alone, yes or no. A re-dispatch after any later
stop reads the lane answer from the notes and never asks Step
0.5 again. Standing alone, a resumed session reads the commit answer from the
notes too; under a track the commit answer is taken from this run's
`commit_answer` line every time, and the line wins when the notes disagree. A `Test command: skipped` line is
copied into the notes verbatim, on a line of its own: the main session reads
it there before any later dispatch of this build or of verify, and asks no
more. Step 6.2 keeps its glossary record in these same notes.

Under a track the notes go in `.claude/track/<feature>/`, beside the
`state.md` a cold session resumes from. Check `.gitignore` covers
`.claude/track/` first — `preflight.py`'s `track_ignored` reports when it
does not and never blocks. An untracked track file never trips `ship`'s
`clean_tree` on its own (#198); committing it and then changing it does, and
that FAIL now names the file rather than leaving the person to guess why the
tree is dirty. Standing alone, put them wherever this project already keeps
working notes.

Order the units: riskiest one with no unmet dependency first. Check
upstream blockers here too — a unit waiting on another team's endpoint is
`blocked` now, not on the morning someone starts it.

**A stop mid-run stops only what it touches.** Wherever this file says
something goes to the person, the affected units are the stuck unit, every
unit reached from it along the `Depends on` column, and every unit whose side
of the ownership map intersects the stuck unit's. Mark those `blocked` in the
state table; the others keep going in schedule order, committed as Step 3's
item 5 says. A blocked unit's uncommitted edits stay out of every later commit: commit each
unit by its own paths, never `git add -A` or `git commit -a`, and name them
under "In flight" if the run stops. When nothing that can run is left, end the report with the question under `##
Pending questions` (`references/pending-questions.md`), its `Blocks:` line
naming the blocked units. The main session re-dispatches you with the answer,
and the table says where to resume. Standing alone you are the main session —
ask directly, with the same units held back meanwhile.

**Derive the ownership map: which unit owns which paths.** The design does
not contain it — link `## Implementation spec`'s `Where it lives` to unit
names. A path landing under two units is not a mapping problem; it is two
units that cannot run in parallel, and possibly a boundary the design drew
wrong, which goes to the user: both units are `blocked` and the question is
handed up, as above.
Without a detail design, locate the paths named by `## Fix` or by the
approved intake criteria and signed decisions in the current source, and
assign each affected path to a unit explicitly. This substitutes for
`## Implementation spec`; do not invent a missing section.

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

That last row is a stop: the units it touches are `blocked`, the others keep
going, and the decision is handed up under `## Pending questions` (Step 1's
rule above).

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
   When there is no detail design, do not invent missing sections. On the
   diagnosis path, quote `## Fix`, `## Failing test`, and
   `## Invariants preserved` from the diagnosis for the contract, proof,
   and constraints. On a decisions-only path, quote intake's numbered
   acceptance criteria and the signed decisions applicable to this unit.
   Carry any stated budgets verbatim; if none are stated, say so. The
   dependency interfaces and allowed/forbidden files are still required.
3. **Implement, test-first.** No production code without a failing test
   first. Write the test, run it, and watch it actually fail before writing
   the code that makes it pass — a test you did not watch fail proves
   nothing, because a test that would pass against the old code too is not
   testing the change. Tell `cai_implementer` to report back rather than guess
   when the spec is ambiguous; that unit is then `blocked` and the ambiguity
   is handed up under `## Pending questions`, per Step 1. On the diagnosis path, the unit that
   carries the fix starts from the test its diagnosis's `## Failing test`
   names — that is the first failing test, before any other; run it, and
   keep the red output, because Step 6.1 needs it.

   Before the first production code of a unit whose brief carries an AC that
   `## Verification levels` gives the `local-run` level, take its baseline: run
   `<cai> local_run --track-dir <dir> --stage build --unit <N> --ac <ids>`
   as one Bash call with `timeout` 600000 and keep the output; Step 6.1 needs
   it. The runner ends itself at 540 s, below that call timeout. If the Bash
   call reports that it timed out or was moved to the background, do not wait
   for it and read no partial output: that AC has no
   baseline. Exit 4 with no start declaration is the same: no baseline.
4. **Verify.** Dispatch `cai_test-runner` with the unit's `Verify with`
   command. Read the real output.
   - Green means no failures **and** no NOT RUN file — a named test file
     that collected 0 tests, or skipped every test, is red even with 0
     failures reported.
   - Green → continue.
   - Red → back to `cai_implementer` once with the actual failure text. Still
     red → that unit is `blocked`, and so are the others Step 1 names; the
     rest keep going, and the failure is handed up under
     `## Pending questions`. No unbounded fix loop.
5. **Commit** only when the commit answer is yes (Step 0.5: the
   `commit_answer` line under a track): commit the unit by its own paths
   with a single git commit using `-m` and a single-quoted, single-line
   message (`git commit -m '<type(scope): summary>'`), with no message file
   written. Keep the summary free of apostrophes, backticks, and `$`;
   paraphrase rather than trying to escape one. Write the id into the table
   beside `done`. When it is no or `unreadable`, commit nothing — leave the
   unit's changes in the working tree and write `uncommitted` beside `done`.
   Either way, re-read the table before starting the next unit.

**With the test command skipped, no unit runs a test.** Item 3's red step
and item 4 have no command to run, and neither does Step 4's run of both
verify commands. Everything else in this stage still runs. Tests a brief
names are still written, but no test harness is added for them. Each unit
has `done (unverified)` in its Status and is committed as item 5 says.

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
3. The commit answer is yes: Gate 1's, from the `commit_answer` line, under a track; Step 0.5's yes standing alone.

Two lanes, never three — `model-selection.md` caps parallel work at 2–4 and
prefers sequential; two is the conservative end of that range.

```bash
git worktree add ../<repo>-<unit-slug> -b <current-branch>-<unit-slug>
```

Each `cai_implementer` gets the worktree's absolute path plus the same brief as
Step 3 — the "must not touch" row especially, since nothing mechanical
enforces the boundary. It commits there, and the brief also says never to
`git stash`: every worktree of a repo shares one stash, so a lane that
stashes can pop the other lane's work into its own tree. Work that has to be
set aside becomes a WIP commit on the lane branch.

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
so before forcing). A stray you cannot account for is a stop: that lane's
unit is `blocked`, the other units go on sequentially, and the question is
handed up under `## Pending questions`.

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
unit starts: that unit and those depending on it are `blocked`, the others
keep going, and the question is handed up under `## Pending questions`.

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

   On the diagnosis path — the design row is itself a diagnosis (it carries
   every heading of the diagnosis template, `design_probe.py`'s
   `DIAGNOSIS_HEADINGS`, not only a `## Failing test` heading — the one
   the probe's not-applicable branch used to check alone — and is still
   not judged by filename) or a detail design whose
   `## Reference` resolves to at least one diagnosis and no resolved
   document carries a `## Use cases / Issues` heading (the same condition
   that branch checks) — there are no `UC`/`R` ids to fill in. Write one row
   per test or check the diagnosis's `## Failing test` names instead; more
   than one diagnosis named in `## Reference` means doing this for each
   diagnosis in turn, not capping at one row per diagnosis. Each row carries
   three things: the red output build itself saw before the fix (only the
   failing lines, not the whole run), the same lines green after the fix,
   and the `file:line` of the fix — never the diagnosis's own red, which may
   predate build's run or be a stale rerun of it. These rows live in the
   same table. Example, going straight to build:

   | Failing test | Red before the fix | Green after | Fix at |
   |---|---|---|---|
   | `scripts/validate.py` Step 6.1 check | ``FAIL …Step 6.1 names the diagnosis path's `## Failing test` `` | `PASS …` | `stage-build.md:<line>` |

   This table never goes back into the diagnosis document either: going
   straight to build, the diagnosis is the design row's own document and
   Gate 1 already left a sign-off fingerprint on it; through a detail
   design, it is not the fingerprinted file, but is still the human-approved
   root cause.
   When the design has no `UC`/`R` ids and is not a diagnosis, trace every
   numbered acceptance criterion from the approved intake (AC1, AC2, ...)
   instead. Each row names the criterion, the `file:line` satisfying it,
   and the test/check with its observed result. A criterion without a
   satisfying location is unimplemented, not silently omitted. If a legacy
   intake has no ids, assign AC1, AC2, ... in its original order in the
   table, quote each criterion verbatim, and leave the signed intake
   unchanged. The conformance lens checks these same criteria.

   An AC at the `local-run` level also gets a row in this baseline table, from
   the runs Step 3 kept; Green after is the same runner command run again once
   the unit is green:

   | AC | Red before | Green after | Satisfied at |
   |---|---|---|---|
   | AC2 | `AC2 FAIL evidence/build/unit-1/<UTC>/AC2.txt` | `AC2 PASS evidence/build/unit-1/<UTC>/AC2.txt` | `src/server.py:41` |

   A check that was already green before the unit started says
   `already green before` in Red before. With no start declaration there was no
   baseline run, and Red before says `no baseline: no start declaration`.

   With the test command skipped, every cell above that needs a test run —
   red before the fix, green after it, a test's observed result — reads
   `not run: test command skipped`. The `file:line` columns are filled in as
   usual.
2. **Write the merged terms into `<top>/.claude/cai-context.md`**, before
   verify. The merged terms are the project terms the Detail design's
   `## Glossary` defines that pass the glossary check. Nobody is asked
   which, under a track or standing alone: no menu, no pending question.
   `<top>` is what `git rev-parse --show-toplevel` prints.

   A finished glossary record is never judged again, so look for one
   first. With no design document there is nothing to hash: skip this item
   entirely and say nothing about it in the report. Run
   `git hash-object <the design document>` from `<top>`; when it
   exits non-zero, write nothing, record nothing, quote git's first line
   in the report and skip the rest of this item. A record in
   `implementation-notes.md` belongs to this design only when its first
   line names the design document's path relative to `<top>`, written
   with `/`, and that hash. When one does and it ends in
   `- Complete: yes`, an earlier run made every choice below: do not judge
   the skip conditions, and pick, rewrite or place nothing again; run the
   check on the record's `- Line:` entries and go on to the write. A
   record that does not end that way,
   or that names another hash because the design changed since, counts as
   never written — judge from the start, and replace it rather than add a
   second.

   With no such record, skip entirely — no file created, nothing said
   about it in the report — when the document is not a Detail design, its
   `## Glossary` has no data row that is not the template's placeholder,
   or none of its terms is a project term. Otherwise pick the terms from
   that `## Glossary` only, never from
   another document, the conversation or the file's existing entries. A
   project term is a concept specific to this project that someone who has
   read no track would need explained: something the project deals in, or
   a step, stage or role of its work. Build leaves out file names,
   functions, fields, status strings, agent names and everyday words. For
   each term kept, in this order: take decision ids and track-document
   paths out of its definition; rewrite a definition that reads like a
   rule or a number into one or two sentences saying what the thing is;
   give it `## Domain` for something the project deals in and `## Process`
   for a step, stage or role, never another heading.

   Write every kept term as the `**Term**: definition` line it will become,
   in the Glossary's order, to one file in the scratch directory
   (`pending-questions.md` says how to make one), and
   run `<cai> glossary_check <that file>`.
   A term it flags is not written, and the report names it with the reason
   the check printed; the check ran only when its last line is
   `-- glossary: N entries checked, M flagged` with N above 0, and on any
   other outcome, whatever the exit code, write nothing, record nothing,
   say in the report that the check did not run, and skip the rest of
   this item — except that on a rerun from a finished record the report
   still names as written each `- Write:` whose `- Line:` the file already
   holds, quoting its `- Replaces:` line when it names one, and the
   `git check-ignore` step below still runs for them. A
   finished record with no `- Line:` entry runs no check. With no finished
   record for this design, record the
   outcome in one edit to `implementation-notes.md` before
   `.claude/cai-context.md` is touched — one `- Write:` entry per term that
   passed, one `- Kept out:` entry per term flagged, `- Complete: yes`
   last, each field on a line of its own so that nothing inside a
   definition can split it:

   ```md
   **Glossary record** for <the design document's path, relative to `<top>`> at <what git hash-object printed>
   - Write: <`## Domain` or `## Process`>
     - Line: <the checked line>
     - Replaces: <the line it replaces, verbatim>, or nothing
   - Kept out: <Term>
     - Reason: <the reason the check printed>
   - Complete: yes
   ```

   With no `- Write:` entry in the record, write nothing, create no file
   and skip the rest of this item; the same when this run's check flags
   every `- Line:`; the report still names every term kept out.
   Otherwise, if `.claude/cai-context.md`
   does not exist, create it verbatim from
   `<cai-root>/templates/cai-context.md.tpl` first. Then write
   each `- Line:` exactly as it was checked, in the record's order. The
   first line in the file, under any heading, whose bold name is the same
   term — the same once backticks are dropped, runs of whitespace are
   folded to one and case is ignored, the way the glossary check compares
   names — is replaced in place. It stays under the heading it was under,
   and the report names that heading, on a rerun too, not the one its
   `- Write:` entry says. With no such line, the new line goes
   after the last entry under its `- Write:` heading, and past any `_Avoid_`
   lines directly under that entry, or directly under
   that heading when it has none; when the file lacks that `## Domain` or
   `## Process` heading, add it at the end of the file first; those two
   are the only headings build ever adds. Hand-written `_Avoid_` lines,
   every other line, other headings and comments are left untouched; a
   term left out or kept out never changes an existing entry, even one
   with its name; and no `Where it lives` column is written.
   A rerun may find part of the write already done. A line that already
   reads as the recorded line is left as it is. When the first line under
   that name is neither the recorded line nor the line the record says it
   replaces — or the record names a line to replace and the file has no
   line of that name — it was changed by hand in between: write nothing
   for that term and quote what the file holds in the report. A `- Write:`
   entry whose `- Replaces:` says nothing, and whose name no line in the file
   carries, is written again: a rerun cannot tell a line deleted by hand
   from one an interrupted run never wrote. On a rerun
   from a finished record, the report is built from the record: each
   `- Write:` entry counts as written and its `- Replaces:` line as
   replaced, whichever run wrote it, unless it was left alone as changed
   by hand or flagged by this run's check; each `- Kept out:` entry is
   named with its reason. Writing by
   name from a record that is never judged again makes this idempotent —
   an interrupted rerun lands the same file.
   If `<top>/CONTEXT.md` exists and its first four lines are the
   template's first four, an earlier cai wrote it. Leave it untouched, and
   say in the report that cai no longer reads it, so the person can move
   the entries they want to keep into `.claude/cai-context.md`, or delete
   it.
   Then run `git check-ignore -q .claude/cai-context.md` from `<top>`.
   Exit 0 means the project's `.gitignore` ignores it: add and commit
   nothing — never `git add -f`, never an edit to `.gitignore` — and say
   in the report that it was written but will not reach the PR. Exit 1:
   when `git status --porcelain -- .claude/cai-context.md` prints nothing —
   a rerun that found every line already written — there is nothing to
   commit, so skip the commit and say nothing about it. Otherwise, when the
   commit answer is yes (Gate 1's under a track, Step 0.5's
   standing alone), commit this write on its
   own by its path, the same way Step 3's commit does; otherwise leave it
   in the working tree. Any other exit: commit nothing, and quote git's
   first line in the report.
3. **Review.** Under a track, skip this step: the branch is reviewed by the
   verify stage, which runs next over this same diff, and a second pass of the
   four lenses would only repeat it. Standing alone there is no verify stage after this
   one. Run `stage-verify.md` over the whole branch, passing the design
   document and the approved intake as the requirements its conformance
   lens reviews against (including the AC rows when no UC/R ids exist), and
   the glossary record Step 6.2 kept in `implementation-notes.md`. Fix
   Blocker/Major per that stage's rules; leave Minor documented; its
   requirement decisions go to the user.
4. **Report.** What each unit built and where it landed, the traceability
   table, every deviation, the name and heading of every glossary term
   written, every glossary definition replaced with the old text quoted, every
   glossary term the check kept out with its reason, every glossary line
   Step 6.2 left alone because it was changed by hand, quoted,
   the sentences Step 6.2 calls for about an earlier cai's file, an
   ignored file, a check that did not run and a `git hash-object` that
   failed, the review verdict (under a
   track: reviewed by the verify stage), and what could not be verified
   automatically as numbered manual steps. Each deviation that changed an
   interface, like every other deviation and every problem found outside the
   change's scope, goes under `## Open items`
   (`references/open-items-report.md`), one entry each, and
   `track_state.py left-open` carries it to Gate 2 as a `[build]` line.

## Report

This is what you hand back to the main session -- not the report this
file's own steps describe. Put these fields in a `## Report` section. The
main session, not you, is the only writer of the track's state table and
of the ledger's `--note`; you write no track file at all.

- what was built
- which units ran in parallel
- every deviation
- the `commit_answer` line this run acted on, verbatim, or a line saying there was none
- anything skipped, the test command included when it was
- the name and heading of every glossary term written; every glossary
  definition replaced, old text quoted; every glossary term the check kept
  out, with its reason; every glossary line left alone because it was
  changed by hand, quoted; that the glossary check did not run, when it
  did not; and git's first line, when `git hash-object` failed
- what is left open -- reminders only: every step Step 6.4 names as a
  manual step, and, with the test command skipped, one more item saying no
  unit ran a test. Every deviation, the ones that changed an interface
  included, and every problem found outside the change's scope, goes in the
  `## Open items` section after these fields instead
  (`references/open-items-report.md`)

The in-flight `unit <N> of <total>` row is still written by Step 5.5
above, not here -- this section is what you hand back once the whole
schedule is done.

Evidence goes in the artifact this stage already produces, never pasted
in here. 4000 characters is the ceiling for this section: the largest
note any finished track has written is 1941 characters, measured across
30 rows in five tracks, and a report carries those fields plus what never
reaches that cell. The number is the user's call, 2026-09-08. A
`## Pending questions` section (`references/pending-questions.md`) sits
outside the ceiling -- a decision handed up has to carry its evidence. The
glossary item above is not counted toward the ceiling either, the user's
call, 2026-10-12: under a track it is where the terms build wrote without
asking reach a person -- the only place, when the glossary file is
git-ignored -- so it is never cut to fit.
