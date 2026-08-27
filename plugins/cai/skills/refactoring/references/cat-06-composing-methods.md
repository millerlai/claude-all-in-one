# Composing Methods (9)

Method-level surgery. Almost all of it exists to fight Long Method. The unit of
work here is small enough that a green test run after every step is cheap — take
it every time.

Local variables are the main obstacle. When Extract Method resists, the fix is
almost always to clean up the temps first.

---

### 1. Extract Method `extract-method`
**Smells**: Long Method, Duplicated Code, Comments, Feature Envy (as step 1)
**Do**: turn a code fragment into its own method named after its intention.
**Pre**: the fragment has a nameable purpose. If you cannot name it better than
the code reads, do not extract.

**Mechanics**
1. Create a new method; name it for *what* it accomplishes, not *how*.
2. Copy the fragment in.
3. Find every variable local to the source method that the fragment touches.
4. Variables used only inside the fragment → declare them locally in the new method.
5. Variables read but not written → pass as parameters.
6. Exactly one variable written and used afterwards → return it and assign at the
   call site. Two or more written → do not extract yet; go to
   **Replace Temp with Query** / **Split Temporary Variable** first, or use
   **Replace Method with Method Object**.
7. Replace the fragment in the source with a call.

**Verify**: compile, run tests. Duplicate fragments elsewhere → replace those too.
**Inverse**: Inline Method
**Chains with**: Move Method (extract the envious part, then move it)

---

### 2. Inline Method `inline-method`
**Smells**: Middle Man, Speculative Generality, over-extraction
**Do**: replace calls with the body and delete the method.
**Pre**: the body is as clear as the name; the method is not polymorphic
(never inline a method that subclasses override).

**Mechanics**
1. Confirm no subclass overrides it.
2. Find all callers.
3. Substitute the body at each call site; adjust for parameters and returns.
4. Compile and test after each substitution if there are many.
5. Delete the method.

**Inverse**: Extract Method

---

### 3. Inline Temp `inline-temp`
**Smells**: noise; blocks Extract Method
**Do**: replace a temp that is assigned once from a simple expression with the
expression itself.
**Pre**: assigned exactly once; the right-hand side has no side effects.

**Mechanics**
1. Confirm the temp is effectively final (declare it final/const to let the
   compiler check).
2. Replace every reference with the right-hand expression.
3. Delete the declaration.

**Inverse**: Introduce Explaining Variable
**Chains with**: Replace Temp with Query (this is usually its first step)

---

### 4. Replace Temp with Query `replace-temp-with-query`
**Smells**: Long Method (temps blocking extraction)
**Do**: turn a temp holding an expression result into a method.
**Pre**: the temp is assigned once; the expression is free of side effects and
does not depend on state that changes between the assignment and the uses.

**Mechanics**
1. Confirm single assignment. Multiple assignments → **Split Temporary Variable** first.
2. Declare the temp final/const; compile to prove it.
3. **Extract Method** on the right-hand side; make it private, name it for the value.
4. Replace the temp's references with calls, one at a time, testing as you go.
5. Delete the temp.

**Cost**: may recompute. That is usually fine; measure before caring. If it is
genuinely hot, keep the temp and note why.
**Inverse**: Introduce Explaining Variable (roughly)
**Chains with**: Extract Method — this is what unblocks it

---

### 5. Introduce Explaining Variable `introduce-explaining-variable`
**Smells**: complicated expression, dense conditional
**Do**: put a subexpression into a well-named temp.
**Pre**: you cannot or should not extract a method — e.g. the expression uses many
locals, or you are in a language/context where an extra method is unwelcome.

**Mechanics**
1. Declare a final/const temp named for the *meaning* of the subexpression.
2. Assign the subexpression to it.
3. Replace the subexpression with the temp.
4. Test. Repeat for other parts.

**Prefer Extract Method** when the expression is reusable or the method is long —
a method is visible to the rest of the class, a temp is not.
**Inverse**: Inline Temp

---

### 6. Split Temporary Variable `split-temporary-variable`
**Smells**: a temp assigned more than once for unrelated purposes
**Do**: one variable per responsibility.
**Pre**: the temp is not a loop variable and not a legitimate accumulator — those
two are the only honest reasons for repeated assignment.

**Mechanics**
1. Rename the temp at its first declaration to reflect its first responsibility;
   declare it final/const.
2. Change references up to the second assignment to the new name.
3. At the second assignment, declare a fresh variable with its own name.
4. Compile, test, repeat for each further responsibility.

**Chains with**: Replace Temp with Query, Extract Method

---

### 7. Remove Assignments to Parameters `remove-assignments-to-parameters`
**Smells**: assigning to a parameter — obscures whether the parameter is in, out,
or both; behaves differently across languages.
**Do**: assign to a local instead.

**Mechanics**
1. Introduce a local initialised from the parameter.
2. Replace all uses after the assignment with the local.
3. Mark the parameter final/const to prevent regression.

**Note**: mutating an *object* passed as a parameter is a different thing and is
sometimes legitimate — this refactoring is about rebinding the parameter name.

---

### 8. Replace Method with Method Object `replace-method-with-method-object`
**Smells**: Long Method with temps too tangled for Extract Method
**Do**: promote the method to its own class, with the locals as fields.
**Pre**: you have already tried Replace Temp with Query and Split Temporary
Variable. This is expensive — a new class — so it is the last resort.

**Mechanics**
1. Create a class named after the method.
2. Give it a final field for the original object, plus one field per parameter and
   per local variable of the method.
3. Constructor takes the original object and the parameters.
4. Add `compute()` (or a domain-appropriate name) holding the original body,
   verbatim, with locals now resolving to fields.
5. Replace the original method's body with: construct the object, call `compute()`.
6. Test. Now every local is a field, so **Extract Method** freely inside the new
   class without passing anything.

**Payoff**: the whole point is step 6. Do not stop at step 5.

---

### 9. Substitute Algorithm `substitute-algorithm`
**Smells**: Duplicated Code (two algorithms, same result), convoluted logic
**Do**: replace the body with a clearer algorithm.
**Pre**: you have tests covering the behaviour, including edge cases. This is the
riskiest refactoring in this chapter — it replaces logic rather than moving it.

**Mechanics**
1. Break the method down first (Extract Method) so you are substituting the
   smallest possible unit.
2. Write the new algorithm alongside.
3. Verify equivalence: run both against the test suite, and if the input space is
   small or generable, diff their outputs over many inputs.
4. Swap in the new one; delete the old.

**Verify**: this one needs stronger evidence than "tests pass". State explicitly
what evidence you have for equivalence.
