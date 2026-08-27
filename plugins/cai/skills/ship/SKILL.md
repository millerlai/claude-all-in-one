---
name: ship
description: "Squash a PR branch into one conventional commit, write a release note, and stop before merging, tagging, or publishing until a person confirms. Usage: /cai:ship [base commit id]"
argument-hint: "[base commit id]"
disable-model-invocation: true
---

Run the ship stage for: $ARGUMENTS

The procedure lives in one place, read by whoever runs this stage — a
track's subagent or this command:
`${CLAUDE_PLUGIN_ROOT}/skills/track/references/stage-ship.md`. Read it in
full and follow it.

**Running this stage on its own writes nothing to any track's `state.md`.**
There is no track underneath this command — the reference file's closing
step, which writes a note into a track's state, does not apply here. If a
track already exists for this work, use `/cai:track` instead so the record
stays with it.
