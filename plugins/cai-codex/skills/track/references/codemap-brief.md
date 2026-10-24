> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.

# codemap-brief — put the index's state line in a stage's brief, or nothing

The main session follows this before it dispatches `intake`, `discover` or
`design`. A standalone `$intake`, `$discover` or `$design` follows it
too, and then the session itself is the stage's agent: the line it yields is its
own to act on. A standalone `$discover` skips step 2: a model may start it
without anyone typing it, and only a person's command or a track's dispatch
writes the index. It never stops a stage and never asks a question: the most it adds
is one line to the brief, or, inside a track, one sentence to the person before
`intake`. A standalone command follows this file only when the index exists, so
it never reaches that sentence.

`<top>` is what `git rev-parse --show-toplevel` prints for the project being
worked on.

1. If `<top>/.cai/codemap/state.json` exists, go on to step 2. Otherwise stop
   here, running no command, adding no line and reminding nobody, with one
   exception: `intake` is about to be dispatched for the first time in this
   session and `<top>/.git` is a file rather than a directory (a linked
   worktree). Then run
   `<cai> codemap_cli status --project-dir "<top>"`;
   on exit 0 with this line in its output:
   `the main checkout has an index; this worktree has none`
   tell the person in one sentence that this worktree has no index while the
   main checkout does, and that `$codemap build` creates one here. Ask
   nothing, wait for nothing, add nothing to the brief. Either way, stop here.
   A project that never built an index, and a main checkout itself, run
   nothing and see nothing of this feature.
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

Never run `build` here, never suggest running it beyond step 1's one sentence,
and never let a state word other than `fresh` hold a stage back: a missing,
failed or non-`fresh` line means the stage reads the code with
`Read`/`Grep`/`Glob` as it always did. Only a person's own `$codemap build`
creates an index.
