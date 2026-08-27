---
name: refactor-scan
description: Scan a class, file, module or whole project for code smells and report each finding with evidence, severity and candidate refactorings. Read-only - never edits code. Use when the user asks what is wrong with this code, where the technical debt is, or asks for a code smell / refactoring assessment.
argument-hint: "[path, class name, or module — defaults to the current directory]"
disallowed-tools: Write, Edit
disable-model-invocation: true
---

# Refactoring scan

Diagnose only. **Do not modify any file in this skill.** The output is a report.

Target: `$ARGUMENTS` (default: current directory).

## Steps

**1. Establish scope and language.**
Identify the language, build system and test command. Determine whether the
target is a single class, a file, a module, or the whole project. If the test
command cannot be found, say so in the report instead of guessing one.

**2. Get the churn signal** (git repos only — it decides priority):

```bash
git log --since="1 year ago" --name-only --format="" -- <scope> \
  | sort | uniq -c | sort -rn | head -30
```

Files nobody touches are low priority no matter how ugly. If the target is not
a git repo, or `git log` fails, note that churn could not be measured and
continue without it — do not stop the scan over it.

**3. Check the safety net.** Locate tests covering the target and note the
coverage. Findings in untested code get a higher risk score and must be
flagged as needing `refactor-safety-net` first.

**4. Decide how to cover it.**
- **Single class or file:** read it yourself and continue inline through
  steps 5–7 below.
- **Module, whole project, or several named targets:** split the scope into
  up to 2–3 groups by module/directory boundary and dispatch one
  `refactoring-detector` agent per group, in parallel, one message — not
  more: `plugins/cai/rules/model-selection.md` caps parallel subagents at
  2–3. Give each agent its group's scope plus the churn signal and
  safety-net note from steps 2–3. If the scope has more groups than that,
  say so and note which groups were sampled and which were deferred rather
  than dispatching more agents.

**5. Name the smells** (only for scope you read yourself in step 4). Work
through the 22 smells in
`${CLAUDE_PLUGIN_ROOT}/skills/refactoring/references/smells.md`. Record only
what you can evidence with a line range and a concrete observation.

**6. Score.** `severity = impact × churn ÷ risk` (definitions in
`smells.md`).

**7. Route.** For each finding, list candidate refactorings from the routing
table, checking preconditions in the relevant `cat-*.md` card. Give one
primary candidate, not a menu.

**8. Reconcile.** If you dispatched detectors in step 4, merge each one's
findings into a single severity-ordered list; otherwise this is just your own
step 5–7 output.

## Output format

```markdown
# Refactoring scan — <target>

**Language** Python 3.12 · **Tests** `pytest -q`, 214 passing · **Coverage of target** ~68%
**Scope note** Sampled top 15 files by churn × size; not exhaustive.

## Findings (by severity)

### 1. Long Method — `Invoice.render` — severity 10.0
`src/billing/invoice.py:142-268`
126 lines, 9 local variables, 4 levels of nesting, 3 comments that each label a block.
Touched in 41 commits this year.
→ **Extract Method**, blocked by tangled temps: **Split Temporary Variable** and
  **Replace Temp with Query** first.

### 2. Feature Envy — `Invoice.formatCurrency` — severity 6.0
`src/billing/invoice.py:271-289`
Calls 5 accessors on `Money` and 0 on `self`.
→ **Move Method** to `Money`.

## Not findings
- `models/dto.py` is a Data Class by shape but is a serialisation boundary type.
  Correct as it stands.

## Untestable areas
- `src/billing/gateway.py` has no tests and makes live HTTP calls. Needs
  characterisation tests before any change.

## Suggested next step
`/refactor-plan src/billing/invoice.py` — 4 findings there form one coherent chain.
```

## Rules

- Every finding needs a **file:line range** and a **concrete observation**. No
  finding may rest on "this looks messy".
- Report what is *fine* too. A scan that flags everything is useless for
  prioritising.
- Do not propose Big Refactorings (#69–72) as findings — report them as
  structural observations with a note that they need a roadmap.
- If you find no significant smells, say so. That is a valid and useful result.
- Never edit. Never run `git commit`. Never run the formatter.
