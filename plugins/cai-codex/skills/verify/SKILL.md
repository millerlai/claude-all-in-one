---
name: verify
description: A diff, branch, or PR to review before it merges — four read-only lenses (correctness, conformance, coverage, security), then Blockers and Majors fixed test-first. Use when the user says "review my changes", "審一下這個 diff" — and on your own changes before handing them over.
argument-hint: "[base ref, or what to review against]"
---
> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.


Run the verify stage for: $ARGUMENTS

The procedure lives in one place, read by whoever runs this stage — a
track's subagent or this command:
`<cai-root>/skills/track/references/stage-verify.md`. Read it in
full and follow it.

**Running this stage on its own writes nothing to any track's `state.md`.**
There is no track underneath this command — the reference file's closing
step, which writes a note into a track's state, does not apply here. If a
track already exists for this work, use `$track` instead so the record
stays with it.
