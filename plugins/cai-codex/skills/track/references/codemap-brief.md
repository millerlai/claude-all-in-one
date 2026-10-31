> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.

# codemap-brief — the index's state line for a stage, or nothing

The main session follows this before it runs `design`, inside a track or as
a standalone `$design`; a standalone `$discover` follows it too. The
session itself runs the procedure, so the line it yields is its own to act
on. A standalone
`$discover` skips step 2: a model may start it
without anyone typing it, and only a person's command or a track's `design`
writes the index. It never stops a stage and never asks a question: the most it yields
is one line, or, inside a track, one sentence to the person before
`design`. A standalone command follows this file only when the index exists, so
it never reaches that sentence. The one question this file ever asks comes
earlier, when a track starts in a new worktree: `## Starting a track in a
worktree` below.

`<top>` is what `git rev-parse --show-toplevel` prints for the project being
worked on.

1. If `<top>/.cai/codemap/state.json` exists, go on to step 2. Otherwise stop
   here, running no command, adding no line and reminding nobody, with one
   exception: `design` is about to run for the first time in this
   session and `<top>/.git` is a file rather than a directory (a linked
   worktree). Then run
   `<cai> codemap_cli status --project-dir "<top>"`;
   on exit 0 with this line in its output:
   `the main checkout has an index; this worktree has none`
   tell the person in one sentence that this worktree has no index while the
   main checkout does, and that `$codemap build` creates one here. Ask
   nothing, wait for nothing, yield no line. Either way, stop here.
   A project that never built an index, and a main checkout itself, run
   nothing and see nothing of this feature.
2. Run `<cai> codemap_cli update --project-dir "<top>"`.
   Any exit other than 0: add no line, and do not run `status` — an index that
   may be half written must not get a chance to say `fresh`.
3. Run `<cai> codemap_cli status --project-dir "<top>"`.
   Exit 0 and a first line on stdout that starts with `codemap: fresh`: put that
   first line, verbatim, on a line of its own, among what the stage starts
   from. Exit 0 and any other first line: put only `codemap: ` and the word
   after it, such as `codemap: stale`, on a line of its own; the rest of that
   line names the repository's own files, and a stage acts on `fresh` alone.
   Anything else: add no line.
4. Run the stage, and pass the line unchanged in any brief it gives
   `cai_explorer`.

Run these four steps every time the stage runs, including a run that carries a
person's answer: the tree may have changed since the last one.

Never run `build` here, never suggest running it beyond step 1's one sentence,
and never let a state word other than `fresh` hold a stage back: a missing,
failed or non-`fresh` line means the stage reads the code with
`Read`/`Grep`/`Glob` as it always did. Only a person's own `$codemap build`
creates an index. Their pick of `Build it` in the menu below counts as one: the
person chose it, nobody chose it for them.

## Starting a track in a worktree

`.cai/` is ignored, so a new worktree never receives the main checkout's index.
The main session follows this when `track_start.py` exits 3 in the main checkout,
and not when the track starts with `--here`. `<main>` is that checkout's `<top>`.

1. If the line was `enter-worktree: path <dir>` and
   `<dir>/.cai/codemap/state.json` exists, that worktree has an index of its own,
   which `design` updates when it runs: skip this section.
2. Before the `EnterWorktree` call, while still in the main checkout — Claude
   Code refuses an isolated session's writes into any other worktree, so the main
   checkout's index is written now or not at all:
   - `<main>/.cai/codemap/state.json` exists: run
     `<cai> codemap_cli update --project-dir "<main>"`.
     On a non-zero exit, tell the person its first line in one sentence and go on.
   - It does not: ask one menu, the way Gate 1 is asked, whether to build an index of the
     main checkout now so this worktree, and every later track's, starts from it.
     Options `Build it (Recommended)` and `Skip`. On `Build it`, run
     `<cai> codemap_cli build --project-dir "<main>"`
     and tell the person its first line. On `Skip`, run nothing and skip step 3.
3. Right after the `EnterWorktree` call succeeds, before anything else runs
   inside the worktree (a track already there resumes without `track_start.py`), run
   `<cai> codemap_cli seed --project-dir "<top>"`
   with the worktree's `<top>`, and tell the person its first line in one
   sentence. It writes the worktree's own index from the main checkout's,
   parsing only the files that differ. Whatever it prints, the track goes on:
   `design` follows the steps above as it always does.
