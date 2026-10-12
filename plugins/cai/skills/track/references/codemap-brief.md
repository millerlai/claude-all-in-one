# codemap-brief — put the index's state line in a stage's brief, or nothing

The main session follows this before it dispatches `intake`, `discover` or
`design`. A standalone `/cai:intake`, `/cai:discover` or `/cai:design` follows it
too, and then the session itself is the stage's agent: the line it yields is its
own to act on. It never stops a stage and never asks a question: the most it adds
is one line.

`<top>` is what `git rev-parse --show-toplevel` prints for the project being
worked on.

1. If `<top>/.cai/codemap/state.json` does not exist, stop here. Run no command,
   add no line, remind nobody. A project that never built an index sees nothing
   of this feature.
2. Run `python ${CLAUDE_PLUGIN_ROOT}/scripts/codemap_cli.py update --project-dir <top>`.
   Any exit other than 0: add no line, and do not run `status` — an index that
   may be half written must not get a chance to say `fresh`.
3. Run `python ${CLAUDE_PLUGIN_ROOT}/scripts/codemap_cli.py status --project-dir <top>`.
   Exit 0 and a first line on stdout: put that first line in the dispatch
   prompt, verbatim, on a line of its own. Anything else: add no line.
4. Dispatch the stage.

Run these four steps for every dispatch of the stage, including one that carries a
person's answer: the tree may have changed since the last one.

Never run `build` here, never suggest running it, and never let a state word
other than `fresh` hold a stage back: a missing, failed or non-`fresh` line
means the stage reads the code with `Read`/`Grep`/`Glob` as it always did. Only a
person's own `/cai:codemap build` creates an index.
