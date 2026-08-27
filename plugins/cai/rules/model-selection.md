# Subagents
- Use at most 2-3 subagents in parallel; prefer sequential execution with worktrees
  for large multi-file tasks to avoid rate-limit failures.

# Model selection for tasks
- Before delegating via the Task tool or a subagent, judge task complexity FIRST and
  pick the cheapest tier that can do it reliably. Never default to the strongest.
- Tiers are named for the kind of work, not for a model. Which model each one
  resolves to lives in `plugins/cai/models.json` and is applied to every component
  by `scripts/gen-models.py`, so re-tiering is a one-line edit there — never a
  hand-edit of a component's frontmatter.
  - **chore** — needs no judgement on any given run: file search, grep/glob
    exploration, renaming, formatting, simple summarization, boilerplate, running
    a known command and reporting what it printed.
  - **build** — engineering judgement inside a fixed contract: well-specified
    features, tests, routine refactors, small-diff review, documentation.
  - **think** — design trade-offs and repair, only when genuinely required:
    cross-cutting architecture, subtle concurrency/correctness bugs, ambiguous
    requirements.
- The test is **"does this step still need judgement on every run?"** — not how
  often the task comes up. Frequency decides the total volume; judgement risk
  decides the tier.
- State in one line which tier you chose and why, before each delegation.
- Unsure between two tiers → start cheaper; escalate only on evidence (failed
  attempt, discovered ambiguity), never because it "might" be hard.
- Prefer the cai plugin agents when they match. Each one already carries its own
  tier, so name the agent and let its frontmatter decide the model — do not
  restate the model in prose. Typical flow:
  `explorer` (locate relevant code)
  → `architect` (ONLY when an architecture/concurrency/ambiguity decision
    is needed; read-only, hands a spec to implementer)
  → `implementer` (build to spec)
  → `test-runner` (after every code change).
  Skip `architect` for well-specified work — it is an escalation, not a default step.
