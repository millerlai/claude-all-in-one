> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.

# ticket-mirror — read once, project after every write, quote what was checked

This file is read by the main session directly, never handed to a
dispatched subagent — `SKILL.md`'s "Running a stage" step 3 says so, and
this file assumes it: a subagent has no interactive tools, and ship's
confirmation below needs one. Every command below is
`<cai> ticket`, run with `--track-dir
.claude/track/<feature>` and `--project-dir <project root>`, the same way
`preflight.py`/`ledger.py` are run in "Running a stage".

Nothing here does anything unless `.claude/cai.json`'s `ticket.enabled` is
true — `ticket.py` checks that itself and prints nothing when it is off
(AC1). The steps below describe what happens on top of that, once it is on.

## Starting from a ticket

`SKILL.md`'s `$track <feature>` sends you here when its argument contains
`://` or is only digits. That is a ticket reference, and a ticket reference is
not a directory name — a URL cannot be one on Windows at all. So do not create
`.claude/track/<that>/`.

1. **Read it without committing to anything.**
   `ticket.py read --ref <the argument> --project-dir <project root>` — note
   there is no `--track-dir`, because there is no track yet. That is the case
   this subcommand takes a `--ref` for: seeing what a ticket says and starting
   work on it are two decisions, and only the second one needs a directory.
2. **Propose a name from the title.** Lower case, hyphenated, three or four
   words. No ticket number in it — the pointer already carries that, and a
   name that repeats it goes stale the moment the track is re-pointed.
3. **Ask.** If `request_user_input` is in your tool list, ask with it —
   otherwise ask with numbered options in text. Offer the proposed name plus
   an explicit free-text/"other" choice yourself — whether the tool also
   adds one is untested. This directory name appears in every
   `$track status` from here on, so it is the person's to pick, and asking
   costs exactly one menu.

A proposed name here can also close on its own before either ask resolves —
this one and the mirroring-off ask below it are the two places this file
asks for the directory name. `references/approval-gates.md`'s "A menu that
closes on its own" section covers both: a selected option creates and
points the directory the way step 4 describes, and no selection creates
nothing, asking again only after the person next writes.

4. **Create the track under the confirmed name, then point it, before the
   first stage runs.**
   `ticket.py point --track-dir .claude/track/<name> --ref <the argument>`.

   The order matters and nothing enforces it: pointing after `intake` has
   already run means intake never read the ticket, and no later stage says so
   — the track simply runs to the end quietly unlinked, which reads exactly
   like a track that never had a ticket.

Mirroring off for this project means step 1 prints nothing at all (AC1). Say
so and ask for a name, rather than inventing one from a URL you could not
open.

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
written requirement and review the other three lenses, rather than inventing
one from a ticket that was never confirmed reachable.

## After every state.md write: project

Every stage row written by "Running a stage" step 3's `passed` path, and
every `$track skip`, is followed by one call: `ticket.py project
--track-dir ... --project-dir ...`. Run it after `state.md` is written,
never before — the comment it renders comes from the row that was just
overwritten. `project()` itself decides whether there is a pointer to
project to, and prints why not when there is none; nothing here needs to
check that first.

## ship: resolve before quoting, and two more confirmation items

Before ship quotes a ticket number anywhere — the commit message, the
release note, the confirmation prompt — resolve it with `ticket.py read
--track-dir ... --project-dir ...` rather than copying whatever `ref` was typed at
`point` time; the two can disagree if `point` was re-run since, and `show` only
echoes the pointer — it never calls a backend, so it cannot confirm the
ticket still exists. The dispatch prompt to the ship stage asks for that resolved
number to appear exactly once in the commit message and exactly once in the PR
body — not copied verbatim from `ref`, since resolving it is the point.

Ship's confirmation before the irreversible operations (`stage-ship.md`'s
human gate) gains two more items, each asked separately from the rest and
from each other. A yes to squashing or publishing is not a yes to either —
ask each on its own, as its own menu (`references/approval-gates.md`):

1. **The comment** — whether to run `ticket.py project` once more recording
   ship's own row.
2. **Closing the ticket** — asked only once the gate's commands have run.
   When the person picked "Stop — hand me the commands", nothing was merged
   or published, so do not ask: tell the person the ticket stays open.
   Otherwise name the resolved number and ask. On a yes, run
   `ticket.py transition --track-dir ... --project-dir ... --confirmed-by-user`,
   once. On anything else, run nothing.

`--confirmed-by-user` marks that the call came from this answer, and this
answer is the only thing that ever passes it — `approval-gates.md`'s Gate 2
names the same item, and no other stage, subagent, or skill closes a ticket.
`transition` refuses without the flag. It does not
itself prove anyone agreed — the menu above is what does, which is why only
a yes to that menu may add it. When `transition` prints that the ticket is
still open, relay that line to the person: nothing retries it, and it is the
only place they hear about it.

## Never copy stderr into --note

`ticket_backend.py` prints one line per backend call, and that line can
carry whatever the real CLI's own stderr held — a 401 from `gh` includes a
credential-bearing URL. What lands on screen is for whoever is reading the
transcript, not for `--note`: `ledger.jsonl` is append-only and syncs to a
cross-project ledger file, so anything written into `--note` does not stay
on this screen. Summarize a projection failure in your own words — the
category word `ticket.py` already printed (`ok`, `auth-failed`,
`unreachable`, ...) is enough — never paste the line above it.
