# Catalog index — 72 refactorings

`slug` is the identifier used by `procedure-apply.md <slug>` and by the generated
per-refactoring commands. **Risk**: L = local and mechanical, M = crosses class
boundaries, H = wide blast radius or behaviour-substituting.

## Composing Methods → `cat-06-composing-methods.md`

| # | Name | slug | Risk | Fixes |
|---|---|---|---|---|
| 1 | Extract Method | `extract-method` | L | Long Method, Duplicated Code, Comments |
| 2 | Inline Method | `inline-method` | L | Middle Man, over-extraction |
| 3 | Inline Temp | `inline-temp` | L | noise |
| 4 | Replace Temp with Query | `replace-temp-with-query` | L | Long Method |
| 5 | Introduce Explaining Variable | `introduce-explaining-variable` | L | complex expression |
| 6 | Split Temporary Variable | `split-temporary-variable` | L | reused temp |
| 7 | Remove Assignments to Parameters | `remove-assignments-to-parameters` | L | unclear parameter role |
| 8 | Replace Method with Method Object | `replace-method-with-method-object` | M | Long Method (tangled temps) |
| 9 | Substitute Algorithm | `substitute-algorithm` | H | Duplicated Code, convoluted logic |

## Moving Features Between Objects → `cat-07-moving-features.md`

| # | Name | slug | Risk | Fixes |
|---|---|---|---|---|
| 10 | Move Method | `move-method` | M | Feature Envy, Shotgun Surgery |
| 11 | Move Field | `move-field` | M | Feature Envy, Inappropriate Intimacy |
| 12 | Extract Class | `extract-class` | M | Large Class, Divergent Change, Data Clumps |
| 13 | Inline Class | `inline-class` | M | Lazy Class |
| 14 | Hide Delegate | `hide-delegate` | L | Message Chains |
| 15 | Remove Middle Man | `remove-middle-man` | M | Middle Man |
| 16 | Introduce Foreign Method | `introduce-foreign-method` | L | Incomplete Library Class |
| 17 | Introduce Local Extension | `introduce-local-extension` | M | Incomplete Library Class |

## Organizing Data → `cat-08-organizing-data.md`

| # | Name | slug | Risk | Fixes |
|---|---|---|---|---|
| 18 | Self Encapsulate Field | `self-encapsulate-field` | L | blocked Move Field |
| 19 | Replace Data Value with Object | `replace-data-value-with-object` | M | Primitive Obsession |
| 20 | Change Value to Reference | `change-value-to-reference` | H | duplicate entities |
| 21 | Change Reference to Value | `change-reference-to-value` | H | awkward shared lifecycle |
| 22 | Replace Array with Object | `replace-array-with-object` | M | Primitive Obsession |
| 23 | Duplicate Observed Data | `duplicate-observed-data` | H | Large Class (GUI) |
| 24 | Change Unidirectional Association to Bidirectional | `change-unidirectional-to-bidirectional` | M | missing navigation |
| 25 | Change Bidirectional Association to Unidirectional | `change-bidirectional-to-unidirectional` | M | Inappropriate Intimacy |
| 26 | Replace Magic Number with Symbolic Constant | `replace-magic-number-with-constant` | L | unexplained literals |
| 27 | Encapsulate Field | `encapsulate-field` | L | Data Class |
| 28 | Encapsulate Collection | `encapsulate-collection` | M | Data Class |
| 29 | Replace Record with Data Class | `replace-record-with-data-class` | M | raw records leaking |
| 30 | Replace Type Code with Class | `replace-type-code-with-class` | M | Primitive Obsession |
| 31 | Replace Type Code with Subclasses | `replace-type-code-with-subclasses` | H | Switch Statements |
| 32 | Replace Type Code with State/Strategy | `replace-type-code-with-state-strategy` | H | Switch Statements |
| 33 | Replace Subclass with Fields | `replace-subclass-with-fields` | M | Lazy Class |

## Simplifying Conditional Expressions → `cat-09-conditionals.md`

| # | Name | slug | Risk | Fixes |
|---|---|---|---|---|
| 34 | Decompose Conditional | `decompose-conditional` | L | Long Method |
| 35 | Consolidate Conditional Expression | `consolidate-conditional-expression` | L | scattered checks |
| 36 | Consolidate Duplicate Conditional Fragments | `consolidate-duplicate-conditional-fragments` | L | duplication in branches |
| 37 | Remove Control Flag | `remove-control-flag` | L | control flag |
| 38 | Replace Nested Conditional with Guard Clauses | `replace-nested-conditional-with-guard-clauses` | L | deep nesting |
| 39 | Replace Conditional with Polymorphism | `replace-conditional-with-polymorphism` | H | Switch Statements |
| 40 | Introduce Null Object | `introduce-null-object` | M | repeated null checks |
| 41 | Introduce Assertion | `introduce-assertion` | L | Comments (implicit assumptions) |

## Making Method Calls Simpler → `cat-10-method-calls.md`

| # | Name | slug | Risk | Fixes |
|---|---|---|---|---|
| 42 | Rename Method | `rename-method` | L | Comments, unclear names |
| 43 | Add Parameter | `add-parameter` | M | missing data |
| 44 | Remove Parameter | `remove-parameter` | M | Speculative Generality |
| 45 | Separate Query from Modifier | `separate-query-from-modifier` | M | hidden side effects |
| 46 | Parameterize Method | `parameterize-method` | M | Duplicated Code |
| 47 | Replace Parameter with Explicit Methods | `replace-parameter-with-explicit-methods` | M | Switch Statements (small) |
| 48 | Preserve Whole Object | `preserve-whole-object` | M | Long Parameter List |
| 49 | Replace Parameter with Method | `replace-parameter-with-method` | M | Long Parameter List |
| 50 | Introduce Parameter Object | `introduce-parameter-object` | M | Long Parameter List, Data Clumps |
| 51 | Remove Setting Method | `remove-setting-method` | M | unwanted mutability |
| 52 | Hide Method | `hide-method` | L | over-wide interface |
| 53 | Replace Constructor with Factory Method | `replace-constructor-with-factory-method` | M | constrained construction |
| 54 | Encapsulate Downcast | `encapsulate-downcast` | L | caller-side casts |
| 55 | Replace Error Code with Exception | `replace-error-code-with-exception` | H | unchecked error codes |
| 56 | Replace Exception with Test | `replace-exception-with-test` | M | exceptions as control flow |

## Dealing with Generalization → `cat-11-generalization.md`

| # | Name | slug | Risk | Fixes |
|---|---|---|---|---|
| 57 | Pull Up Field | `pull-up-field` | M | Duplicated Code |
| 58 | Pull Up Method | `pull-up-method` | M | Duplicated Code |
| 59 | Pull Up Constructor Body | `pull-up-constructor-body` | M | Duplicated Code |
| 60 | Push Down Method | `push-down-method` | M | Refused Bequest |
| 61 | Push Down Field | `push-down-field` | M | Refused Bequest |
| 62 | Extract Subclass | `extract-subclass` | H | Large Class |
| 63 | Extract Superclass | `extract-superclass` | H | Duplicated Code |
| 64 | Extract Interface | `extract-interface` | M | Large Class, test seams |
| 65 | Collapse Hierarchy | `collapse-hierarchy` | H | Lazy Class |
| 66 | Form Template Method | `form-template-method` | H | Duplicated Code |
| 67 | Replace Inheritance with Delegation | `replace-inheritance-with-delegation` | H | Refused Bequest |
| 68 | Replace Delegation with Inheritance | `replace-delegation-with-inheritance` | H | Middle Man |

## Big Refactorings → `cat-12-big-refactorings.md`

| # | Name | slug | Risk | Fixes |
|---|---|---|---|---|
| 69 | Tease Apart Inheritance | `tease-apart-inheritance` | H | tangled hierarchy |
| 70 | Convert Procedural Design to Objects | `convert-procedural-design-to-objects` | H | procedural design |
| 71 | Separate Domain from Presentation | `separate-domain-from-presentation` | H | logic in UI |
| 72 | Extract Hierarchy | `extract-hierarchy` | H | overloaded class |

These four are campaigns, not single steps. See the chapter file.

## Inverse pairs

Refactoring is bidirectional. Knowing the inverse tells you how to back out.

| Forward | Inverse |
|---|---|
| Extract Method | Inline Method |
| Extract Class | Inline Class |
| Hide Delegate | Remove Middle Man |
| Introduce Explaining Variable | Inline Temp |
| Change Value to Reference | Change Reference to Value |
| Change Unidirectional → Bidirectional | Change Bidirectional → Unidirectional |
| Parameterize Method | Replace Parameter with Explicit Methods |
| Add Parameter | Remove Parameter |
| Pull Up Method / Field | Push Down Method / Field |
| Extract Subclass / Superclass | Collapse Hierarchy |
| Replace Inheritance with Delegation | Replace Delegation with Inheritance |
| Replace Type Code with Subclasses | Replace Subclass with Fields |
| Replace Error Code with Exception | Replace Exception with Test |

If a plan proposes a refactoring and its inverse in the same run, the plan is
wrong. Stop and re-diagnose.
