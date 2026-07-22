# Auto memory discipline
- Record only stable facts: build/test commands, conventions, architectural
  decisions, environment quirks, user preferences.
- Do NOT record implementation details that evolve with the code (function
  signatures, file line numbers, current bug states, in-progress work) — they
  go stale and mislead future sessions. Prefer re-checking the code over
  trusting a memory note.
- Date-stamp every note (YYYY-MM-DD). When reading a note whose subject may
  have changed since its date, verify against the current code before relying
  on it.
- When a note is found to be stale or wrong, delete or correct it immediately.
