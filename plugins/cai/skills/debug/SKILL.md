---
name: debug
description: Find the root cause of a bug before proposing any fix — a test that fails, a crash, a stack trace, unexpected behaviour, or something that used to work and stopped. Use when the user says "this is broken", "it's not working", "the test fails", "fix this bug", "為什麼會壞", "這段程式有 bug", or pastes an error message or stack trace. Not for a diff that might not be mergeable (`verify`), code that behaves correctly but is hard to read (`refactor`), or a question about what's unknown before any code exists (`discover`) — this is for something that demonstrably does not work right now.
---

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

## Step 1 — Reproduce it, on purpose

Find the exact steps that trigger it, every time. Not reproducible yet →
gather more data (logs, a smaller repro case, the exact input); a fix aimed
at a bug you can't reliably trigger is aimed at nothing.

## Step 2 — Read what's already there

- The error message and the full stack trace, not just its last line — the
  cause is often named higher up, where the trace started.
- What changed recently: `git log`, `git diff` against the last known-good
  state, a new dependency, a config or environment difference. Most bugs are
  introduced, not discovered.

## Step 3 — On a multi-component system, find which one breaks

Don't theorize about which layer is at fault — instrument the boundary
between each pair of components (log what enters, what leaves, what the
config actually resolved to) and run it once. The evidence names the
component; only then investigate that one.

## Step 4 — One hypothesis, one small test

State it as a sentence: "I think X causes this, because Y." Make the
smallest possible change that would prove or disprove it — one variable,
not a bundle of plausible fixes at once. Wrong → a new hypothesis, not a
second fix stacked on the first. You cannot tell which change worked if two
land together.

## Step 5 — Fix at the root, test-first

Same discipline `stage-build.md`'s Step 3 uses for new code: write the
failing test that reproduces the bug, run it, and watch it actually fail —
before writing the fix. Then fix the root cause you named in Step 4, run the
test again, and read the output showing it pass. The evidence rule is the
same one `stage-verify.md` opens with: no completion claim without having
just run the command and read what it printed.

One fix at a time. No unrelated cleanup riding along — that's `refactor`'s
job, on a separate pass.

## After three fixes fail

Stop. A fix that doesn't work, and then another, and then a third, is not
bad luck — it's an architecture that's fighting you at every attempt.
Question the design instead of trying a fourth patch: say what's failing
and why the failures look structural (`AskUserQuestion`, or escalate to
`architect` if the fix now spans components).

## When not to use this

- The code already does what it should, and the request is to make it
  cleaner or better structured — `refactor`.
- The question is whether a branch is safe to merge, not whether something
  is broken right now — `verify`.
- Nothing is broken yet; the question is what you don't know before writing
  code — `discover`.
