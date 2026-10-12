---
type: regex
pattern: "Changes requested"
match: contains
weight: 1
---

Regresses `skills/track/references/approval-gates.md:68`–`:73` (Gate 1's
four-row menu) and `:13`–`:23` (why the answer must be a menu, not prose):
the third of the four menu options the design sign-off offers, spelled
exactly as the plugin writes it. This case can PASS whether the model
describes an actual menu or only lists the four options as prose — it
measures wording, not behaviour, because `AskUserQuestion` is not among this
run's allowed tools.
