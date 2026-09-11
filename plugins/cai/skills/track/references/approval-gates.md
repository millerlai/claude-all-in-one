# approval-gates — every stop for a person is a menu, never a typed word

This file is read by the main session directly, never handed to a dispatched
subagent — the same arrangement `references/ticket-mirror.md` and
`references/pending-questions.md` already run on, and for the reason those
files state: the platform removes `AskUserQuestion` from every subagent, and
a menu is the one thing this file is about.

`SKILL.md`'s "Human gates" says *where* the track stops for a person. This
says *how* it asks, and the answer is the same everywhere: `AskUserQuestion`,
two to four labelled options, the reasoning in the message above it (#74).

**Why a menu rather than "reply `approved` when you've read it".** That
sentence fails three ways at once. Typing a word is work, and work at the
exact moment the person is being asked to be careful. The word is not the
question — nobody disagrees by typing `approved`, so the only answer the
prompt is shaped to receive is yes. And whatever comes back is free text, so
"looks fine", a question of their own, and silence all arrive as "not
`approved`" with nothing distinguishing them. A menu makes the answer one
click, makes *no* and *not like that* different answers, and leaves free text
for the case that actually needs it — `AskUserQuestion` adds that entry
itself, so it is never an option you write, and "none of these" never needs
one of the four slots.

**Who asks.** Dispatched by the track, a stage cannot voice its own gate: it
stops there and hands it up under `references/pending-questions.md`, and the
main session puts the menu. Standing alone (`/cai:design`, `/cai:build`,
`/cai:ship`) you are the main session — ask directly. The gate does not move;
only who speaks it does.

**One menu per turn**, biggest blast radius first, the rest queued —
`epistemics.md`'s rule, and the reason two of the items below are asked
separately from the thing they look attached to.

## Gate 1 — the design sign-off, after `design` and before any code

Say the document's path, then ask. Nothing in `build` starts until this is
answered, and `preflight.py build` fingerprints whatever was signed off, so
the answer is load-bearing rather than ceremonial.

| Option | What it does |
|---|---|
| Approve | Write `approved <YYYY-MM-DD>` into `## Status` **first**, then append the ledger row. `build` may start. |
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
| Run them | They run, in the order quoted. |
| Stop — hand me the commands | Nothing runs. Report them for the person to run themselves. |

Two more confirmations sit beside this one and are asked on their own turns,
because a yes to publishing is not a yes to either:

- **The squash**, `stage-ship.md` Step 4 — show the drafted commit message
  and ask before rewriting history.
- **The ticket**, `references/ticket-mirror.md`'s ship section — whether to
  run `ticket.py project` once more for ship's own row, only when mirroring
  is on.

## The other stops, which are not gates

`SKILL.md` names exactly two gates and this file does not add a third. These
stops already exist in their own stage references; what they take from here
is only the shape — a menu, never a sentence to type a word back into:

- `stage-intake.md` Step 4 — the problem statement and the recommended
  approach, before anything is designed.
- `stage-design.md`'s cost-sizing — the four lines, before a pass that reads
  a whole directory.
- `stage-build.md` Step 0.5 — commit per unit, and the parallel lane. Two
  decisions, so two turns.

Their options are whatever that stage's own text already offers. The rule
here is the shape and the free-text slot, not a vocabulary.
