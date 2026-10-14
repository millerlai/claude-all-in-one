---
name: track
description: "One feature carried through every SDLC stage — intake, discover, design, build, verify, ship — with its state kept in .claude/track/ so a later session can resume where it stopped. Usage: $track [<feature>|status|skip <stage> --reason \"<why>\"|done]"
argument-hint: "[<feature>|status|skip <stage> --reason \"<why>\"|done|cancel --reason \"<why>\"]"
---
> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.


```
$track <feature>     create or resume; <feature> may not be `current` or `done`
$track               resume whatever .claude/track/current names
$track status        list tracks, where this one stopped, next step, what was skipped
$track skip <stage> --reason "<why>"   record the reason, then advance
$track done          print what was left open, then move into done/, clear `current`
$track cancel --reason "<why>"   end it unfinished: record why, move into done/, clear `current`
```

There is no `advance` subcommand. A gate that passes writes the next row
itself — a manual step taken almost every time right after a gate passes is
a step that should have been automatic.

## Resolving state

`status` and plain resume never come from reading files and reasoning about
them — run `<cai> track_state status` (or
`resolve` for just the feature name) and relay what it prints. It is the
zero-token answer to "where did this track stop"; re-deriving that by hand
risks disagreeing with it.

Exit 2 from either means stop and report exactly what was printed, guessing
nothing: no active track, or a `state.md` that is missing, disagrees with
`stages.json`, or holds an unknown `status`. None of these print a `next:`.

## `$track <feature>`

Reject `current` and `done` as names; an argument with `://` or only digits is
a ticket, not a name — `references/ticket-mirror.md`. If `.claude/track/<feature>/`
already exists, this is a resume: skip straight to the next unfinished
stage `track_state.py status` names. Otherwise this is a new track. Before creating
anything, run `<cai> track_start --track-dir .claude/track/<feature> --project-dir <project root>` and relay what it prints; on `main`/`master` it pulls and branches to `track/<feature>` first, so intake never blocks on it. Exit 2 means stop, create nothing, and report exactly what it printed.

Create `.claude/track/<feature>/state.md`, then `.claude/track/current`, then
start the first stage below. The table: `| stage | status | artifact | note |`,
a `|---|---|---|---|` rule, one row naming each `stages.json` stage, rest empty.

## Running a stage

For the stage about to run:

1. **Preflight.** `<cai> preflight <stage>
   --track-dir .claude/track/<feature> --project-dir <project root>`. Exit 2 means
   stop and report every line it printed — no model work happens. Record it as `blocked` first, per step 3,
   unless the only FAIL is `open_items_decided`: then run the open-items stop and record nothing. Exit 0 means proceed.
2. **Dispatch.** Look up this stage's row in `stages.json` and hand its work
   to the subagent named in that row's `agent` field — never choose by
   judgement, the field decides, because model tier rides on it. Tell the agent to
   read its `reference` file, resolved against `<cai-root>/skills/track/`,
   and give it `<top>`, what `git rev-parse --show-toplevel` prints. For `build`
   and `verify`, that reference file has you dispatch its helpers directly
   yourself instead of handing over the whole procedure — follow what it says
   there before dispatching the stage's own agent, if any.
   Before handing the work over, run `<cai> timing begin
   --track-dir .claude/track/<feature> --stage <stage> --platform codex` and put the line
   it prints (`cai-timing-run: <run_id>`) unchanged in every dispatch prompt of this stage, each helper's too; if it fails, dispatch without it. Every re-dispatch of a stage, one carrying a person's answer too, runs `begin` again first.
3. **Record.** Once the report is back — a `## Pending questions` one too — first run
   `<cai> timing end --track-dir .claude/track/<feature> --run <run_id>`
   (the value from step 2's line; a failure changes nothing). Then every attempt goes in the ledger, not only the ones that
   worked — a stage whose failures leave no trace cannot say how many times
   it has been tried, or why it failed last time:

   ```
   <cai> ledger append
       --track-dir .claude/track/<feature> --stage <stage>
       --outcome passed|failed|blocked|skipped|unavailable --gate auto|human
       [--artifact <path>] --note "<why, one line>"
   ```

   Only the passing path overwrites a row from here; the rest append and stop. The one other writer anywhere is `stage-build.md`'s Step 5.5, which — when a run stops before its units are finished — sets that stage's own `status` to `in-progress`, sets its `note` to `unit <N> of <total>`, and appends a `## Handoff` block. Every other `note` cell is yours, written from the fields the stage handed up under `## Report`. A build report's glossary item goes into that note as three counts — terms written, definitions replaced, terms kept out — never as the list itself: `ledger.py` cuts an over-long note from its end, which is where `Left open:` sits. Write only reminders after `Left open:`, a literal marker last in that note, items separated by `; `: what the stage's Report lists as left open, never an open item; on an overwrite carry the old row's reminders into the new note unless the new report settles them. Also feed the report of every `passed` stage to `<cai> open_items add --track-dir .claude/track/<feature> --project-dir <project root> --stage <stage> --report-file -` (the report on stdin, as `references/pending-questions.md` feeds `pending.py start`), after `ledger.py` exits 0 and before the `state.md` row is overwritten. If `add` exits 2 naming an entry, fix that entry the way a `ship_draft_check.py` FAIL is fixed and run `add` again before writing the row; if `add` exits 2 naming the record itself, say so in one line and write the report's items after `Left open:` as before. Quote `track_state.py left-open` in build's, verify's and ship's briefs.

   - **Preflight exited 2** → `blocked`. **Unless** its output holds
     `FAIL ledger_attempts` — that stage is already at its cap and another
     record only pushes the count further past it; report without appending — or `ship`'s only FAIL is `open_items_decided`: run the open-items stop and append nothing, since five resumes would spend `ship`'s retries. When that FAIL quotes a read error the stop cannot run: report the line, append nothing, and ask the person to repair the record.
   - **The dispatch never ran: HTTP 429/500/502/503/529, or error type
     `rate_limit_error`, `overloaded_error`, `api_error`** → `unavailable`,
     with `--note` quoting the provider's error verbatim. This one does not
     count toward the retry cap, so a run that produced bad work is `failed`,
     never this.
   - **The work did not pass the stage's own gate** → `failed`, `--note`
     saying what failed.
   - **It passed** → `passed` **first**, and only once `ledger.py` exits 0,
     overwrite that stage's `state.md` row: `status` = `done`, plus artifact
     and note — never append a row; the row count must equal `stages.json`'s.

   `--gate human` belongs to the two human gates below, and to a withdrawal of the commit answer (`approval-gates.md`, "Withdrawing"), and nowhere else; at the design gate it takes `--artifact`, and its `--note` is exactly `commit: yes` or `commit: no`, with nothing after it.
   A non-zero exit from `ledger.py` stops the step: report it and leave `state.md` untouched.

When `.claude/cai.json` enables ticket mirroring, you — the main session, not a subagent — follow `<cai-root>/skills/track/references/ticket-mirror.md` for this stage: before dispatch in step 2, and after every `state.md` write above, including `$track skip`.
Before `build`'s dispatch in step 2, you — the main session, not a subagent — settle the test command as `<cai-root>/skills/track/references/test-command.md`'s `## Before build` says. A missing one never stops the stage, and that section also says what `verify`'s dispatch carries after a skip.
Before `build`'s and `verify`'s dispatch, you — the main session, not a subagent — quote in the brief the `commit_answer` line `preflight.py` printed; whoever commits, you included for what `verify` changed, runs `preflight.py` again right before every commit and acts on the line that run prints, as `<cai-root>/skills/track/references/approval-gates.md`'s Gate 1 and "Verify's changes, inside a track" say; under a track no menu asks whether to commit.
Before `intake`, `discover` or `design`'s dispatch in step 2, you — the main session, not a subagent — follow `<cai-root>/skills/track/references/codemap-brief.md`, which adds at most one line to the dispatch prompt and never stops the stage.
When `intake` reports, you — the main session, not the read-only `cai_architect` — write the body of its `## Intake document` section, verbatim, to `.claude/track/<feature>/intake.md` before the approval menu, then record that path as the stage's `--artifact` and in its `state.md` row; `verify` plans from that file and `preflight.py` (`discover`, `design`) blocks without it.
A report ending in `## Pending questions` is not an outcome: before step 3, you — the main session, not a subagent — follow `<cai-root>/skills/track/references/pending-questions.md`, because no subagent can ask the person directly here either.
A `pending:` section in `track_state.py status` means an earlier round of questions was never finished: ask its first `open` question as `references/pending-questions.md` says, then re-dispatch with its saved report, instead of running the stage again. After step 3 records `passed`, `failed` or `skipped`, run `<cai> pending clear --track-dir .claude/track/<feature> --stage <stage>`.
## Human gates

Exactly two stages stop for a person, never more:

- **After `design`** — before any code exists, a person signs off on the
  design artifact. Do not start `build` without that sign-off.
- **Before the irreversible operations in `ship`** — merging, tagging,
  publishing. Confirm with the person before running them, then run
  tagging and publishing yourself: no subagent runs an irreversible
  git/gh operation here, so `ship`'s own dispatched stage only
  prepares. Not the merge, though — the guard denies `gh pr merge` on
  this platform, so hand that command back for the person to run
  themselves.

Gate 1 and Gate 2's push follow `rules/epistemics.md`: use `request_user_input` if it is in your
tool list and the current mode permits it; otherwise ask with
numbered options in text instead, never a
sentence the person has to type a word back into; Gate 2's merge is the bash guard's permission prompt. You — the main session, not
a subagent — follow `<cai-root>/skills/track/references/approval-gates.md`
for the options each one carries and where the answer lands.

Every other stage, including ones marked `auto_invoke: false` in
`stages.json`, still runs preflight and dispatch above; `auto_invoke` only
says whether this skill may start the stage on its own or must wait to be
asked — it is not a third human gate. Yet `ship` starts unasked once `verify`
passes: `approval-gates.md`'s Gate 2 says why and how (#316).

## `$track status`

Run `track_state.py status` and relay its output verbatim: current track,
every stage's status, the next unfinished stage, and the reason on every
`skipped` row.

## `$track skip <stage> --reason "<why>"`

`--reason` is required — refuse the subcommand without it. Append it to the
ledger first (step 3's command, `--outcome skipped --artifact — --note
"<the reason>"`), then overwrite the named stage's row: `status` = `skipped`,
`note` = the reason, `artifact` = `—`. Then proceed to the next stage's
preflight as in "Running a stage" above.

A skip also clears that stage's retry count, so this is the way out of a stage
preflight has capped. The other two are `CAI_TRACK_MAX_ATTEMPTS` (a bigger
number, or `0` for no cap) and deleting `ledger.jsonl`; the
`FAIL ledger_attempts` message prints all three.

## `$track done`

First run `<cai> track_state left-open` and relay its output verbatim; once the refusal below has passed, ask the open items still undecided, fix pending or filing their one menu, as `references/approval-gates.md`'s `## Open items before ship` says for `done`; then follow `<cai-root>/skills/track/references/ticket-mirror.md`'s `$track done` section, which says what runs after the move too — all skipped when the refusal below fires, when a pick fixes an item or is Stop, and while a menu is unanswered.
Then move `.claude/track/<feature>/` to `.claude/track/done/<feature>/` and delete `.claude/track/current`. Refuse if any stage's row is empty
or `in-progress` — report which are which.
Once the PR has merged, tell the person to switch to the base branch, `git pull`, then run `$git-sweep`, which shows its table before deleting anything — run none of this yourself.

## `$track cancel --reason "<why>"`

For a track that will not finish, which `done` refuses. `--reason` is required — refuse the subcommand without it. Write `.claude/track/<feature>/cancelled.md` holding today's date and the reason, then move into `done/` and delete `current` as `done` does, whatever the rows say.
Run none of `done`'s other steps: say in one line that the branch, any PR and whatever `references/ticket-mirror.md` mirrored stay as they are, that nothing queued is posted, and how many are undecided (`<cai> open_items undecided --track-dir .claude/track/<feature>`, run before the move) — what happens to them is the person's call.
