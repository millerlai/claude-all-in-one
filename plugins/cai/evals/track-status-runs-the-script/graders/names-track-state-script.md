---
type: regex
pattern: track_state.py
match: contains
weight: 1
---

Regresses `skills/track/SKILL.md:21`–`:25` ("never come from reading files
and reasoning about them" — status must come from running the script) and
`:27`–`:29` (what an exit 2 from it means). A PASS names the script the
plugin says to run; a FAIL means the model reconstructed the answer by
reading and reasoning about track files instead, or named something else.
