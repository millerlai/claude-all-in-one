# Subagents
- Use at most 2-3 subagents in parallel; prefer sequential execution with worktrees
  for large multi-file tasks to avoid rate-limit failures.

# Layers, cheapest first
- Make the free layer bigger before routing what's left by judgement risk. Moving a
  judgement call down a paid tier to save money, before asking whether it needed a
  model at all, is the mistake to avoid.
  - **program** — a deterministic check settles it: does the file/heading/path exist,
    does the test command exit 0, is the branch protected. No judgement, no model.
    `plugins/cai/scripts/design_probe.py`, `preflight.py`, `track_state.py`, and
    `scripts/validate.py` are this layer — each answers in milliseconds a question
    that would otherwise cost a model turn. `preflight.py` runs before every stage
    precisely so a stage that can't start doesn't cost anything to refuse.
  - **chore** — needs no judgement on any given run: file search, grep/glob
    exploration, renaming, formatting, simple summarization, boilerplate, running
    a known command and reporting what it printed.
  - **build** — engineering judgement inside a fixed contract: well-specified
    features, tests, routine refactors, small-diff review, documentation.
  - **think** — design trade-offs and repair, only when genuinely required:
    cross-cutting architecture, subtle concurrency/correctness bugs, ambiguous
    requirements.

# Model selection for tasks
- Before delegating via the Task tool or a subagent, check whether a program layer
  check already answers it. If not, judge task complexity and pick the cheapest
  tier that can do it reliably. Never default to the strongest.
- Tiers are named for the kind of work, not for a model. Which model each one
  resolves to lives in `plugins/cai/models.json` and is applied to every component
  by `plugins/cai/scripts/gen-models.py`, so re-tiering is one line there — never a
  hand-edit of a component's frontmatter.
- The test is **"does this step still need judgement on every run?"** — not how
  often the task comes up. Frequency decides the total volume; judgement risk
  decides the tier.
- State in one line which tier you chose and why, before each delegation.
- Unsure between two tiers → start cheaper; escalate only on evidence (failed
  attempt, discovered ambiguity), never because it "might" be hard.
- Prefer the cai plugin agents when they match. Each one already carries its own
  tier, so name the agent and let its frontmatter decide the model — do not
  restate the model in prose. The track skill's stages dispatch to
  `architect` (intake, discover) → `implementer` (build) → `verifier`
  (verify) → `shipper` (ship); `design` runs in-session, because it has to
  reach `AskUserQuestion` and no subagent has that tool. `explorer`,
  `test-runner`, `reviewer`, and `designer` are called in as needed.
