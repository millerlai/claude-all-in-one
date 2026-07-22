# Code style (cross-project)
- Prefer pure functions; avoid hidden global state.
- Comment the *why*, not the *what*.
- Match the file's existing style even if you'd do it differently — during a surgical
  change this wins over the above; flag the divergence in a note instead of "fixing" it.

# Simplicity first
- Minimum code that solves the problem. Nothing speculative — no features,
  abstractions, "flexibility", or config I didn't ask for.
- Skip error handling for cases that can't occur — but if the skeptic pass finds a real
  path to that state, it's not impossible; handle it.
- Test: would a senior engineer call this overcomplicated? If yes, simplify.

# Surgical changes
- Touch only what the request requires; every changed line traces to it.
- Don't improve/refactor/reformat code that isn't broken.
- Remove imports/vars/functions that *your* changes made unused.
- Don't delete pre-existing dead code unless asked — mention it instead.
