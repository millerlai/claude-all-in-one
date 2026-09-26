> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.

# approval-gates — every stop for a person is a menu, never a typed word

This file is read by the main session directly, never handed to a dispatched
subagent — the same arrangement `references/ticket-mirror.md` and
`references/pending-questions.md` already run on, and for the reason those
files state: no subagent can ask the person directly here either, and
a menu is the one thing this file is about.

`SKILL.md`'s "Human gates" says *where* the track stops for a person. This
says *how* it asks, and the answer is the same everywhere: if
`request_user_input` is in your tool list, ask with it — a menu the person
clicks; only when it is not in your tool list, ask with numbered options
in text instead. Either way,
two to four labelled options, the reasoning in full in the same message, before the options (#74).

**Why a menu rather than "reply `approved` when you've read it".** That
sentence fails three ways at once. Typing a word is work, and work at the
exact moment the person is being asked to be careful. The word is not the
question — nobody disagrees by typing `approved`, so the only answer the
prompt is shaped to receive is yes. And whatever comes back is free text, so
"looks fine", a question of their own, and silence all arrive as "not
`approved`" with nothing distinguishing them. A menu makes the answer one
click, makes *no* and *not like that* different answers, and leaves free text
for the case that actually needs it — whether the question tool
(`request_user_input`, or numbered text options when it's absent) adds that
entry itself is untested, so write it in yourself, and "none of these"
never needs one of the four slots.

**Who asks.** Dispatched by the track, a stage cannot voice its own gate: it
stops there and hands it up under `references/pending-questions.md`, and the
main session puts the menu. Standing alone (`$design`, `$build`,
`$ship`) you are the main session — ask directly. The gate does not move;
only who speaks it does.

**One menu per turn**, biggest blast radius first, the rest queued —
`epistemics.md`'s rule, and the reason two of the items below are asked
separately from the thing they look attached to.

## Gate 1 — the design sign-off, after `design` and before any code

**What is being signed.** The `design` stage writes more than one document
(`stage-design.md`), and they are not all signed here. What a person signs is
the **stance** and the **answered Tier 1 decisions** — the two that were
written to be read in full. The build spec is not signed: it is written for
whoever builds, nobody reviews it line by line, and pretending otherwise is
how a signature comes to mean "I gave up reading". Name the stance and
decisions documents in the menu's message; name the build spec as the thing
this authorises, not as the thing being read.

That split is also what keeps re-signing possible. A change to a signed
document invalidates the signature, so what gets signed has to stay small
enough to sign again — which is why those two carry ceilings the probe
enforces and the build spec does not.

What the Approve's ledger row fingerprints is a third thing: the document in
the track's design row, which is what `build` reads — the build spec when
Detail ran (`stage-design.md`, "Which path goes in the track's `design`
row"). The person reads the stance and the decisions; fingerprinting the
build spec is what makes the authorisation stick. An edit to it after the
Approve re-opens the gate, and re-signing stays cheap: what the person
re-reads is still those two small documents.

Say the documents' paths, then ask. Nothing in `build` starts until this is
answered: `preflight.py build` refuses to start unless a `passed` record with
`gate: human` carries the sha256 of the design row's document as it stands —
so skipping this menu is caught by the gate itself, and so is an edit to that
document after it. Where that record sits on the ledger does not matter:
handed up as a pending question, it lands before the stage's own `passed`
row, and that is fine. An approval of any other document does not stand in
for this one — the stance approval is not Gate 1.

| Option | What it does |
|---|---|
| Approve | Where the design row's document has a `## Status` of its own (a diagnosis, a legacy high-level design), write `approved <YYYY-MM-DD>` into it **first**, then append the ledger row; elsewhere, only the row. The row is `--gate human --artifact <that document>`. `build` may start. |
| Changes requested | Re-dispatch `design` with what they said, quoted. Counts as one of that stage's three rounds. |
| Reject | The design stops here. Record the outcome and what was rejected; build nothing. |

**That order is not a preference.** `ledger.py append --artifact` takes a
sha256 of the document as it stands at that moment, and `preflight.py build`
refuses to start against anything else — so writing the date after the row is
recorded fingerprints a `draft` and then invalidates it with the very edit
that marks it approved. This repo has been here once already, from the other
direction: `tests/test_preflight_build_gate.py`'s opening paragraph. "Running
a stage" step 3's own ordering — ledger first, then the `state.md` row — is
untouched by this and stays as written; it is about the track's table, not
about the document being signed.

The writer is you, the main session. `stage-design.md` step 6's "never set it
yourself" is addressed to the stage that produced the document, and it still
holds: what changes `draft` to `approved` is a person picking Approve here,
never the design stage deciding its own work is done.

**No `(recommended)` on either gate's menu**, and this is a deliberate
exception to `epistemics.md`, which asks every question tool for "the
recommended one first and said to be". That rule is for a choice between ways
forward, where a wrong pick costs a rewrite and withholding what you know is
unhelpful. A gate is not that: what is being signed off is your own output,
so a recommendation here is you grading your own work and putting a thumb on
the scale at the one moment the person is being asked to be sceptical. The
stops in the last section are ordinary choices and do carry a recommendation
— the carve-out is the two gates, not the file.

## Gate 2 — before `ship`'s irreversible operations

Quote the exact commands about to run — merging, tagging, publishing, a
force-push — and what each one makes public. "Confirm the release?" is not
this question; the commands are.

| Option | What it does |
|---|---|
| Run them | Checked once more first, then they run, in the order quoted — see below. |
| Stop — hand me the commands | Nothing runs. Report them for the person to run themselves. |

**Before "Run them" runs anything, inside a track**, the base branch may have
moved since `ship`'s preflight read it, and a branch that no longer merges
cleanly opens a PR that GitHub marks conflicting and runs no CI on. So you —
the main session, before dispatching anything — run these two, in order:

```
git fetch origin
<cai> preflight ship --track-dir .claude/track/<feature> --project-dir <project root>
```

- **Exit 0** → the quoted commands run. If the fetch failed, say so with the
  first line of its error: the check then used what the last fetch saw.
- **Exit 2** → none of the quoted commands runs. Report every `FAIL` line to
  the person, and record `ship` as `blocked` (`--gate auto`) with `--note`
  quoting them, the way `SKILL.md`'s "Running a stage" step 3 records a
  preflight exit 2 — unless a line is `FAIL ledger_attempts`, which is
  reported without appending. `state.md`'s ship row does not change.

"Stop — hand me the commands" hands over the quoted commands only, not
these two.

**Standing alone** (`$ship`, no track), there is no `state.md` for
`preflight.py ship` to read, so neither runs: the quoted commands run as
quoted, and you say in one line that the merge with the base branch was not
checked.

Three more confirmations sit beside this one and are asked on their own
turns, because a yes to publishing is not a yes to any of them:

- **The squash**, `stage-ship.md` Step 4 — show the drafted commit message
  and ask before rewriting history.
- **The ticket comment**, `references/ticket-mirror.md`'s ship section —
  whether to run `ticket.py project` once more for ship's own row, only when
  mirroring is on.
- **Closing the ticket**, the same section — only when mirroring is on, and
  only after "Run them" above has run. Offer "Close #<number>" and "Leave it
  open", no `(recommended)`: this is part of the gate. Only the first runs
  `ticket.py transition --confirmed-by-user`; the second runs nothing.

## The other stops, which are not gates

`SKILL.md` names exactly two gates and this file does not add a third. These
stops already exist in their own stage references; what they take from here
is only the shape — a menu, never a sentence to type a word back into:

- `stage-intake.md` Step 5 — the problem statement, the route Step 2 derived
  (broken, or never there) with its evidence, and the recommended approach,
  before anything is designed.
- `stage-design.md`'s cost-sizing — the four lines, before a pass that reads
  a whole directory.
- `stage-design.md`'s stance approval, at the end of Stance mode. Decisions
  mode refuses to start on a `draft`, so this is a real stop — but it is
  inside the `design` stage, not after it, which is why it is here and not a
  third gate. Same three options as Gate 1, and the same writer: the date
  goes into `## Status` when a person picks Approve, never when the stage
  decides its own work is done.
- `stage-design.md`'s diagnosis sign-off, when Detail follows it. The root
  cause is approved there, in `## Status`, with no ledger row; Gate 1 comes
  after Detail, on the detail design. Going straight to `build`, the same
  stop is Gate 1 itself.
- `stage-design.md`'s Tier 1 entries, in Decisions mode — one menu per entry,
  in dependency order, re-running the cost test on what remains after each
  answer. These are ordinary choices between ways forward, so unlike the two
  gates they **do** carry a `(recommended)` when the evidence supports one.
- `stage-build.md` Step 0.5 — commit per unit, the parallel lane, and, for a
  detail design whose glossary has project terms, which of them join
  `CONTEXT.md`. Up to three decisions, so up to three turns.

Their options are whatever that stage's own text already offers. The rule
here is the shape and the free-text slot, not a vocabulary.

## A menu that closes on its own

Whether the question tool ever closes a question on its own is untested on
this platform. A question result that comes back saying the person did not
answer it is what this section calls a timed-out menu, handled as the rest
of this section describes.

A timed-out menu never becomes the person's answer by default. What each stop
in this file does about one:

| Stop | On timeout |
| --- | --- |
| Gate 1 | Nothing is written. No `approved`, no `--gate human` row. `build` does not start. |
| Gate 2, the squash, the ticket comment, closing the ticket | None of it runs. |
| Step 0.5 commit per unit | Treated as no, so the parallel lane stays off. |
| Step 0.5 parallel lane | Whichever option the result reports as selected, still gated by `stage-build.md` Step 4's three conditions; sequential when the result reports nothing selected. |
| Step 0.5 glossary | No project term joins `CONTEXT.md`; the file is left untouched. |
| The track-directory name (`ticket-mirror.md`) | Whichever name the result reports as selected; left unanswered when the result reports nothing selected. |
| Every other stop in this file's list, or handed up under `pending-questions.md` | Left unanswered. |

A timed-out menu left unanswered above is not skipped — it is not an answer,
and nothing downstream may treat it as one. Nothing about it is acted on or
written, nothing is re-dispatched because of it, and it does not spend a
round of `pending-questions.md` — no round runs against a menu that closed on
its own. Any question queued behind it waits with it, in the same order it
was already in. The menu is asked again only after the person next writes,
never inside the same turn the timeout arrived in. Text typed into the
free-text entry before the clock ran out still counts as nothing selected,
the same as if the person had never touched the menu — a partial draft is not
a pick. When a result reports nothing selected, Claude never substitutes the
`(recommended)` option as if the person had chosen it — a recommendation is a
suggestion for a person to accept, not a default Claude reaches for on a
timeout's behalf. That is not the same as the two rows above that already use
whichever option a timeout does report selected, recommended label or not.

Because a timed-out menu can pass silently otherwise, the run says one line
per menu that timed out, naming the stop and the outcome applied above. At
the two stops where a selected option is used rather than left unanswered —
the parallel lane and the track-directory name — that line also names the
option used, since the result reporting an option "selected" may just be
reporting wherever the cursor happened to be resting, not a real choice.
Nothing here turns the setting on, and the track does not need it on to run;
it only has to know what to do the day it happens to be.
