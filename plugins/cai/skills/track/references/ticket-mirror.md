# ticket-mirror — read once, project after every write, quote what was checked

This file is read by the main session directly, never handed to a
dispatched subagent — `SKILL.md`'s "Running a stage" step 3 says so, and
this file assumes it: a subagent has no interactive tools, and ship's
confirmation below needs one. Every command below is
`python ${CLAUDE_PLUGIN_ROOT}/scripts/ticket.py`, run with `--track-dir
.claude/track/<feature>` and `--project-dir <project root>`, the same way
`preflight.py`/`ledger.py` are run in "Running a stage".

Nothing here does anything unless `.claude/cai.json`'s `ticket.enabled` is
true — `ticket.py` checks that itself and prints nothing when it is off
(AC1). The steps below describe what happens on top of that, once it is on.

## Before dispatch: read once

**intake** reads the ticket once, before step 2's dispatch: `ticket.py read
--track-dir ... --project-dir ...`. Its stdout — number, title, body — is
intake's starting point for the problem statement, the same way a pasted
request would be. A read that fails (no pointer yet, an unknown backend, or
the backend call itself) prints one line and still exits 0; treat that the
same as no ticket at all and proceed from the request in the conversation.

**verify**, only when intake was skipped for this track, reads the ticket
the same way, once, immediately before `stage-verify.md`'s Step 1 lens
dispatch — not instead of that dispatch, before it. When the read succeeds,
its body becomes the written requirement handed to the conformance lens, in
place of the plan/issue/user-words `stage-verify.md` normally uses. When it
fails, or the integration is off or unreachable, or intake already ran (so
Step 0 already found a requirement from its ordinary sources), nothing
changes here: `stage-verify.md:47-50` stands as written — say there is no
written requirement and review the other two lenses, rather than inventing
one from a ticket that was never confirmed reachable.

## After every state.md write: project

Every stage row written by "Running a stage" step 3's `passed` path, and
every `/cai:track skip`, is followed by one call: `ticket.py project
--track-dir ... --project-dir ...`. Run it after `state.md` is written,
never before — the comment it renders comes from the row that was just
overwritten. `project()` itself decides whether there is a pointer to
project to, and prints why not when there is none; nothing here needs to
check that first.

## ship: resolve before quoting, and one more confirmation item

Before ship quotes a ticket number anywhere — the commit message, the
release note, the confirmation prompt — resolve it with `ticket.py read
--track-dir ... --project-dir ...` rather than copying whatever `ref` was typed at
`point` time; the two can disagree if `point` was re-run since, and `show` only
echoes the pointer — it never calls a backend, so it cannot confirm the
ticket still exists. The dispatch prompt to the ship stage asks for that resolved
number to appear exactly once in the commit message and exactly once in the PR
body — not copied verbatim from `ref`, since resolving it is the point.

Ship's confirmation before the irreversible operations (`stage-ship.md`'s
human gate) gains one more item, asked separately from the rest: whether to
run `ticket.py project` once more recording ship's own row. A yes to
squashing or publishing is not a yes to this — ask it on its own.

## Never copy stderr into --note

`ticket_backend.py` prints one line per backend call, and that line can
carry whatever the real CLI's own stderr held — a 401 from `gh` includes a
credential-bearing URL. What lands on screen is for whoever is reading the
transcript, not for `--note`: `ledger.jsonl` is append-only and syncs to a
cross-project ledger file, so anything written into `--note` does not stay
on this screen. Summarize a projection failure in your own words — the
category word `ticket.py` already printed (`ok`, `auth-failed`,
`unreachable`, ...) is enough — never paste the line above it.
