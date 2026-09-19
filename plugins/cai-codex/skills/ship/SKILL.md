---
name: ship
description: "Squash a PR branch into one conventional commit, write a release note, and stop before merging, tagging, or publishing until a person confirms. Usage: $ship [base commit id]"
---
> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.


Run the ship stage for: $ARGUMENTS

The procedure lives in one place, read by whoever runs this stage — a
track's subagent or this command:
`<cai-root>/skills/track/references/stage-ship.md`. Read it in
full and follow it.

**Running this stage on its own writes nothing to any track's `state.md`.**
There is no track underneath this command — the reference file's closing
step, which writes a note into a track's state, does not apply here. If a
track already exists for this work, use `$track` instead so the record
stays with it.
