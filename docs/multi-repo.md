# Multi-Repo Development

Working across sibling repos (e.g. a backend repo + a frontend repo) from one
Claude Code session.

## Grant access to another repo

One-off:

```bash
claude --add-dir ../other-repo
```

Persistent — add to the main repo's `.claude/settings.json`
(see `templates/multi-repo.settings.json`):

```json
{ "permissions": { "additionalDirectories": ["../other-repo"] } }
```

## Load the other repo's CLAUDE.md and rules too

By default only file access is granted. To also load the added directory's
`CLAUDE.md` / `.claude/rules/`, set the env var and use the CLI flag:

```bash
CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1 claude --add-dir ../other-repo
```

Caveat: the env var only affects directories added via `--add-dir`;
directories from `settings.json` never load their CLAUDE.md.

## Parallel work: worktrees

- `claude --worktree` gives a session an isolated git worktree, so multiple
  sessions can edit the same repo without stepping on each other.
- For very large repos, configure sparse checkout so worktrees only materialize
  the paths you need, and symlink heavy dirs like `node_modules`:

```json
{
  "worktree": {
    "sparsePaths": ["services/api", "shared"],
    "symlinkDirectories": ["node_modules"]
  }
}
```

## Layered CLAUDE.md in monorepos

- Starting from a subdirectory loads that dir's CLAUDE.md plus all ancestors'.
- Starting from the root loads subdirectory CLAUDE.md files on demand, when
  Claude first reads files there.
- Keep each CLAUDE.md scoped to its directory; use `claudeMdExcludes` in
  settings to skip irrelevant ones.
