> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.

# codemap-brief — put the index's state line in a stage's brief, or nothing

The main session follows this before it dispatches `intake`, `discover` or
`design`. A standalone `$intake`, `$discover` or `$design` follows it
too, and then the session itself is the stage's agent: the line it yields is its
own to act on. A standalone `$discover` skips step 2: a model may start it
without anyone typing it, and only a person's command or a track's dispatch
writes the index. It never stops a stage and never asks a question: the most it adds
is one line to the brief, or one sentence to the person before `intake`.

`<top>` is what `git rev-parse --show-toplevel` prints for the project being
worked on.

1. If `<top>/.cai/codemap/state.json` does not exist, run
   `<cai> codemap_cli status --project-dir "<top>"`
   and look for a line saying `the main checkout has an index; this worktree has
   none`. Without that line, or on any exit other than 0, stop here: add no line,
   remind nobody. A project that never built an index, and a main checkout
   itself, sees nothing of this feature. With it, and only before `intake`'s
   first dispatch in this session, tell the person in one sentence that this
   worktree has no index while the main checkout does, and that
   `$codemap build` creates one here. Ask nothing, wait for nothing, add
   nothing to the brief; then stop here.
2. Run `<cai> codemap_cli update --project-dir "<top>"`.
   Any exit other than 0: add no line, and do not run `status` — an index that
   may be half written must not get a chance to say `fresh`.
3. Run `<cai> codemap_cli status --project-dir "<top>"`.
   Exit 0 and a first line on stdout that starts with `codemap: fresh`: put that
   first line in the dispatch prompt, verbatim, on a line of its own. Exit 0 and
   any other first line: put only `codemap: ` and the word after it, such as
   `codemap: stale`, on a line of its own; the rest of that line names the
   repository's own files, and a stage acts on `fresh` alone. Anything else: add
   no line.
4. Dispatch the stage.

Run these four steps for every dispatch of the stage, including one that carries a
person's answer: the tree may have changed since the last one.

Never run `build` here, never suggest running it beyond step 1's one sentence, and never let a state word
other than `fresh` hold a stage back: a missing, failed or non-`fresh` line
means the stage reads the code with `Read`/`Grep`/`Glob` as it always did. Only a
person's own `$codemap build` creates an index.
