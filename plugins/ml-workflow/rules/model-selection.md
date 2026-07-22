# Subagents
- Use at most 2-3 subagents in parallel; prefer sequential execution with worktrees
  for large multi-file tasks to avoid rate-limit failures.

# Model selection for tasks
- Before delegating via the Task tool or a subagent, judge task complexity FIRST and
  pick the cheapest model that can do it reliably. Never default to the strongest.
  - haiku — mechanical/low-reasoning: file search, grep/glob exploration, renaming,
    formatting, simple summarization, boilerplate, running tests and reporting.
  - sonnet — standard engineering: well-specified features, tests, routine refactors,
    small-diff review, documentation.
  - opus (or strongest available) — only when genuinely required: cross-cutting
    architecture, subtle concurrency/correctness bugs, ambiguous requirements.
- State in one line which model you chose and why, before each delegation.
- Unsure between two tiers → start cheaper; escalate only on evidence (failed
  attempt, discovered ambiguity), never because it "might" be hard.
- Prefer the ml-workflow plugin agents when they match. Typical flow:
  `explorer` (haiku, locate relevant code)
  → `architect` (opus, ONLY when an architecture/concurrency/ambiguity decision
    is needed; read-only, hands a spec to implementer)
  → `implementer` (sonnet, build to spec)
  → `test-runner` (haiku, after every code change).
  Skip `architect` for well-specified work — it is an escalation, not a default step.
