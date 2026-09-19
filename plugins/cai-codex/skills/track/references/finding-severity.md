# finding-severity -- what Blocker, Major and Minor mean, and what the security lens hunts

Two things live here because more than one procedure needs them, and a second
copy of a definition is a second definition: the three severity words a review
ranks its findings by, and the four hunt items the `verify` stage's security
lens works from.

## The three severities

`stage-verify.md`'s Step 2 already requires every surviving `Blocker` and
`Major` to name the requirement it rests on -- the original request's own
words, a plan or issue paragraph, or an existing standing obligation. These
three are that rule written as a test you can apply to one finding.

- **`Blocker`** -- the change is wrong as it stands: it fails a requirement it
  can name, on the path that requirement is about, so merging it ships the
  failure. Many findings do not make a Blocker; one that makes the change
  wrong does.
- **`Major`** -- the change is right on the path it was written for and fails a
  requirement it can name on another path that same requirement covers, so it
  is wrong under conditions that will occur rather than conditions that might.
- **`Minor`** -- no requirement is at stake: the finding names a preference, a
  cost, or a tidier alternative, and no failure. Pure taste lands here, and a
  `Minor` is recorded and left unfixed unless the user asks for it.

The security lens has no floor: a hit on one of the four items below is ranked
by these same three, on the same evidence, as any other lens's finding.

## The security lens's four hunt items

Four, and there is no fifth. Each is a question asked of this diff, not a
subject to think about.

1. **Shell execution.** Does this diff route an external call through a command
   interpreter -- a shell flag, a system or popen call, or a string assembled
   and handed to one -- where an argument vector was passed before?
2. **What reaches the argument vector.** Who controls the values that end up in
   the call, including the name of the program being run? A call with no shell
   is not therefore safe: choosing which binary runs is a privilege surface of
   its own.
3. **Secrets and payloads in what is kept.** Does this diff add a path that
   sends raw standard error, raw standard output, or a full argument vector
   into a print, a file, or any record that outlives the run? Where one
   function has more than one output site, was every one of them changed?
4. **Guard bypass.** Where the repo refuses a list of command shapes, does this
   diff let a shape that list does not cover through -- a new separator, an
   alias, a different quoting form -- or widen a path on which the guard fails
   open?

## When the repo under review keeps its own review policy

Read `.claude/cai-review.md` in the repo being reviewed, if it is there. It
supplies where each of the four items lands in that repo and an example of
each, and nothing else: it adds no fifth item and it does not change what the
three severities mean.

A repo without that file is the ordinary case, not an error. A missing file
means nobody there ever wrote one -- use the four items above as they stand,
and say nothing about its absence.
