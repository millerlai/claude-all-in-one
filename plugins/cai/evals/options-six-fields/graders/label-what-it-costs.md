---
type: regex
pattern: "What it costs"
match: contains
weight: 1
---

Regresses `skills/options/references/template.md:28`–`:35`: the fourth of the
six field labels the `options` skill's output skeleton requires, spelled and
capitalised exactly as the skill writes it. A PASS shows the label made it
into the response; a FAIL means either the skill did not expand or the model
did not follow its skeleton for this field.
