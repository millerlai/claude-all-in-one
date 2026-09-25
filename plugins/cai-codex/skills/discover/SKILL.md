---
name: discover
description: An unknown that would change the work, surfaced before implementation code is written — the codebase area is unfamiliar, the requirements are ambiguous, the option space is unexplored, a term is undefined, or the result will be judged by look and feel. Use when the user says "what am I missing", "interview me about this", "brainstorm the options", "mock this up first", or "I don't know what X is".
argument-hint: "<what is unclear>"
---
> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.


Run the discover stage for: $ARGUMENTS

The procedure lives in one place, read by whoever runs this stage — a
track's subagent or this command:
`<cai-root>/skills/track/references/stage-discover.md`. Read it
in full and follow it.

**Running this stage on its own writes nothing to any track's `state.md`.**
There is no track underneath this command — the reference file's closing
step, which writes a note into a track's state, does not apply here. If a
track already exists for this work, use `$track` instead so the record
stays with it.
