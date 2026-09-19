# Organizing Data (16)

Data representation. The recurring theme: primitives and raw structures lose
meaning, and meaning is what lets behaviour find its home.

Note for non-Java languages: several of these (Self Encapsulate Field, Encapsulate
Field, Replace Record with Data Class) are partly artefacts of Java-era style.
Translate to the idiom — Python properties, C# auto-properties, TS getters,
Go struct methods — rather than applying them literally.

---

### 18. Self Encapsulate Field `self-encapsulate-field`
**Smells**: subclass needing to vary access; blocked Move Field
**Do**: route the class's *own* access to a field through its accessors.
**Pre**: you need the indirection — a subclass will override, or lazy
initialisation is coming, or Move Field needs a seam. Otherwise skip it; direct
access is fine and clearer.

**Mechanics**
1. Add getter and setter if absent.
2. Replace internal reads with the getter, internal writes with the setter, one at a time.
3. Make the field private.
4. Test.

**Inverse**: direct field access

---

### 19. Replace Data Value with Object `replace-data-value-with-object`
**Smells**: Primitive Obsession
**Do**: turn a primitive field that has grown behaviour or validation into a class.

**Mechanics**
1. Create the class with a final field for the value, a getter, and a constructor.
2. Change the host's field type to the new class.
3. Update the host's getter to return `value.getValue()`, and the setter to
   construct a new instance.
4. Test, then move behaviour and validation into the new class.

**Follow with**: Change Value to Reference, if instances need shared identity.

---

### 20. Change Value to Reference `change-value-to-reference`
**Smells**: many equal copies of an object that should be one shared entity
**Do**: replace multiple equal instances with a single shared instance.
**Pre**: the object has real identity (a Customer, an Account), and updates to one
should be visible everywhere. Do not do this to genuine value objects.

**Mechanics**
1. **Replace Constructor with Factory Method**.
2. Decide who owns access — a registry, repository, or the object that logically
   contains them.
3. Decide whether instances are created eagerly (precreate all) or lazily
   (factory looks up, creates on miss).
4. Change the factory to return the shared instance.
5. Test — pay attention to anywhere the code relied on copies being independent.

**Inverse**: Change Reference to Value
**Warning**: this introduces shared mutable state. Confirm the concurrency story.

---

### 21. Change Reference to Value `change-reference-to-value`
**Smells**: awkward shared lifecycle for something that is really just a value
**Do**: replace a shared reference object with immutable value instances.
**Pre**: the object is small and immutable — or can be made immutable.

**Mechanics**
1. Make the class immutable: **Remove Setting Method** on every field.
2. Implement value equality (`equals`/`hashCode`, `__eq__`/`__hash__`, `PartialEq`,
   record/dataclass semantics — whatever the language provides).
3. Remove the factory/registry; allow direct construction.
4. Test, watching for anywhere identity comparison (`==` on references) was used.

**Inverse**: Change Value to Reference

---

### 22. Replace Array with Object `replace-array-with-object`
**Smells**: Primitive Obsession — an array whose *positions* carry meaning
(`row[0]` is the name, `row[1]` is the score).
**Do**: replace it with a class with named fields.

**Mechanics**
1. Create the class with the array as an internal field to start.
2. Add a named accessor per position, delegating to the array index.
3. Repoint clients at the named accessors, one at a time, testing.
4. Replace the array field with real typed fields; update the accessors.
5. Delete the array.

**Modern equivalent**: a record/dataclass/struct/named tuple. Reach for that.

---

### 23. Duplicate Observed Data `duplicate-observed-data`
**Smells**: Large Class — domain data trapped in a GUI/controller class
**Do**: move domain data to a domain object and keep the view in sync via observer.
**Pre**: you actually need both copies — otherwise just **Move Field**.

**Mechanics**
1. Create the domain class if absent, and a link from the view to it.
2. Make the domain object observable (observer/event/binding mechanism).
3. Register the view as observer.
4. **Move Field** each piece of data to the domain object.
5. Have the view's event handlers write to the domain object, and its update
   method read from it.
6. Test the round trip in both directions.

**Modern equivalent**: this is a hand-rolled version of what reactive state
libraries and data binding do. If the framework offers it, use the framework.

---

### 24. Change Unidirectional Association to Bidirectional `change-unidirectional-to-bidirectional`
**Do**: add a back-pointer so both classes can navigate.
**Pre**: you genuinely need the reverse navigation. This *adds* coupling — the
default should be to avoid it.

**Mechanics**
1. Add the back-pointer field.
2. Decide which side is the controller — the one-side in a one-to-many, or the
   more responsible side in a one-to-one.
3. Add a modifier on the controlling side that sets both directions consistently.
4. Make the non-controlling side's modifier package-private/internal so it cannot
   be desynchronised.
5. Test, especially for the half-updated case.

**Inverse**: Change Bidirectional Association to Unidirectional

---

### 25. Change Bidirectional Association to Unidirectional `change-bidirectional-to-unidirectional`
**Smells**: Inappropriate Intimacy
**Do**: delete the unneeded direction.

**Mechanics**
1. Prove the direction is unused: find every read of the back-pointer.
2. If a few readers remain, see whether the value can be passed in as a parameter
   or reached another way (**Replace Parameter with Method** in reverse).
3. **Self Encapsulate Field** on the back-pointer, then make the getter compute or
   fail; test.
4. Delete the field and its modifiers.

**Inverse**: Change Unidirectional Association to Bidirectional

---

### 26. Replace Magic Number with Symbolic Constant `replace-magic-number-with-constant`
**Smells**: unexplained literals
**Do**: name the number.

**Mechanics**
1. Declare a constant with a name explaining the *meaning*, not the value
   (`GRAVITATIONAL_ACCELERATION`, not `NINE_POINT_EIGHT`).
2. Replace occurrences — but only those with the same meaning. Two `7`s that mean
   different things get two constants.
3. Test.

**Note**: if the number is a type code, go to **Replace Type Code with Class**
instead — a bare constant is only half the fix.

---

### 27. Encapsulate Field `encapsulate-field`
**Smells**: Data Class, public mutable state
**Do**: make the field private, expose accessors.

**Mechanics**
1. Add getter and setter.
2. Repoint every external reference; test.
3. Make the field private.

**Then**: look for behaviour that should move in (**Move Method**). Encapsulation
alone does not fix a Data Class — it just stops the bleeding.

---

### 28. Encapsulate Collection `encapsulate-collection`
**Smells**: Data Class; callers mutating a returned collection behind the owner's back
**Do**: return a read-only view; provide add/remove methods.

**Mechanics**
1. Add `addX` / `removeX` methods on the owner.
2. Initialise the field to an empty collection; remove any setter that replaced it
   wholesale (or make it copy the contents instead of aliasing).
3. Repoint callers that mutate the returned collection onto add/remove; test each.
4. Change the getter to return an unmodifiable/frozen/copied view.
5. Compile and let the failures find remaining mutators.

**Then**: look for callers that iterate the collection to compute something —
those are Feature Envy. **Move Method** them onto the owner.

---

### 29. Replace Record with Data Class `replace-record-with-data-class`
**Smells**: raw records from a database row, CSV, or wire format leaking through
the codebase
**Do**: wrap the record in a class with named accessors.

**Mechanics**
1. Create the class with the raw record as a private field.
2. Add an accessor per element.
3. Repoint clients; test.
4. Once no client touches the raw record, replace the internal representation.

**Note**: this is the first step, not the goal. Follow with **Move Method** to
give the new class behaviour, or it becomes a Data Class.

---

### 30. Replace Type Code with Class `replace-type-code-with-class`
**Smells**: Primitive Obsession
**Do**: replace an int/string type code with a dedicated class.
**Pre**: the type code does *not* drive behaviour (no conditionals on it). If it
does, use one of the next two instead.

**Mechanics**
1. Create the class; give it a private field for the code, a getter, and static
   instances (or an enum) for each legal value.
2. Add a static lookup from raw code to instance.
3. Change the host's field type; keep the old code-based accessors delegating
   temporarily so callers keep compiling.
4. Repoint callers one at a time; test.
5. Delete the code-based accessors.

**Modern equivalent**: a language-level `enum`. Prefer it.

---

### 31. Replace Type Code with Subclasses `replace-type-code-with-subclasses`
**Smells**: Switch Statements, Primitive Obsession
**Do**: turn each type-code value into a subclass.
**Pre**: the code is **immutable after construction** and the class has no other
subclassing need. Otherwise use State/Strategy.

**Mechanics**
1. **Self Encapsulate Field** on the type code.
2. **Replace Constructor with Factory Method** on the host.
3. Create one subclass per value; each overrides the type-code getter to return
   its constant.
4. Make the factory return the right subclass per code.
5. Test; then remove the type-code field and make the getter abstract.
6. Now **Replace Conditional with Polymorphism** on each switch over the code.

**Follow with**: Replace Conditional with Polymorphism — this refactoring only
builds the structure; it does not remove the conditionals by itself.

---

### 32. Replace Type Code with State/Strategy `replace-type-code-with-state-strategy`
**Smells**: Switch Statements, Primitive Obsession
**Do**: move the type code into a state object held by the host.
**Pre**: the code **changes during the object's life**, or the class already has
subclasses for another reason. Both rule out subclassing the host.

**Mechanics**
1. **Self Encapsulate Field** on the type code.
2. Create the state superclass and one subclass per value.
3. Add abstract getter on the state class; each subclass returns its constant.
4. Replace the host's type-code field with a field holding the state object.
5. Change the host's setter to assign the right state instance.
6. Test; then **Replace Conditional with Polymorphism** to push behaviour into the
   state classes.

**Difference from #31**: subclasses replace the *host*; state objects are *held by*
the host and can be swapped at runtime.

---

### 33. Replace Subclass with Fields `replace-subclass-with-fields`
**Smells**: Lazy Class — subclasses that differ only in constant return values
**Do**: collapse them into fields on the parent.
**Pre**: the subclasses have no behavioural difference, only data.

**Mechanics**
1. **Replace Constructor with Factory Method** on the superclass.
2. Move any subclass-type-testing code out of clients into the factory.
3. Add a field to the superclass for each differing constant.
4. Add a protected superclass constructor taking the values.
5. Point each subclass constructor at it, then repoint the factory at the
   superclass constructor directly.
6. Test, delete the subclasses.

**Inverse**: Replace Type Code with Subclasses
