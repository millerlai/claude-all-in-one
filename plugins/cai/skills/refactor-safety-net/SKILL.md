---
name: refactor-safety-net
description: Build characterisation tests around untested legacy code so it can be refactored safely - pin the current behaviour, including behaviour that looks wrong. Use when code needs refactoring but has no test coverage, or when refactor-scan or refactor-apply reports a missing safety net.
argument-hint: "<path or class to pin>"
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
disable-model-invocation: true
---

# Build a safety net

Refactoring without tests is editing and hoping. This skill writes
**characterisation tests**: tests that document what the code *currently does*,
not what it *should* do.

Target: `$ARGUMENTS`

This is what `refactor-scan` means when it flags a finding under "Untestable
areas," and what `refactor-plan` means by "Blocked — run `refactor-safety-net`
first." Once this skill reports a green baseline, planning can order steps
against it.

**Write scope is a prose constraint, not a mechanical one.** This skill
legitimately writes both tests and the seam-creating refactorings that make
them possible, so the tool level cannot narrow `Write`/`Edit` to "tests and
seams only" the way a diagnose-only skill narrows it to nothing. Start on a
clean working tree and commit after every seam-creating step — the same
checkpoint discipline as `plugins/cai/rules/workflow.md` — so a write that
strayed past a seam is visible in the diff and trivial to revert. Do not run
this alongside `refactor-apply` or `refactor-auto` on the same target: those
also write, and two writers on one target race.

## The key distinction

| | Unit test | Characterisation test |
|---|---|---|
| Asserts | intended behaviour | actual current behaviour |
| A surprising result means | a bug to fix | a fact to record |
| Written | before or with the code | before refactoring legacy code |

**If the code does something wrong, pin the wrong behaviour.** Add a comment
saying you believe it is wrong. Fixing it is a separate task under the other
hat (see `refactoring`'s two hats) — mixing the fix into the safety net
destroys the net's entire purpose.

## Steps

**1. Find the seams.** Identify what makes the code hard to test: filesystem,
network, clock, randomness, global state, database, direct construction of
collaborators.

**2. Break the minimum dependencies.** Use the *least invasive* seam:

| Blocker | Seam, cheapest first |
|---|---|
| Clock | inject a time function; or freeze via the test library |
| Randomness | seed it, or inject the generator |
| Network / DB | **Extract Interface** on the client, pass a fake in tests |
| Filesystem | temp dir fixture; or inject a path |
| Direct construction | **Replace Constructor with Factory Method**, override in test |
| Global state | save/restore in a fixture (last resort) |

**Extract Interface** and **Replace Constructor with Factory Method** are
themselves refactorings — do them in their own commits, one at a time, before
the tests exist, accepting that this window is the risky part. Keep the steps
tiny.

**3. Probe the actual behaviour.** For each entry point, call it with
representative inputs and **record what comes back**. Do not predict the
output from reading the code — run it. Reading the code is how you get the
same wrong model that produced the bug.

**4. Write the tests.** Cover, in this order:
- the happy path with typical inputs
- every branch you can reach (use coverage output to find the ones you missed)
- boundaries: empty, zero, negative, null, max, single element
- the error paths — pin the exact exception type and message if callers depend
  on them

**5. Verify the net actually catches things.** Mutate the source deliberately
— flip a comparison, change a constant, delete a line — and confirm a test
fails, then revert the mutation. Do this for **at least three separate
mutations**. A green suite that catches nothing is worse than no suite,
because it grants false confidence, and this loop is the only evidence that
the net is not that.

**6. Measure and report.** Line and branch coverage of the target, before and
after. State plainly what is still unpinned.

## Output

```markdown
# Safety net — src/billing/gateway.py

**Seams introduced**
- Extract Interface `PaymentClient` from `StripeClient` (commit 4a1b2c3)
- Injected clock into `Gateway.__init__`, defaulting to `time.time` (commit 5b2c3d4)

**Tests added** `tests/test_gateway_characterisation.py` — 23 tests
Coverage of target: 12% → 84% lines, 71% branches

**Pinned behaviour that looks wrong** (do not fix here)
- `charge()` returns `None` on a network timeout instead of raising. Two callers
  treat `None` as success. Pinned as-is in `test_charge_timeout_returns_none`.
- Amounts are rounded with banking rounding in one path and half-up in another.
  Both pinned. Likely a real bug — file it.

**Still unpinned**
- The retry path (`_retry_with_backoff`) needs a controllable sleep. Do not
  refactor that method yet.

**Mutation check** 3 of 3 deliberate mutations caught: comparison flip in
`_validate_amount` (red → reverted), constant change in `_MAX_RETRIES` (red →
reverted), deleted early-return in `charge` (red → reverted).

Ready to refactor: `Gateway.charge`, `Gateway.refund`, `Gateway._format_request`.
Not ready: `Gateway._retry_with_backoff`.
```

## Rules

- Never "fix" surprising behaviour. Pin it, comment it, report it.
- Name the tests after the observed behaviour
  (`test_returns_none_when_timeout`), not after intent (`test_handles_errors`).
- If a seam cannot be created without changing behaviour, stop and say so —
  do not force it. Some code needs a different approach instead: an
  integration test at a higher level, or approval testing on serialised
  output.
- Report the mutation count and outcome every time. A report without it is not
  evidence the net works, whatever else it says.
- Once a target is pinned and green, hand it back — this skill only builds
  the net.
