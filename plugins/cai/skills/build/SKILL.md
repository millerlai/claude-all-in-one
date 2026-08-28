---
name: build
description: "Build a detail design's work breakdown unit by unit, test-first, verifying and committing each one before the next starts — or, with no design document, cut checkpointed units yourself. Usage: /cai:build <detail design doc, or what to build>"
argument-hint: "<detail design doc, or what to build>"
disable-model-invocation: true
---

Run the build stage for: $ARGUMENTS

The procedure lives in one place, read by whoever runs this stage — a
track's subagent or this command:
`${CLAUDE_PLUGIN_ROOT}/skills/track/references/stage-build.md`. Read it in
full and follow it.

**Running this stage on its own writes nothing to any track's `state.md`.**
There is no track underneath this command — the reference file's closing
step, which writes a note into a track's state, does not apply here. If a
track already exists for this work, use `/cai:track` instead so the record
stays with it.
