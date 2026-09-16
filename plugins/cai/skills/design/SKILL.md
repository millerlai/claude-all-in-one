---
name: design
description: "Write a design document for review — diagnosis (something is broken: the root cause and the fix, one page), stance (the trade this system makes, one page, read in full), decisions (the choices that trade implies, routed so only what needs a person reaches one), detail (turns an approved entrance into something that can be built from), or delta (recovers the decisions from a branch already built). Usage: /cai:design <what to design, or the mode: diagnosis|stance|decisions|detail|delta>"
argument-hint: "<what to design — or which mode, if not obvious>"
disable-model-invocation: true
---

Run the design stage for: $ARGUMENTS

The procedure lives in one place, read by whoever runs this stage — a
track's subagent or this command:
`${CLAUDE_PLUGIN_ROOT}/skills/track/references/stage-design.md`. Read it in
full, pick the mode it describes (diagnosis / stance / decisions / detail /
delta), and follow it. `high-level` is the legacy single-document shape, kept
so designs already signed off stay passable — do not start a new one there.

**Diagnosis and stance are the two entrances**, and one test picks between
them rather than the wording of the request: can you write a test that fails
now and would pass if an existing promise held? Yes means broken (diagnosis);
no, because nothing ever promised it, means it was never there (stance). The
reference file states it in full.

**Running this stage on its own writes nothing to any track's `state.md`.**
There is no track underneath this command — the reference file's closing
step, which writes a note into a track's state, does not apply here. If a
track already exists for this work, use `/cai:track` instead so the record
stays with it.
