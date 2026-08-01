---
name: finding-unknowns
description: Surface what the user doesn't know before writing implementation code. Use whenever the codebase area is unfamiliar, the requirements are ambiguous, the solution space has not been explored, or the result will be judged by look and feel. Also use when the user invokes /cai:finding-unknowns, or says "what am I missing", "find my blindspots", "interview me about this", "brainstorm the options", "show me some directions", "mock this up first", "I've never touched this code", or "I don't know what X is".
---

# finding-unknowns — make the unknowns visible before you build

A wrong assumption costs the least before any code exists. Every move below is a
cheap way to convert an unknown into something the user can react to — and
reacting is far easier than imagining.

## Step 1 — Name the unknown

| What is unknown | Move | Output |
|---|---|---|
| This part of the codebase | **A. Blindspot pass** | Numbered landmines + a rewritten prompt |
| This problem domain | **B. Vocabulary ladder** | Mental model → terms → what good looks like |
| What the user actually wants | **C. Interview** | One question at a time, biggest blast radius first |
| Which solution to pick | **D. Option space** | ~10 options, S→XL, each grounded in real files |
| What it should look like | **E. Directions & mock** | One HTML file, N incompatible directions, fake data |

More than one can apply. Pick the one whose answer would change the most work,
run it, then re-check — a blindspot pass often exposes that the spec was
ambiguous too.

## Step 2 — Offer before you run

Say in one line which move you propose, why, and roughly what it costs. Then
wait.

> Before I touch the auth module I'd like to do a blindspot pass — I've not read
> this area and the SSO flow probably has conventions I'd break. ~5 minutes. OK?

Skip the offer only when the user already named the move. **Never burn a long
discovery pass unbidden** — an unwanted one is worse than none, because the next
one gets refused too.

## The moves

### A. Blindspot pass — unfamiliar code

Dispatch `explorer` first (Haiku, read-only) to map the area, then report:

- **Scope and stakes** — one line on what looked simple vs. what is actually there.
- **5–8 numbered landmines.** Each one needs all three parts:
  - what the thing is, concretely, with `file:line`;
  - **why it bites** — the specific failure it causes if ignored;
  - **the sentence to add to the next prompt** so it doesn't.
- **The rewritten prompt** — a single block folding all of the above into the
  request the user should have made. This is the actual deliverable.
- **Suggested sequence** with one checkpoint where the user should look before
  you continue.

Read the code, not your priors. A landmine you can't point at a file for is a
guess — drop it or label it as one.

### B. Vocabulary ladder — unfamiliar domain

The user needs the words a practitioner would use, so their next prompt can be
precise:

- **The mental model** — the domain's stages in order, 3–5 of them.
- **The vocabulary ladder** — ~7 terms, each with a definition and how it gets
  used in a real sentence.
- **What good looks like** — the criteria by which the result gets judged.
- **The payoff** — 3–4 example prompts written in the new vocabulary, so the
  user can copy one.

### C. Interview — ambiguous requirements

- Open with the count and the ordering: *"7 open questions, ordered by blast
  radius."*
- **Ask one question at a time and wait.** A numbered list of seven questions is
  not an interview; it gets one vague answer covering none of them.
- Order by whether the answer changes the architecture, not by what's easiest to
  answer. Cheap cosmetic questions go last or get dropped.
- Offer a default with each question ("I'd assume X — correct me"), so a shrug
  still moves things forward.
- Close by writing the answers back as a short spec the user can correct in one
  read.

### D. Option space — unexplored solution space

Search the codebase **first**; an option list written from imagination is worth
nothing.

- ~10 interventions, ordered cheapest → most ambitious, sized `S` (ship this
  afternoon) through `XL` (quarter-long bet).
- Each entry: title, the `file:line` evidence it's grounded in, what it would
  change, and the size.
- Lead with the pattern you found — often most options turn out to be wiring up
  machinery that already exists rather than building anything.
- End by asking which ones resonate. Do not pick for the user.

### E. Directions & mock — the result is judged by look or feel

`workflow.md` already requires a prototype here; this is how to build one.

- **One self-contained HTML file** with fake data. Write it to the session
  scratchpad or a directory the user names — never into the app, never
  committed.
- **N deliberately incompatible directions** (4 is a good default) rendering the
  *same* data. If two of them could be described by the same sentence, one is
  wasted. Push the extremes: dense ops console vs. airy editorial vs. keyboard
  terminal.
- Under each direction, list what's distinctive about it so the user can say
  "steal that, skip that" per element rather than picking a winner wholesale.
- Finish with 3–4 concrete decision questions and a reply template the user can
  fill in one line.
- State plainly that nothing is wired up.

## Step 3 — Fold it back

The artifact is an input, not a deliverable to admire:

- Feed the answers straight into the next prompt or the implementation plan.
  Once that plan exists, `plan-review` is what audits it back against these
  answers.
- Durable, project-specific findings → the project's `CLAUDE.md` or memory,
  following `memory.md` (stable facts only — not line numbers or in-progress
  state).
- Surprises that appear later, during the build → `implementation-notes.md`, per
  the deviations rule in `workflow.md`.

## When not to use this

- The task is mechanical and already well specified — just do it.
- The user has clearly stated what they want. Interviewing someone who already
  answered is noise.
- Something is broken and needs diagnosing. That is debugging: reproduce, find
  the root cause, fix. Exploring the option space first is procrastination.

## Note on format

The technique this skill is built from renders every artifact as HTML. Only move
E genuinely needs to be seen to be judged; A–D read faster as markdown in the
terminal, so keep them there.
