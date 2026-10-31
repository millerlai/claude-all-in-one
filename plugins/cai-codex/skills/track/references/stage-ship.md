# stage-ship — squash, release-note, and stop before anything irreversible

The main session runs this file, both inside a track and when someone runs
`$ship` standing alone, with no track underneath it; the track hands it
to no subagent. The procedure below is the same either way.

**On Codex, this stage prepares only and never runs the irreversible
operations below** — merging, tagging, publishing. No subagent runs an irreversible git/gh operation here: after
the person confirms, the main session runs tagging and publishing
itself, but not the merge — the guard denies `gh pr merge` on this
platform (its "ask" permission decision is parsed but not acted on
here), so hand that exact command back for the person to run
themselves. That confirmation
is one of the two human gates the track never skips; running this stage
standing alone does not remove it. Closing the ticket is not one of this
stage's operations: `$track done` offers it instead. The sandbox's own push approval
prompt is untested through release — do not treat it as a second safety
net; Gate 2 is the only confirmation you can rely on.

**Gate 2's push is asked as a menu**, quoting the exact commands about to
run — never a sentence the person types a word back into.
`references/approval-gates.md` holds its options. The merge is one more
confirmation, not a menu: the bash guard's permission prompt, which on Codex
is a denial that hands the command to the person. That confirmation, and
every "stop and ask" below, is asked directly.

## The grounding rule

Everything this stage writes — the commit message, the release note, the PR
body — is prose about a diff, read later by people who will not open the
diff to check it. That is exactly the shape a plausible sentence survives
in: a use case renumbered, a file described that was never added, a report
named that does not exist.

So every factual claim in what you hand back names the diff line, commit,
or file it came from, and you confirmed that source in this pass. Three
things settle a claim and nothing else does: a hunk in `git diff
<BASE>..HEAD`, a line in `git log <BASE>..HEAD`, or a file you opened and
read. Not the design document's plan for the change — that says what was
intended, not what landed. Not the branch name. Not what the last stage
reported.

A claim you cannot ground gets cut, not softened. "Also improves error
handling" with no hunk behind it is not a weaker claim than the ones that
have one; it is the one that will be wrong.

**Reading budget.** Grounding is bounded by the diff, not by the repository.
Read `git log` and `git diff --stat` first, then each file's diff once —
not again for each claim; open a file or run a search outside the diff only
to confirm a name or path a claim quotes. A claim about what the rest of the
code does or does not do — "no other caller", "now unused", "matches the
existing convention" — needs a repo-wide search to ground, so it is cut; say
what the hunk shows instead. When the diff is large, write from the commit
subjects and the files the stat lists, and open a hunk only for a claim that
names one. Past about 40 tool calls, stop checking: cut each claim still
ungrounded and hand the draft back. A draft that takes a hundred calls
has checked the repository, not the diff.

## Step 1 — Preflight checks

```bash
git status --porcelain --untracked-files=no
git branch --show-current
```

Only a tracked file with uncommitted changes blocks: name the files and stop.
Committing them is the person's (or stashing them, but only when `git worktree
list` shows a single worktree, since every worktree of a repo shares one
stash); you never commit here, whatever Gate 1's commit answer was. An untracked file never blocks: the squash (Step 5) neither includes
nor touches it (#198). Must be on a feature branch — if on `main`/`master` or
detached HEAD, stop.

## Step 2 — Determine BASE

If a commit id was given, validate it:

```bash
git cat-file -t <given-id>            # must print "commit"
git merge-base --is-ancestor <given-id> HEAD   # exit 0 means it is an ancestor of HEAD, nonzero means it is not
```

Either check failing → stop, tell the user the id is invalid or not an
ancestor of HEAD.

Otherwise detect the default branch and compute the merge-base — run these
as separate commands, not piped through shell variables or `${VAR:-default}`,
so it works on Windows:

```bash
git symbolic-ref --short refs/remotes/origin/HEAD
git merge-base HEAD origin/<default-branch>
```

Fall back to `origin/main`, then `origin/master`, if the first command fails.

## Step 3 — Show what will be squashed

```bash
git log --oneline <BASE>..HEAD
git diff --stat <BASE>..HEAD
```

0 commits → nothing to do, stop. 1 commit → only the message needs
rewriting, proceed. Otherwise show the commit list to the user.

## Step 4 — Draft the final commit message

Read `git log <BASE>..HEAD --pretty=format:'%h %s%n%b'` and the diff stat.
Compose one conventional commit message in English: `type(scope): summary`,
imperative mood, ≤72 chars, then 2–6 body bullets summarizing the *net*
change — not a replay of intermediate commits, and not fixup/WIP noise.
Every bullet is a claim; the grounding rule above applies to each one.

**Write at the level of behaviour.** A bullet says what a person using the
change can now do, or no longer suffers — not which function, constant or
parameter was edited; those stay in the diff. Tests get one line at the same
level: the main behaviours they now check ("rejects an expired login token"),
never a count, a list of test names or assertions, or the error-handling and
edge-case tests, unless the change is about those. Report the run as "tests
pass", with no number. When the issue's acceptance criteria or the design asks
for something more specific — every modified existing test listed, say — do
that, and name the criterion that asked.

When
the track has a ticket number (`references/ticket-mirror.md`'s ship
section), reference it as `Refs #<number>` and never with a closing keyword —
closing stays with `$track done`. No ticket number leaves the message
unaffected.

End the message with the trailer lines your own instructions give for commits
(`Co-Authored-By:` and the like), if any, before it is checked and shown, so
the message the person approves is the one committed.

**Draft first, and stop at the menu.** On a branch's first ship (and again
for each fix round), do Steps 1–4 and 7's drafting only, changing nothing,
then check both texts and show them with the commands in one menu, as
`references/approval-gates.md`'s Gate 2 section says; its "Run them" is the
consent to rewriting history and to publishing. Steps 5 and 6 and Step 7's
commands run only after "Run them", with both approved texts unchanged. This
is history-rewriting; never skip confirmation.

## Step 5 — Backup, then squash

```bash
git branch backup/<branch>-<timestamp>   # <branch> from Step 1; <timestamp> as YYYYMMDD-HHMMSS, computed yourself rather than with a bash-only date substitution
git reset --soft <BASE>
# Choose <scratch-dir> as rules/workflow.md's Codex sandbox permissions section says. Write the message (title, a blank line, the body) to <scratch-dir>/cai-commit-msg.txt with your file-writing tool, not the shell, overwriting any earlier copy; leave it there afterwards.
git commit -F '<full path of cai-commit-msg.txt>'
```

## Step 6 — Verify and report

```bash
git log --oneline -3
git status
git diff --stat <BASE>..HEAD    # content must be identical to before the squash
```

Report the new single commit (hash + title), the backup branch name, and
the push instruction: `git push --force-with-lease` only — never plain
`-f`/`--force`.

## Step 7 — Write the release note

Drafted with Step 4, before the squash: `git diff <BASE>..HEAD` is the same
before and after it. The two commands below run only after "Run them".

One paragraph, written for someone who was not in this conversation: what
changed, why (the requirement it satisfies, not the mechanism), and
anything a caller needs to do differently. Tests and detail follow Step 4's
*Write at the level of behaviour*. Pull the "why" from the design
document this track produced, if one exists, rather than re-deriving it
from the diff — but the *what* still comes from the diff under the
grounding rule, since a design document describes a plan and this paragraph
describes what shipped. Where the two disagree, the diff is right and the
gap is worth a sentence. When the track has a ticket number, reference it
as `Refs #<number>` and never with a closing keyword — closing stays with
`$track done`. No ticket number leaves the body unaffected. Put it in the PR description — you have `gh`, and that is where it always
lands. Choose <scratch-dir> as rules/workflow.md's Codex sandbox permissions section says. Write the release note to <scratch-dir>/cai-pr-body.md with your file-writing tool, not the shell, overwriting any earlier copy, then pass the file and leave it there afterwards:

```bash
gh pr create --title '<title>' --body-file '<full path of cai-pr-body.md>'   # keep the title free of apostrophes: bash and PowerShell escape one differently
```

When a pull request is already open — a fix round
(`references/approval-gates.md`) — update it instead of opening another:

```bash
gh pr edit <number> --title '<title>' --body-file '<full path of cai-pr-body.md>'   # the body file written above; same apostrophe rule for the title
```

If this project also keeps a `CHANGELOG.md`, write the same paragraph
into it as the change's entry after "Run them", and name the file in the
report.

Give a command that waits, such as `gh pr checks --watch`, a Bash `timeout`
it fits in: a call that times out is moved to the background rather than
killed. Name any still running in the report, and stop it with TaskStop.

## Rollback

```bash
git reset --soft backup/<branch>-<timestamp>
```

`--soft` fully restores the original history — the squash never touches the
working tree, so only the branch pointer needs to move back. Never
`git reset --hard`.

## When not to use this

- The branch has already been squashed and the message is fine — say so and
  do nothing.
- Nothing has changed since the last ship — there is no diff to note.

## Report

Under a track, these fields go in a `## Report` section of the report file
the track's `SKILL.md` step 2 names -- not the report this file's own steps
describe. Its step 3 alone writes the track's state table and the ledger's
`--note` from them; this stage writes no other track file.

- the final commit hash
- whether the merge/tag/publish step ran or is still waiting on the person
- where the release note landed
- what is left open -- anything still waiting on the person after merge, one item each

Evidence goes in the artifact this stage already produces, never pasted
in here. 4000 characters is the ceiling for this section: the largest
note any finished track has written is 1941 characters, measured across
30 rows in five tracks, and a report carries those fields plus what never
reaches that cell. The number is the user's call, 2026-09-08.
