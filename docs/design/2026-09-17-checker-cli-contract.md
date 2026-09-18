# checker CLI contract — what the four probe scripts actually share

Maintainer reference, Ours side (`CLAUDE.md:28-32`): no shipped component reads
this file, so it stays out of `plugins/cai/`. Its job is to stop the next
change to any of the four scripts from silently breaking one of the others
without a shared contract written down anywhere. It is prose, not a probe —
nothing runs it, and it goes stale exactly as fast as the four scripts drift
from it; a change to any of D1-D5 below should update this file in the same
commit, and a reviewer who finds it out of date should treat the code as the
truth.

The four scripts: `plugins/cai/scripts/options_lint.py`,
`plugins/cai/scripts/design_probe.py`, `plugins/cai/scripts/preflight.py`,
`plugins/cai/scripts/provenance.py`.

## What they actually share

Only two things, verified against today's code
(`.claude/track/output-schema-validator/discover.md:25-36`):

1. **stdout, one line per probe**: `"PASS " + label` or `"FAIL " + label`.
2. **exit code**: `0` when every probe passed, `2` when at least one failed.

Nothing else is common — usage errors, encoding, and what happens on an
absent input all diverge. A caller that assumes more than these two things
will break on at least one of the four scripts.

## D1 — usage error exit code collides with "a probe failed"

`options_lint.py` and `design_probe.py` have no `ArgParser` subclass, so
argparse's own `error()` exits `2` — the same code a real FAIL produces
(`plugins/cai/scripts/options_lint.py:189`,
`plugins/cai/scripts/design_probe.py:597-599` use the stock
`argparse.ArgumentParser`). `preflight.py` and `provenance.py` both carry an
`ArgParser` subclass that routes a usage mistake to exit `1` instead
(`plugins/cai/scripts/preflight.py:492-498`,
`plugins/cai/scripts/provenance.py:299-306`).

**Consequence**: a caller that shells out to `options_lint.py` or
`design_probe.py` and treats `exit 2` as "there is a FAIL to show the user"
will show a wrong-flag typo as if it were a real finding. `preflight.py`'s own
`build()` sidesteps this for `options_lint.py` entirely by calling
`probes(text)` in-process rather than through the CLI — see
`docs/design/2026-09-17-output-schema-validator-detail.md`'s `Implementation
spec` section — so this divergence never reaches that caller.

## D2 — stdout encoding is not uniformly forced

`options_lint.py:186-187`, `preflight.py:506-507`, and `provenance.py:314-315`
all call `sys.stdout.reconfigure(encoding="utf-8")` before printing.
`design_probe.py:589` calls `sys.stdout.reconfigure(errors="replace")` only —
no `encoding=` — so it inherits whatever the console's own encoding is.

**Consequence**: `preflight.py:126-134`'s existing subprocess call to
`design_probe.py` passes `text=True` without `encoding=`, so both sides
happen to agree on the console locale today; changing either side's encoding
handling independently would break that agreement. This is why stance's `##
Out of scope` keeps `preflight.py:126-134` untouched this round.

## D3 — the summary line's shape is not fixed

`provenance.py:358` can append `" -- hint; <hint>"` to its summary line when
it has something actionable to say; the other three always print the plain
`"-- <kind>: %d probe(s) failed"` shape
(`options_lint.py:204`, `design_probe.py:617`, `preflight.py:531`). A parser
that expects the summary line to always match one fixed pattern will not
match `provenance.py`'s hinted form.

## D4 — a label can carry embedded newlines

`preflight.py`'s own `ledger_attempts` probe (`plugins/cai/scripts/preflight.py:165-176`)
puts a person's ledger note — which can itself contain `\n` — inside a
single probe's label. A line-oriented parser that assumes "one line, one
probe" will silently drop the continuation lines of that label. No other
probe in any of the four scripts does this today, but a caller aggregating
output from more than one script has to allow for it.

## D5 — "the input isn't there" means opposite things

`options_lint.py:196-198` and `design_probe.py:601-602` both treat a missing
document as a FAIL, exit `2`. `provenance.py:322-334` treats a missing ledger
(or an empty one) as "the feature is not in use" — zero output, exit `0`.
`preflight.py`'s own per-stage probes side with `provenance.py`'s convention
wherever an absent artifact is a legitimate state rather than an error (for
example `options_drafts()`'s silent-pass shape, described in the same detail
document referenced above, when the design artifact is not a decisions
document or `## Tier 1` is empty).

**Consequence**: a caller cannot infer which convention a given script uses
from the other three; it has to know, per script, which one applies.

## Scenario → checker

Which checker actually runs for a given situation, and where that call
lives — not a description of what could run it, a citation to what does.

| Scenario | Which one runs | Called by, at file:line |
|---|---|---|
| Can a track stage start? | `preflight.py`'s own per-stage probes | `plugins/cai/scripts/preflight.py:488-489` (`STAGES`), e.g. `:343` for `build()` |
| Does a stance/decisions/hld/detail/delta/diagnosis document meet its own shape rules? | `design_probe.py` | `plugins/cai/scripts/preflight.py:126-134` (design gate, subprocess); also invoked directly from the author's own prose instructions, e.g. `plugins/cai/skills/track/references/stage-design.md:306` |
| Does a six-field option draft meet the shape `option-explainer.md` asks for? | `options_lint.py` | `plugins/cai/scripts/preflight.py`'s `options_drafts()`, called in-process from `build()` (the three returns at `:377`, `:395`, `:397` in the detail design above); also invoked directly from `plugins/cai/skills/track/references/pending-questions.md`'s Step 0 and `plugins/cai/skills/track/references/stage-design.md:373` (legacy High-level mode) |
| Do the citations a rule-provenance ledger claims still resolve? | `provenance.py` | `plugins/cai/skills/track/references/stage-verify.md:38` (verify stage, unconditional, once) |

## Path convention this contract assumes

`options_drafts()` (see the detail design above) looks for one draft file per
`## Tier 1` entry in a decisions document, at
`<track-dir>/options-<id>.md`, where `<id>` is that entry's `### ` heading's
first whitespace-separated token with only `[A-Za-z0-9_.-]` kept (falling
back to the entry's 1-based position if that empties it out). Both
`pending-questions.md` and `stage-design.md`'s legacy High-level mode name
this same path so a person writing a draft and a script looking for one agree
on where it lives.
