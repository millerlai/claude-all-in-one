---
name: intake
description: "Turn a request into an acceptance-testable problem statement before any code exists — explore context, ask one question at a time, propose 2-3 approaches with a recommendation, then wait for approval. Usage: /cai:intake <request>"
argument-hint: "<request>"
disable-model-invocation: true
---

Run the intake stage for: $ARGUMENTS

The procedure lives in one place, read by whoever runs this stage — a
track's subagent or this command:
`${CLAUDE_PLUGIN_ROOT}/skills/track/references/stage-intake.md`. Read it in
full and follow it.

**Running this stage on its own writes nothing to any track's `state.md`.**
There is no track underneath this command — the reference file's closing
step, which writes a note into a track's state, does not apply here. If a
track already exists for this work, use `/cai:track` instead so the record
stays with it.
