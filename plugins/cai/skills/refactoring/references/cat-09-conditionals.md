# Simplifying Conditional Expressions (8)

Conditional logic is where complexity concentrates. Most of this chapter is about
making the *structure* of a decision visible, and then — where the decision is
about a type — deleting the decision entirely.

---

### 34. Decompose Conditional `decompose-conditional`
**Smells**: Long Method, complicated conditional
**Do**: extract the condition, the then-branch and the else-branch each into their
own named method.

**Mechanics**
1. **Extract Method** on the condition; name it for the question it asks
   (`isSummerRate(date)`, not `checkDate`).
2. **Extract Method** on the then-part.
3. **Extract Method** on the else-part.
4. Test.

**Payoff**: the remaining `if` reads as a statement of policy rather than a wall of
mechanism. Worth doing even when each extracted method is one line.

---

### 35. Consolidate Conditional Expression `consolidate-conditional-expression`
**Smells**: several separate conditionals that all produce the same result
**Do**: combine into one condition, then extract it.
**Pre**: the checks are genuinely one concept and have no side effects, and
combining does not break short-circuit ordering that the code relies on.

**Mechanics**
1. Confirm none of the conditions has a side effect. If one does, do not combine.
2. Combine with `&&` / `||` as appropriate (sequential ifs returning the same
   value → `||`; nested ifs → `&&`).
3. Test.
4. **Extract Method** on the combined condition, named for what it means as a whole.

**Do not** combine checks that happen to share a result but mean different things —
that hides the fact that there are two rules.

---

### 36. Consolidate Duplicate Conditional Fragments `consolidate-duplicate-conditional-fragments`
**Smells**: the same statement at the start or end of every branch
**Do**: move it out of the conditional.

**Mechanics**
1. Identical code at the *start* of every branch → move it above the conditional.
2. Identical code at the *end* of every branch → move it below (mind early returns
   and exceptions).
3. Identical code in the middle → check whether it can be moved to an end first;
   otherwise **Extract Method**.
4. Test.

---

### 37. Remove Control Flag `remove-control-flag`
**Smells**: a boolean variable used purely to exit a loop or skip work
**Do**: use `break`, `continue`, or `return` instead.

**Mechanics**
1. Find where the flag is set to its terminating value.
2. Replace that assignment with `break`/`continue` if the flag only ends the loop.
3. If the flag also carries a result, replace with `return` of that result.
4. Delete the flag and its checks; test.

**Then**: extracting the loop into its own method (**Extract Method**) often makes
the `return` form the cleanest.

---

### 38. Replace Nested Conditional with Guard Clauses `replace-nested-conditional-with-guard-clauses`
**Smells**: deep nesting; the normal path buried at the bottom
**Do**: return early on the exceptional cases; leave the main path unindented.
**Pre**: the branches are *not* equally weighted alternatives. If they are, an
if/else is correct and clearer — do not force early returns onto a symmetric choice.

**Mechanics**
1. Identify the exceptional / early-exit conditions.
2. Convert each to `if (exceptional) return ...;` at the top, one at a time, testing.
3. Reverse conditions as needed so the guard reads positively.
4. Once all guards are lifted, un-nest the remaining main path.
5. Consolidate guards that return the same thing (**Consolidate Conditional Expression**).

---

### 39. Replace Conditional with Polymorphism `replace-conditional-with-polymorphism`
**Smells**: Switch Statements, Duplicated Code
**Do**: move each branch into an overriding method on a subclass; the conditional
disappears.
**Pre**: an inheritance/interface structure keyed on the varying thing already
exists. If not, build it first with **Replace Type Code with Subclasses** or
**Replace Type Code with State/Strategy**.

**Mechanics**
1. Ensure the conditional's containing method lives on the class that owns the
   type — **Extract Method** then **Move Method** if not.
2. Choose one subclass. Copy the corresponding branch's body into an overriding
   method there.
3. Compile and test.
4. Delete that branch from the superclass conditional; test.
5. Repeat until the conditional is empty.
6. Make the superclass method abstract (or leave a sensible default).

**Do not** apply when the branch count is small, stable, and confined to one
method — the indirection costs more than the switch. Use
**Replace Parameter with Explicit Methods** instead.

**Keep exactly one switch**: the factory that decides which subclass to create.

---

### 40. Introduce Null Object `introduce-null-object`
**Smells**: repeated `if (x == null)` checks scattered across callers
**Do**: create a subclass representing "nothing", with the default behaviour.
**Pre**: the null case has a sensible default for *every* operation. If some
operation cannot be defaulted, a null object hides a real error — do not use it.

**Mechanics**
1. Create a null subclass (or an instance implementing the same interface) that
   answers `isNull()` true, or use an explicit optional type.
2. Give it a benign implementation of each method: empty string, zero, no-op,
   another null object.
3. Change the source to return the null object instead of null.
4. Remove the null checks at call sites, one at a time, testing after each.
5. Compile and let the remaining checks surface.

**Modern equivalent**: `Optional`/`Maybe`/`Option`, or a sum type. Prefer those
when the language has them — they make absence visible in the type rather than
silently benign.

---

### 41. Introduce Assertion `introduce-assertion`
**Smells**: Comments describing a required state; implicit assumptions
**Do**: state the assumption in code.
**Pre**: the condition should *always* be true. Assertions are for programmer
errors, never for validating external input — that needs real error handling.

**Mechanics**
1. Write the assertion where the assumption is made.
2. Ensure it has no side effects — many builds strip assertions, so behaviour must
   not depend on the assertion running.
3. Test with assertions both enabled and disabled.

**Better still**: if the assertion can be made unnecessary by restructuring so the
invalid state is unrepresentable, do that instead. An assertion documents a
weakness; removing the weakness is stronger.
