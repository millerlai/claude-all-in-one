# Big Refactorings (4)

These are not single moves. Each is a **campaign** — weeks or months of small
refactorings pointed at a structural goal, carried out alongside feature work
rather than as a freeze.

Rules for all four:

- **Never** propose one as a single task or a single PR. Produce a direction and
  a first increment.
- Every increment must leave the system shippable and green.
- The campaign must be visible to the team; it cannot be done quietly by one
  person in one sitting.
- Stop early if the direction proves wrong. Sunk cost is not a reason to continue.
- Progress happens where you are already working. Refactor the parts you touch for
  features; do not open a separate front.

When Claude identifies one of these, its output should be a **roadmap document
plus a first small step**, never an attempt to execute the whole thing.

---

### 69. Tease Apart Inheritance `tease-apart-inheritance`
**Symptom**: one hierarchy doing two jobs at once — class names read like
`SessionDeal`, `TabularSessionDeal`, `ActiveDeal`, `TabularActiveDeal`. The
combinatorial explosion is the tell.

**Direction**: identify the two (or more) independent axes of variation; keep one
as inheritance and extract the other into a delegated hierarchy.

**Increments**
1. Build a grid: rows = one axis, columns = the other. Confirm the duplication.
2. Pick the *less* important axis — usually the one appearing in name suffixes.
3. Use **Extract Class** to create a delegate hierarchy for that axis.
4. **Move Method** / **Move Field** the axis-specific features into it, one at a
   time, testing.
5. When the subclasses for that axis are empty, delete them
   (**Collapse Hierarchy**).
6. Repeat if a third axis exists.

**Result**: two small hierarchies composed, instead of one large multiplied one.

---

### 70. Convert Procedural Design to Objects `convert-procedural-design-to-objects`
**Symptom**: long procedures operating on dumb record/struct/dictionary data;
class names ending in `Manager`, `Util`, `Processor`, `Service` that hold no state.

**Direction**: give the data classes their behaviour.

**Increments**
1. **Replace Record with Data Class** on each record type.
2. Take one long procedure. **Extract Method** it into coherent chunks.
3. **Move Method** each chunk onto the data class whose data it uses most.
4. Repeat, procedure by procedure, until the procedural classes are thin
   coordinators.
5. **Inline Class** or delete the now-empty procedural shells.

**Do not** attempt to redesign everything up front. Convert one procedure per
session and ship.

**Caveat**: not every procedural design is wrong. Data pipelines, transforms and
functional cores are legitimately procedural. Apply this where behaviour and data
are being forced apart, not where they are properly separated by design.

---

### 71. Separate Domain from Presentation `separate-domain-from-presentation`
**Symptom**: business rules living in controllers, view models, React components,
or window classes. The tell: you cannot test a rule without instantiating UI.

**Direction**: move all domain logic into domain classes that know nothing about
the UI. Presentation depends on domain; never the reverse.

**Increments**
1. Create a domain class for each screen's underlying concept.
2. **Move Field** the domain data out of the presentation class — use
   **Duplicate Observed Data** where the UI needs its own copy in sync.
3. **Extract Method** the business rules embedded in event handlers, then
   **Move Method** them to the domain class.
4. Leave in presentation only: reading input, formatting output, wiring events.
5. Write tests against the domain class with no UI in the picture. **The new tests
   are the proof this worked.**

**Check the direction of dependency after every increment.** A single import of a
UI type into a domain class undoes the campaign.

---

### 72. Extract Hierarchy `extract-hierarchy`
**Symptom**: one class doing too much, its methods riddled with conditionals that
all switch on the same handful of "cases" or "variants".

**Direction**: one subclass per case; the conditionals disappear into polymorphism.

**Increments**
1. Enumerate the cases the conditionals distinguish. Write them down explicitly —
   this list is the design.
2. If the case is not already explicit, introduce it as a type code, then
   **Replace Type Code with Subclasses** (fixed at construction) or
   **Replace Type Code with State/Strategy** (varies at runtime).
3. **Replace Constructor with Factory Method** so creation picks the subclass.
4. One conditional at a time: **Replace Conditional with Polymorphism**, testing
   after each.
5. **Push Down Method** / **Push Down Field** anything now case-specific.
6. Make the base abstract when nothing concrete remains.

**Stop condition**: if the cases turn out not to be independent — you keep needing
combinations — you are looking at **Tease Apart Inheritance** instead. Recognise
that early; a hierarchy with `AandB`, `AandC` subclasses is the failure mode.
