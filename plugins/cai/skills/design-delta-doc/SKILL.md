---
name: design-delta-doc
description: "Write a design document for a branch that is already built — read the diff against its base, recover the decisions from the commits and the code, and mark UNVERIFIED whatever the evidence does not reach. Usage: /cai:design-delta-doc [base-ref]"
argument-hint: "[base-ref — defaults to the branch point]"
model: sonnet
effort: high
---

Write a delta design document for the changes on this branch: $ARGUMENTS

The failure this exists to catch is a design document that restates the diff in
prose. The diff is already in git, and anyone can read it. What is *not* in git
is why any of it was done that way — and that is the half this document carries.

## The evidence rule

Every sentence about why something was done carries its source: a `file:line`, a
documentation URL, or the commit that says it. Three sources count:

- **the diff and the code around it** — what changed, and what it implies about
  code it did not touch;
- **the branch's own record** — commit messages, the PR description, comments
  the change itself added;
- **neither** — write `UNVERIFIED`, and leave it in the finished document.

What does not count: what the change obviously *should* have been for, what a
refactor of this shape usually achieves, what the new function names imply.
Catching yourself writing *presumably*, *the intent was*, or *this was likely to*
means you are writing `UNVERIFIED` in a longer form.

**This command does not stop to ask.** It runs start to finish, including under
`-p`. A decision you cannot source is written `UNVERIFIED` — not guessed, and
not quietly dropped. The author fills those in afterwards, which they can only
do if they can see which rows are theirs. An invented but plausible reason is
worse than a blank: it outlives everyone who could have corrected it.

This is deliberately **not** the rule block `/cai:design-high-level-doc` and
`/cai:design-implementation-detail-doc` share. Theirs sends four kinds of
decision to `AskUserQuestion`, because those documents are written *before* the
choice is made and a silent choice is one the user never made. Here every choice
already shipped. Asking about them would be asking the user to re-derive their
own branch; the useful thing is an honest split between the reasons that were
recovered and the reasons that were not.

## Step 0 — Fix the scope

Find the base ref, taking the first that works:

1. the ref given above, if one was;
2. `git symbolic-ref --short refs/remotes/origin/HEAD` — if it answers, that is
   the default branch;
3. `origin/main`, or `origin/master` if `main` does not exist.

Then read the two commands' output:

- `git merge-base HEAD <base-ref>` — the branch point.
- `git diff --stat <branch-point>...HEAD` — the file list.

Run these as separate commands and carry the values yourself. Do not wire them
into one pipeline with shell variables, `sed`, or `${VAR:-default}` — none of
that parses under the PowerShell tool, and this command has to work on Windows.

This is `diff-review`'s Step 0 (`plugins/cai/skills/diff-review/SKILL.md:16-37`),
copied rather than cross-referenced: a skill's text is only loaded when that
skill runs, so a pointer would aim at something you cannot see.

An empty diff, or one that is entirely generated files, stops here. Say so.

## Step 1 — Read the diff

```bash
git log --oneline <BASE>..HEAD
git diff <BASE>..HEAD
```

Read it properly. Open the surrounding files wherever the diff alone does not
show what a change implies — a hunk that deletes a guard tells you nothing about
what now reaches the code the guard was protecting.

## Step 2 — Recover the why, before writing anything

This is the step that decides whether the document is worth having. Work through
all four sources before you conclude something is unrecoverable:

- `git log --format=%B <BASE>..HEAD` — the full message bodies, not the subject
  lines. On a branch of WIP commits this is often empty of reasoning; that is a
  finding, not a failure.
- The PR description, if there is one: `gh pr view --json title,body`.
- Comments the change *added* — a `why` written next to the code is the best
  evidence there is, and it is in the diff you already read.
- Any design document the branch implements, under `docs/`.

Then list the deliberate choices you found and, next to each, whether these
sources actually explain it. That list becomes `## Decisions`. Resist the pull
to fill a thin list by promoting mechanical edits into "decisions" — three real
rows beat nine padded ones.

## Step 3 — Write it

Unless the user named a path, write to:

```
docs/design/<YYYY-MM-DD>-<topic>-delta.md
```

Take the date from the system (`date +%F`), never from memory. `<topic>` is
lowercase words joined by hyphens and spelled out.

Write the document's contents in whatever language `communication.md` sets for
responses. The headings and table headers stay English — `design_probe.py`
matches on them.

Start from the shipped template rather than a blank file. Find `<plugin-root>`
by taking the first of these that exists, the same way `/cai:setup` does:

1. `~/.claude/plugins/cache/claude-all-in-one/cai/*/` — highest version if
   several are present;
2. `./plugins/cai/` — a local checkout, if the working directory is one.

Copy `<plugin-root>/templates/design-delta.md.tpl` to that path and fill it in.
Its guidance lives in HTML comments; delete each one as you answer it. Do not
add or rename headings — the probe checks for exactly the set the template
ships.

`## Before / After` takes two Mermaid diagrams, per `documentation.md`: `elk`
renderer, labels in double quotes rather than hand-escaped entities, and
`classDef` colouring so added, modified and unchanged nodes are distinguishable.
Two diagrams, not one — a single picture of the end state is something the
reader could have drawn from the code, and the delta is the pair.

## Step 4 — Validate the diagrams by rendering them

```bash
mmdc -i <the document> -o <scratchpad>/check.md
```

If `mmdc` is not installed, say so and offer the install line rather than
claiming the diagrams were checked.

## Step 5 — Check it mechanically

```bash
python <plugin-root>/scripts/design_probe.py --kind delta <the document>
```

It answers only questions with one answer: are the six headings present and
filled, does `## Scope` name a commit range, are there two Mermaid blocks, does
every decision row carry evidence or say `UNVERIFIED`, does `## Impact` have
rows. Fix what it reports and re-run until it exits 0.

One failure is worth naming in advance, because its message misleads: a
`## Scope` holding only `a3f21bc..HEAD` is reported as **empty**, not as short.
The check behind it wants one line of at least 20 characters, so write the scope
as a sentence — base ref, range, and how many files changed.

## Step 6 — Hand it over

Say where the document is, and **count the `UNVERIFIED` rows out loud**. That
number is the point of the hand-off: it is the list of things only the author
knows, and it is the one part of this document that cannot be produced without
them.

Do not merge, push, or commit anything. This command reads and writes one file.

## When not to use this

- The branch is a few lines. Read the diff.
- You want to check your *own* understanding of a branch before merging → the
  `/cai:quiz` command; it asks you questions instead of answering them.
- You want to know whether the change is any *good* → `diff-review`. This
  command describes what was built and does not judge it.
- Nothing is built yet → `/cai:design-high-level-doc`, which weighs options
  before they are decided instead of recording them afterwards.
- You want a document describing the whole subsystem as it now stands, not this
  change set. That is a different document, and this template will fight you —
  its `## Scope`, `## Before / After` and `## Decisions` are all framed around a
  range of commits.
