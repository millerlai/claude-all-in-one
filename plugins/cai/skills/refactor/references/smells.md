# Code smells → refactoring routing

A smell is a surface indication that usually corresponds to a deeper problem.
It is a hint, not a verdict. Never refactor without first naming the smell — the
name is what makes the choice of refactoring defensible in review.

There is no metric threshold that decides this for you. Line counts and field
counts are evidence, not proof. Weigh them against how often the code is read
and changed.

## Quick routing table

| Smell | Primary moves | Secondary |
|---|---|---|
| Duplicated Code | Extract Method, Pull Up Method | Form Template Method, Extract Class, Substitute Algorithm |
| Long Method | Extract Method | Replace Temp with Query, Decompose Conditional, Replace Method with Method Object |
| Large Class | Extract Class, Extract Subclass | Extract Interface, Duplicate Observed Data |
| Long Parameter List | Introduce Parameter Object, Preserve Whole Object | Replace Parameter with Method |
| Divergent Change | Extract Class | — |
| Shotgun Surgery | Move Method, Move Field | Inline Class |
| Feature Envy | Move Method | Extract Method (then Move Method) |
| Data Clumps | Extract Class, Introduce Parameter Object | Preserve Whole Object |
| Primitive Obsession | Replace Data Value with Object, Replace Type Code with Class | Extract Class, Introduce Parameter Object, Replace Array with Object |
| Switch Statements | Replace Conditional with Polymorphism | Replace Type Code with Subclasses/State-Strategy, Replace Parameter with Explicit Methods, Introduce Null Object |
| Parallel Inheritance Hierarchies | Move Method, Move Field | — |
| Lazy Class | Inline Class, Collapse Hierarchy | — |
| Speculative Generality | Collapse Hierarchy, Inline Class | Remove Parameter, Rename Method |
| Temporary Field | Extract Class | Introduce Null Object |
| Message Chains | Hide Delegate | Extract Method + Move Method |
| Middle Man | Remove Middle Man | Inline Method, Replace Delegation with Inheritance |
| Inappropriate Intimacy | Move Method, Move Field | Change Bidirectional Association to Unidirectional, Extract Class, Hide Delegate, Replace Inheritance with Delegation |
| Alternative Classes with Different Interfaces | Rename Method, Move Method | Extract Superclass |
| Incomplete Library Class | Introduce Foreign Method | Introduce Local Extension |
| Data Class | Move Method, Encapsulate Field | Encapsulate Collection, Remove Setting Method, Hide Method |
| Refused Bequest | Push Down Method, Push Down Field | Replace Inheritance with Delegation |
| Comments | Extract Method, Rename Method | Introduce Assertion |

---

## The smells in detail

### 1. Duplicated Code
**Detect**: identical or near-identical expressions in two places.
- Same class → **Extract Method**, call from both.
- Sibling subclasses → **Extract Method** in each, then **Pull Up Method**. If the
  bodies differ in the middle, **Form Template Method**.
- Same outcome, different algorithm → keep the clearer one, **Substitute Algorithm**.
- Unrelated classes → **Extract Class** and let both use it, or decide the
  behaviour belongs to exactly one of them and route the other through it.

**Caution**: coincidental duplication is not duplication. If the two copies would
change for *different* reasons, unifying them creates coupling that is worse than
the copy. Apply the rule of three.

### 2. Long Method
**Detect**: you have to scroll; you need a comment to explain a block; nested
loops and conditionals.
- 99% of the time: **Extract Method**. Name by *intention*, not mechanism.
- Blocked by temps → **Replace Temp with Query**, **Split Temporary Variable**.
- Blocked by parameters → **Introduce Parameter Object**, **Preserve Whole Object**.
- Still tangled → **Replace Method with Method Object** (heavy artillery).
- Conditionals → **Decompose Conditional**. Loops → extract the loop body.

**Heuristic**: the trigger is not length, it is the semantic distance between what
the method is called and how it works. Extract even one line if the name explains
it better than the code does.

### 3. Large Class
**Detect**: too many fields; too many methods; the class name is a noun that means
nothing specific ("Manager", "Helper", "Data").
- **Extract Class** on a cohesive subset of fields (look for common prefixes and
  suffixes — `depositAmount`/`depositCurrency` belong together).
- If the subset makes sense as a specialisation → **Extract Subclass**.
- Look at how clients use it and **Extract Interface** per usage cluster; the
  clusters show you the seams.
- GUI class holding domain data → **Duplicate Observed Data** to move the data out.

### 4. Long Parameter List
**Detect**: 4+ parameters, or parameters that keep getting added.
- Data reachable from an object you already have → **Replace Parameter with Method**.
- Several parameters all come off one object → **Preserve Whole Object**.
- Several parameters with no owning object → **Introduce Parameter Object**.

**Exception**: when you deliberately do not want the callee to depend on the caller's
object, a long list is the correct price. Note the tradeoff rather than blindly compressing.

### 5. Divergent Change
**Detect**: one class changes for many unrelated reasons — "these three methods
change per database, those four change per payment type".
- **Extract Class** per axis of change.
Goal: one reason to change per class.

### 6. Shotgun Surgery
**Detect**: one conceptual change forces small edits across many files.
- **Move Method** / **Move Field** to gather the scattered behaviour into one class.
- Create the class if none fits; **Inline Class** to absorb near-empty ones.
Goal: one class per common change. Divergent Change and Shotgun Surgery are
opposites — fixing one too aggressively creates the other.

### 7. Feature Envy
**Detect**: a method calls many getters on another object to compute something.
- **Move Method** to the class that owns the data.
- Only part of it envious → **Extract Method** on that part, then **Move Method**.
- Method uses several classes → move it to the one holding the most data it uses.

**Exception**: Strategy, Visitor and similar patterns break this rule on purpose,
to isolate what varies. Do not "fix" a deliberate pattern.

### 8. Data Clumps
**Detect**: the same 3–4 items travel together as fields and as parameters.
- **Extract Class** where they appear as fields.
- **Introduce Parameter Object** / **Preserve Whole Object** in signatures.

**Test**: delete one of the items — do the rest still make sense? If not, there is
an object waiting to be born.

### 9. Primitive Obsession
**Detect**: strings and ints carrying meaning — phone numbers, currency, ZIP codes,
ranges, status flags.
- Single value → **Replace Data Value with Object**.
- Type code with no behaviour → **Replace Type Code with Class**.
- Type code driving conditionals → **Replace Type Code with Subclasses**, or
  **Replace Type Code with State/Strategy** if the code changes during the object's
  life or the class already has a superclass.
- Group of fields → **Extract Class**. In signatures → **Introduce Parameter Object**.
- Array with positional meaning → **Replace Array with Object**.

### 10. Switch Statements
**Detect**: the same `switch`/`if-else` chain on a type code appearing in several
places. Adding a case means editing all of them.
- **Extract Method** on the switch, **Move Method** onto the class that owns the
  type code, then **Replace Type Code with Subclasses** (or **State/Strategy**),
  then **Replace Conditional with Polymorphism**.
- Few cases, single method, stable → polymorphism is overkill; use
  **Replace Parameter with Explicit Methods**.
- One branch handles null → **Introduce Null Object**.

**Caution**: a switch inside a factory that *creates* the polymorphic objects is
correct and should stay. There must be exactly one.

### 11. Parallel Inheritance Hierarchies
**Detect**: every new subclass of A forces a new subclass of B; matching name prefixes.
- **Move Method** / **Move Field** so one hierarchy refers to instances of the other,
  until the referring hierarchy collapses.

### 12. Lazy Class
**Detect**: a class that no longer earns its maintenance cost — often the residue
of an earlier refactoring or of a plan that never happened.
- Near-useless subclass → **Collapse Hierarchy**.
- Near-useless component → **Inline Class**.

### 13. Speculative Generality
**Detect**: hooks, abstract classes, and parameters serving a future that never
arrived. Strong tell: the only caller is a test.
- **Collapse Hierarchy**, **Inline Class**, **Remove Parameter**, **Rename Method**.
- If a method or class is exercised only by its own test, delete both.

### 14. Temporary Field
**Detect**: a field set only in certain circumstances, null or meaningless the rest
of the time; typically the scratch state of one complex algorithm.
- **Extract Class** holding the field plus the code that uses it (this produces a
  method object).
- **Introduce Null Object** for the invalid state, to delete the guards.

### 15. Message Chains
**Detect**: `a.getB().getC().getD()`. The client is coupled to the navigation path.
- **Hide Delegate** at one or more points in the chain.
- Better: **Extract Method** on what the client actually does with the result, then
  **Move Method** to push it down the chain.

**Caution**: hiding every link turns each intermediate into a Middle Man. This
smell and Middle Man are opposites; find the balance, don't maximise either.

### 16. Middle Man
**Detect**: half a class's methods do nothing but delegate.
- **Remove Middle Man**, let clients talk to the real object.
- A few trivial delegators → **Inline Method**.
- Delegation plus real extra behaviour → **Replace Delegation with Inheritance**.

### 17. Inappropriate Intimacy
**Detect**: two classes reaching into each other's private parts; bidirectional
references; subclass depending on superclass internals.
- **Move Method** / **Move Field** to put things on the right side.
- **Change Bidirectional Association to Unidirectional** if one direction is unused.
- Shared concern → **Extract Class**; or **Hide Delegate** to interpose.
- Inheritance-driven → **Replace Inheritance with Delegation**.

### 18. Alternative Classes with Different Interfaces
**Detect**: two classes do the same job with different method names.
- **Rename Method** to align signatures, **Move Method** until protocols match,
  then **Extract Superclass** (or an interface).

### 19. Incomplete Library Class
**Detect**: you need a method a third-party class doesn't have and you cannot edit it.
- One or two methods → **Introduce Foreign Method**.
- A body of behaviour → **Introduce Local Extension** (subclass or wrapper).

### 20. Data Class
**Detect**: fields with getters and setters and nothing else; other classes
manipulate its internals in detail.
- Public fields → **Encapsulate Field**. Collection fields → **Encapsulate Collection**.
- Fields that must not change after construction → **Remove Setting Method**.
- Find the behaviour operating on this data elsewhere and **Move Method** it in;
  **Extract Method** first if only part of a caller can move.
- Then **Hide Method** on accessors no longer needed outside.

**Exception**: DTOs, wire formats, ORM rows and value objects are legitimately
data-only. Do not "fix" a boundary type.

### 21. Refused Bequest
**Detect**: a subclass ignores or nulls out much of what it inherits.
- **Push Down Method** / **Push Down Field** into a new sibling, leaving only what
  is genuinely common in the parent.
- Much stronger version: the subclass reuses implementation but does not honour the
  superclass's *interface* (breaks substitutability). That one is serious —
  **Replace Inheritance with Delegation**.

**Note**: refusing an implementation is mild and often not worth cleaning. Refusing
an interface is a real defect.

### 22. Comments
Comments are not themselves a smell — they are frequently deodorant for one.
- Comment explaining a block → **Extract Method**, name it after the comment.
- Comment explaining a method → **Rename Method**.
- Comment stating a required precondition → **Introduce Assertion**.
- Comment explaining *why* → keep it. That information is not in the code and
  cannot be refactored into it.

---

## Severity scoring for scans

Score each finding so plans can be ordered. Report as `S = impact × churn ÷ risk`.

**Impact (1–5)** — how much the smell obstructs comprehension and change.
**Churn (1–5)** — how often the file has changed recently (`git log --format=%h -- <file> | wc -l` over the last 6–12 months). Static code is cheap to leave alone.
**Risk (1–5)** — blast radius: number of call sites, test coverage, whether it is a public API.

Refactor high-impact, high-churn, low-risk findings first. A terrible class that
nobody has touched in three years is at the bottom of the list, not the top.
