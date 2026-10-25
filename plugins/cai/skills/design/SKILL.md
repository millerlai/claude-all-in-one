---
name: design
description: "Turn a request into agreed acceptance criteria and a design document for review — diagnosis (something is broken: the root cause and the fix, one page), stance (the trade this system makes, one page, read in full), decisions (the choices that trade implies, routed so only what needs a person reaches one), detail (turns an approved entrance into something that can be built from), or delta (recovers the decisions from a branch already built). Usage: /cai:design <what to design, or the mode: diagnosis|stance|decisions|detail|delta>"
argument-hint: "<what to design — or which mode, if not obvious>"
disable-model-invocation: true
---

Run the design stage for: $ARGUMENTS

The procedure lives in one place, read by whoever runs this stage — a track's subagent or this
command: `${CLAUDE_PLUGIN_ROOT}/skills/track/references/stage-design.md`. First, if
`<top>/.cai/codemap/state.json` exists, follow
`${CLAUDE_PLUGIN_ROOT}/skills/track/references/codemap-brief.md` yourself; you run this stage, so
the line it yields is yours to act on. Read the stage reference in full and follow it from its
first step: explore the context, route the request, interview, propose approaches and agree the
acceptance criteria (Steps 1–5), then pick the mode it describes
(diagnosis / stance / decisions / detail / delta). `high-level` is the legacy
single-document shape, kept so designs already signed off stay passable — do not start a new one there.

**Diagnosis and stance are the two entrances**, and the route test in Step 2 picks between
them rather than the wording of the request. The reference file states it in full.

**Running this stage on its own writes nothing to any track's `state.md`.**
There is no track underneath this command — the reference file's closing
step, which writes a note into a track's state, does not apply here. If a
track already exists for this work, use `/cai:track` instead so the record
stays with it.
