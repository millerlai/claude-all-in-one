---
name: discover
description: An unknown that would change the work, surfaced before implementation code is written — the codebase area is unfamiliar, the requirements are ambiguous, the option space is unexplored, a term is undefined, or the result will be judged by look and feel. Use when the user says "what am I missing", "interview me about this", "brainstorm the options", "mock this up first", or "I don't know what X is".
argument-hint: "<what is unclear>"
---

Run the discover procedure for: $ARGUMENTS

This is a standalone command, not a stage of `/cai:track`: a track's `design`
stage recommends it when the option space is unexplored, and never runs it.

The procedure lives in one place, read by this command:
`${CLAUDE_PLUGIN_ROOT}/skills/track/references/stage-discover.md`. First, if
`<top>/.cai/codemap/state.json` exists, follow
`${CLAUDE_PLUGIN_ROOT}/skills/track/references/codemap-brief.md` yourself,
skipping its step 2: a model may start this command on its own, so it reads
the index with `status` and never runs `update`. You run this stage, so the
line it yields is yours to act on. Read the stage
reference in full and follow it.

**Running this stage on its own writes nothing to any track's `state.md`.**
There is no track underneath this command — the reference file's closing
step, which writes a note into a track's state, does not apply here. If a
track already exists for this work, use `/cai:track` instead so the record
stays with it.
