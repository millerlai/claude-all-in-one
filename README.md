# claude-all-in-one

A [Claude Code](https://claude.com/claude-code) plugin that installs a working
set of everyday capabilities — cheaper model routing, safer git, and a shared
set of behavioural rules — into every project on your machine.

## What you get

| | |
|---|---|
| **Cost-tiered subagents** | `explorer` (Haiku, read-only scouting), `implementer` (Sonnet), `test-runner` (Haiku), `architect` (Opus, read-only design). Claude picks the cheapest model that can do the job instead of defaulting to the strongest. |
| **`/ml-workflow:git`** | Runs git and `gh` operations under Haiku 4.5 rather than the main session model. Confirms what it will touch before acting, never stages files you didn't name. |
| **`/ml-workflow:haiku`** | Runs any mechanical one-off — renames, formatting, lookups — under Haiku, and reports back if the task turns out to need real reasoning. |
| **`/ml-workflow:git-pr-rebase`** | Squashes a PR branch into one well-written conventional commit. Takes a backup branch first and shows you the message before rewriting anything. |
| **Bash safety guard** | A `PreToolUse` hook that blocks force pushes, `reset --hard`, `git clean -f`, `--no-verify`, and `rm -rf`, and hands the command back to you. |
| **Shared rules** | Seven instruction files covering how Claude should communicate, verify claims, write code, run its workflow, choose models, use memory, and write docs. Installed to user scope by `/ml-workflow:setup`. |

## Prerequisites

- Claude Code CLI, installed and authenticated.
- Git.
- Python 3 on `PATH` — `python3` on macOS/Linux, `python` or the `py` launcher
  on Windows. The bash guard needs it; `/ml-workflow:setup` tells you if it's
  missing.

## Install

Inside any Claude Code session:

```
/plugin marketplace add millerlai/claude-all-in-one
/plugin install ml-workflow@claude-all-in-one
```

Restart the session, then run:

```
/ml-workflow:setup
```

Setup copies the rule files into `~/.claude/rules/`, asks which language you
want Claude to reply in, sets up your global `~/.claude/CLAUDE.md`, and verifies
the bash guard actually fires. Restart once more so the new rules load.

Agents, commands, and the guard work in every project from then on. The rules
apply to every project too, since they live at user scope.

## Updating

The marketplace is cloned locally, so refresh it first — otherwise an update
re-serves the cached commit:

```
/plugin marketplace update claude-all-in-one
/plugin update ml-workflow
```

Re-run `/ml-workflow:setup` afterwards to pick up rule changes, and restart the
session — running sessions don't hot-reload plugin agents or hooks.

If content changed without a version bump, or the cache looks corrupted:

```
/plugin marketplace update claude-all-in-one
/plugin uninstall ml-workflow@claude-all-in-one
/plugin install ml-workflow@claude-all-in-one
```

## The rules

`/ml-workflow:setup` writes these to `~/.claude/rules/`. They are ordinary
Markdown — edit your copies freely; setup flags files that look hand-edited and
asks before overwriting them.

| File | What it governs |
|---|---|
| `communication.md` | Response language, conciseness, leading with the answer. |
| `epistemics.md` | Check before answering, cite sources, never fabricate, re-read as a skeptic before delivering. |
| `coding.md` | Pure functions, comment the why, minimum code, surgical changes only. |
| `workflow.md` | Branch before touching code, plan non-trivial changes, run tests before claiming done, never commit unless asked. |
| `model-selection.md` | Which subagent and model tier to use for which kind of task. |
| `memory.md` | Record stable facts only; don't persist implementation details that go stale. |
| `documentation.md` | Markdown, Mermaid for structure, validate diagrams before shipping. |

`communication.md` ships defaulting to English; `/ml-workflow:setup` rewrites
that line to whatever language you pick.

## Your global CLAUDE.md

`~/.claude/rules/` loads automatically, so your `~/.claude/CLAUDE.md` only needs
what the rules can't know — your OS, your stack, and the mistakes you don't want
repeated. Setup writes a thin starter there if you don't have one.

If you already have a CLAUDE.md, setup never overwrites it. It reports which of
your sections are now covered by a rules file and offers to slim the file down,
because a rule kept in both places is sent to the model twice in every session
and the two copies drift apart as soon as one is edited. `validate.py` enforces
the same invariant on the shipped template.

## Also included

- `docs/multi-repo.md` — cross-repo sessions with `--add-dir` and worktrees,
  plus `templates/multi-repo.settings.json`.
- `docs/multi-session.md` — sessions, background agents, agent teams, memory.
  Agent teams are experimental and need `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.
- Optional: [mermaid-cli](https://github.com/mermaid-js/mermaid-cli)
  (`npm install -g @mermaid-js/mermaid-cli`) so Claude can actually render and
  validate the diagrams `documentation.md` asks for.

Claude Code's built-in auto memory keeps per-project notes in
`~/.claude/projects/<project>/memory/` — inspect with `/memory`. Curated
instructions belong in the rules; hard constraints belong in hooks.

## Contributing / developing

Add the marketplace from a local checkout, then install to test your changes:

```
/plugin marketplace add /path/to/claude-all-in-one
/plugin install ml-workflow@claude-all-in-one
```

Everything users receive lives under `plugins/ml-workflow/` — the plugin cache
copies only that directory, so anything outside it never reaches an installer.

Adding guidance rather than code? [GUIDE.md](GUIDE.md) covers which component
should hold it — a convention, a procedure, or a constraint — and why putting it
in the wrong one makes it quietly stop working. It applies just as well to your
own `~/.claude/` setup.

Before pushing, run:

```bash
python scripts/validate.py
```

It checks the manifests, that every agent/command/skill has the frontmatter
Claude Code needs to load it, that hook commands point at files that exist, and
that the guard still blocks what it should — through the same dispatcher the
hook uses, on your platform.
