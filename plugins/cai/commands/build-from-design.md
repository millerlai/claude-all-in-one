---
description: "Build an approved detail design unit by unit — its work breakdown is the schedule, one Sonnet implementer per unit briefed from the document's own spec sections, Haiku for the verification, each unit green and committed before the next starts. Usage: /cai:build-from-design <detail design doc> [target project dir]"
argument-hint: "<detail design doc> [target project dir]"
model: sonnet
effort: medium
---

Build this detail design: $ARGUMENTS

Invoke the `build-from-design` skill and follow it end to end — the gate, the
state table, one unit at a time, and the close-out. Do not skip to implementing
because the document looks clear; its Step 0 exists because a design that reads
well and has no verification gate produces units nobody can call done.

Name the target project directory: the one given above, or the repo you are in.
Say which you used.

This command is pinned to Sonnet on purpose. The orchestration — reading the
document, cutting the schedule, writing each unit's brief, ranking findings — is
the main tier. The skill carries the same pair, so the tier holds whether this
was invoked as a command or the skill was reached by name mid-conversation. The
two delegations below it stay as the skill defines them: `implementer` on Sonnet
for the code, `explorer` and `test-runner` on Haiku for locating and running.

`effort: medium` for the same reason it is not higher: this runs one round per
unit, so the setting is paid once per unit rather than once per invocation, and
the judgement each round actually needs is bounded — the document already made
the design decisions, and anything it left open goes to the user rather than
being reasoned about here.

If the work turns out to need an architecture decision the document never made,
stop and ask with `AskUserQuestion` rather than deciding. That is not this
lane's call to make, in either direction — writing in a preference the user
never gave and leaving something out because they never asked for it are the
same silent decision with opposite signs.
