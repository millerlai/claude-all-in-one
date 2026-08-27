---
name: refactor-plan
description: Turn code smell findings into an ordered, dependency-aware, budgeted refactoring plan with one named refactoring per step. Produces a checklist, not code changes. Use after refactor-scan, or when the user asks how they should approach cleaning up a class or module.
argument-hint: "[path or class — will scan first if no findings exist yet]"
allowed-tools: Read, Grep, Glob, Bash, Write
disable-model-invocation: true
---

# Refactoring plan

Turn findings into an ordered, budgeted checklist. **Do not change production
code in this skill** — the only file this skill may write is the plan
document, `docs/refactoring-plan.md` by default, or the path the user names.

That write scope is a prose constraint, not a mechanical one: the tool level
can only grant or remove all of `Write`, not limit it to one path. Start this
skill on a clean working tree and commit before running it, so a mistaken
write is trivial to see and revert.

Planning is safe to run alongside a scan, which writes nothing. Do not run it
while `refactor-apply` or `refactor-auto` is working the same target: those
move the baseline this plan is being measured against, so the plan would be
ordered against a tree that no longer exists by the time anyone reads it.

Target: `$ARGUMENTS`

## Steps

**1. Get findings.** Use the findings already in the conversation, in
`refactor-scan`'s output format (severity-ordered, each with file:line and a
primary candidate refactoring). If there are none, run the `refactor-scan`
procedure first.

**2. Record the baseline.** Test command, current pass count, current commit
SHA. A plan without a baseline cannot be verified. **If tests are red now,
stop and say so** — planning on a red baseline is meaningless.

**3. Select and order.** For each finding, pick one primary refactoring and
check its preconditions against the matching card, per the routing and
enabling-chain rules in
`${CLAUDE_PLUGIN_ROOT}/skills/refactoring/references/selection.md`. Where
preconditions fail, either pick the alternative or add the enabling
refactoring as its own step.

**4. Budget.** Class 5–8 steps; module 8–15 steps; project → a roadmap plus
the top 1–2 findings only (`selection.md`, section 5). Prefer finishing one
file completely over touching many halfway. If the plan would exceed ~400
changed lines, split it into PRs and mark the boundary explicitly.

**5. Write it out** to `docs/refactoring-plan.md` (or the path the user
names), so it survives across sessions. Create the parent directory if it
does not exist. If the file already exists, confirm with the user before
overwriting it.

Every step in the plan follows the loop in
`${CLAUDE_PLUGIN_ROOT}/skills/refactoring/SKILL.md`'s non-negotiable safety
protocol when it is executed — this skill orders and budgets the steps, it
does not re-explain how to run one.

## Output format

```markdown
# Refactoring plan — src/billing/invoice.py

**Baseline** 214 tests green (`pytest -q`) @ a3f21c9
**Budget** 6 steps · est. ~250 changed lines · 1 PR
**Goal** `Invoice.render` readable without scrolling; currency logic on `Money`.

## Steps

- [ ] 1. **Rename Method** `Invoice.calc` → `calculateTotal`
      risk L · fixes Comments · enables review of 4
- [ ] 2. **Split Temporary Variable** `tmp` in `render` (3 unrelated uses)
      risk L · enables 3, 4
- [ ] 3. **Replace Temp with Query** `basePrice`
      risk L · enables 4
- [ ] 4. **Extract Method** `render` L180-214 → `renderLineItems`
      risk L · fixes Long Method
- [ ] 5. **Move Method** `formatCurrency` → `Money`
      risk M · fixes Feature Envy · 7 call sites
- [ ] 6. **Extract Class** tax fields → `TaxPolicy`
      risk M · fixes Large Class · new file

Each step: apply → typecheck → test → commit `refactor: <Name> on <target>`.

## Deferred to a later PR
- **Replace Conditional with Polymorphism** on `render`'s payment switch —
  needs `Replace Type Code with Subclasses` first; that is its own PR.

## Explicitly not doing
- **Extract Superclass** between `Invoice` and `Receipt`. They share formatting,
  not identity. If it recurs a third time, Extract Class instead.

## Blocked
- Anything in `gateway.py` — no tests. Run `refactor-safety-net` first.
```

## Rules

- **One named refactoring per step.** "Clean up the render method" is not a step.
- Every step names its target precisely: class, method, or line range.
- Every step declares its risk (L/M/H) and what it fixes or enables.
- Include the **Deferred**, **Not doing**, and **Blocked** sections. Recording
  what you rejected and why is what stops the next session from
  re-litigating it.
- Big Refactorings (#69–72) never become steps. They become a roadmap document
  plus a first small increment that stands on its own.
- If the plan needs a test seam, `Extract Interface` comes before whatever
  needs it.
