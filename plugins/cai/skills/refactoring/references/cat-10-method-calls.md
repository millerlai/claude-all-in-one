# Making Method Calls Simpler (15)

Interface design. Everything here changes a signature, so the first step in every
one of them is the same: **find every caller**. Use the language server's "find
references" rather than grep where possible; grep misses dynamic dispatch and
over-matches common names.

If the method is part of a published API you do not control, you cannot simply
change it. Use the deprecation path: add the new form, make the old form delegate,
mark it deprecated, remove it a release later.

---

### 42. Rename Method `rename-method`
**Smells**: Comments, Alternative Classes with Different Interfaces, Speculative Generality
**Do**: give the method a name that says what it does.

**Mechanics**
1. Check sub/superclasses for the same signature — rename the whole family together.
2. Prefer the IDE/LSP rename operation.
3. By hand: create the new method, move the body, make the old one delegate, test,
   repoint callers, delete the old one.
4. Published API → keep the old name delegating and deprecated.

**The single highest value-per-risk refactoring in the catalog.** Do it liberally.

---

### 43. Add Parameter `add-parameter`
**Do**: add a parameter the method needs.
**Pre**: you have checked the alternatives first — **Replace Parameter with
Method** (can the callee get it itself?) and **Preserve Whole Object**. Long
parameter lists are a smell; each addition should be justified.

**Mechanics**
1. Check sub/superclasses.
2. Add an overload with the new signature that delegates to the old one, or add
   the parameter and fix all callers at once if the count is small.
3. Repoint callers; test.
4. Delete the old signature.

**Inverse**: Remove Parameter

---

### 44. Remove Parameter `remove-parameter`
**Smells**: Speculative Generality, Long Parameter List
**Do**: delete a parameter nobody uses.
**Pre**: unused in this method *and* in every override. A parameter unused here but
used by an override must stay — the signature is shared.

**Mechanics**
1. Check the whole polymorphic family.
2. Add the new signature delegating to the old, or edit and fix callers.
3. Test, delete the old.

**Inverse**: Add Parameter

---

### 45. Separate Query from Modifier `separate-query-from-modifier`
**Smells**: a method that returns a value *and* changes state — callers cannot ask
without also causing the change.
**Do**: split into a pure query and a pure command.
**Pre**: not applicable to things that are inherently atomic (a queue's `pop`, a
counter's `getAndIncrement`, anything relying on a lock). Note the exception rather
than forcing the split.

**Mechanics**
1. Create a query method that returns the value with no side effect — for now,
   duplicate the necessary logic.
2. Change the original to call the query and return its result; test.
3. Repoint each caller to call the query, then the modifier, in that order; test.
4. Remove the return value from the modifier.

**Payoff**: queries become freely callable, cacheable and testable.

---

### 46. Parameterize Method `parameterize-method`
**Smells**: Duplicated Code — several methods doing the same thing with different
constants (`fivePercentRaise`, `tenPercentRaise`).
**Do**: one method with a parameter.

**Mechanics**
1. **Extract Method** the common shape if needed.
2. Add the general method with the parameter.
3. Repoint callers, passing the literal; test.
4. Delete the specific methods.

**Inverse**: Replace Parameter with Explicit Methods
**Stop when**: the parameter starts driving branching logic — then you have made
things worse, and #47 is the right direction.

---

### 47. Replace Parameter with Explicit Methods `replace-parameter-with-explicit-methods`
**Smells**: Switch Statements — a parameter that only selects behaviour via a
conditional inside the method.
**Do**: one method per case.
**Pre**: the set of cases is small and stable, and callers know their case at
compile time. If the caller has to switch to pick which method to call, you have
moved the problem — revert and use polymorphism instead.

**Mechanics**
1. Add one method per branch of the internal conditional.
2. Repoint each caller to the matching explicit method; test.
3. Delete the parameterised method.

**Inverse**: Parameterize Method

---

### 48. Preserve Whole Object `preserve-whole-object`
**Smells**: Long Parameter List, Data Clumps
**Do**: pass the object instead of several values pulled out of it.

**Mechanics**
1. Add a parameter for the whole object.
2. Replace each derived parameter's uses in the body with calls on the object,
   removing parameters one at a time, testing between.
3. Update callers to pass the object.

**Tradeoff**: this creates a dependency from the callee to the object's class. If
the callee is in a lower layer that must not know about it, the long list is the
correct choice — say so.

---

### 49. Replace Parameter with Method `replace-parameter-with-method`
**Smells**: Long Parameter List
**Do**: delete a parameter the callee can compute or fetch itself.
**Pre**: the callee can reach the same value, and the caller was not deliberately
overriding it.

**Mechanics**
1. **Extract Method** on the caller's computation of the argument, if needed.
2. Replace the parameter's uses in the body with the call; test.
3. **Remove Parameter**.

---

### 50. Introduce Parameter Object `introduce-parameter-object`
**Smells**: Long Parameter List, Data Clumps
**Do**: group parameters that travel together into an object.

**Mechanics**
1. Create an immutable class with a field per parameter and a constructor.
2. **Add Parameter** for the new object; leave the old parameters in place.
3. Remove the old parameters one at a time, replacing their uses with accessors,
   testing between.
4. Update callers to construct the object.
5. Then look for behaviour that operates on those values and **Move Method** it in —
   otherwise you have created a Data Class.

**Step 5 is the point.** A parameter object that only shortens signatures is a
modest win; one that attracts behaviour is a real one.

---

### 51. Remove Setting Method `remove-setting-method`
**Smells**: Data Class; mutability that shouldn't exist
**Do**: delete the setter for a field that must not change after construction.

**Mechanics**
1. Ensure the constructor sets the field.
2. Find every caller of the setter; repoint construction-time calls to the constructor.
3. Any remaining caller means the field *does* change — stop and reconsider.
4. Remove the setter, make the field final/readonly; test.

---

### 52. Hide Method `hide-method`
**Smells**: Data Class; over-wide interface
**Do**: reduce visibility of a method nobody outside uses.

**Mechanics**
1. Confirm no external caller (check reflection, DI frameworks, serialisation and
   test code before concluding).
2. Reduce visibility one level; compile.
3. Repeat until it breaks, then step back one.

Do this regularly — a shrinking interface is a sign the class is absorbing its
own behaviour correctly.

---

### 53. Replace Constructor with Factory Method `replace-constructor-with-factory-method`
**Smells**: constructors that can't do what's needed
**Do**: wrap construction in a static method.
**Pre**: you need behaviour a constructor cannot provide — returning a subclass,
returning a cached instance, a meaningful name, or failing without throwing.

**Mechanics**
1. Add a static factory method whose body calls the constructor.
2. Repoint callers; test.
3. Reduce the constructor's visibility to private/protected.

**Enables**: Replace Type Code with Subclasses, Change Value to Reference,
Replace Subclass with Fields — all of which need this first.

---

### 54. Encapsulate Downcast `encapsulate-downcast`
**Smells**: callers forced to cast the result of a method
**Do**: do the cast inside the method and return the specific type.

**Mechanics**
1. Narrow the method's declared return type.
2. Cast inside; remove the cast at every call site; test.
3. For a collection, this may mean returning a typed collection or an iterator.

**Modern note**: with generics this is largely obsolete. If you are hitting it in
new code, the real fix is usually to parameterise the type properly.

---

### 55. Replace Error Code with Exception `replace-error-code-with-exception`
**Smells**: magic return codes that callers forget to check
**Do**: throw instead.
**Pre**: the condition really is exceptional. If the caller can reasonably expect
it, an exception is the wrong tool — see #56.

**Mechanics**
1. Decide checked vs unchecked (or the language's equivalent): can the caller
   reasonably be expected to handle it? Yes → checked/explicit. No → unchecked.
2. Add the new throwing method alongside the code-returning one.
3. Move each caller across: replace the code check with a try/catch or propagation;
   test after each.
4. Delete the old method.

**Do not** use exceptions for ordinary control flow. In Go and Rust the idiomatic
target is a returned error / `Result`, not a panic.

---

### 56. Replace Exception with Test `replace-exception-with-test`
**Smells**: exceptions used for a condition the caller can simply check
**Do**: check first; reserve exceptions for the genuinely unexpected.

**Mechanics**
1. Add the guard clause before the risky call.
2. Move the catch block's handling into the guard's branch.
3. Test with the exception path forced, to confirm the guard covers it.
4. Remove the try/catch.

**Caution**: watch for the check-then-act race. If the condition can change between
the check and the action (files, shared state, concurrency), the exception was
correct — keep it.

**Inverse**: Replace Error Code with Exception
