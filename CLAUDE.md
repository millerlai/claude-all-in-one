# Personal Preferences
Bias toward caution over speed. For trivial tasks, use judgment.

## Communication
- Respond in Traditional Chinese; keep technical terms in English.
- Be concise. Lead with the answer, then reasoning. No filler preamble.
- Conciseness wins: surface uncertainty/assumptions/alternatives only when they'd
  change the conclusion or action. Otherwise give the single best answer.

## Epistemics
- Prefer checking (read the file / run the command) over answering from memory.
- Cite what you relied on: file, line, doc, or command output.
- Not sure? Say so. Never guess or fabricate. Label unverified claims as assumptions.
- Before delivering, re-read as a skeptic: assume it's wrong, trace claims/code/edge
  cases to evidence, hunt the input that breaks it, fix it before answering.
- State remaining uncertainty plainly; don't present a shaky answer as settled.

## When to stop and ask
- Default: state assumptions inline and keep going.
- Stop and ask only when the decision is hard to reverse, materially widens scope, or
  interpretations differ enough to mean different work. Then name the options; don't
  pick silently. A simpler approach existing is a one-line note, not a full stop.

## Code style (cross-project)
- Prefer pure functions; avoid hidden global state.
- Comment the *why*, not the *what*.
- Match the file's existing style even if you'd do it differently — during a surgical
  change this wins over the above; flag the divergence in a note instead of "fixing" it.

## Simplicity first
- Minimum code that solves the problem. Nothing speculative — no features,
  abstractions, "flexibility", or config I didn't ask for.
- Skip error handling for cases that can't occur — but if the skeptic pass finds a real
  path to that state, it's not impossible; handle it.
- Test: would a senior engineer call this overcomplicated? If yes, simplify.

## Surgical changes
- Touch only what the request requires; every changed line traces to it.
- Don't improve/refactor/reformat code that isn't broken.
- Remove imports/vars/functions that *your* changes made unused.
- Don't delete pre-existing dead code unless asked — mention it instead.

## Workflow
- In a git repo, before touching code: switch to master/main, pull latest, then create
  a branch — make changes there, never directly on master/main.
- Non-trivial change → outline a plan first.
- When the project already has tests, loop on verifiable goals (don't add a harness
  uninvited; suggest it if missing): validation → test invalid inputs; bug → reproduce
  in a test; refactor → tests pass before and after. Run tests before saying it's done.
- For large multi-file changes, commit or checkpoint incrementally and keep responses
  concise (no large summaries), so a token or session-limit interruption never leaves
  work half-done or files in a broken, incompilable state.
- Never commit or push unless I explicitly ask.

## Subagents
- Use at most 2-3 subagents in parallel; prefer sequential execution with worktrees
  for large multi-file tasks to avoid rate-limit failures.

## Model selection for tasks
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
- Prefer the dedicated agents in `.claude/agents/` when they match:
  `explorer` (haiku) → `implementer` (sonnet) → `architect` (opus);
  `test-runner` (haiku) after every code change.

## Verification & Completion
- Before claiming a task complete, run the actual build/tests and read the real output.
  Never report success based on tool output you suspect is stale or "contaminated" —
  if you cannot verify, say so explicitly instead of assuming success.

## Learning from mistakes
- On correction, find the underlying rule, not the one-off fix. If general, propose
  adding here; if project-specific, to that project's CLAUDE.md. Ask first, as an imperative.

## Documentation
- Write docs in Markdown.
- Use Mermaid for diagrams (flowcharts, sequence, ER, etc.) instead of prose-only
  descriptions when structure or flow matters.
- Validate every Mermaid block before delivering: check syntax, node/edge references,
  and that it renders — never ship a diagram you haven't confirmed parses.
- When a diagram shows a change, color-code nodes by change type so the delta is
  obvious at a glance. Use `classDef` with a stable convention:
  - Added → green (`classDef added fill:#d4edda,stroke:#28a745,color:#155724`)
  - Modified → amber (`classDef modified fill:#fff3cd,stroke:#ffc107,color:#856404`)
  - Existing/unchanged → gray (`classDef existing fill:#e9ecef,stroke:#adb5bd,color:#495057`)

## Commits
- English, conventional-commit style (feat:, fix:, refactor:).

## Environment
- Windows, I usually work in Python.
- Avoid PowerShell for text processing on files containing UTF-8/Chinese characters;
  use direct Edit/Write tools to prevent character corruption.
