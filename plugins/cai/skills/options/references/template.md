# Output skeleton

Fill top to bottom. Nothing is skipped; "not applicable" is written out with
its reason, never left blank.

---

## Background — only when the terms cannot be glossed inline

[Everything the reader needs before the options make sense, in plain words.]

## Dimensions compared here

- **[dimension]** — [what it measures, stated as something observable]
- **[dimension]** — [...]
- **[dimension]** — [...]

## Side by side

| | Option A | Option B |
|---|---|---|
| [dimension 1] | | |
| [dimension 2] | | |
| [dimension 3] | | |

## Samples — when the options differ in something the reader will see

An output format, a file's contents, a message's wording, a column that
changes. The table above *describes* that difference, and a described format
is the one thing a reader cannot check against anything. Show each option's
real output instead, here, before the six fields:

````
Option A — [name]

```
[the actual output, on one real input]
```

Option B — [name]

```
[the same input, run the other way. Write "(lines 1-4 identical to A)"
instead of repeating the part that does not differ]
```
````

Two things make the pair readable, and both are easy to lose:

- **The same input on both sides.** Two samples from two different inputs are
  the format version of describing two options on different dimensions — each
  one makes sense alone and neither can be read against the other.
- **The identical part elided.** What survives on the page is then the
  difference itself, which is the only thing being chosen between.

If the options do not differ in anything the reader will ever see, skip this
section — do not manufacture a sample to fill it.

## Option A — [name] (recommended)

1. **What it literally is**: [literally what it does. One sentence, no jargon.]
2. **ELI5**: [one everyday-life analogy for the same thing, worded differently
   from the line above]
3. **What actually changes**: [which files appear or change, what is different
   to operate afterwards]
4. **What it costs**: [time, complexity, what has to be learned]
5. **How reversible**: [low / medium / high] — [what replacing it later costs]
6. **When it fits**: [the condition that makes this the right option]

## Option B — [name]

[the same six fields, numbered 1-6, in the same order]

## The pick

If you would rather not weigh it, pick [X], because [reason].
That stops being the right pick when [condition changes]; then it is [Y].

---

## Using this

- **Bullets for the dimensions, numbers for the fields.** That is not
  decoration: it is how `scripts/options_lint.py` tells a dimension list from
  an option, in a reply written in any language. A numbered dimension list
  reads as an option with three fields, and the probe says so.
- **The title line carries `(recommended)`** on exactly one option — the
  marker the probe reads, and the same one a design document's options use.
- **Write the draft to a file and lint it before sending:**
  `python ${CLAUDE_PLUGIN_ROOT}/scripts/options_lint.py <the draft>`.
  Exit 0 or fix what it names. It sees shape only; the ELI5 checks below and
  the rules file's other boxes are still read by you.
- Two options: the side-by-side table is optional, the six fields are not.
- Three or more: the table is required.
- A dimension every option scores the same on has no discriminating power —
  drop it from the table.
- The ELI5 line is the one most likely to collapse into the definition line.
  Read the two back to back before sending: if either could be deleted without
  losing information, one of them is not doing its job.
