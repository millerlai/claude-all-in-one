# stage-ship — squash, release-note, and stop before anything irreversible

This file is read two ways: by the subagent the track dispatches to run this
stage, and by `/cai:ship` when someone runs the stage standing alone, with
no track underneath it. The procedure below is the same either way.

**Before the irreversible operations below — merging, tagging, publishing,
and closing the linked ticket — confirm with the person first.** This is
one of the two human gates the track never skips; running this stage
standing alone does not remove it. Closing the ticket joins this same gate
rather than adding a third — see `references/ticket-mirror.md`'s ship
section for that confirmation's own separate item.

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

**When this stage runs as a dispatched subagent, the main session applies
this rule again to its output before using it** — re-derive each claim from
the diff itself. A subagent's report is a draft, and the diff is the only
thing that outranks it.

## Step 1 — Preflight checks

```bash
git status --porcelain
git branch --show-current
```

Working tree must be clean — if dirty, stop and ask the user to commit or
stash first. Must be on a feature branch — if on `main`/`master` or detached
HEAD, stop.

## Step 2 — Determine BASE

If a commit id was given, validate it:

```bash
git cat-file -t <given-id>            # must print "commit"
git merge-base --is-ancestor <given-id> HEAD && echo OK   # must print OK
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

**Show the drafted message to the user and wait for confirmation** before
Step 5. This is history-rewriting; never skip confirmation.

## Step 5 — Backup, then squash

```bash
git branch "backup/${BRANCH}-$(date +%Y%m%d-%H%M%S)"
git reset --soft <BASE>
git commit -m "<title>" -m "<body>"
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

One paragraph, written for someone who was not in this conversation: what
changed, why (the requirement it satisfies, not the mechanism), and
anything a caller needs to do differently. Pull the "why" from the design
document this track produced, if one exists, rather than re-deriving it
from the diff — but the *what* still comes from the diff under the
grounding rule, since a design document describes a plan and this paragraph
describes what shipped. Where the two disagree, the diff is right and the
gap is worth a sentence. Put it wherever this project keeps release notes — a
`CHANGELOG.md` entry if one exists, otherwise the PR description.

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

## Closing

Before handing off, write into `state.md`'s `note` cell for `ship`: the
final commit hash, whether the merge/tag/publish step ran or is still
waiting on the person, and where the release note landed.
