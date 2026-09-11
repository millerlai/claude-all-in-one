# Worked example, good and bad

## The question: which state management library for a small app

### Bad — F1 plus F2 plus F3 plus F4, and F6

> Three options:
> - **Redux Toolkit**: industry standard, complete ecosystem, good for large projects
> - **Zustand**: lightweight, clean API, no boilerplate
> - **Jotai**: atomic design, fine-grained updates, better performance
>
> They all have their merits — it depends on your project's needs.

What is wrong with it:

- **F1 bare terms**: boilerplate, atomic, fine-grained updates — none glossed
- **F2 different axes**: ecosystem, then simplicity, then speed
- **F3 abstract consequences**: "good for large projects" names nothing you
  could observe afterwards
- **F4 refuses to pick**: ends on "depends on your needs"
- **F6 every word understood, still no picture**: a reader who knows what
  "boilerplate" means still cannot say what any of the three *is*

### Also bad — all six fields present, none of them findable

> **Zustand** — literally it creates one shared box of data any part of the
> screen reads and writes directly. ELI5: like a whiteboard in a shared
> kitchen, anyone can wipe a line and rewrite it. Changes: usually one extra
> `store.js`, and changing a field touches only that file. Costs: almost no
> new concepts, an hour with the docs. Reversible: medium. Fits: one to three
> people and no need to trace a value's history.

Nothing is missing. Every field is there, in order, and the paragraph is
accurate — so every check about *content* passes, which is how this shape
survived the rule for as long as it did (#73).

What is wrong with it is that none of it can be found. Comparing two options
on "how reversible" means reading two 90-word sentences to the end and
holding both. The fields exist for scanning; a paragraph is the one layout
that cannot be scanned.

The repair is mechanical, and `scripts/options_lint.py` is what catches it:
a title line, then the six as a numbered list, one field per item.

### Good — same question, six fields per option

> **Straight answer**: at your size, Zustand. Reasoning at the bottom.
>
> **Background**: a state management library solves "one piece of data, many
> screens need it". Without one, the data is handed down by hand through every
> layer, so changing it in one place touches many files.
>
> **The three dimensions compared here**:
> - **Fixed-format code per piece of state** — extra lines typed for each new
>   piece of data
> - **What you can see while debugging** — whether you can see who changed the
>   data and to what
> - **Cost of handing it to someone new** — how long before they can change it
>   safely
>
> | | Redux Toolkit | Zustand |
> |---|---|---|
> | Fixed-format code | 15-20 lines per piece of state | 3-5 lines |
> | Debug visibility | A browser add-on replays every change | Add your own logging |
> | Handover cost | Half a day to a day | About an hour |
>
> **Redux Toolkit**
> 1. **What it literally is**: keeps all the data in one place, and every
>    change to it has to be submitted as a described, recorded change.
> 2. **ELI5**: like a company where nobody takes cash out of the safe directly —
>    you fill in a slip, it gets stamped, and the ledger keeps every slip ever
>    filed. Slower to get a dollar out; you can always find out who took it.
> 3. **What actually changes**: adds a `store/` directory with one file per
>    feature; changing one field usually touches 2-3 files.
> 4. **What it costs**: three concepts to learn — slice, reducer, dispatch — about half a
>    day.
> 5. **How reversible**: low — the style spreads into every component, so
>    replacing it later is a rewrite.
> 6. **When it fits**: more than about five people touch the code, or you need to
>    trace exactly why a number changed.
>
> **Zustand (recommended)**
> 1. **What it literally is**: creates one shared box of data that any part of
>    the screen can read from and write to directly.
> 2. **ELI5**: like a whiteboard in a shared kitchen — anyone can read it, anyone
>    can wipe a line and rewrite it. Nothing to fill in first, and nothing that
>    remembers who wrote what.
> 3. **What actually changes**: usually one extra `store.js`; changing a field
>    touches only that file.
> 4. **What it costs**: almost no new concepts, about an hour with the documentation.
> 5. **How reversible**: medium — usage stays close to plain React, so swapping it
>    out is a contained change.
> 6. **When it fits**: one to three people, and no need to trace the history of a
>    value.
>
> **On Jotai**: it differs from Zustand mainly in update efficiency at very
> large component counts, which your size does not reach. Listing it would add
> a decision without adding a choice, so it is left out.
>
> **The pick**: Zustand. At your size, the extra code Redux asks for buys
> nothing you can use. If the team passes five people, or you start needing the
> history of a value, moving to Redux later is still open.

### What the good version does

1. Answer first, so nobody reads to the end to find out what to do
2. Background before options — the degradation path when terms are dense
3. Three dimensions as bullets, every one defined as something observable
4. Same-axis table, so the options can be read across
5. All six fields for both options, numbered, one per item, none blank
6. Jotai excluded on the record, with the reason
7. A pick, marked `(recommended)` on the option and stated again at the end
   with the condition that would void it

### The two ELI5 lines, checked against the three

| Check | Redux Toolkit | Zustand |
|---|---|---|
| No proper noun, abbreviation, or package name | pass — safe, slip, ledger | pass — whiteboard, kitchen |
| One everyday-life analogy present | pass — the safe and the slips | pass — the shared whiteboard |
| Worded differently from the definition | pass — the definition says "recorded change", the analogy says who took the dollar | pass — the definition says "shared box", the analogy says wipe and rewrite |
