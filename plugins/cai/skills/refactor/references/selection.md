# Selecting and sequencing refactorings

How to go from "here is a codebase / module / class" to "here is an ordered list
of named refactorings, and here is why".

## 1. Scope the target

| Scope | What to read | Realistic finding count |
|---|---|---|
| **Class / file** | The file, its direct collaborators, its tests | 3–10 |
| **Module / package** | Public surface, dependency edges, hot files | 10–30 |
| **Whole project** | Structure, build/test setup, top-20 files by churn × size | Sample only — never exhaustive |

For whole-project scope, **do not attempt a full inventory**. Sample: take the
files with the highest `churn × size`, plus anything the user names, and report
those. Say clearly that the scan is a sample.

Useful signals:

```bash
# churn over the last year
git log --since="1 year ago" --name-only --format="" | sort | uniq -c | sort -rn | head -30

# size
find . -name "*.<ext>" -not -path "*/node_modules/*" | xargs wc -l | sort -rn | head -30

# how the code is verified
ls Makefile package.json pyproject.toml build.gradle pom.xml Cargo.toml go.mod 2>/dev/null
```

## 2. Diagnose before prescribing

For each finding, produce all four fields. A finding without evidence is an
opinion and must not appear in a plan.

```
SMELL      Long Method
LOCATION   src/billing/invoice.py:142-268  (Invoice.render)
EVIDENCE   126 lines; 9 locals; 4 nesting levels; 3 explanatory comments
SEVERITY   impact 4 × churn 5 ÷ risk 2 = 10.0
```

Impact, churn and risk are defined in `smells.md`.

## 3. Route smell → candidates

Use the routing table in `smells.md`. Then narrow by preconditions from the
refactoring's card. Most bad plans are precondition failures — for example
proposing Replace Type Code with Subclasses when the code changes at runtime
(State/Strategy is the right one), or Pull Up Method when the bodies differ in
the middle (Form Template Method is the right one).

## 4. Order by the enabling chain

Refactorings unblock each other. Running them out of order forces rework. The
common chains:

**Long Method**
```
Split Temporary Variable → Replace Temp with Query → Extract Method
                                                   → Decompose Conditional
        (if still tangled) → Replace Method with Method Object → Extract Method
```

**Switch on a type code**
```
Extract Method (the switch) → Move Method (onto the type owner)
  → Replace Type Code with Subclasses      (code fixed at construction)
    or Replace Type Code with State/Strategy (code varies at runtime)
  → Replace Conditional with Polymorphism  (per switch site)
  → Push Down Method / Push Down Field
```

**Large Class**
```
Extract Interface (find the seams) → Extract Class (per cohesive field cluster)
  → Move Method → Move Field → Hide Delegate (if the split should stay internal)
```

**Feature Envy**
```
Extract Method (isolate the envious part) → Move Method → Encapsulate Field (cleanup)
```

**Data Class**
```
Encapsulate Field → Encapsulate Collection → Remove Setting Method
  → Move Method (pull behaviour in) → Hide Method
```

**Long Parameter List**
```
Replace Parameter with Method  (cheapest — can the callee fetch it?)
  → Preserve Whole Object      (do they all come from one object?)
  → Introduce Parameter Object (no owning object exists)
  → Move Method (behaviour into the new object, so it isn't a Data Class)
```

**Duplicated Code across siblings**
```
Extract Method (both sides) → align names/signatures (Rename Method)
  → Pull Up Method     (bodies identical)
  or Form Template Method (bodies differ in the middle)
```

**Deep conditionals**
```
Decompose Conditional → Consolidate Conditional Expression
  → Consolidate Duplicate Conditional Fragments
  → Replace Nested Conditional with Guard Clauses
  → Introduce Null Object (if the null branch dominates)
```

**Ordering rules**
1. Enablers before the refactorings they enable.
2. Low risk before high risk. Rename and Extract Method first — they make
   everything after them easier to read and review.
3. Local before structural. Finish inside a method before moving between classes,
   and between classes before touching hierarchies.
4. Anything requiring a new test seam comes after **Extract Interface**.
5. Never schedule a refactoring and its inverse in the same run.

## 5. Budget

Every plan states a budget and stops when it is spent. Defaults:

| Scope | Steps per run | Stop condition |
|---|---|---|
| Class | 5–8 | all high-severity findings addressed |
| Module | 8–15 | budget spent, or one file left fully clean |
| Project | produce a roadmap, execute the top 1–2 findings only | — |

Prefer **finishing one file completely** over touching ten files halfway. A
half-refactored file is worse than the original — the reader now has two idioms
to hold in their head.

## 6. Hard stops

Abort and report rather than continuing when:

- Tests fail before you start. Report it; do not "fix it while you're in there".
- A step's tests go red and a small revert does not restore green.
- The refactoring would change a public API without an agreed deprecation path.
- The change touches generated code, vendored code, or migrations.
- The plan reaches a Big Refactoring — produce a roadmap instead of executing.
- Total diff exceeds ~400 changed lines for one PR. Split it.
- You cannot name the smell. No smell, no refactoring.

## 7. Output contract

Plans are written as a checklist so they survive across sessions:

```markdown
## Refactoring plan — src/billing/invoice.py
Baseline: 214 tests green (`pytest -q`), commit a3f21c9
Budget: 6 steps

- [ ] 1. Rename Method  `Invoice.calc` → `Invoice.calculateTotal`     [L] enables review
- [ ] 2. Split Temporary Variable  `tmp` in `render`                  [L] enables 4
- [ ] 3. Replace Temp with Query  `basePrice`                         [L] enables 4
- [ ] 4. Extract Method  lines 180-214 → `renderLineItems`            [L] Long Method
- [ ] 5. Move Method  `formatCurrency` → `Money`                      [M] Feature Envy
- [ ] 6. Extract Class  tax fields → `TaxPolicy`                      [M] Large Class

Deferred: Replace Conditional with Polymorphism on `render` — needs a type
hierarchy first; separate PR.
Not doing: Extract Superclass with `Receipt` — the two are not the same kind of
thing, only share formatting. Extract Class instead if it recurs.
```

Each executed step gets its own commit: `refactor: <Name> on <target>`.
