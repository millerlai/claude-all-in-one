> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.

# pending-questions — the stage collects them, the main session asks

This file is read by the main session directly, never handed to a dispatched
subagent — the same arrangement `references/ticket-mirror.md` already runs
on, for the reason that file states in its own opening: a subagent has no
interactive tools.

That is not a convention this repo chose. No subagent can ask the person
directly here either: stage dispatch does not hand a runner an
interactive tool. So a stage reference telling its runner to ask —
`stage-design.md`'s decision rule, `stage-build.md`'s Step 0.5,
`stage-ship.md`'s confirmation — is naming a tool that runner does not have.
Left to itself it answers the question instead, and a decision nobody made
lands in an approved design document or a force-push.

Running a stage standing alone (`$design`, `$build`, `$ship`)
puts the main session in the runner's seat, where the question tool is
available directly. Ask directly there; none of this applies.

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

0. **Lay the options out before asking, and lint them.** The question tool's
   labels hold a few words each, so the reasoning goes in the message above
   it, in `option-explainer.md`'s six-field shape — the stage handed up
   evidence, and a menu that drops it asks the person to choose blind. Also
   write that message to a file — when the round is about a decisions
   document's `## Tier 1` entry, that file is `<track-dir>/options-<id>.md`,
   `<id>` being the entry's own id (e.g. `options-D1.md`), since that is the
   path `preflight.py build`'s `options_drafts` check looks for — and run
   `<cai> options_lint <the draft>`; exit 0
   or fix what it names (#73). That file is where the lint and `preflight.py`
   read it later, not where the person reads it: once the lint exits 0, send
   the linted text itself, in full, as the message that asks. A file path
   plus a one-line summary per option is the failure this step exists to
   prevent. This is the main session's step for the same reason the asking
   is: four of the six stage agents can run neither a script nor a `Write`.
1. **Ask one decision per turn.** The question tool, biggest blast radius
   first, the rest queued. A turn carrying two questions carries none — the
   second gets answered against a guess about the first.
2. **Re-dispatch the same stage's agent**, quoting both the question and the
   answer verbatim in the brief. The agent that comes back has no memory of
   the one that asked, and a paraphrase of an answer is not the answer.
   Carry the round's whole report in that same brief, not only the answers:
   a stage handed back one line re-derives every citation it had already
   established, on whatever tier that stage runs on.
3. **Three rounds at most.** A fourth means the stage cannot be specified by
   asking: record `failed`, `--note` naming what stayed open.

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
