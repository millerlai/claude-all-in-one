# feedback-loops — ten ways to build a command that goes red on this bug

Referenced from `debug/SKILL.md`'s Step 1: this is what to reach for when
"gather more data" isn't enough by itself, and no command yet exists that
you have run and watched fail on the exact symptom.

Spend disproportionate effort here. A tight command that goes red on this
bug and nowhere else settles more of the debugging than any amount of
reading the code first — bisection, hypothesis-testing, and instrumentation
in Steps 2–4 all just consume the loop this step builds.

## Ten ways, roughly in this order

1. **A failing test** at whatever seam reaches the bug — unit, integration,
   end-to-end.
2. **A curl or HTTP script** against a running dev server.
3. **A CLI invocation** against a fixture input, diffing its output against
   a known-good snapshot.
4. **A headless browser script** that drives the UI and asserts on the DOM,
   the console, or the network.
5. **A captured trace, replayed.** Save the real request, payload, or event
   log to disk and replay it through the code path in isolation. Redact it
   per `debug/SKILL.md`'s redact rule before it touches disk — a captured
   trace routinely carries a live credential or session token, and this file
   is a fresh place to hold one down.
6. **A throwaway harness** — a minimal subset of the system (one service,
   mocked dependencies) that exercises the bug's code path with a single
   call.
7. **A property or fuzz loop.** For "sometimes wrong output", run hundreds
   of random inputs and look for the failure mode.
8. **A bisection harness.** If the bug appeared between two known states
   (commit, dataset, version), automate "check out state X, check, repeat"
   so it can run unattended across the range.
9. **A differential loop.** Run the same input through the old and new
   version (or two configs) and diff the outputs.
10. **A human-in-the-loop script**, last resort. If a person has to click
    something, drive them through a script that prompts for the one
    observation needed and records it, so the loop stays structured even
    with a human step in it.

## Tighten it once it exists

A loop that only sometimes goes red on the real bug is barely a loop:

- Faster — cache setup, skip unrelated initialisation, narrow the scope to
  just the failing path.
- Sharper — assert on the specific symptom, not "didn't crash".
- More deterministic — pin the clock, seed the RNG, isolate the filesystem,
  freeze the network.

For a bug that doesn't reproduce every time, the goal is a higher
reproduction rate, not a clean one-shot repro: loop the trigger many times,
add stress, narrow timing windows. A rate too low to debug against needs
raising before Step 1's completion criterion can be met at all.

## When no loop can be built

Say so explicitly, list what was tried, and stop at reproduction per Step
1's completion criterion — do not carry a hypothesis forward from a bug you
cannot reliably trigger.
