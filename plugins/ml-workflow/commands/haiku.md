---
description: Run a quick, mechanical task under Haiku instead of the main session model — renames, formatting, simple lookups, one-off shell commands, boilerplate. Usage: /ml-workflow:haiku <task>
model: claude-haiku-4-5-20251001
argument-hint: <quick task>
---

Execute this task: $ARGUMENTS

Rules:
- This lane is for mechanical, low-reasoning work only. If the task turns out
  to require design decisions or multi-file reasoning, STOP and report back
  that it should run on the main session model instead.
- Keep output terse: what was done, files touched (if any), result.
