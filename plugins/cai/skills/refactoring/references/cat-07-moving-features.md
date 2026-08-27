# Moving Features Between Objects (8)

Deciding where behaviour lives. The core question is always: *which class holds
the data this code uses?* Put the behaviour there.

These refactorings change signatures and therefore have a larger blast radius
than the method-level ones. Find every reference before you start.

---

### 10. Move Method `move-method`
**Smells**: Feature Envy, Shotgun Surgery, Inappropriate Intimacy, Parallel Inheritance Hierarchies, Data Class
**Do**: move a method to the class it actually talks to.
**Pre**: the target class is reachable from the source (field, parameter, or
constructible). Do not move a method that subclasses override without handling
the whole hierarchy.

**Mechanics**
1. Inventory everything the method uses from its current class — fields, other
   methods, superclass features. Consider whether those should move too.
2. Check for overrides in sub/superclasses. If present, either move the whole
   family or abandon.
3. Copy the method to the target; adjust it to fit (rename if the old name only
   made sense in the old home).
4. Compile the target; add whatever references it needs.
5. Decide how the source reaches the target: an existing field, an existing
   parameter, or pass it in.
6. Turn the original into a delegating call.
7. Test.
8. Decide whether to keep the delegator (useful for a wide public API) or update
   all callers and delete it. Prefer deleting.

**Inverse**: Move Method back
**Chains with**: Extract Method (extract the envious part first)

---

### 11. Move Field `move-field`
**Smells**: Feature Envy, Inappropriate Intimacy, Parallel Inheritance Hierarchies
**Do**: move a field to the class that uses it most.
**Pre**: you know every access. Public field → **Self Encapsulate Field** first so
that all access goes through accessors, which makes the move mechanical.

**Mechanics**
1. If the field is public or directly accessed, **Self Encapsulate Field** first.
2. Create the field plus accessors in the target.
3. Ensure the source can reach a target instance.
4. Delete the source field; point the source's accessors at the target's.
5. Test, then push callers to the target directly where sensible.

**Inverse**: Move Field back

---

### 12. Extract Class `extract-class`
**Smells**: Large Class, Divergent Change, Data Clumps, Temporary Field, Primitive Obsession, Duplicated Code
**Do**: split one class into two along a cohesive seam.
**Pre**: you can name the new class. If the best name you have is a suffix like
"Info" or "Helper", the seam is wrong — look again.

**Mechanics**
1. Decide the split. Look for field-name prefixes/suffixes and for methods that
   use only a subset of fields.
2. Create the new class. Wire the link (usually source → new; add the back-link
   only if genuinely required).
3. **Move Field** each field, one at a time, testing.
4. **Move Method** each method, starting from the lowest-level ones, testing.
5. Review both interfaces; trim anything now unused.
6. Decide whether the new class is exposed to clients or stays hidden behind the
   original — if hidden, consider **Hide Delegate**.
7. If the new object is immutable-shaped, consider making it a value object.

**Inverse**: Inline Class

---

### 13. Inline Class `inline-class`
**Smells**: Lazy Class, Speculative Generality, Shotgun Surgery, Middle Man
**Do**: fold a class that no longer pays its way into its user.
**Pre**: it has essentially one client. Many clients → it is not lazy, it is shared.

**Mechanics**
1. Declare the absorbing class's own versions of the doomed class's public methods,
   delegating for now.
2. Change all references from the doomed class to the absorbing one; test.
3. **Move Method** and **Move Field** everything across.
4. Delete the empty class.

**Inverse**: Extract Class

---

### 14. Hide Delegate `hide-delegate`
**Smells**: Message Chains, Inappropriate Intimacy
**Do**: add a delegating method on the server so clients stop navigating through it.
**Pre**: the client's dependency on the navigation path is a real liability — the
intermediate structure is likely to change.

**Mechanics**
1. For each call the client makes through the server to the delegate, add a
   simple delegating method on the server.
2. Repoint clients at it; test after each.
3. When no client needs it, remove the accessor that exposed the delegate.

**Inverse**: Remove Middle Man
**Tension**: over-applying this produces Middle Man. Hide the links clients
actually shouldn't know about — not every link.

---

### 15. Remove Middle Man `remove-middle-man`
**Smells**: Middle Man
**Do**: let clients call the delegate directly.
**Mechanics**
1. Add an accessor for the delegate on the server.
2. Move each client from `server.foo()` to `server.getDelegate().foo()`; test.
3. Delete the delegating methods that are now unused.

**Inverse**: Hide Delegate

---

### 16. Introduce Foreign Method `introduce-foreign-method`
**Smells**: Incomplete Library Class
**Do**: add the missing behaviour as a method in the *client* class, taking the
library instance as its first parameter.
**Pre**: you cannot modify the library, and there are only one or two such methods.

**Mechanics**
1. Write the method in the client class, taking the library object as a parameter.
2. Comment it clearly as a foreign method that belongs on the library class.
3. Replace inline occurrences with calls.

**Escalate to**: Introduce Local Extension when the count grows past two or three.

---

### 17. Introduce Local Extension `introduce-local-extension`
**Smells**: Incomplete Library Class
**Do**: create your own subclass or wrapper of the library class, holding all the
methods you wish it had.
**Pre**: several foreign methods have accumulated.

**Mechanics**
1. Choose subclass or wrapper:
   - **Subclass** — simpler, but impossible if the class is final/sealed, and it
     does not help with instances the library itself hands you.
   - **Wrapper** — works in both those cases, but you must forward the entire
     interface, and object identity is no longer preserved.
2. Give it a constructor taking the original (wrapper) or mirroring the original's
   constructors (subclass).
3. Move the foreign methods in.
4. Repoint clients at the extension.

**Caution**: with a wrapper, watch for equality and identity comparisons across
the boundary — they are the usual source of bugs here.
