---
name: git-sweep
description: List local branches whose work already landed on the base branch, and delete only the ones the user confirms. Usage: $git-sweep [--delete]
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

Never pass `--delete` on the first run of a conversation. Show the table,
let the user look at it, and pass `--delete` only after they say so. If they
asked to clean up branches in their opening message, that is a request to see
the table first -- it is not advance permission to delete.

What the five statuses mean, since the user will ask about the ones that are
not `deletable`:

- `deletable` -- the branch's work is on the base branch, by ancestry or by a
  merged pull request. The `WHY` column names which.
  Or it is a `backup/<source>-<suffix>` branch whose source's pull request
  merged after the backup's last commit; the `WHY` column then reads
  `backup of <source>: pr #N merged`. That match is by name only -- nothing
  checks the backup's contents.
- `held` -- checked out in a worktree, so git would refuse to delete it. To
  remove it the user has to `git worktree remove <path>` first; say so rather
  than doing it unasked.
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

If the table is preceded by a `note:` line, relay it: it means the merged
pull request signal was unavailable, so any branch merged by squash could only
read as `keep` that run. Backup branches can then only read as `keep` too. On
a repository that squashes -- which is what this plugin's own `ship` stage
does -- that note is the difference between an empty table and a correct one,
so do not drop it as boilerplate.

After a `--delete` run, each deleted branch prints the SHA it was at and the
`git branch` command that puts it back. Relay those lines; they are the only
undo the user gets.
