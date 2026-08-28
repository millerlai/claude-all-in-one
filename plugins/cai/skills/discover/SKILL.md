---
name: discover
description: Surface what the user doesn't know before writing implementation code — a blindspot pass, a vocabulary ladder, an interview, an option space, or a mock, whichever unknown would change the most work. Use whenever the codebase area is unfamiliar, the requirements are ambiguous, the solution space has not been explored, or the result will be judged by look and feel. Also use when the user invokes /cai:discover, or says "what am I missing", "find my blindspots", "interview me about this", "brainstorm the options", "show me some directions", "mock this up first", "I've never touched this code", or "I don't know what X is".
argument-hint: "<what is unclear>"
---

Run the discover stage for: $ARGUMENTS

The procedure lives in one place, read by whoever runs this stage — a
track's subagent or this command:
`${CLAUDE_PLUGIN_ROOT}/skills/track/references/stage-discover.md`. Read it
in full and follow it.

**Running this stage on its own writes nothing to any track's `state.md`.**
There is no track underneath this command — the reference file's closing
step, which writes a note into a track's state, does not apply here. If a
track already exists for this work, use `/cai:track` instead so the record
stays with it.
