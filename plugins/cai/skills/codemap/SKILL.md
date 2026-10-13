---
name: codemap
description: Build, refresh, check or query a disposable index of this repository's tracked files and their top-level symbols, kept under .cai/codemap/ and ignored by git. Usage: /cai:codemap status|build|update|query <text>
argument-hint: "status|build|update|query <text>"
disable-model-invocation: true
---

## What typing this command authorises

Typing `/cai:codemap build` or `/cai:codemap update` authorises writing inside
`<top>/.cai/codemap/` (creating `<top>/.cai/` if it is missing) and nowhere
else; `<top>` is what
`git rev-parse --show-toplevel` prints. The directory ignores itself, holds only
what can be rebuilt, and may be deleted by hand at any time. `status` and
`query` write nothing.

## Steps

Run exactly one of these, with `<project root>` the directory you are working
in, and paste its output as it is. The first line is always the state line:
`codemap: fresh`, `stale`, `partial`, `absent` or `unsupported`, with a reason.

- `status`: `python ${CLAUDE_PLUGIN_ROOT}/scripts/codemap_cli.py status --project-dir "<project root>"`
- `build`: `python ${CLAUDE_PLUGIN_ROOT}/scripts/codemap_cli.py build --project-dir "<project root>"`
  creates the index, or replaces one that is damaged.
- `update`: `python ${CLAUDE_PLUGIN_ROOT}/scripts/codemap_cli.py update --project-dir "<project root>"`
  re-reads only the files that changed. With no index it writes nothing and
  says `codemap: absent`.
- `query`: `python ${CLAUDE_PLUGIN_ROOT}/scripts/codemap_cli.py query --project-dir "<project root>" -- '<text as typed>'`.
  Single-quote the text, after the `--` that keeps a text starting with `-`
  from being read as an option. If it contains a single quote, straight (`'`)
  or curly (`‘` `’` `‚` `‛`, which PowerShell also ends a string on), do not
  call the script: reply with one line saying the text cannot contain one, and
  stop.

Exit 2 means the run could not finish; the line it printed says why. Do not
retry with other flags.

## What the index is

A pointer, not evidence. A hit names a file and a line to open; whatever you
claim about the code cites the original `file:line` you read there. When the
state line is not `codemap: fresh`, read the code the way you would without an
index.
