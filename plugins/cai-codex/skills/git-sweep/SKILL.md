---
name: git-sweep
description: List local branches whose work already landed on the base branch, and delete only the ones the user confirms. Usage: $git-sweep [--delete [--detach]]
---
> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.


Run `<cai-root>/scripts/branch_sweep.py` and relay its table
verbatim. The script decides which branches are deletable; do not re-derive
that yourself, and do not run `git branch --merged`, `gh pr list` or any other
check of your own to second-guess a row. Its answer and yours must be the same
answer.

- Default run: no arguments. It prints the table and changes nothing.
- Against a base other than the repository's default: `--base <branch>`.
- To actually delete: `--delete`, which removes only the rows the table
  already called `deletable`.
- To free the rows it called `detachable` as well: `--delete --detach`.

Never pass `--delete` on the first run of a conversation. Show the table,
let the user look at it, and pass `--delete` only after they say so. If they
asked to clean up branches in their opening message, that is a request to see
the table first -- it is not advance permission to delete.

`--detach` needs a yes of its own. It changes a second working directory, so
"delete them" said about the `deletable` rows does not cover it: name the
`detachable` rows and the worktree each one is in, and pass `--detach` only
after the user says to free those too. Say as well that a branch with no
commits of its own reads as already on the base, so a worktree someone has
only just started in can be among them.

What the six statuses mean, since the user will ask about the ones that are
not `deletable`:

- `deletable` -- the branch's work is on the base branch, by ancestry or by a
  merged pull request. The `WHY` column names which.
  Or it is a `backup/<source>-<suffix>` branch whose source's pull request
  merged after the backup's last commit; the `WHY` column then reads
  `backup of <source>: pr #N merged`. That match is by name only -- nothing
  checks the backup's contents.
- `detachable` -- the same proof as `deletable`, but the branch is checked out
  in another worktree, whose path ends the `WHY` column. `--detach` moves that
  worktree onto the same commit with no branch, then deletes the branch. The
  worktree's directory and every file in it stay as they were; what the user
  is left with is a worktree on a detached HEAD, theirs to remove or reuse.
- `held` -- checked out in a worktree and not proven safe to free. The `WHY`
  column gives the reason first, then where: a worktree's path, or `checked
  out in the current worktree` for the branch this ran from, which switching
  to the base branch and running again frees.
- `ahead` -- carries commits its upstream never received. Even when its pull
  request is merged, those commits exist nowhere else; never offer to delete
  one without saying that first.
- `gone` -- the remote branch is deleted but nothing proves it was merged.
  Some repositories delete a head branch on merge, and a person can delete one
  at any time; the script will not guess which happened.
- `keep` -- no merge signal at all.
  A backup whose `WHY` ends in `merged before its last commit` has a source
  whose pull request merged before the backup's last commit, so it is
  probably left over from a later round on a reused branch name.

Removing a worktree is the user's to do: do not run `git worktree remove`
unasked, and never suggest `--force`. Git deletes a worktree's ignored files
without asking, and git 2.39.2 for Windows was measured following a directory
junction inside one and deleting the files it points at. If they ask for one
to be removed, show them the links and ignored files in it first.

If the table is preceded by a `note:` line, relay it: it means the merged
pull request signal was unavailable, so any branch merged by squash could only
read as `keep` that run. Backup branches can then only read as `keep` too. On
a repository that squashes -- which is what this plugin's own `ship` stage
does -- that note is the difference between an empty table and a correct one,
so do not drop it as boilerplate.

After a `--delete` run, each deleted branch prints the SHA it was at and the
`git branch` command that puts it back; one freed with `--detach` prints a
second command under it, which puts its worktree back on the branch. Relay
those lines, indented ones included; they are the only undo the user gets.
