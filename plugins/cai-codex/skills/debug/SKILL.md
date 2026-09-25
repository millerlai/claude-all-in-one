---
name: debug
description: Something demonstrably broken right now — a failing test, a crash, wrong behaviour, a regression — where the root cause comes before any fix. Use when the user says "this is broken", "fix this bug", "為什麼會壞", or pastes an error message or stack trace.
---
> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.


# Debugging

A bug fixed without finding its root cause comes back, usually somewhere
worse. The rule below exists because the tempting move — change the line the
stack trace points at, run it once, ship it — produces a fix that looks
right and isn't.

## The rule

**No fix before the root cause is found and stated.** "It's probably X, let
me try changing that" is a guess wearing a fix's clothes. If you cannot say
in one sentence why the bug happens, you are not ready to touch the code.

This applies double under time pressure. Guessing under a deadline is how a
fifteen-minute bug turns into a three-hour one.

Redact secrets from anything shown below (a reply, a diagnosis document, a
temporary log) — write `<REDACTED>` in their place, and build commands
against environment variables so a credential never has to appear at all.

## Step 1 — Reproduce it, on purpose

Find the exact steps that trigger it, every time. Not reproducible yet →
gather more data (logs, a smaller repro case, the exact input); ten ways to
build one when it isn't obvious are in
`<cai-root>/skills/debug/references/feedback-loops.md`. A fix
aimed at a bug you can't reliably trigger is aimed at nothing.

**Done when you can point at one command**: named, rerunnable, already run
this session, its redacted output pasted, its failure matching the symptom
described. An existing failing test already is that command. None yet →
write down what you tried and stop here, at reproduction. Then shrink it —
drop one remaining element at a time, rerunning after each cut — until
every element left is load-bearing: dropping any one stops the failure.

## Step 2 — Read what's already there

- If `<top>/CONTEXT.md` exists — `<top>` being the path your brief names or,
  if it names none, what `git rev-parse --show-toplevel` prints — read it
  first and use its terms. If it does not exist, or neither gives you
  `<top>`, say nothing about it and do not suggest creating one. Read only
  that one file, not a `CONTEXT.md` in any subdirectory, and never write it.
- The error message and the full stack trace, not just its last line — the
  cause is often named higher up, where the trace started.
- What changed recently: `git log`, `git diff` against the last known-good
  state, a new dependency, a config or environment difference. Most bugs are
  introduced, not discovered.

## Step 3 — On a multi-component system, find which one breaks

Don't theorize about which layer is at fault — instrument the boundary
between each pair of components (log what enters, what leaves, what the
config actually resolved to) and run it once, tagging any temporary log
with a marker unique to this session, e.g. `[DEBUG-a4f2]` — cleanup becomes
one grep for that tag. The evidence names the component; only then
investigate that one.

## Step 4 — One hypothesis, one small test

List 3–5 falsifiable hypotheses before testing any — the first plausible one
skips the other four. State each as: "If X is the cause, changing Y would
make the symptom disappear." Show the list, then test one at a time,
without waiting for a reply.

For whichever is up: make the smallest possible change that would prove or
disprove it — one variable, not a bundle of plausible fixes at once. Wrong →
a new hypothesis, not a second fix stacked on the first. You cannot tell
which change worked if two land together.

## Step 5 — Fix at the root, test-first

Same discipline `stage-build.md`'s Step 3 uses for new code: write the
failing test that reproduces the bug, run it, and watch it actually fail —
before writing the fix. Then fix the root cause you named in Step 4, run the
test again, and read the output showing it pass. The evidence rule is the
same one `stage-verify.md` opens with: no completion claim without having
just run the command and read what it printed.

One fix at a time. No unrelated cleanup riding along — that's `refactor`'s
job, on a separate pass. Before calling it done: grep Step 3's tag — zero
hits left.

## After three fixes fail

Stop. A fix that doesn't work, and then another, and then a third, is not
bad luck — it's an architecture that's fighting you at every attempt.
Question the design instead of trying a fourth patch: say what's failing
and why the failures look structural (the question tool, or escalate to
`cai_architect` if the fix now spans components).

## Inside a track

Run standing alone, this skill ends at a working fix. Inside a track, the
design stage's **diagnosis mode** (`stage-design.md`) is where steps 1–4's
findings get written down and signed: what a person approves there is the
**root cause**, because a wrong cause makes every fix downstream of it wrong.

Two seams, both already described above from this side:

- **The entry condition is Step 5's failing test, written first.** A test that
  fails now and would pass if an existing promise held — an existing test, the
  documentation, a spec, an invariant, never anyone's expectation. Cannot
  write one because nothing ever promised it? Then nothing is broken: that is
  a requirement, and the track's stance mode owns it.
- **"After three fixes fail" is an escalation, not an ending.** Handing the
  design question up is exactly diagnosis mode escalating to stance mode. It
  goes one way only, and the track records it.

Steps 1–4 sometimes need a command or edit `cai_designer` cannot run itself;
`stage-design.md`'s diagnosis mode routes that to the main session.

## When not to use this

- The code already does what it should, and the request is to make it
  cleaner or better structured — `refactor`.
- The question is whether a branch is safe to merge, not whether something
  is broken right now — `verify`.
- Nothing is broken yet; the question is what you don't know before writing
  code — `discover`.
