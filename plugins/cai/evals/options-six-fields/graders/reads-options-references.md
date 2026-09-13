---
type: tool_used
tool: Read
input_match: skills[\/]+options[\/]+references
min: 1
weight: 1
---

Regresses `skills/options/SKILL.md:21`–`:29` (the "Which reference to read"
table plus "Read the one you need, not all three."): the six field labels can
be produced from memory, so the label graders alone cannot tell whether the
model actually opened one of the skill's reference files or reconstructed the
skeleton without reading it. A PASS is tool-call-level evidence that a
reference file under `skills/options/references/` was read at least once; a
FAIL means the labels above, if present, came from the model's memory of the
skeleton rather than from consulting the skill's own reference.
