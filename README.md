# claude-all-in-one

Personal [Claude Code](https://claude.com/claude-code) configuration, packaged
as a **plugin marketplace** so the whole setup installs into any project on any
machine with two commands.

## Contents

```
.claude-plugin/marketplace.json    Marketplace catalog (this repo is the marketplace)
plugins/ml-workflow/               The plugin
  agents/                          Cost-tiered subagents pinned to models:
                                     explorer (haiku, read-only scouting)
                                     implementer (sonnet)
                                     test-runner (haiku)
                                     architect (opus, read-only design)
  commands/git.md                  /ml-workflow:git — git ops under Haiku
  commands/haiku.md                /ml-workflow:haiku — any quick task under Haiku
  hooks/ + scripts/bash_guard.py   PreToolUse guard blocking destructive commands
                                     (force push, hard reset, git clean -f,
                                      --no-verify, rm -rf) — pure-Python, Windows-safe
.claude/rules/                     Topical instruction files (communication,
                                     epistemics, coding, workflow, model-selection,
                                     documentation) — copy to ~/.claude/rules/
                                     for global effect
CLAUDE.md                          Slim entry point for this repo
templates/multi-repo.settings.json Multi-repo access template
docs/multi-repo.md                 Cross-repo workflows (--add-dir, worktrees)
docs/multi-session.md              Sessions, background agents, agent teams, memory
```

## Prerequisites

- [Claude Code CLI](https://claude.com/claude-code) installed and authenticated
  (v2.1.32+ for agent teams; any recent version otherwise).
- Git. Python 3 on PATH (for the bash guard hook; ships with most setups).

## Installation

### 1. Install the plugin (agents + commands + hooks, all projects)

Inside any Claude Code session:

```
/plugin marketplace add millerlai/claude-all-in-one
/plugin install ml-workflow@claude-all-in-one
```

That's it — agents, commands, and the bash guard are now available in every
project. Update later with `/plugin update ml-workflow`.

#### Updating and force reinstall

The marketplace is cloned locally, so always refresh it first — otherwise
update/reinstall still serves the cached commit:

```
/plugin marketplace update claude-all-in-one
/plugin update ml-workflow
```

Force reinstall (only needed if content changed without a version bump, or the
cache looks corrupted):

```
/plugin marketplace update claude-all-in-one
/plugin uninstall ml-workflow@claude-all-in-one
/plugin install ml-workflow@claude-all-in-one
```

If even that serves stale content, delete the plugin's cache directory under
`~/.claude/plugins/` and install again. Either way, restart the session —
running sessions don't hot-reload plugin agents/hooks.

### 2. Install the global rules (instruction files)

Rules are not a plugin component, so copy them once to user scope:

```bash
# macOS / Linux
mkdir -p ~/.claude/rules && cp .claude/rules/*.md ~/.claude/rules/

# Windows (PowerShell)
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\rules" | Out-Null
Copy-Item .claude\rules\*.md "$env:USERPROFILE\.claude\rules\"
```

Re-run after pulling updates. Project-specific overrides go in each repo's own
`CLAUDE.md` / `.claude/rules/`.

### 3. Optional: enable agent teams (experimental)

```bash
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

See `docs/multi-session.md` for when teams beat subagents (and when they don't).

## Usage

- `/ml-workflow:git <git operation>` — run git ops under Haiku 4.5.
- `/ml-workflow:haiku <task>` — run any mechanical quick task under Haiku.
- Agents dispatch automatically per the model-selection rules, or mention them:
  `@agent-explorer`, `@agent-implementer`, `@agent-test-runner`, `@agent-architect`.
- Multi-repo sessions: `docs/multi-repo.md` + `templates/multi-repo.settings.json`.
- The bash guard blocks force-push / hard-reset / `git clean -f` / `--no-verify` /
  `rm -rf` and tells Claude to hand the command back to you.

## Memory

Claude Code's built-in auto memory (on by default) keeps per-project notes in
`~/.claude/projects/<project>/memory/` — inspect with `/memory`. This replaces
the previously recommended `claude-mem` tool. Curated instructions belong in
CLAUDE.md / rules; hard constraints belong in hooks.

## Optional tools

- **mermaid-cli** — renders and validates Mermaid diagrams via `mmdc`, matching
  the Mermaid convention in `.claude/rules/documentation.md`:

  ```bash
  npm install -g @mermaid-js/mermaid-cli
  ```

## Developing this repo

Working on the plugin itself? Add the marketplace from the local checkout, then
reinstall to test changes:

```
/plugin marketplace add /path/to/claude-all-in-one
/plugin install ml-workflow@claude-all-in-one
```

## Notes

- `.claude/settings.local.json` is per-user local settings, intentionally
  excluded via a global gitignore rule and not tracked here.
- Plugin commands are namespaced (`/ml-workflow:git`, formerly `/ml-workflow:git-haiku`);
  the old project-scope `/git-haiku` was moved into the plugin.
