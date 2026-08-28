# Apply one refactoring — execute a single named refactoring on a target

This is the dispatcher for all 72 refactorings. It executes **exactly one** on
**exactly one** target.

Request: `$ARGUMENTS`

## Resolve

1. Match the named refactoring against `${CLAUDE_PLUGIN_ROOT}/skills/refactor/references/catalog-index.md`.
   Accept the slug (`extract-method`), the full name (`Extract Method`), or a
   close variant. Ambiguous → ask which one; do not guess.
2. Open the card in the matching `cat-*.md`. Read **Pre** and **Mechanics** before
   touching anything.
3. If the user described a *problem* rather than naming a refactoring, do not
   improvise — run `procedure-scan.md` to name the smell first.

## Pre-flight (all four, every time)

| Check | Fail action |
|---|---|
| Working tree clean (or changes are the user's own, acknowledged) | Ask before proceeding |
| Test command known and **currently green** | Stop. Report the red tests; do not fix them here |
| Target has test coverage | Stop and offer `procedure-safety-net.md` |
| Card's **Pre** conditions hold | Report which one fails and name the correct alternative |

State the baseline explicitly: `Baseline: 214 tests green @ a3f21c9`.

## Execute

Follow the card's numbered mechanics **in order**. The compile/test loop after
each step, and what counts as green or red, is the safety protocol in
`${CLAUDE_PLUGIN_ROOT}/skills/refactor/SKILL.md` under
"## Non-negotiable safety protocol" — follow it there; it is not restated here.

Rules while executing:

- Use the language server's rename/extract if available. A mechanical tool beats
  hand-editing every time.
- Find call sites with the LSP's find-references, not grep, wherever possible.
  Grep misses dynamic dispatch and over-matches common names.
- **Behaviour must not change.** No bug fixes, no added validation, no "while I'm
  here" improvements, no reformatting of untouched lines. If you spot a bug,
  write it down and keep going.
- Do not start a second refactoring. If the card says a follow-up is needed
  (e.g. Replace Type Code with Subclasses → Replace Conditional with Polymorphism),
  finish this one, commit, and *report* the follow-up.

## Finish

The full-suite run and the commit are the safety protocol's own finishing
steps (`${CLAUDE_PLUGIN_ROOT}/skills/refactor/SKILL.md`,
"## Non-negotiable safety protocol") — do them there, then:

1. Show the diff summary: files touched, lines added/removed.
2. Report:

```
✓ Extract Method — Invoice.render L180-214 → renderLineItems
  3 files changed, +18 −22 · 214 tests green · commit b81f3a2
  Follow-up available: Move Method renderLineItems → LineItemFormatter (Feature Envy)
```

## Abort conditions

Stop and report rather than continuing:

- Tests were red before you started.
- A step goes red and a small revert does not restore green.
- The refactoring would change a public API with no agreed deprecation path.
- The target is generated code, vendored code, or a migration.
- The diff passes ~400 lines — that is no longer one refactoring.
- The named refactoring is #69–72 (a Big Refactoring). Those are campaigns; produce
  a roadmap and a first increment instead of executing.
