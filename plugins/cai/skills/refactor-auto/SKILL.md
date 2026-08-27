---
name: refactor-auto
description: Run the full refactoring loop autonomously on a class, file or module - scan for smells, plan an ordered sequence, then apply and verify each refactoring one at a time within a step budget, committing after each green step. Use when the user asks to just refactor this, clean this up, or tidy up a module end to end.
argument-hint: "<path or class> [--budget N] [--dry-run]"
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
disable-model-invocation: true
---

# Autonomous refactoring loop

Drives `refactor-plan` and `refactor-apply` in turn within a single approved
budget. Because it is autonomous, the guardrails are stricter, not looser: one
approval covers the whole plan, but the first edit only happens after the plan
has been shown and approved.

Target: `$ARGUMENTS`

## Gate — refuse to start unless all of these hold

1. Tests exist for the target and are **currently green**.
2. The working tree is clean, or the user has explicitly accepted the state.
3. The target is a class, file or module. **Whole-project scope is refused** —
   produce a roadmap and let the user pick a module.
4. The target is not generated code, vendored code, or migrations.

If any gate fails, say which and stop. Offer `refactor-safety-net` for #1.

The loop holds the target repo's write access for its whole run. Nothing else
that writes may work the same target while it is going — a second writer moves
the baseline out from under the circuit breakers, and a breaker measuring
against a baseline that has shifted is not a brake.

## Loop

```
1. SCAN     → run the refactor-scan procedure for evidenced findings
2. PLAN     → run the refactor-plan procedure to get an ordered, budgeted
              checklist (docs/refactoring-plan.md by default)
3. CONFIRM  → show the whole plan, get one approval for it
4. For each step, until the budget is spent:
     a. run the refactor-apply procedure for that step's named refactoring
     b. check the circuit breakers below
     c. on green: continue to the next step
     d. on red: the step's own procedure reverts and reports it; count it
        toward the circuit breakers and continue
5. VERIFY   → full suite + before/after summary
6. REPORT   → the format below
```

**Step 3 is not optional.** Nothing is edited before the plan has been shown
and approved once, for the whole plan — not per step. `--dry-run` stops right
after step 3 and never reaches step 4.

## Budget

Default 8 steps, or the plan's own budget if smaller. `--budget N` overrides.
Stop when the budget is spent even if findings remain — report the remainder
as not attempted.

## Circuit breakers — stop the whole loop, not just the step

Any one of these ends the loop entirely and moves straight to VERIFY/REPORT,
not just the step in progress:

- **Two consecutive steps go red.**
- **Cumulative diff passes ~400 lines.**
- **A step would need to change a public API** with no agreed deprecation path.
- **The plan reaches a Big Refactoring** (`refactoring/references/cat-12-big-refactorings.md`).
- **A test file was modified.** This is the most important one — a modified
  test means behaviour changed, which means it was not a refactoring.

## Report

```markdown
# Refactoring run — src/billing/invoice.py

**Baseline** 214 green @ a3f21c9 → **Now** 214 green @ e0c9d14
**Budget** 8 · **Applied** 6 · **Blocked** 1 · **Not attempted** 1
**Diff** 5 files, +142 −198

## Applied
1. ✓ Rename Method `calc` → `calculateTotal`                     b81f3a2
...

## Blocked
7. ✗ Extract Class `TaxPolicy` — reverted, 3 tests reach into `Invoice._taxRate`
   directly. Needs Self Encapsulate Field first, then retry.

## Not attempted
8. — Replace Conditional with Polymorphism — needs a type hierarchy. Separate PR.

## Before / after
`Invoice.render` 126 lines → 34 lines · longest method in file 126 → 41

## Behaviour
No test files modified. No test assertions changed. 214 green before and after.
```

The **Behaviour** section is mandatory. If it cannot honestly say no test file
was modified, this run was not a refactoring, and the report must say so
plainly instead of hedging.

Where the run departed from the approved plan — a step reordered, a target
narrowed, a refactoring swapped for a cheaper one — log it in the format
`checkpointed-execution` already defines, under a `## Deviations` heading:

```md
- Step 4 — plan said Extract Class, did Extract Method.
  Why: <what the plan did not anticipate>
  Cost: <what this changes for the remaining steps, or "none">
```

The approval covered the plan that was shown. A loop that quietly does
something else has spent an approval on work the user never saw.
