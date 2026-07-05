# claude-all-in-one

Personal [Claude Code](https://claude.com/claude-code) configuration: project-level instructions and custom slash commands.

## Contents

- `CLAUDE.md` — project instructions Claude Code automatically loads for this repo (communication style, workflow rules, code conventions, etc.).
- `.claude/commands/git-haiku.md` — custom `/git-haiku` slash command.

## Prerequisites

- [Claude Code CLI](https://claude.com/claude-code) installed and authenticated.
- Git.

## Installation

```bash
git clone git@github.com:millerlai/claude-all-in-one.git
cd claude-all-in-one
```

Open the directory with Claude Code:

```bash
claude
```

`CLAUDE.md` is loaded automatically as project instructions; no further setup is required.

## Optional tools

Extra CLIs that complement this setup (both require Node.js / npm):

- **claude-mem** — persistent memory for Claude Code.

  ```bash
  npx claude-mem install
  ```

- **mermaid-cli** — renders and validates Mermaid diagrams via the `mmdc` command, matching the Mermaid documentation convention in `CLAUDE.md`.

  ```bash
  npm install -g @mermaid-js/mermaid-cli
  ```

## Usage

- `/git-haiku` — runs the requested git operation (commit, push, branch, etc.) under the Haiku 4.5 model instead of the main session model.

## Notes

- `.claude/settings.local.json` is a per-user local settings file. It is intentionally excluded via a global gitignore rule and is not tracked in this repo.
