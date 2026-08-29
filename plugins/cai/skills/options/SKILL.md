---
name: options
description: "Lay out two or more ways forward so a person can actually choose between them: shared comparison dimensions, six fields per option including an everyday-life ELI5 analogy, a recommendation and the condition that voids it. Use before a list of options goes out, and after one already did and the reader could not act on it — 看不懂 / 這是什麼意思 / 差在哪 / 幫我展開 / 講白話一點 / 比較一下 / expand that / what is the difference / explain it simply / which should I pick. Usage: /cai:options <what to compare, or nothing to rewrite the previous message>"
argument-hint: "<what to compare — or nothing, to expand the previous message>"
disable-model-invocation: true
---

Lay out options someone can actually choose between: $ARGUMENTS

Two entrances, one procedure. **Before** — a reply is about to offer two or
more ways forward. **After** — one already went out and the reader could not
act on it; rewrite that message, never restate it.

The always-on half of this lives in `rules/option-explainer.md` and applies
whether or not this skill was invoked. This file is what does not fit in 45
lines: the skeleton, the dimension library, and a worked example.

If `$ARGUMENTS` is empty and the previous message holds no option list, say so
and stop. Do not invent a set of options to expand.

## Which reference to read

| Situation | Read |
|---|---|
| You need the output skeleton | `${CLAUDE_PLUGIN_ROOT}/skills/options/references/template.md` |
| You are unsure what to compare on | `${CLAUDE_PLUGIN_ROOT}/skills/options/references/dimensions.md` |
| You want the worked good and bad pair | `${CLAUDE_PLUGIN_ROOT}/skills/options/references/good-bad.md` |

Read the one you need, not all three.

## Procedure

1. **Is there a choice at all?** One reasonable way forward — say so and stop.
   An option that is plainly worse — name it, say why it is excluded, leave it
   out. Never pad to three.
2. **Missing a fact the choice turns on?** Ask one question — one — and stop
   there. Do not list options against a guess.
3. **Pick 2-4 dimensions** from `dimensions.md` before writing any option. Do
   not invent a set when one there fits.
4. **Fill all six fields for every option**, in `template.md`'s order:
   `What it literally is`, `ELI5`, `What actually changes`, `What it costs`,
   `How reversible`, `When it fits`. No blanks; "not applicable" carries its reason.
5. **Pick one**, and state the condition that would make it the wrong pick.
6. **Run the self-check** in the rules file — all seven boxes, including the
   three ELI5 ones. A no is a rewrite of that field, not a caveat under it.

## The ELI5 field, specifically

It is not field 1 with friendlier words. That field
says what the thing *is*; the ELI5 says what it is *like*. Three yes/no checks
decide whether it is done, and the rules file's self-check carries the same
three:

1. No proper noun, abbreviation, or package name anywhere in it.
2. One everyday-life analogy is actually present.
3. Worded differently from field 1.

Check 3 is the one that fails: writing the same sentence twice in softer words
is how the sixth field quietly becomes a copy of the first.

## When the entrance is the remedial one

The reader still has the previous message on screen, so restating it is worth
nothing. Add, in this order:

1. A glossary of every term that message used, one plain sentence each.
2. The 2-4 dimensions it never declared, and what each one measures.
3. A same-axis table of the surviving options.
4. All six fields for each surviving option.
5. The pick, and the condition that voids it.
6. If those options barely differ, say so and collapse them. Being asked to
   expand a list is not an instruction to keep every item in it.

## Hard prohibitions

- No option list before the dimensions are named.
- No ending on "it depends", "both have their merits", "up to you".
- No option kept for symmetry.
- No ELI5 that repeats field 1 in other words.
