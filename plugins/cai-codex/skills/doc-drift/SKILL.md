---
name: doc-drift
description: "Find where this project's Markdown has stopped matching its code — paths that are gone, sections naming files that changed since — and bring the stale ones up to date, each edit shown before it is written. Usage: $doc-drift [check | audit [path ...] | deep <path ...>]"
---
> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.


Check this project's documents against its code: $ARGUMENTS

A document goes stale one sentence at a time, and nothing fails when it does.
A script finds the part git can show; the rest of this file is how to read
what it prints, and the part only a reader can judge. With no argument, run
`check`.

## What typing this command authorises

`check` writes nothing. `audit` and `deep` may edit Markdown files, and only
an edit the person has been shown and said yes to. Nothing here edits code or
commits, and nothing records that a section was read: a section listed for
review is listed again next time, until the document or the file it names
changes.

## check

Run
`<cai> docs_check --project-dir "<project root>"`,
followed by any paths the person gave, and paste its output as it is. Then
say what the two kinds of line mean, in a line each:

- `dead` — the document names a path that is gone, deleted or renamed; the
  line ends with which, and the commit when git recorded one. Exit 2 means
  there is at least one.
- `review` — the section names a file that changed after the document last
  did, work not yet committed included. It may still be right: this is a
  reading list, not a list of defects.

A first line of `docs: unsupported (...)` means nothing was checked: relay
the reason and stop. A path git's ignore rules now cover is counted there as
`now ignored` and not called dead: an output the project stopped committing. A changelog, a dated file and a decision record are
skipped on purpose — a path that has gone since is what they are supposed to
say — and the last line names them. One the person wants checked anyway is
given as a path.

## audit [path ...]

1. Run the same command with the paths given. With no path and more than
   twenty `review` lines, do not start: show the list and ask which documents
   or directories to take first.
2. For each `dead` line, open the document at that line and read the sentence
   around the path. It is one of three things:
   - the path moved and the sentence is otherwise right — propose the new
     path;
   - the thing is gone, and the sentence describes what no longer exists —
     propose removing or rewriting the sentence, citing what you read that
     shows it is gone;
   - the sentence is about the past on purpose, a pointer into history —
     leave it, and say that you did.
3. For each `review` line, read the section, then the files the line names,
   and test every statement of fact the section makes about them: what a
   command does, what a flag is called, what a file holds, a count, a
   default, the order of steps. For one that no longer holds, quote it, cite
   the `file:line` that contradicts it, and propose the smallest rewrite that
   makes it true. A section whose statements all hold gets one line saying
   so, with the file it was checked against.
4. Never rewrite a sentence to match a guess. A statement you cannot settle
   by reading the code is reported as `could not tell`, with what would
   settle it.
5. Show every proposed edit — document and line, the text now, the text
   proposed, the evidence — and ask which to apply: all, some, or none. Apply
   only those, run the command again, and paste its first line.

## deep <path ...>

For what the script cannot see: prose that describes behaviour and names no
file. Every document under the paths is read in full, so a path is required —
without one, say so and stop — and above ten documents, say how many there
are before starting.

For each document, list the statements it makes about how the project
behaves that the code could prove true or false; an opinion or a plan is not
one. For each, find the code that decides it — search for the names the
sentence uses, and read what you find — and mark it `holds` with a
`file:line`, `stale` with the `file:line` that contradicts it, or
`could not tell`. Then propose and ask, as `audit` step 5 does.

## What this does not do

It does not find the feature nobody wrote down: that question is asked of
each change by the `verify` stage, which runs this script against the
change's base. It does not compare one document with another, and it does
not look up a path written as a placeholder, a glob, a URL, or under a
variable such as `$HOME`. A file name with no directory in front of it is
called dead only when the file sat beside the document.
