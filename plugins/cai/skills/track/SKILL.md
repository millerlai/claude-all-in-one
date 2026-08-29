---
name: track
description: "Carry one feature through the six SDLC stages (intake, discover, design, build, verify, ship), keeping state in .claude/track/ so a new session with no memory of this conversation can resume. Usage: /cai:track [<feature>|status|skip <stage> --reason \"<why>\"|done]"
argument-hint: "[<feature>|status|skip <stage> --reason \"<why>\"|done]"
---

```
/cai:track <feature>     create or resume; <feature> may not be `current` or `done`
/cai:track               resume whatever .claude/track/current names
/cai:track status        list tracks, where this one stopped, next step, what was skipped
/cai:track skip <stage> --reason "<why>"   record the reason, then advance
/cai:track done          move into done/, clear `current`
```

There is no `advance` subcommand. A gate that passes writes the next row
itself — a manual step taken almost every time right after a gate passes is
a step that should have been automatic.

## Resolving state

`status` and plain resume never come from reading files and reasoning about
them — run `python ${CLAUDE_PLUGIN_ROOT}/scripts/track_state.py status` (or
`resolve` for just the feature name) and relay what it prints. It is the
zero-token answer to "where did this track stop"; re-deriving that by hand
risks disagreeing with it.

`resolve --track-root .claude/track` exit 2 means no active track (or
`current` names a directory that no longer exists) — report exactly what it
printed and stop; do not guess a feature name.

## `/cai:track <feature>`

Reject `current` and `done` as feature names. If `.claude/track/<feature>/`
already exists, this is a resume: skip straight to the next unfinished
stage `track_state.py status` names. Otherwise this is a new track — first
count existing directories under `.claude/track/` (excluding `done/`); at
5 already, refuse and say why instead of creating a sixth. Archived tracks
under `done/` never count toward this cap — it only grows.

Create `.claude/track/<feature>/state.md` with one row per `stages.json`
stage, all empty, write `.claude/track/current`, then proceed to that
track's first stage below.

## Running a stage

For the stage about to run:

1. **Preflight.** `python ${CLAUDE_PLUGIN_ROOT}/scripts/preflight.py <stage>
   --track-dir .claude/track/<feature> --project-dir <project root>`. Exit 2 means
   stop and report every line it printed — no model work happens. Record it
   as `blocked` first, per step 3. Exit 0 means proceed.
2. **Dispatch.** Look up this stage's row in `stages.json`; its `reference`
   resolves against `${CLAUDE_PLUGIN_ROOT}/skills/track/`. `agent: null` means
   read that file and run the stage here, because it needs `AskUserQuestion`
   and no subagent has it. Otherwise tell the named subagent to read it and do
   the work — never choose by judgement, the field decides, model tier rides on it.
3. **Record.** Every attempt goes in the ledger, not only the ones that
   worked — a stage whose failures leave no trace cannot say how many times
   it has been tried, or why it failed last time:

   ```
   python ${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py append
       --track-dir .claude/track/<feature> --stage <stage>
       --outcome passed|failed|blocked|unavailable --gate auto|human
       [--artifact <path>] --note "<why, one line>"
   ```

   Only the passing path touches `state.md`; the rest append and stop.

   - **Preflight exited 2** → `blocked`. **Unless** its output holds
     `FAIL ledger_attempts` — that stage is already at its cap and another
     record only pushes the count further past it; report without appending.
   - **The dispatch never ran: HTTP 429/500/502/503/529, or error type
     `rate_limit_error`, `overloaded_error`, `api_error`** → `unavailable`,
     with `--note` quoting the provider's error verbatim. This one does not
     count toward the retry cap, so a run that produced bad work is `failed`,
     never this.
   - **The work did not pass the stage's own gate** → `failed`, `--note`
     saying what failed.
   - **It passed** → `passed` **first**, and only once `ledger.py` exits 0,
     overwrite that stage's row in `state.md` (status, artifact, note) —
     never append a row; the row count must stay equal to `stages.json`'s.

   `--gate human` belongs to the two human gates below and nowhere else. A
   non-zero exit stops the step: report it and leave `state.md` untouched.

## Human gates

Exactly two stages stop for a person, never more:

- **After `design`** — before any code exists, a person signs off on the
  design artifact. Do not start `build` without that sign-off.
- **Before the irreversible operations in `ship`** — merging, tagging,
  publishing. Confirm with the person before running them.

Every other stage, including ones marked `auto_invoke: false` in
`stages.json`, still runs preflight and dispatch above; `auto_invoke` only
says whether this skill may start the stage on its own or must wait to be
asked — it is not a third human gate.

## `/cai:track status`

Run `track_state.py status` and relay its output verbatim: current track,
every stage's status, the next unfinished stage, and the reason on every
`skipped` row.

## `/cai:track skip <stage> --reason "<why>"`

`--reason` is required — refuse the subcommand without it. Append it to the
ledger first (step 3's command, `--outcome skipped --artifact — --note
"<the reason>"`), then overwrite the named stage's row: `status` = `skipped`,
`note` = the reason, `artifact` = `—`. Then proceed to the next stage's
preflight as in "Running a stage" above.

A skip also clears that stage's retry count, so this is the way out of a stage
preflight has capped. The other two are `CAI_TRACK_MAX_ATTEMPTS` (a bigger
number, or `0` for no cap) and deleting `ledger.jsonl`; the
`FAIL ledger_attempts` message prints all three.

## `/cai:track done`

Move `.claude/track/<feature>/` to `.claude/track/done/<feature>/` and
delete `.claude/track/current`. Refuse if any stage's row is still empty —
report which ones.
