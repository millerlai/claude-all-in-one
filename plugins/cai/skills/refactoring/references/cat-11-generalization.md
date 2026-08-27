# Dealing with Generalization (12)

Moving features up and down a hierarchy, and building or dismantling hierarchies.
These have the widest blast radius in the catalog — a change to a superclass
touches every subclass and every client of all of them.

Before any of these, map the hierarchy: every subclass, every override, every
client. Do not start until you have that map.

**Language note**: Go, Rust and most modern style guides prefer composition over
inheritance. In those settings, read "superclass" as "interface/trait +
delegated implementation", and treat **Replace Inheritance with Delegation** as
the default direction of travel.

---

### 57. Pull Up Field `pull-up-field`
**Smells**: Duplicated Code across siblings
**Do**: move an identical field from subclasses to the superclass.
**Pre**: the field means the same thing in every subclass, even if the names
differ. Same name but different meaning → do not pull up.

**Mechanics**
1. Verify every subclass uses it the same way.
2. **Rename Field** in subclasses so the names agree.
3. Declare it in the superclass (protected, or private with accessors — prefer the
   latter).
4. Delete the subclass fields; test.

**Inverse**: Push Down Field

---

### 58. Pull Up Method `pull-up-method`
**Smells**: Duplicated Code across siblings
**Do**: move an identical method to the superclass.
**Pre**: the bodies are identical, or can be made identical. Bodies that differ in
the middle → **Form Template Method** instead.

**Mechanics**
1. Inspect the bodies; align them (**Rename Method**, **Add/Remove Parameter**,
   **Pull Up Field** for anything they reference).
2. Copy one body into the superclass; adjust references.
3. Delete one subclass copy; test. Repeat for each.
4. Check remaining subclasses and clients for anything now broken or redundant.

**Inverse**: Push Down Method

---

### 59. Pull Up Constructor Body `pull-up-constructor-body`
**Smells**: Duplicated Code in subclass constructors
**Do**: move common construction into a superclass constructor.

**Mechanics**
1. Add a superclass constructor if absent.
2. Move the common statements to it, taking the needed values as parameters.
3. Have each subclass constructor call it first (`super(...)`), keeping only its
   own specific statements.
4. Test.

**Note**: constructors are more constrained than methods — ordering matters and
`super` must come first in most languages. If it gets awkward, use
**Replace Constructor with Factory Method** and pull up an ordinary init method
instead.

---

### 60. Push Down Method `push-down-method`
**Smells**: Refused Bequest
**Do**: move a superclass method used by only some subclasses down into them.

**Mechanics**
1. Confirm which subclasses actually use it.
2. Copy it into each of those; test.
3. Delete from the superclass; test.
4. Remove it from any interface the superclass exposes if no longer general.

**Inverse**: Pull Up Method

---

### 61. Push Down Field `push-down-field`
**Smells**: Refused Bequest
**Do**: move a superclass field used by only some subclasses down.

**Mechanics**
1. Declare it in each subclass that uses it.
2. Delete it from the superclass.
3. Test; remove now-dead superclass accessors.

**Inverse**: Pull Up Field

---

### 62. Extract Subclass `extract-subclass`
**Smells**: Large Class; features used only by some instances
**Do**: create a subclass for the special-case features.
**Pre**: the variation is fixed at construction. If it changes over the object's
life, **Extract Class** (delegation) instead — you cannot change an object's class.

**Mechanics**
1. Create the subclass; give the superclass a factory method if construction is
   direct (**Replace Constructor with Factory Method**).
2. Make the factory return the subclass for the special case.
3. **Push Down Method** and **Push Down Field** the special-case features, one at a
   time, testing.
4. Remove now-redundant type flags on the superclass.
5. Consider making the superclass abstract.

**Inverse**: Collapse Hierarchy / Replace Subclass with Fields

---

### 63. Extract Superclass `extract-superclass`
**Smells**: Duplicated Code, Alternative Classes with Different Interfaces
**Do**: create a common parent for two classes with shared features.
**Pre**: they are genuinely the same kind of thing. Sharing a few methods is not
the same as sharing an identity — if in doubt, **Extract Class** and delegate
instead of inheriting.

**Mechanics**
1. Create the (usually abstract) superclass; make both classes extend it.
2. **Pull Up Constructor Body**, then **Pull Up Field**, then **Pull Up Method**,
   one at a time, testing after each.
3. Align names and signatures first where they differ (**Rename Method**).
4. Examine clients — many can now be typed to the superclass.

**Alternative**: **Extract Interface**, when only the protocol is shared.

---

### 64. Extract Interface `extract-interface`
**Smells**: Large Class (usage clusters), duplicated protocol, untestable dependency
**Do**: name a subset of a class's protocol as an interface.

**Mechanics**
1. Create an empty interface.
2. Declare the methods for the chosen usage cluster.
3. Make the class implement it.
4. Repoint client declarations to the interface type where the cluster fits.
5. Test.

**Best use**: identifying the seams of a Large Class, and creating a test seam for
a hard dependency (clock, network, filesystem). Do not extract an interface with
exactly one implementation and no test need — that is Speculative Generality.

---

### 65. Collapse Hierarchy `collapse-hierarchy`
**Smells**: Lazy Class, Speculative Generality
**Do**: merge a subclass and superclass that are no longer meaningfully different.

**Mechanics**
1. Choose which to remove.
2. **Pull Up** or **Push Down** all fields and methods so everything lands in the
   survivor, testing after each move.
3. Repoint all references to the survivor.
4. Delete the empty class; test.

**Inverse**: Extract Subclass / Extract Superclass

---

### 66. Form Template Method `form-template-method`
**Smells**: Duplicated Code across siblings with the same shape but differing steps
**Do**: lift the shared sequence to the superclass; leave the varying steps as
overridable methods.

**Mechanics**
1. Decompose both methods so the *sequence of steps* becomes identical, even
   though the steps differ (**Extract Method** on each differing chunk).
2. Align the extracted methods' names and signatures across subclasses.
3. **Pull Up Method** on the now-identical outer method — this is the template.
4. Make the varying steps abstract (or give sensible defaults) on the superclass.
5. Test after each pull-up.

**Step 1 is 90% of the work.** Do not attempt the pull-up until the shapes match.
**Alternative**: pass the varying steps as functions/closures instead of
subclassing — usually simpler in modern languages.

---

### 67. Replace Inheritance with Delegation `replace-inheritance-with-delegation`
**Smells**: Refused Bequest, Inappropriate Intimacy
**Do**: hold the former superclass as a field instead of extending it.
**Pre**: the subclass uses only part of the superclass, or does not honour its
interface. This is the right default when inheritance was chosen for code reuse
rather than for genuine "is-a".

**Mechanics**
1. Add a field in the subclass for an instance of the superclass; initialise it to
   the object itself at first (`this`) so nothing breaks.
2. Change each inherited method the subclass uses into a delegating method to the
   field, one at a time, testing.
3. Remove the `extends`; point the field at a fresh instance.
4. Compile; fix the fallout — anything that breaks was an undeclared dependency.
5. Delete delegating methods clients no longer need.

**Cost**: you lose polymorphic substitutability. Check every place the subclass was
used as its superclass type; some may need an extracted interface.
**Inverse**: Replace Delegation with Inheritance

---

### 68. Replace Delegation with Inheritance `replace-delegation-with-inheritance`
**Smells**: Middle Man — a class delegating nearly everything
**Do**: inherit instead.
**Pre**: **all** of the delegate's interface is being forwarded, and the delegating
object is a genuine subtype. If it forwards only some methods, inheriting would
expose the rest wrongly — leave it as delegation.

**Mechanics**
1. Make the delegating class extend the delegate.
2. Set the delegate field to `this`.
3. Delete the simple delegating methods one at a time, testing.
4. Repoint anything using the delegate field directly.
5. Remove the field.

**Also blocked when**: the delegate is shared between several objects (state would
be duplicated), or the class already has a superclass.
**Inverse**: Replace Inheritance with Delegation
