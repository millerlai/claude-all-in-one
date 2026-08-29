# stage-design — decide what to build, before code exists

This file is read two ways: by a track that has reached this stage, and by
`/cai:design` when someone runs the stage standing alone, with no track
underneath it. The procedure below is the same either way, and neither way
runs in a subagent — the decision rule below sends architecture-level choices
to `AskUserQuestion`, which Claude Code removes from every subagent even when
its `tools:` field names it. Work handed to `designer` comes back with those
choices unresolved, for whoever dispatched it to put to the user.

The failure this stage exists to catch is a design that arrives already
committed — plausible, detailed, and resting on an architecture nobody was
asked about, or on a capability nobody checked was actually available.

## Pick a mode, and say which

- **High-level** — a new system, or an architecture-level choice on an
  existing one. Weighs options and stops before implementation detail.
- **Detail** — turns an approved high-level design into a document an
  engineering team can build from without coming back to ask what you meant.
- **Delta** — the branch is already built. Recovers the decisions from the
  diff and the commits instead of deciding anything.

Most work entering this stage from `intake`/`discover` wants High-level
first, then Detail once the user approves it. Delta only applies when code
already exists and nobody wrote down why it looks the way it does.

## Say what it will cost, then wait

Before either mode starts, four lines: the document path and the headings it
will carry; how much of the target directory has to be read and how many
documentation sources fetched; what is already unclear enough that you will
have to ask; and what this will not decide. Then wait for a go.

Detail mode is the longer of the two and the one most worth sizing — it reads
the whole target directory and renders every diagram. A pass that expensive
should not begin on an assumption that it was wanted.

## The two rules High-level and Detail both obey

**The evidence rule.** Every sentence about how something currently
behaves — this codebase, a library, a platform API — carries its source: a
`file:line`, or a documentation URL plus the sentence relied on.

Three sources count, and nothing else does:

- **This project** — dispatch `explorer` (read-only) to locate and quote the
  relevant lines, then read those files yourself and decide what they mean.
  A scout's summary is a pointer, not evidence.
- **Official documentation** — for any tool, framework, or platform the
  design stands on, fetch the vendor's own docs (`explorer`'s tools are
  Read/Grep/Glob only, so this needs a chore-tier subagent with web access),
  then interpret it yourself. Record the URL and the sentence taken.
- **Neither** — write `UNVERIFIED`, and name the design decision that stops
  standing up if the guess turns out wrong.

What does not count: what you remember about the library, what a function's
name implies, what a similar project usually does, "standard practice".
Catching yourself writing *typically*, *generally*, *should be able to*, or
*presumably* means you are writing `UNVERIFIED` in a longer form.

**The decision rule.** Four situations stop you and send you to
`AskUserQuestion`, with real options and what each costs here:

- an architecture-level choice — component boundaries, source of truth, sync
  or async, where state lives, which way a dependency points;
- a requirement not clear enough to design against;
- evidence that does not settle it, and two or more approaches both survive;
- anything touching credentials, personal data, or who is allowed to do
  what. These are architecture-level whether or not they look it: asking
  costs a question, choosing wrong costs an incident.

Never resolve one silently in either direction. Writing your preference in
is a decision the user never made; leaving something out because they did
not ask for it is the same decision with the opposite sign.

**One decision at a time, biggest blast radius first** — the same ordering
`stage-discover.md`'s interview move uses.

## Mode: High-level

1. **Feasibility, before the document.** List every capability the design
   needs and settle each under the evidence rule in a table: `C1`, `C2`, …,
   Capability, Verdict (`verified`/`UNVERIFIED`/`infeasible`), Evidence. The
   ids are load-bearing — `design_probe.py` fails the document if a
   capability is cited by no option, or a recommended option rests on one
   that is not `verified`.
2. **Use cases and issues.** Number them (`UC1`, `R1`, …) so a later
   traceability table has something to point at. Any requirement you would
   otherwise invent goes to `AskUserQuestion`.
3. **Compare options, then ask.** At least two real options per
   architecture-level choice, each citing the `C<n>` ids it rests on, why
   it's possible here, what it costs, how it fails. Mark at most one
   `(recommended)`, only if every capability it cites is `verified`. Put the
   choice to the user with `AskUserQuestion` — one decision at a time,
   biggest blast radius first. Escalate to `architect` (think tier,
   read-only) only when a choice genuinely spans several subsystems or turns
   on concurrency/consistency/migration ordering the evidence could not
   settle.
4. **Write it.** Unless the user named a path:
   `docs/design/<YYYY-MM-DD>-<topic>-high-level.md`, date from `date +%F`,
   `<topic>` spelled out. Copy
   `${CLAUDE_PLUGIN_ROOT}/templates/design-high-level.md.tpl`, fill it in,
   delete the HTML-comment guidance as you answer it. Do not add or rename
   headings. Two Mermaid diagrams (main flow, components) per
   `documentation.md`. Validate by rendering:
   `mmdc -i <the document> -o <scratchpad>/check.md`. `## Status` starts
   `draft`.
5. **Check, then review.**
   `python ${CLAUDE_PLUGIN_ROOT}/scripts/design_probe.py --kind hld <the document>`
   first — fix what it reports and re-run until it exits 0. Then invoke
   `plan-review` against the document with the high-level skeleton, running
   lens 8 (Precision) last. Fix Blocker/Major, take section 4 to
   `AskUserQuestion`. At most three rounds.
6. **Stop.** Hand it over with `## Status` still `draft`. Only the user's
   approval changes it to `approved <YYYY-MM-DD>` — never set it yourself.
   Before handing over, check the draft carries no signature, schema, file
   path for code that doesn't exist, pinned version, or pseudocode — those
   belong in the detail design.

## Mode: Detail

0. **The gate.** Open the named high-level design and check, in the file:
   `## Status` reads `approved` with a date; `## Open questions` is empty or
   every entry carries its answer; `## Use cases / Issues` numbers its
   entries. Any failing, stop and say which.
1. **Ground it in the real directory.** Read the target project directory;
   every claim about existing code resolves to a real `file:line` you have
   opened. Write to `docs/design/<YYYY-MM-DD>-<topic>-detail.md`, same
   `<topic>` as the high-level design. Copy
   `${CLAUDE_PLUGIN_ROOT}/templates/design-detail.md.tpl`, fill it in, same
   heading discipline as High-level.
2. **Four tables before any prose:** the `## Reference` block (path + status
   line the probe follows), the traceability table (every `UC`/`R` id vs.
   what satisfies it here), the glossary (every load-bearing term, its
   definition, `file:line`/`new — path`/`concept`), the budgets table
   (every quantity, and the `Number` column must contain an actual number —
   an unknown one comes from the user under the decision rule).
3. **Four diagrams**, Mermaid: architecture, component, flow, and one
   sequence per use case (past six, name which were skipped and why).
   Validate by rendering.
4. **The implementation spec.** Per component: Responsibility (one
   sentence), Interface (real signature), Data (shape in/out, types),
   Errors, Concurrency, Observability, Where it lives, What it reuses
   (`file:line`).
5. **`## Naming`.** Every name the implemented system creates, spelled out
   always. A name you invent is a decision — ask for it via
   `AskUserQuestion` rather than writing it in.
6. **Three sections a component spec doesn't contain:** `## Rollout`
   (ship in pieces? migration/backfill? what breaks in flight? rollback),
   `## Verification` (criterion / level / what it needs / green before),
   `## Work breakdown` (unit / depends on / can run alongside / done when —
   cut where Step 4's interfaces already cut them, riskiest unit with no
   unmet dependency first). Record upstream blockers here too. Deviations
   during the build follow the format `stage-build.md` defines.
7. **What you could not pin down** → `AskUserQuestion` under the decision
   rule, one at a time, biggest blast radius first. A confident guess is
   worse than an open question.
8. **Check, then review.**
   `python ${CLAUDE_PLUGIN_ROOT}/scripts/design_probe.py --kind detail --project-dir <target project dir> <the document>`
   first, fix and re-run until 0. Then `plan-review` with the detail
   skeleton, lens 8 first. Blocker/Major → fix and re-probe *and* re-review;
   section 4 → `AskUserQuestion`; Minor → leave documented. At most three
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
   `${CLAUDE_PLUGIN_ROOT}/templates/design-delta.md.tpl`. `## Before /
   After` takes two Mermaid diagrams (not one — a single end-state picture
   is something the reader could have drawn from the code).
5. **Validate the diagrams** by rendering, same as the other modes.
6. **Check it mechanically.**
   `python ${CLAUDE_PLUGIN_ROOT}/scripts/design_probe.py --kind delta <the document>`,
   fix and re-run until 0. `## Scope` needs one sentence of at least 20
   characters — a bare `a3f21bc..HEAD` reads as empty, not short.
7. **Hand it over.** Say where the document is, and count the `UNVERIFIED`
   rows out loud — that number is the list of things only the author knows.
   Do not merge, push, or commit anything; this mode reads and writes one
   file.

## The gate every mode shares

`plan-review` plus `${CLAUDE_PLUGIN_ROOT}/scripts/design_probe.py` are the
gate. The probe is free and answers only what has one answer — run it
before spending any reading on `plan-review`'s findings. This is the design
gate `track`'s human checkpoint sits on: nothing after this stage starts
until a person signs off on the design artifact.

## When to skip this stage entirely

A design document that nobody needed is the most expensive kind, because it
reads exactly like one that was needed. Each of these belongs somewhere else:

- **The change is small enough that a code review would settle it.** A
  feasibility table over a two-file change is ceremony, and ceremony is what
  makes someone skip this stage the time it would have mattered.
- **The decisions are already made and you want them written down.** That is
  dictation, not design — write the document, but skip the option-weighing
  this stage exists for rather than staging a choice nobody is making.
- **Nothing is being designed; something is broken.** That is `/cai:debug`:
  reproduce it, find the root cause, fix that.
- **The requirements themselves are the unknown.** Run `discover` first, then
  come back — this stage traces a design against requirements, and it has
  nothing to trace against yet.
- **Detail mode only:** the high-level design is still `draft`, or its open
  questions are unanswered. An open architecture question is a decision the
  detail document would otherwise make by accident, one implementation detail
  at a time.
- **Detail mode only:** the design is agreed and what you want is the code.
  That is the `build` stage.
- **Delta mode only:** the branch is a few lines — read the diff. To check
  your own understanding before merging use `/cai:quiz`; to judge whether the
  change is any *good* use the `verify` stage. Delta mode recovers what was
  decided, which is a third thing.

## Closing

Before handing off, write into `state.md`'s `note` cell for `design`: which
mode ran, where the document landed, what `plan-review` returned, and any
deviation from this procedure.
