# pending-questions — the stage collects them, the main session asks

This file is read by the main session directly, never handed to a dispatched
subagent — the same arrangement `references/ticket-mirror.md` already runs
on, for the reason that file states in its own opening: a subagent has no
interactive tools.

That is not a convention this repo chose. The platform removes
`AskUserQuestion` from every subagent before it starts, whatever the agent's
`tools:` field says — it is on the list of tools filtered out "even when
listed in the `tools` field" (https://code.claude.com/docs/en/sub-agents,
"Available tools"). So a stage reference telling its runner to ask —
`stage-design.md`'s decision rule, `stage-build.md`'s Step 0.5,
`stage-ship.md`'s confirmation — is naming a tool that runner does not have.
Left to itself it answers the question instead, and a decision nobody made
lands in an approved design document or a force-push.

Running a stage standing alone (`/cai:design`, `/cai:build`, `/cai:ship`)
puts the main session in the runner's seat, where `AskUserQuestion` is
present. Ask directly there; none of this applies.

## What a stage hands up

The stage finishes everything the answer does not block, then ends its
report with:

```
## Pending questions
1. <the decision, one line>
   Background: <what the run found, cited file:line, not a summary>
   Options: <2-4; the recommended one first and marked `(recommended)`; each
            with what it costs and what choosing it forecloses>
   Blocks: <what in this stage cannot continue until this is answered>
```

A stage with nothing to ask omits the section. An empty one reads as "asked
and got nothing back", which is a different and much worse claim.

## What the main session does with it

**Save the round before asking anything.** Until they are answered the
questions exist only in this conversation, and a session that ends first
takes them along. Write the stage's whole report to a file in the system
temp directory — never inside the repo — and run
`python ${CLAUDE_PLUGIN_ROOT}/scripts/pending.py start --track-dir
.claude/track/<feature> --stage <stage> --round <1-3> --report-file <that
file>`. The command takes each question from the report's
`## Pending questions` section, verbatim, and writes
`<track-dir>/pending.md` with the report beside them; it is the only thing
that writes that file, so do not edit it by hand. Exit 2 means it refused
and wrote nothing: ask the questions anyway and say plainly that this round
will not outlive the session. The same goes when `start` or `clear` names a
`pending.md` it cannot read or does not recognise: say so plainly, ask the
person to delete `<track-dir>/pending.md`, and carry on asking without
saving this round. A session that opens on a `pending:` section
in `track_state.py status` starts from "Resuming a saved round" below
instead.

0. **Lay the options out before asking, and lint them.** `AskUserQuestion`'s
   labels hold a few words each, so the reasoning goes in the message above
   it, in `option-explainer.md`'s six-field shape — the stage handed up
   evidence, and a menu that drops it asks the person to choose blind. Also
   write that message to a file — when the round is about a decisions
   document's `## Tier 1` entry, that file is `<track-dir>/options-<id>.md`,
   `<id>` being the entry's own id (e.g. `options-D1.md`), since that is the
   path `preflight.py build`'s `options_drafts` check looks for — and run
   `python ${CLAUDE_PLUGIN_ROOT}/scripts/options_lint.py <the draft>`; exit 0
   or fix what it names (#73). That file is where the lint and `preflight.py`
   read it later, not where the person reads it: once the lint exits 0, send
   the linted text itself, in full, as the message that asks. A file path
   plus a one-line summary per option is the failure this step exists to
   prevent. This is the main session's step for the same reason the asking
   is: four of the six stage agents can run neither a script nor a `Write`.
1. **Ask one decision per turn.** `AskUserQuestion`, biggest blast radius
   first, the rest queued. A turn carrying two questions carries none — the
   second gets answered against a guess about the first.

   A menu that closes on its own is not one of these three rounds:
   `references/approval-gates.md`'s "A menu that closes on its own" section
   says no round of this file's list runs against it, and whatever else is
   queued behind it waits, in the same order, until it is answered.

   Save each answer before asking the next question: write it to a file in
   the system temp directory and run
   `python ${CLAUDE_PLUGIN_ROOT}/scripts/pending.py answer --track-dir
   .claude/track/<feature> --question <n> --answer-file <that file>`, which
   records it verbatim and marks that question `answered`. A menu that closes
   on its own gets no such call — nothing was answered — so its question
   stays `open`.
2. **Re-dispatch the same stage's agent**, quoting both the question and the
   answer verbatim in the brief. The agent that comes back has no memory of
   the one that asked, and a paraphrase of an answer is not the answer.
   Carry the round's whole report in that same brief, not only the answers:
   a stage handed back one line re-derives every citation it had already
   established, on whatever tier that stage runs on. Once the round was saved
   the report and every question and answer are in `pending.md`, so a
   resumed session quotes them from there.
3. **Three rounds at most.** A fourth means the stage cannot be specified by
   asking: record `failed`, `--note` naming what stayed open.

## Resuming a saved round

`track_state.py status` prints a `pending:` section after `next:` when the
track holds a `pending.md`: the stage, the round, how many questions are
answered, one line per question, and `on:`, the branch and short HEAD as
they are now — the file does not store them, so compare `on:` with the
branch the track belongs to and say so if they differ. Do not run the
stage's preflight and dispatch again. Ask the first question marked `open`
as steps 0 and 1 say, taking its text from `pending.md`; once none is open,
go straight to step 2. A `pending:` line that ends `ignored` — the file
could not be read, is in a format this version does not know, or belongs to
a stage already `done` or `skipped` — is not a round to resume: ask nothing
from it and run the stage as usual.

## Clearing it

Once `ledger.py append` exits 0 for the stage with `passed`, `failed` or
`skipped`, run
`python ${CLAUDE_PLUGIN_ROOT}/scripts/pending.py clear --track-dir
.claude/track/<feature> --stage <stage>`. It removes the file only when it
is that stage's own. After `blocked` or `unavailable` make no such call: the
questions are still open, so the file stays.

## What this is not

- **Not a ledger attempt.** A stage that hands up questions has not passed,
  failed, or been blocked, so "Running a stage" step 3 appends nothing and
  the retry cap (`preflight.py`'s `ledger_attempts`, 5 by default) does not
  move. Only the round that reaches an outcome writes a row. Were it
  otherwise, three rounds of honest questions would exhaust a five-attempt
  cap and the stage would be refused for having done the right thing.
- **Not a third human gate.** `SKILL.md`'s "Human gates" still names exactly
  two, and they decide whether the track advances. These answer something
  the stage could not answer itself; the stage then runs on. `ship`'s
  confirmation is the one that looks like a counter-example and is not: it
  is already one of the two, and it arrives through this file only because
  the subagent holding it cannot voice it. When what arrives *is* one of the
  two, its options are not the stage's to invent — take them from
  `references/approval-gates.md`, which also says where the answer lands.
