---
name: design
description: "Write a design document for review — high-level (weighs architecture options, stops before implementation detail), detail (turns an approved high-level design into something a team can build from), or delta (recovers the decisions from a branch already built). Usage: /cai:design <what to design, or the mode: high-level|detail|delta>"
argument-hint: "<what to design — or which mode, if not obvious>"
disable-model-invocation: true
---

Run the design stage for: $ARGUMENTS

The procedure lives in one place, read by whoever runs this stage — a track,
or this command:
`${CLAUDE_PLUGIN_ROOT}/skills/track/references/stage-design.md`. Read it in
full, pick the mode it describes (high-level / detail / delta), and follow
it. Run it here, in this session: it has to reach `AskUserQuestion`, and no
subagent can.

**Running this stage on its own writes nothing to any track's `state.md`.**
There is no track underneath this command — the reference file's closing
step, which writes a note into a track's state, does not apply here. If a
track already exists for this work, use `/cai:track` instead so the record
stays with it.
