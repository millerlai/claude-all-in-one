---
name: usage
description: Show token usage and equivalent API spend for one track or across projects. Usage: /cai:usage [track|7|30|60]
model: haiku
disable-model-invocation: true
---

Run `${CLAUDE_PLUGIN_ROOT}/scripts/usage_report.py`, one call, and relay its
output verbatim. Do not add up, re-derive, or restate any number yourself --
every total, every per-model breakdown, and every "unpriced" figure comes only
from what the script prints.

- One track's own usage: `track --track-dir <the track's directory>`.
- Cross-project usage over the last N days: `range --days <N>`, where N is
  whatever number of days the user said. If they did not say a number, ask
  instead of guessing one.
- If the command exits non-zero, relay stderr verbatim and stop -- do not
  explain or guess at the cause.

Two things the report says but a reader can miss:
- Every dollar figure is *equivalent API spend* -- what the same usage would
  cost on pay-per-token pricing. It is not what was actually billed; the
  reader is on a subscription.
- The report only covers usage from the day central tracking was first turned
  on. Anything before that date shows as "no data", not as zero -- it was
  never recorded, not free.
