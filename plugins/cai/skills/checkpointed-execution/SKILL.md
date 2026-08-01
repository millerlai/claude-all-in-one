---
name: checkpointed-execution
description: Run a long, multi-file change as a sequence of independently verifiable and committable units, so an interruption resumes instead of reverting. Use when the work spans more than a handful of files or several phases, when executing an approved multi-phase plan, or when the user says "this is a big refactor", "work through the whole codebase", "這個改動很大", "分階段做". Not for single-file edits.
---

# checkpointed-execution — make the interruption survivable

Long runs do not fail gracefully. A session limit, a token limit, or a dropped
connection lands wherever it lands, and the cost is set entirely by what the
tree looks like at that moment: eleven half-edited files means a revert and a
full re-run, while the same interruption one commit later costs nothing.

The unit of work is therefore not the task. It is the largest change that can
be verified and committed on its own.

## Step 0 — Before the first edit

**Check what branch you are on first.** `workflow.md` says never work directly
on `main`/`master`, and the bash guard blocks a commit made there — so on a
protected branch this procedure stalls at its first checkpoint, with the state
file left saying `In flight:` non-empty. Create a branch before promising
anything below.

**Get the commit decision made once, up front.** `workflow.md` says never commit
unless asked; this procedure needs a commit per unit. Ask once, for the whole
run — "I'll commit after each verified unit on this branch" — and get a yes. Do
not ask again per unit, and do not commit without that yes. If the answer is no,
say plainly that interruptions will cost a revert, and continue without commits.

**Pick the state file.** If an approved plan already exists, that is the state
file — do not create a second one. Otherwise start `implementation-notes.md`
alongside the code.

Give it a status table before writing any code:

| # | Unit | Files | Verify with | Status | Commit |
|---|---|---|---|---|---|
| 1 | … | … | the exact command | `pending` | |

`Status` is one of `pending` / `in progress` / `done` / `blocked`. The `Verify
with` column holds the actual command, scoped to what this unit touches — not
"run the tests". A whole-suite run that takes ten minutes or hangs will get
skipped under time pressure, and then the checkpoints are worthless.

## Step 1 — Size the units

Aim for something that fits comfortably in one sitting: roughly five files, or
one phase of an approved plan, whichever is smaller. Two properties matter more
than the size:

- **It compiles and passes on its own.** A unit that only makes sense together
  with the next one is not a unit; merge them or re-cut the boundary.
- **It is meaningful to revert.** If reverting the commit leaves something
  incoherent, the boundary is in the wrong place.

## Step 2 — The loop

For each unit, in order:

1. Mark it `in progress` in the state file.
2. Implement it. Nothing outside the unit's file list — scope creep here is
   what makes the next interruption expensive.
3. Run the unit's verify command. Read the real output. Failing means fix and
   re-run, not proceed.
4. Commit, and write the commit id into the table alongside `done`.
5. Re-read the state file before starting the next unit, so a fresh session
   could pick up from exactly here.

**Never leave the tree uncompilable between commits.** If a unit turns out to
require a broken intermediate state, that is the signal to re-cut it, not to
push through.

## Step 3 — Deviations

`workflow.md` requires logging any deviation from the plan rather than silently
re-scoping. The format, in the state file under a `## Deviations` heading:

```md
- Unit 3 — plan said X, did Y.
  Why: <what the plan did not anticipate>
  Cost: <what this changes for later units, or "none">
```

Take the conservative option, log it, keep going. Report every deviation with
the final result — not only the ones that turned out to matter.

## Step 4 — Handing off

**No hook fires before a session dies.** The available events are
`SessionStart`, `SessionEnd`, `UserPromptSubmit`, `Stop`, `StopFailure`,
`PreToolUse`, `PostToolUse` — none of them warn you that the budget is about to
run out. Nothing enforces this step; it holds only because the state file is
updated as you go.

Which is why Step 2 ends by re-reading it: the table *is* the handoff. When a run is getting
long, stop at a clean commit boundary rather than starting a unit you may not
finish, and append:

```md
## Handoff
- Done: units 1–3 (commits abc123, def456, 789abc)
- Next: unit 4 — <the first concrete action>
- In flight: <uncommitted state, or "none">
- Watch out for: <what the next session would otherwise rediscover>
```

`In flight: none` is the goal. If it says anything else, the stopping point was
wrong.

## When not to use this

- One file, or a change small enough to verify in a single pass.
- Exploration, where the shape is not yet known — that is `finding-unknowns`.
- No plan yet and the change is non-trivial — write the plan first; this is how
  you execute one, not how you make one.
