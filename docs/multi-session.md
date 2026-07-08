# Multi-Session Workflows

Three tiers, lightest first. Escalate only when the lighter tier can't do it —
heavier tiers consume significantly more tokens.

## 1. Resume / fork a session

- `claude --resume` (or the session picker) continues past sessions; sessions
  can be named and forked.
- `/rewind` restores earlier checkpoints within a session.

## 2. Background sessions (one operator, many sessions)

- `claude agents` opens the agent view: dispatch background sessions into any
  directory, monitor status, peek and reply, or attach to take over.
- Background sessions run under a supervisor process and use worktree isolation
  for file edits — safe to run several against the same repo.

## 3. Agent teams (sessions talking to each other)

Experimental. Enable per-machine:

```bash
# settings.json → "env", or export in your shell
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

- One session acts as team lead; teammates are full Claude Code instances with
  their own context windows, coordinating via a shared task list and mailbox.
- Unlike subagents (report only to the caller), teammates message each other
  and self-claim tasks; you can also talk to any teammate directly.
- Teammates can be spawned from the ml-workflow plugin agent definitions, which
  pins their model and tool whitelist — the cost ladder still applies:
  explorer/test-runner on haiku, implementer on sonnet, architect on opus.
- Quality gates: hook into `TeammateIdle` / `TaskCompleted`; exiting with
  code 2 sends feedback back and keeps the teammate working.

Start with read-only parallel work (investigation, code review). Sequential
edits to the same files are still better done in a single session or subagent.

## Long-term memory

- Auto memory is built in and on by default: Claude maintains notes per project
  under `~/.claude/projects/<project>/memory/`, shared across worktrees of the
  same repo. `MEMORY.md` is the index (first 200 lines load each session);
  inspect and edit with `/memory`.
- Curated instructions belong in CLAUDE.md / `.claude/rules/`; hard constraints
  belong in hooks + permission rules, not prose.
