# address-rate — hand-transcribed verify-row disposition, per done track

One row per `done` track that carries a verify row (AC8). `source` is
`<track>/state.md:<line>`; `.claude/track/` is ignored (`.gitignore:11`), so
that citation cannot be dereferenced from a fresh clone -- a limitation, not
a bug, and it belongs in the measurement doc too.

Five processed columns per track: `raised` (total findings the verify row
names), `fixed` (really changed code or added a test), `left_minor` (Minor,
recorded and left per `finding-severity.md:24`), `triaged` (downgraded,
rejected, or parked for a later round -- neither `fixed` nor `left_minor`).
The identity `fixed + left_minor + triaged == raised` holds on every row
below except `pb06-ledger-metrics`, whose `raised`/`left_minor` are marked
`UNVERIFIED` rather than a number (F10) -- the recompute check accepts that
row as it stands rather than inventing a count for it, and excludes it from
the eleven-row totals below.

| track | raised | fixed | left_minor | triaged | source |
|---|---|---|---|---|---|
| track-status-vocabulary | 5 | 1 | 3 | 1 | track-status-vocabulary/state.md:12 |
| pb02-plugin-evals | 5 | 1 | 3 | 1 | pb02-plugin-evals/state.md:9 |
| track-context-budget | 5 | 1 | 2 | 2 | track-context-budget/state.md:12 |
| pb02-evals-ci | 6 | 1 | 5 | 0 | pb02-evals-ci/state.md:9 |
| issue78-rule-guards | 8 | 2 | 6 | 0 | issue78-rule-guards/state.md:9 |
| pr60-followups | 4 | 2 | 2 | 0 | pr60-followups/state.md:12 |
| ticket-integration | 9 | 5 | 4 | 0 | ticket-integration/state.md:12 |
| guardrail-hardening | 6 | 2 | 4 | 0 | guardrail-hardening/state.md:9 |
| option-explainer-with-eli5 | 4 | 4 | 0 | 0 | option-explainer-with-eli5/state.md:12 |
| gap02-usage-ledger | 6 | 6 | 0 | 0 | gap02-usage-ledger/state.md:12 |
| pb04-security-lens | 3 | 0 | 2 | 1 | pb04-security-lens/state.md:9 |
| pb06-ledger-metrics | UNVERIFIED | 3 | UNVERIFIED | 0 | PR #93 description (pr-93-body.md:21 gives three Major fixed and a security lens with no findings; pr-93-body.md:27 lists Minor items in a bracketed clause readable as either 4 or 9, so `raised` and `left_minor` stay UNVERIFIED rather than guessed) |

**Eleven-row totals (recomputed by pytest, `pb06-ledger-metrics` excluded
per F10):** `raised` 61, `fixed` 25, `left_minor` 31, `triaged` 5. Identity:
25 + 31 + 5 = 61. Fix rate (`fixed / raised`) = 25 / 61 = 0.409836...
Response rate (`(fixed + triaged) / raised`) = 30 / 61 = 0.491803...
