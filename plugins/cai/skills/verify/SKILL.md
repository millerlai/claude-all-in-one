---
name: verify
description: Review a branch diff before merging by dispatching three read-only reviewers (correctness, conformance, coverage) in parallel and reconciling their findings, then fix Blockers and Majors with a failing test run before and a passing one after. Use when the user asks to review a diff, branch, or PR before merging, says "review my changes", "check this before I merge", "審一下這個 diff", "找出這次改動的問題" — and on your own changes before handing them over.
argument-hint: "[base ref, or what to review against]"
---

Run the verify stage for: $ARGUMENTS

The procedure lives in one place, read by whoever runs this stage — a
track's subagent or this command:
`${CLAUDE_PLUGIN_ROOT}/skills/track/references/stage-verify.md`. Read it in
full and follow it.

**Running this stage on its own writes nothing to any track's `state.md`.**
There is no track underneath this command — the reference file's closing
step, which writes a note into a track's state, does not apply here. If a
track already exists for this work, use `/cai:track` instead so the record
stays with it.
