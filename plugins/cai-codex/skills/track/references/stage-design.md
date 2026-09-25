> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.

# stage-design — decide what to build, before code exists

This file is read two ways: by the subagent the track dispatches to run this
stage, and by `$design` when someone runs the stage standing alone, with
no track underneath it. The procedure below is the same either way.

**Asking is the one thing that is not.** Dispatched by the track you are a
subagent, and no subagent can ask the person directly here either.
Each mention of the question tool below then means: finish
what the answer does not block, and end the report with the
`## Pending questions` section `references/pending-questions.md` specifies.
Standing alone you are the main session — ask directly.

The failure this stage exists to catch is a design that arrives already
committed — plausible, detailed, and resting on an architecture nobody was
asked about, or on a capability nobody checked was actually available.

## Pick a mode, and say which

- **Diagnosis** — something is broken. Names the root cause and the fix, one
  page. Entry condition below; it is not "someone called it a bug".
- **Stance** — the trade this system makes: what it optimises for, what it
  gives up, and the invariants nothing later may violate. One page, read in
  full by a person.
- **Decisions** — the queue of choices that trade implies, each one routed by
  the three tests below so that only what needs a person reaches one.
- **Detail** — turns an approved stance and its answered decisions into a
  document that can be built from without coming back to ask what you meant.
- **Delta** — the branch is already built. Recovers the decisions from the
  diff and the commits instead of deciding anything.

**Diagnosis and Stance are the two entrances, and one test picks between
them** — the same one `stage-intake.md` runs to route the work:

> Can you write a test that fails now and would pass if an existing promise
> held?

A promise is an existing test, the documentation, a spec, or an invariant.
Never anyone's expectation: an expectation nobody wrote down is a
requirement, and requirements are Stance's problem.

- **Yes** → something is broken. Diagnosis.
- **No, because nothing ever promised it** → it was never there. Stance.

Do not route on the words the request arrived in. "Add a retry" sounds like a
feature and its root cause is often a misconfigured pool, where the retry
treats the symptom — and the ticket's wording never says so.

After either entrance, the rest is shared: Decisions where choices survive,
then Detail. Delta only applies when code already exists and nobody wrote
down why it looks the way it does.

**Why these are three documents and not one.** A document that has to be read
before a decision and a document that has to be complete enough to build from
pull in opposite directions: the first fails by being long, the second by
being short. One file serving both ends up too long to read and still not
enough to build from — which is what the old single high-level design became,
and why it stopped being reviewed in full.

**High-level** is that old shape, still accepted (`--kind hld`) so documents
already signed off stay passable. Do not write a new one.

## Say what it will cost, then wait

Before any mode starts, four lines: the document path and the headings it
will carry; how much of the target directory has to be read and how many
documentation sources fetched; what is already unclear enough that you will
have to ask; and what this will not decide. Then wait for a go — asked as a
menu, never as a sentence to type a word back into
(`references/approval-gates.md`).

Detail mode is the longest and the one most worth sizing — it reads the whole
target directory and renders every diagram. A pass that expensive should not
begin on an assumption that it was wanted. Stance mode is the cheapest, and
sizing it is still worth the one line: it ends at a human gate, so starting it
unbidden spends the person's attention, not just tokens.

## The two rules every deciding mode obeys

**The evidence rule.** Every sentence about how something currently
behaves — this codebase, a library, a platform API — carries its source: a
`file:line`, or a documentation URL plus the sentence relied on.

Three sources count, and nothing else does:

- **This project** — locate and quote the relevant lines yourself with
  `Read`/`Grep`/`Glob`, then decide what they mean; a scout's summary
  would only be a pointer, not evidence.
- **Official documentation** — for any tool, framework, or platform the
  design stands on, hand the fetch up as a `## Pending questions` item
  (a request, not a decision) and wait for the main session to dispatch
  a web-capable helper and return what it found, then interpret it
  yourself. Record the URL and the sentence taken.
- **Neither** — write `UNVERIFIED`, and name the design decision that stops
  standing up if the guess turns out wrong.

What does not count: what you remember about the library, what a function's
name implies, what a similar project usually does, "standard practice".
Catching yourself writing *typically*, *generally*, *should be able to*, or
*presumably* means you are writing `UNVERIFIED` in a longer form.

**The decision rule.** Never resolve a choice silently in either direction.
Writing your preference in is a decision the person never made; leaving
something out because they did not ask for it is the same decision with the
opposite sign.

That does **not** mean every choice goes to the question tool. Asking about
all of them spends, on the seventeen that did not need it, the attention the
three that did were going to get. Which choices reach a person is decided by
the three tests below; every other choice is still recorded, in the tier it
landed in, never nowhere.

**One decision at a time, biggest blast radius first** — the same ordering
`stage-discover.md`'s interview move uses.

## The three tests

Run them in order on every choice. The first two are gates — a choice that
trips one leaves this queue. Only the third routes.

**1. The conflict test.** Does this option violate an invariant in the stance?

Violating one the system set for itself sends the whole thing back to Stance
mode: the trade is being changed, and that is not a decision to make one
implementation detail at a time. Violating a cross-project one is not a
re-open at all — that road is closed, find another.

Either way the option is **deleted, not weighed**, and lands in the decisions
document's `## Ruled out` with the invariant it hit. It does not become an
option a person is shown. Mixing deleted options into a tier fills the tier
with things nobody may pick.

**2. The origin test.** Is this option's failure condition a technical fact,
or an assumption about how people behave?

- *"the library's double-click event carries no timestamp"* — technical. Keep
  it, go to test 3.
- *"the operator stops looking at the screen after pressing"* — behavioural.
  This is not a design decision. It is a requirement nobody settled, wearing a
  design decision's clothes.

Behavioural ones go to `## Requirement gaps` with one of two exits: a **veto
condition** — the requirement rewritten so it can delete options ("the chart
must stay visible while a verdict is in flight"), which usually removes half
the options and sometimes the whole decision; or a **verification path** —
who can settle the assumption and how. An assumption with neither is a guess,
and a guess may not be used as grounds.

When *every* option in one choice fails this test, send the whole choice
back rather than splitting it — those options are betting on opposite
behaviours, so what is missing is the requirement, not the design. A choice
mixing both kinds splits into two: the behavioural half goes back, the
technical half goes to test 3.

**3. The cost test.** What does it cost to undo this if it is wrong?

| | Low | High |
|---|---|---|
| Blast radius | one component | more than one |
| Found out when | next test run | after release, after data accumulates, when a user reports it |
| Undo cost | just change it | migrate data, change a published contract, make users relearn |

Anything unanswerable counts as **high** — in a new domain "when would we
find out" is often unknown, and guessing low is how an unbounded risk gets
filed as routine. Credentials, personal data, and who is allowed to do what
are high on the third row by default: asking costs a question, choosing wrong
costs an incident.

**All three low** → the builder decides. One row in `## Tier 3`, searchable,
never shown for review.
**Any one high** → a person sees it, in one of two tiers below.

## The two tiers, and cutting the entries right

**Before tiering, check the choice is one choice.** The commonest miscut is a
cost column that raises a question and then does not answer it ("which of
these two is the source of truth needs saying"). That is a second decision
hiding inside the first: **a cost column that poses a question with no answer
is an entry of its own — split it out.** Unsplit, the host may be the only
survivor of its options (Tier 2, scanned) while the passenger is three-rows-
high (Tier 1, answered), and the pair gets waved through together. On a solo
project there is no second reviewer to catch that.

- **Tier 1 — answered.** High cost, *and* the options differ in substance.
  Ask one at a time. At most `TIER1_MAX` (5).
- **Tier 2 — scanned.** High cost, *but* the evidence leaves one live option.
  Three lines each, shown all at once; the person answers nothing unless they
  want to overturn something. At most `TIER2_MAX` (10).

**The bar for Tier 2 is a citation, not a preference.** If the grounds are not
a `file:line` or a documentation URL, the entry does not qualify: get the
evidence, or move it to Tier 1 and let a person decide. `design_probe.py`
enforces this, because nothing reviews what is scanned.

**Order Tier 1 by dependency**, not by size: whichever answer changes the
*options available* to other entries goes first. After each answer, re-run the
cost test on what is left — entries routinely drop to Tier 2 or Tier 3 once an
earlier one lands. If nothing drops, these decisions do not constrain each
other, which is worth saying out loud.

**Over budget is not a formatting problem.** It says the design has not
converged — a stance that was never settled, so every entry re-argues it, or
boundaries that split one decision into five. Stop and re-cut rather than
asking the person to read more. The two ceilings are starting values: the way
to calibrate them is to ask, once, whether the last round was actually read in
full, and lower them when the answer is no.

## Mode: Diagnosis

0. **Write the failing test first.** Not after the cause is found — first. It
   is this mode's entry condition, and writing it is what checks the routing
   rather than trusting it. Name which promise it tests against: an existing
   test, the documentation, a spec, an invariant.

   **Cannot write one, because nothing ever promised this?** Stop. This is
   Stance mode's work, and continuing here would produce a root cause for a
   behaviour that was never guaranteed. Say so and hand the routing back.

1. **Find the cause, not the line.** Run `$debug`'s steps 1–4 —
   reproduce on purpose, read the trace and what changed recently, instrument
   the boundary on a multi-component system, one hypothesis and one small
   test at a time. That file owns the procedure; this mode owns the document
   it produces, and does not restate it.

   The rule that matters here is its first one: **no fix before the root
   cause is found and stated.** This mode is where "stated" gets a reader.

   **Inside a track, steps 1–4 sometimes need a command or a temporary
   change `cai_designer` cannot run itself** — Step 1's reproduction command,
   Step 3's tagged boundary log, or Step 4's one small test. `cai_designer`'s
   own Bash is `python`/`py`/`python3`/`mmdc` only, and it writes no code
   (`designer.md`). This does not apply standing alone: outside a track
   this stage is the main session, and it already runs everything itself.

   Hand it up as a `## Pending questions` item, worded as a request rather
   than a decision, with two options: run it as written (recommended), or
   don't — leave diagnosis at Step 1's "write down what you tried and stop
   here, at reproduction" (`debug/SKILL.md`), with nothing filled in
   afterward. Name every command in full, every tagged log's `file:line`
   and the line to add there, every Step 4 temporary change's `file:line`
   and its edit, and which outputs to bring back — everything this pass can
   already name, in one item, since each hand-up spends one of
   `pending-questions.md`'s three rounds. Told to run it: add the logs and
   temporary changes, run the commands, revert both back to what they were,
   grep the tag for zero hits, redact the output per `debug/SKILL.md`'s
   redact rule, and carry that output unchanged into the next pass. Refused,
   or a command will not run at all: diagnosis stays at reproduction, per
   Step 1's own rule — nothing is invented in its place.

2. **Write it.** Unless the person named a path:
   `docs/design/<YYYY-MM-DD>-<topic>-diagnosis.md`, date from `date +%F`.
   Copy `<cai-root>/templates/design-diagnosis.md.tpl`, fill it
   in, delete the HTML-comment guidance as you answer it. Do not add or
   rename headings.

   `## Root cause` answers one question beyond naming the cause: **what would
   still be true if you fixed the line the stack trace points at?** "The same
   thing could happen again through another path" means you have a symptom
   and the cause is further up. `## Blast radius` is what turns one fix into
   the right fix — the second caller found there is the ticket that would
   otherwise come back in three weeks.

3. **One diagram, and render it.** `## Picture` draws the path and marks
   where it goes wrong. That is what a reader checks the cause against, and
   it is faster than the same claim in prose. Same rules and same `mmdc`
   check as the other modes, and a sentence under it saying what to look at.

4. **Escalate rather than decide.** If the fix needs an architecture-level
   choice, or two approaches both survive the evidence, or the cause lands on
   an invariant — stop and hand it up to Stance mode. `$debug`'s "after
   three fixes fail, question the design" is the same escalation seen from
   the other side.

   **That escalation is one-way and gets recorded.** Diagnosis → Stance is
   common (a small bug turns out to be a design problem); the reverse
   essentially never happens. How often a track escalates is the most direct
   reading available of how vague this system's design intent is.

5. **Check, then review.**
   `<cai> design_probe --kind diagnosis <the document>`
   until it exits 0, then `plan-review` against it.

6. **Stop.** `## Status` stays `draft`. What the person signs here is **the
   root cause**, not the fix: a wrong cause makes every fix downstream of it
   wrong, and that is the one judgement a person makes better than the
   evidence alone. Same menu as the other entrance
   (`references/approval-gates.md`).

   After sign-off the work goes straight to Detail when the fix touches more
   than a couple of files, or to `build` when it does not — Decisions has
   nothing to route, because a diagnosis with real options escalated at
   step 4 instead. Going to `build`, this stop is Gate 1: the diagnosis is
   the design row's document, and the Approve fingerprints it. Going to
   Detail, it is a stop inside `design`, like the stance approval — the date
   goes into `## Status`, no ledger row — and Gate 1 comes after Detail, on
   the detail design the design row then names.

## Mode: Stance

1. **Read before you write.** Whatever the trade touches — the existing code,
   the platform, the library — settle it under the evidence rule first. A
   stance written from what you remember is a guess a person is being asked to
   sign.
2. **Write the trade, all four parts.** Unless the person named a path:
   `docs/design/<YYYY-MM-DD>-<topic>-stance.md`, date from `date +%F`. Copy
   `<cai-root>/templates/design-stance.md.tpl`, fill it in, delete
   the HTML-comment guidance as you answer it. Do not add or rename headings.
   - `## Optimises for` is one or two sentences. Optimising for everything
     rules out nothing, and a stance that rules out nothing deletes no options
     later — which is the entire job it has.
   - `## Sacrifices` is the heading that decides whether this survives the
     next person. Without it they will "fix" the slowness, the missing view,
     the extra click, not knowing it was bought.
   - `## Invariants` splits two ways. **This system's** come from the trade.
     **Cross-project** ones are true of every project here and unchanged by
     this request — the person's own rules file, the platform's limits, what
     the test environment can actually observe. Reference those, never restate
     them. An empty list switches the conflict test off.
   - `## Rejected stances` needs at least one. "There was no alternative" is
     what gets written when nobody looked.
3. **The trade is the person's, not yours.** Which way it goes — what gets
   optimised and what gets given up — is the largest decision in the whole
   design. Put it to them with the question tool rather than writing your
   preference in and asking them to approve it.
4. **One diagram, and render it.** `## Overview` carries the shape the stance
   implies — main flow, or before/after when this changes something that
   exists. Not the component graph; that belongs to the build spec. Per
   `documentation.md`: elk renderer, quoted labels, `classDef` colouring for
   what changes. Validate by rendering:
   `mmdc -i <the document> -o <scratchpad>/check.md`. A sentence under it says
   what to look at — a diagram with no reading is decoration.
5. **Check, then review.**
   `<cai> design_probe --kind stance <the document>`
   until it exits 0. It enforces the one-page ceiling; over it, cut, do not
   reword. Then `plan-review` against the document.
6. **Stop.** `## Status` stays `draft`. Only the person's approval changes it
   to `approved <YYYY-MM-DD>`, through the menu in
   `references/approval-gates.md`. Decisions mode reads that line and refuses
   to start on a draft.

## Mode: Decisions

0. **The gate.** Open the stance document and check, in the file: `## Status`
   reads `approved` with a date, `## Invariants` is non-empty,
   `## Use cases / Issues` numbers its entries. Any failing, stop and say
   which. Weighing options against a trade nobody agreed to is how a stance
   gets replaced one implementation detail at a time.
1. **Feasibility, before any option.** Every capability this design needs,
   settled under the evidence rule in a table: `C1`, `C2`, …, Capability,
   Verdict (`verified`/`UNVERIFIED`/`infeasible`), Evidence. The ids are
   load-bearing — the probe fails a capability no entry cites, and a Tier 2
   entry resting on one that is not `verified`.
2. **List every choice, then run the three tests on each**, in order. Write to
   `docs/design/<YYYY-MM-DD>-<topic>-decisions.md`, same `<topic>` as the
   stance. Copy `<cai-root>/templates/design-decisions.md.tpl`,
   same heading discipline.
   - conflict test → `## Ruled out`, with the invariant it hit;
   - origin test → `## Requirement gaps`, with a veto condition or a
     verification path;
   - cost test → `## Tier 1`, `## Tier 2`, or `## Tier 3`.
3. **Draw every Tier 1 entry.** One small Mermaid diagram per entry, showing
   the options side by side — this is the one place a person is asked to hold
   two designs in their head at once, and two pictures do that faster than two
   columns of prose. Same rules and same rendering check as Stance mode.
4. **`Found out when` is never blank.** It is what lets a person read fast: an
   entry a test catches tomorrow is scanned, one that surfaces after a
   migration is not. Unknown counts as late, not as low.
5. **Check, then ask.**
   `<cai> design_probe --kind decisions <the document>`
   until it exits 0 — budgets, citations and diagrams are all mechanical, so
   fix them before spending any reading on review. Then `plan-review`, then
   put Tier 1 to the person with the question tool, **one at a time, in
   dependency order**, re-running the cost test on what remains after each
   answer.
6. **Report the gap count.** The probe prints `requirement_gaps (N this
   round)`. Three or more for three rounds running means the requirements
   stage is what needs fixing, not this document — say so rather than
   absorbing it again.

## Mode: High-level (legacy)

Kept so that designs already signed off in this shape stay passable. New work
runs Stance then Decisions instead. The procedure below is unchanged.

1. **Feasibility, before the document.** List every capability the design
   needs and settle each under the evidence rule in a table: `C1`, `C2`, …,
   Capability, Verdict (`verified`/`UNVERIFIED`/`infeasible`), Evidence. The
   ids are load-bearing — `design_probe.py` fails the document if a
   capability is cited by no option, or a recommended option rests on one
   that is not `verified`.
2. **Use cases and issues.** Number them (`UC1`, `R1`, …) so a later
   traceability table has something to point at. Any requirement you would
   otherwise invent goes to the question tool.
3. **Compare options, then ask.** At least two real options per
   architecture-level choice, each citing the `C<n>` ids it rests on, why
   it's possible here, what it costs, how it fails. Mark at most one
   `(recommended)`, only if every capability it cites is `verified`. Lay each
   one out in `option-explainer.md`'s six-field shape — a title line, then the
   six numbered, one per item — write it to `<track-dir>/options-<id>.md`
   (`<id>` from the choice being decided, e.g. `options-D1.md`) and check it
   before it goes anywhere:
   `<cai> options_lint <the options, as a file>`,
   exit 0 or fix what it names (#73). Then put the choice to the user with
   the question tool — one decision at a time, biggest blast radius first.
   Escalate to `cai_architect` (think tier, read-only) only when a choice
   genuinely spans several subsystems or turns on
   concurrency/consistency/migration ordering the evidence could not settle.
4. **Write it.** Unless the user named a path:
   `docs/design/<YYYY-MM-DD>-<topic>-high-level.md`, date from `date +%F`,
   `<topic>` spelled out. Copy
   `<cai-root>/templates/design-high-level.md.tpl`, fill it in,
   delete the HTML-comment guidance as you answer it. Do not add or rename
   headings. Two Mermaid diagrams (main flow, components) per
   `documentation.md`. Validate by rendering:
   `mmdc -i <the document> -o <scratchpad>/check.md`. `## Status` starts
   `draft`.
5. **Check, then review.**
   `<cai> design_probe --kind hld <the document>`
   first — fix what it reports and re-run until it exits 0. Then invoke
   `plan-review` against the document with the high-level skeleton, running
   lens 8 (Precision) last. Fix Blocker/Major, take section 4 to
   the question tool. At most three rounds.
6. **Stop.** Hand it over with `## Status` still `draft`. Only the user's
   approval changes it to `approved <YYYY-MM-DD>` — never set it yourself.
   That approval is the track's first human gate, and it is asked as a menu
   with three options: `references/approval-gates.md` holds them, and says
   who writes the date once Approve comes back.
   Before handing over, check the draft carries no signature, schema, file
   path for code that doesn't exist, pinned version, or pseudocode — those
   belong in the detail design.

## Mode: Detail

0. **The gate.** Open the documents this elaborates and check, in the files:
   the stance's `## Status` reads `approved` with a date and its
   `## Use cases / Issues` numbers its entries; the decisions document's
   `## Tier 1` entries each carry a `Decided:` line. Any failing, stop and say
   which. (A legacy high-level design instead: `## Status` approved,
   `## Open questions` empty or every entry answered, use cases numbered.)

   An unanswered Tier 1 entry is an architecture question this document would
   otherwise settle by accident, one implementation detail at a time.
1. **Ground it in the real directory.** Read the target project directory;
   every claim about existing code resolves to a real `file:line` you have
   opened. Write to `docs/design/<YYYY-MM-DD>-<topic>-detail.md`, same
   `<topic>` as the stance. Copy
   `<cai-root>/templates/design-detail.md.tpl`, fill it in, same
   heading discipline as the modes above.
2. **Four tables before any prose:** the `## Reference` block (path + status
   line the probe follows), the traceability table (every `UC`/`R` id vs.
   what satisfies it here), the glossary (every load-bearing term, its
   definition, `file:line`/`new — path`/`concept`), the budgets table
   (every quantity, and the `Number` column must contain an actual number —
   an unknown one comes from the user under the decision rule).
3. **Four diagrams**, Mermaid: architecture, component, flow, and one
   sequence per use case (past six, name which were skipped and why).
   Validate by rendering. **Each one carries a sentence under it** naming what
   to look at — the boundary that moved, the arrow that reversed, the box that
   is new; a diagram with no reading is decoration, because the author already
   knows what is interesting in it and the reader does not. A diagram that
   explains one component goes in that component's block in step 4, not here:
   this section holds the four that describe the whole.
4. **The implementation spec.** Per component: Responsibility (one
   sentence), Interface (real signature), Data (shape in/out, types),
   Errors, Concurrency, Observability, Where it lives, What it reuses
   (`file:line`).
5. **`## Naming`.** Every name the implemented system creates, spelled out
   always. A name you invent is a decision — ask for it via
   the question tool rather than writing it in.
6. **Three sections a component spec doesn't contain:** `## Rollout`
   (ship in pieces? migration/backfill? what breaks in flight? rollback),
   `## Verification` (criterion / level / what it needs / green before),
   `## Work breakdown` (unit / depends on / can run alongside / done when —
   cut where Step 4's interfaces already cut them, riskiest unit with no
   unmet dependency first). Record upstream blockers here too. Deviations
   during the build follow the format `stage-build.md` defines.
7. **What you could not pin down** → the question tool under the decision
   rule, one at a time, biggest blast radius first. A confident guess is
   worse than an open question.
8. **Check, then review.**
   `<cai> design_probe --kind detail --project-dir <target project dir> <the document>`
   first, fix and re-run until 0. Then `plan-review` with the detail
   skeleton, lens 8 first. Blocker/Major → fix and re-probe *and* re-review;
   section 4 → the question tool; Minor → leave documented. At most three
   rounds; past that, stop and report what's open with a recommendation.

## Mode: Delta

This is deliberately **not** the two rules above — the changes already
shipped, so there is nothing left to ask about. This mode runs start to
finish without stopping.

**The evidence rule (delta variant).** Every sentence about why something
was done carries its source: `file:line`, a documentation URL, or the
commit that says it. Three sources count: the diff and code around it, the
branch's own record (commit messages, PR description, comments the change
added), or neither — write `UNVERIFIED` and leave it in the document. An
invented but plausible reason is worse than a blank: it outlives everyone
who could have corrected it.

1. **Fix the scope.** Find the base ref (given, or
   `git symbolic-ref --short refs/remotes/origin/HEAD`, or `origin/main`).
   Then `git merge-base HEAD <base-ref>` and
   `git diff --stat <branch-point>...HEAD`, as separate commands — never
   piped through shell variables, `sed`, or `${VAR:-default}` on Windows.
   An empty or fully-generated diff stops here.
2. **Read the diff.** `git log --oneline <BASE>..HEAD` and
   `git diff <BASE>..HEAD`, opening surrounding files wherever the diff
   alone doesn't show what a change implies.
3. **Recover the why**, before writing anything: full commit message bodies
   (`git log --format=%B <BASE>..HEAD`), the PR description
   (`gh pr view --json title,body`), comments the change added, any design
   document the branch implements. List the deliberate choices found and
   whether these sources actually explain them — that becomes
   `## Decisions`. Three real rows beat nine padded ones.
4. **Write it.** `docs/design/<YYYY-MM-DD>-<topic>-delta.md`. Copy
   `<cai-root>/templates/design-delta.md.tpl`. `## Before /
   After` takes two Mermaid diagrams (not one — a single end-state picture
   is something the reader could have drawn from the code).
5. **Validate the diagrams** by rendering, same as the other modes.
6. **Check it mechanically.**
   `<cai> design_probe --kind delta <the document>`,
   fix and re-run until 0. `## Scope` needs one sentence of at least 20
   characters — a bare `a3f21bc..HEAD` reads as empty, not short.
7. **Hand it over.** Say where the document is, and count the `UNVERIFIED`
   rows out loud — that number is the list of things only the author knows.
   Do not merge, push, or commit anything; this mode reads and writes one
   file.

## The gate every mode shares

`plan-review` plus `<cai-root>/scripts/design_probe.py` are the
gate. The probe is free and answers only what has one answer — run it
before spending any reading on `plan-review`'s findings. This is the design
gate `track`'s human checkpoint sits on: nothing after this stage starts
until a person signs off on the design artifact, through the menu
`references/approval-gates.md` describes.

Each mode has its own `--kind`: `diagnosis`, `stance`, `decisions`, `detail`,
`delta`, and `hld` for the legacy shape. What the person signs is whichever
entrance ran — a root cause, or a stance and its answered Tier 1 entries —
never the build spec, which is written for whoever builds and is not reviewed
line by line. That is why the first two have
ceilings and the third does not: **what a person signs has to stay small
enough to sign again** after it changes.

**Which path goes in the track's `design` row:** the document `build` reads —
the detail design when Detail mode ran, otherwise the last document this
stage wrote. A detail design's `## Reference` names the stance and the
decisions it elaborates, so a reader who starts there reaches all three.
`preflight.py` reads that cell, picks the kind off the suffix, and runs the
matching probe; Gate 1's Approve fingerprints the same file. Not because the
person reads the build spec line by line — they sign the entrance's
documents, above — but because it is what `build` acts on, so editing it
after the Approve re-opens the gate.

**A known gap in that arrangement.** The ledger fingerprints one file, so
editing the *stance* or the decisions document after sign-off does not trip
`preflight.py build` the way editing the document in the design row does.
The probe still catches the case that matters — the stance's `## Status`
going back to `draft` — but a reworded invariant under an unchanged status
is not caught. Until the ledger can carry more than one artifact, treat an
edit to either after sign-off as re-opening the gate, and say so rather than
relying on a check that will not fire.

## When to skip this stage entirely

A design document that nobody needed is the most expensive kind, because it
reads exactly like one that was needed. Each of these belongs somewhere else:

- **The change is small enough that a code review would settle it.** A
  feasibility table over a two-file change is ceremony, and ceremony is what
  makes someone skip this stage the time it would have mattered.
- **The decisions are already made and you want them written down.** That is
  dictation, not design — write the document, but skip the option-weighing
  this stage exists for rather than staging a choice nobody is making.
- **Something is broken and the fix is obvious once seen** — a typo, an
  off-by-one, a line anyone would point at. Run `$debug` and fix it.
  Diagnosis mode is for a broken thing whose *cause* is worth a person's
  confirmation; a document proving what everyone can already see is the same
  ceremony this list exists to prevent.
- **The requirements themselves are the unknown.** Run `discover` first, then
  come back — this stage traces a design against requirements, and it has
  nothing to trace against yet.
- **Decisions mode only:** the stance is still `draft`. Weighing options
  against a trade nobody agreed to replaces the stance one option at a time.
- **Detail mode only:** a Tier 1 entry is still unanswered. An open
  architecture question is a decision the build spec would otherwise make by
  accident, one implementation detail at a time.
- **Detail mode only:** the design is agreed and what you want is the code.
  That is the `build` stage.
- **Delta mode only:** the branch is a few lines — read the diff. To check
  your own understanding before merging use `$quiz`; to judge whether the
  change is any *good* use the `verify` stage. Delta mode recovers what was
  decided, which is a third thing.

## Report

This is what you hand back to the main session -- not the report this
file's own steps describe. Put these fields in a `## Report` section. The
main session, not you, is the only writer of the track's state table and
of the ledger's `--note`; you write no track file at all.

- which mode ran
- where the document landed
- what `plan-review` returned
- any deviation from this procedure

Evidence goes in the artifact this stage already produces, never pasted
in here. 4000 characters is the ceiling for this section: the largest
note any finished track has written is 1941 characters, measured across
30 rows in five tracks, and a report carries those fields plus what never
reaches that cell. The number is the user's call, 2026-09-08. A
`## Pending questions` section (`references/pending-questions.md`) sits
outside the ceiling -- a decision handed up has to carry its evidence.
