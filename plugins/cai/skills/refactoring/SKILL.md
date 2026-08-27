---
name: refactoring
description: Use when improving the internal structure of existing code without changing its behaviour - cleaning up a long method, breaking up a god class, removing duplication, taming conditionals, fixing an inheritance hierarchy, or when the user says refactor, code smell, technical debt, tidy up, restructure, or names a specific refactoring such as Extract Method or Replace Conditional with Polymorphism. Also use before adding a feature to code that resists the change.
---

# Refactoring

Refactoring is changing the internal structure of software **without changing its
observable behaviour**. If behaviour changes, it is not a refactoring — it is a
rewrite, and it must be labelled and reviewed as one.

This skill supplies three things: the safety protocol, the smell→refactoring
routing table, and the mechanics for 72 named refactorings.

## The two hats

At any moment you are wearing exactly one hat. Say which one out loud.

| Hat | You may | You may not |
|---|---|---|
| **Refactoring** | Restructure code, rename, move | Add behaviour, add tests for new behaviour, "fix a bug while you're in there" |
| **Adding function** | Add behaviour + its tests | Restructure unrelated code |

Swapping hats mid-edit is the single most common way refactoring goes wrong.
When you notice a bug during refactoring, write it down and finish the
refactoring first.

## Non-negotiable safety protocol

Run this loop for **every** refactoring, no exceptions.

1. **Establish the net.** Find the test command and confirm the relevant tests
   pass *before* touching anything. If there is no coverage for the target, stop
   and build characterisation tests first (see `refactor-safety-net`).
2. **Take one small step.** One named refactoring, one target. Not two.
3. **Compile / typecheck.**
4. **Run the tests.** Green → continue. Red → revert this step, do not debug
   forward. Then retry with a smaller step.
5. **Commit.** One refactoring per commit, message `refactor: <Name> on <target>`.
   A green commit per step is what makes the work revertible.
6. Repeat.

Hard rules:

- **Never** mix a refactoring commit with a behaviour change.
- **Never** batch five refactorings and then run the tests once.
- If tests do not exist and cannot be written, work through the safest
  refactorings only (Rename, Extract Method, Introduce Explaining Variable) and
  say explicitly that the net is missing.
- Prefer the IDE/language-server rename and extract operations where available;
  a mechanical tool is safer than hand-editing.
- Performance is a separate hat too. Refactor first for clarity, then measure,
  then optimise the small part that matters.

## Reference files — read on demand, not all at once

| File | Read when |
|---|---|
| `${CLAUDE_PLUGIN_ROOT}/skills/refactoring/references/smells.md` | Diagnosing: you have code, you need to name what is wrong |
| `${CLAUDE_PLUGIN_ROOT}/skills/refactoring/references/selection.md` | Choosing and sequencing refactorings, scoring, budget |
| `${CLAUDE_PLUGIN_ROOT}/skills/refactoring/references/catalog-index.md` | You need the one-line summary of all 72 and where each lives |
| `${CLAUDE_PLUGIN_ROOT}/skills/refactoring/references/cat-06-composing-methods.md` | Method-level: extract, inline, temps, algorithm |
| `${CLAUDE_PLUGIN_ROOT}/skills/refactoring/references/cat-07-moving-features.md` | Between objects: move method/field, extract/inline class, delegation |
| `${CLAUDE_PLUGIN_ROOT}/skills/refactoring/references/cat-08-organizing-data.md` | Data: encapsulation, type codes, value/reference, collections |
| `${CLAUDE_PLUGIN_ROOT}/skills/refactoring/references/cat-09-conditionals.md` | Conditionals: decompose, guard clauses, polymorphism, null object |
| `${CLAUDE_PLUGIN_ROOT}/skills/refactoring/references/cat-10-method-calls.md` | Interfaces: rename, parameters, factories, errors |
| `${CLAUDE_PLUGIN_ROOT}/skills/refactoring/references/cat-11-generalization.md` | Hierarchies: pull up/push down, extract super/sub/interface, template method |
| `${CLAUDE_PLUGIN_ROOT}/skills/refactoring/references/cat-12-big-refactorings.md` | Multi-week structural campaigns |

## Default workflow

```
scan (name the smells)  →  plan (ordered, budgeted)  →  apply (one at a time)  →  verify
```

- `refactor-scan` — inventory smells in a target, with evidence and severity
- `refactor-plan` — turn a scan into an ordered, dependency-aware plan
- `refactor-apply` — execute one named refactoring by the book's mechanics
- `refactor-auto` — run the whole loop autonomously within a budget
- `refactor-safety-net` — build characterisation tests before touching risky code

## Choosing a refactoring

Do not pick by taste. Pick by this chain:

1. **Name the smell** (`${CLAUDE_PLUGIN_ROOT}/skills/refactoring/references/smells.md`). If you cannot name it, you do not
   yet have a reason to change the code.
2. **Look up the candidates** the smell routes to.
3. **Check preconditions** in the refactoring's card. Most failed refactorings
   are precondition failures, not step failures.
4. **Check the enabling chain.** Many refactorings are blocked until a smaller
   one clears the way — e.g. Extract Method is blocked by tangled temps, so
   Replace Temp with Query or Split Temporary Variable comes first.
5. **Prefer the cheapest refactoring that removes the smell.** Extract Method
   beats Replace Method with Method Object unless the temps are truly tangled.

## When *not* to refactor

Say so plainly rather than proceeding:

- The code is scheduled for deletion or replacement.
- It works, is never read, and is never modified. Ugly and stable beats churned.
- You are close to a deadline — the debt is real, but the interest is not due today.
- The code is so broken that a rewrite is cheaper. Refactoring assumes the code
  mostly works.
- There are no tests, no way to write them, and the code is business-critical.

## Rule of three

First time, just do it. Second time, wince and duplicate. Third time, refactor.
Two occurrences of duplication are not yet evidence of the right abstraction;
premature abstraction is its own smell (Speculative Generality).

## Language notes

The catalog vocabulary is object-oriented and was written with Java in mind, but
the mechanics transfer. Adjust as follows:

- **Python / Ruby / JS**: `Self Encapsulate Field` and `Encapsulate Field` are
  usually redundant — use properties/accessors idiomatically instead. Prefer
  `Replace Type Code with Subclasses` only when behaviour genuinely varies.
- **Go / Rust**: no inheritance — translate `Extract Superclass` and
  `Form Template Method` into interface/trait extraction plus composition.
  `Replace Conditional with Polymorphism` becomes an interface + implementations
  (Go) or an enum/trait object (Rust).
- **Functional code**: `Replace Temp with Query` and `Extract Method` still apply;
  `Replace Conditional with Polymorphism` becomes pattern matching or a dispatch
  table; skip the mutable-state refactorings entirely.
- **TypeScript**: `Replace Type Code with Subclasses` often loses to a
  discriminated union. Prefer the idiom over the literal mechanics.
