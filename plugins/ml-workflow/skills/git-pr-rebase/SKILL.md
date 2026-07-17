---
name: git-pr-rebase
description: Squash all commits on the current PR branch into a single, well-written conventional commit. Use whenever the user invokes /git-pr-rebase, or asks to "squash this branch", "clean up commits before merging", "rebase onto the branch point", or wants one final commit message for a PR. Handles both an explicitly given base commit id and auto-detection of the branch point (the commit the branch was created from, typically the tip of main at branch time).
---

# git-pr-rebase — Squash PR branch into one commit

Squash every commit on the current branch (since it diverged from the base) into a single commit with a clean, conventional commit message. Equivalent to `git rebase -i <base>` with everything squashed, but implemented non-interactively via `git reset --soft`.

## Argument

The user may pass a commit id: `/git-pr-rebase <commit-id>`.

- **If a commit id is given** → use it as `<BASE>`.
- **If not given** → auto-detect the branch point (see Step 2).

## Workflow

Follow these steps in order. Stop and report to the user on any failed check — do not improvise recovery.

### Step 1 — Preflight checks

```bash
git status --porcelain
git branch --show-current
```

- Working tree must be clean. If dirty → stop, ask the user to commit or stash first.
- Must be on a feature branch. If on `main`/`master` or detached HEAD → stop.

### Step 2 — Determine BASE

**If the user provided a commit id**, validate it:

```bash
git cat-file -t <given-id>            # must print "commit"
git merge-base --is-ancestor <given-id> HEAD && echo OK   # must print OK
```

If either check fails → stop and tell the user the id is invalid or not an ancestor of HEAD.

**If not provided**, detect the default branch and compute the merge-base:

```bash
DEFAULT=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|origin/||')
# Fallbacks if the above fails: try origin/main, then origin/master, then local main
BASE=$(git merge-base HEAD "origin/${DEFAULT:-main}")
```

`git merge-base HEAD origin/main` is exactly "the last commit on main before this branch's first commit" — the commit id the user would otherwise look up manually.

### Step 3 — Show what will be squashed

```bash
git log --oneline <BASE>..HEAD
git diff --stat <BASE>..HEAD
```

- **0 commits** → nothing to do; stop.
- **1 commit** → only the message needs rewriting; still proceed (the flow below handles it naturally).
- Show the commit list to the user so they can see what's being collapsed.

### Step 4 — Draft the final commit message

Read the material needed to write a good message:

```bash
git log <BASE>..HEAD --pretty=format:'%h %s%n%b'
git diff --stat <BASE>..HEAD
```

Compose **one** conventional commit message in **English**:

- Title: `type(scope): summary` — imperative mood, ≤ 72 chars. Pick the dominant type (`feat`, `fix`, `refactor`, `docs`, `chore`, ...). If the branch mixes types, use the one matching the PR's primary purpose.
- Body: 2–6 bullet points summarizing the *net* change (what the PR does overall), not a replay of the intermediate commits. Ignore fixup/WIP noise like "fix typo", "address review".
- If commit messages reference an issue/PR number, keep the reference in the body footer.

**Show the drafted message to the user and wait for confirmation** (or edits) before executing Step 5. This is a history-rewriting operation; never skip confirmation.

### Step 5 — Backup, then squash

```bash
BRANCH=$(git branch --show-current)
git branch "backup/${BRANCH}-$(date +%Y%m%d-%H%M%S)"   # safety net
git reset --soft <BASE>
git commit -m "<title>" -m "<body>"
```

Use multiple `-m` flags or a heredoc for the multi-line body — do not try to embed literal newlines in a single `-m`.

### Step 6 — Verify and report

```bash
git log --oneline -3
git status
git diff --stat <BASE>..HEAD    # content must be identical to before the squash
```

Report to the user:

1. The new single commit (hash + title).
2. The backup branch name.
3. Push instruction — the remote branch has diverged, so:

```bash
git push --force-with-lease
```

**Never use `git push -f` or `git push --force`** — use `--force-with-lease` only (plain force push is blocked by the bash guard hook, and is unsafe regardless).

## Rollback

If anything looks wrong after the squash:

```bash
git reset --soft backup/<branch>-<timestamp>
```

`--soft` is sufficient and fully restores the original history: the squash never
touches the working tree (identical tree before/after), so only the branch
pointer needs to move back. Do not use `git reset --hard` — it is blocked by the
ml-workflow bash guard hook and is unnecessary here.

The backup branch can be deleted once the PR is merged: `git branch -D backup/...`

## Notes & edge cases

- `git reset --soft <BASE>` + commit produces the same tree as a fully-squashed `git rebase -i <BASE>`, with no interactive editor involved.
- Merge commits inside the branch are flattened automatically by this approach — no special handling needed.
- If `origin/HEAD` is not set (fresh clone quirk), `git remote set-head origin -a` fixes it, or just fall back to `origin/main`.
- If the branch has already been squashed (exactly 1 commit whose message the user is happy with), say so and do nothing.
