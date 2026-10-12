---
name: codemap
description: Build, refresh, check or query a disposable index of this repository's tracked files and their top-level symbols, kept under .cai/codemap/ and ignored by git. Usage: $codemap status|build|update|query <text>
---
> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.


## What typing this command authorises

Typing `$codemap build` or `$codemap update` authorises writing inside
`<top>/.cai/codemap/` and nowhere else; `<top>` is what
`git rev-parse --show-toplevel` prints. The directory ignores itself, holds only
what can be rebuilt, and may be deleted by hand at any time. `status` and
`query` write nothing.

## Steps

Run exactly one of these, with `<project root>` the directory you are working
in, and paste its output as it is. The first line is always the state line:
`codemap: fresh`, `stale`, `partial`, `absent` or `unsupported`, with a reason.

- `status`: `<cai> codemap_cli status --project-dir <project root>`
- `build`: `<cai> codemap_cli build --project-dir <project root>`
  creates the index, or replaces one that is damaged.
- `update`: `<cai> codemap_cli update --project-dir <project root>`
  re-reads only the files that changed. With no index it writes nothing and
  says `codemap: absent`.
- `query`: `<cai> codemap_cli query --project-dir <project root> '<text as typed>'`.
  Single-quote the text; if it contains a single quote, do not call the
  script: reply with one line saying the text cannot contain one, and stop.

Exit 2 means the run could not finish; the line it printed says why. Do not
retry with other flags.

## What the index is

A pointer, not evidence. A hit names a file and a line to open; whatever you
claim about the code cites the original `file:line` you read there. When the
state line is not `codemap: fresh`, read the code the way you would without an
index.
