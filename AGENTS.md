# Working on this repo (Codex)

Codex reads this file automatically. It has no documented equivalent of
`CLAUDE.md`'s `@`-imports, so the rules are restated here rather than linked.

This file is **authored, not generated**. `plugins/cai/rules/*.md` stays the
source of truth for what the plugin ships to Claude Code users; this file
adapts those rules to a runtime with no per-agent model tiers and no
question tool, driven by a model that follows prompt contracts closely and is
already biased toward compression. A verbatim copy would work against that.
"Where these rules come from" maps each section back to its source — when a
rule changes there, change it here too.

## Completion bar

Done means verified, not "should work".

After changing anything under `plugins/cai/` or `.claude-plugin/`, run both:

- `python scripts/validate.py` — manifests, every component's frontmatter, and
  that the bash guard still blocks what it should
- `python -m pytest` — the tests under `tests/`, which exercise what the
  scripts in `plugins/cai/scripts/` actually do

For a narrower change, run the targeted test for the changed behaviour. If
validation cannot be run at all, say so and name the next best check. Never
report success from output you suspect is stale.

Working is only half the gate; matching what was asked is the other half.
Restate the request, spec, or plan as a checklist and point each item at the
code that satisfies it (`file:line`). Report anything unimplemented, partial,
or built differently rather than declaring it done.

## Evidence and uncertainty

- Read the file or run the command rather than answering from memory.
- Cite what you relied on: file, line, or command output.
- NEVER describe code you have not opened as if you had read it. If a file,
  symbol, or output is not available to you, say that it is not, and say what
  you would need to answer.
- Label unverified claims as assumptions. State remaining uncertainty plainly
  instead of presenting a shaky answer as settled.
- Before delivering, re-read as a skeptic: assume it is wrong, trace each
  claim to evidence, hunt the input that breaks it, and fix that first.

## Autonomy and approval

This is the only section that governs when to ask. Do not add permission
checks elsewhere — repeated "ask first" instructions produce permission
prompts for work that was already authorized.

Proceed without asking:

- reading files, searching, inspecting git history, and running the test suite
  or any other non-destructive command
- in-scope edits, when the request asks you to change, build, or fix something

Inspect and report, but do not implement, when the request is to answer,
explain, review, diagnose, or plan. Those authorize a written result only.

Ask, and wait for an answer:

- anything hard to reverse — `git push`, force-push, opening a PR, deleting or
  overwriting a file, or changing the environment (`pip install`, `npm i -g`)
- a change that materially widens the scope you were given
- a request where two readings lead to genuinely different work; name the
  options rather than picking silently

Never commit or push unless asked. Never skip hooks or bypass signing.

For a non-trivial change, write the plan first — which files, and what changes
in each — and get agreement before editing. That is one gate up front, not a
confirmation before every step. Once the plan is agreed, run it in
checkpointed units: an interruption must not leave the tree uncompilable or
the work half-done.

Everything not blocked by an answer keeps going. Ask at the point the answer
changes what you do next, not at the top of the turn.

## Scope of a change

- Touch only what the request requires; every changed line traces back to it.
- Do not refactor, reformat, or improve code that is not broken, and do not
  fold an unrelated cleanup into the change.
- Remove the imports, variables, and functions that *your* change made unused.
  Mention pre-existing dead code; do not delete it unasked.
- Match the file's existing style, naming, and library versions even where you
  would do it differently. Flag the divergence in a note instead of fixing it.
- When the ask is "like X", read X's source before writing. A description or a
  screenshot reproduces the look, not the semantics.
- Prefer pure functions; avoid hidden global state. Comment the why, not the
  what.
- Write the minimum code that solves the problem. No speculative features,
  abstractions, or configuration that was not asked for.
- New behaviour ships with a test. Where tests already exist, loop on a
  verifiable goal: a bug gets a failing test first, a refactor passes the same
  tests before and after.

## Debugging

- Before proposing any fix, list the three most likely causes and say which
  observation would tell them apart. Gather that evidence before editing.
- Two failed fixes in a row means the model of the bug is wrong. Stop
  proposing fixes; add logging or assertions and collect evidence rather than
  guessing a third time.
- Fix the root cause. A change that silences the symptom without explaining it
  comes back, usually somewhere worse.
- No opportunistic refactoring inside a bug fix.

## Design documents and plans

Use these sections, in this order:

1. Background
2. Goals and non-goals
3. Proposed approach
4. Alternatives considered, and why each was not chosen
5. Risks, failure behaviour, and how the result gets validated
6. Open questions

Non-goals and alternatives are mandatory. They carry what the document decided
*against*, and a reviewer cannot judge the decision without them. How many
alternatives is a judgement call — follow the pruning rule under "Presenting
options" rather than padding to a fixed count.

For a high-level design, write background and goals/non-goals first and get
agreement before drafting the rest; a wrong premise there wastes the whole
document. Detail and delta designs do not need that gate.

Order a plan by what is most likely to change: data model, interfaces, and
anything user-facing first; mechanical refactoring last.

When implementation hits something the plan did not anticipate, take the
conservative option, log the deviation and its reason, keep going, and report
the deviations with the result. Silently re-scoping hands back a change nobody
approved.

## Presenting options

When a reply is about to offer two or more ways forward, name 2-4 comparison
dimensions first, then describe every option on the same ones. Gloss every
term, abbreviation, and package name on first use.

Per option: what it literally is; the same thing as one everyday-life analogy
in different words; what observably changes (which files appear or change,
what is different to operate afterwards); what it costs; how reversible; and
the condition that makes it the right pick.

If two options barely differ, or one is plainly worse, say so and cut the
list. Close with a pick and the condition that would void it — never end on
"it depends".

A question is not a decision. "What are my options", "which should I use",
"compare these" — answer in prose with a recommendation and why.

## Output shape

Lead with the conclusion, then the evidence that supports it, any material
caveat, and the next action. Keep every required fact, decision, caveat, and
next step; trim introductions, repetition, generic reassurance, and optional
background, in that order.

Response language belongs to whoever is working, not to this repo, so it is
deliberately unset here — the same reason `CLAUDE.md` does not import
`communication.md`. Set yours in `~/.codex/AGENTS.md`.

## Documentation

- Write docs in Markdown, and use Mermaid when structure or flow matters.
- Validate every Mermaid block before delivering: syntax, node and edge
  references, and that it actually renders.
- Do not hand-escape `<`, `>`, or `&` as HTML entities inside Mermaid source.
  Quote the label instead — `A["text"]` — or reword to avoid the character.
- For flowcharts set the `elk` renderer, and confirm the target honours it;
  GitHub's Markdown preview silently falls back to `dagre`.
- When a diagram shows a change, colour nodes by change type: added green,
  modified amber, unchanged gray.

## Memory

Record stable facts only — build and test commands, conventions,
architectural decisions, environment quirks, preferences — and date-stamp each
note (YYYY-MM-DD).

Do not record what evolves with the code: signatures, line numbers, current
bug state, work in progress. Re-check the code instead of trusting a note.
Delete or correct a note as soon as it is found stale.

## Reasoning effort

Codex has no per-agent model tier, so reasoning effort is the cost knob that
`model-selection.md` spends on tiers. Treat it as a last-mile adjustment, not
the first response to a weak result.

When a result is weak, check the prompt first: is a success criterion, a
dependency rule, a tool-routing rule, or a verification step missing? Raising
effort rarely supplies what the prompt never said.

- `low` — mechanical, latency-sensitive work where quality does not drop:
  renames, formatting, running a known command and reporting what it printed.
- `medium` — the default, and right for most work in this repo.
- `high` / `xhigh` — only where the extra depth has visibly paid off.
- `max` — hardest quality-first work only: cross-cutting design, a subtle
  correctness or concurrency bug. Not a global default.

Before reaching for more effort, check whether a deterministic answer already
exists. `plugins/cai/scripts/design_probe.py`, `preflight.py`, `track_state.py`
and `scripts/validate.py` each settle in milliseconds a question that would
otherwise cost a model turn.

Effort is not a substitute for a heavier model. Per the bundled model list,
`gpt-5.6-luna` is the fast, lower-cost member and tops out at `max`; only
`gpt-5.6-terra` offers `ultra`. If the problem is depth rather than latency,
change the model rather than climbing luna's ladder.

## Repo specifics

- Windows, mostly Python. Avoid PowerShell for text processing on files
  containing UTF-8 or Chinese characters — use file edits directly, so
  characters are not corrupted.
- `.claude/settings.json` registers a `PostToolUse` hook that runs
  `scripts/validate.py` whenever a file edit touches `plugins/cai/` or
  `.claude-plugin/`. That hook is Claude Code's; **under Codex nothing runs it
  for you**, so run it by hand after every such change.
- Keep every `.cmd` file pure ASCII. CMD.exe reads them through the OEM
  codepage and one multi-byte character mangles every line after it.
- No text file may start with a UTF-8 BOM. It is invisible in an editor, but
  `mermaid-cli` rejects a diagram outright with `Parse error on line 1` and
  CMD.exe prints the three bytes before the first line runs. PowerShell's `>`,
  `>>` and `Out-File` write one by default here.
- Changing the bash guard means adding a case to `CASES` in
  `scripts/validate.py`. That file and `tests/` are the two places this repo
  keeps tests: `validate.py` checks the plugin's shape and the guard, `tests/`
  checks what the scripts do.
- Before working on an existing branch, ask which one is authoritative rather
  than assuming whatever is checked out.
- Commits are English, conventional-commit style (`feat:`, `fix:`,
  `refactor:`), and explain why rather than what.

## Where these rules come from

Each section adapts one or more of `plugins/cai/rules/*.md`. Keep the two in
step; `scripts/validate.py` checks that every rule file is still named here.

| Rule file | Adapted into |
| --- | --- |
| `epistemics.md` | Completion bar, Evidence and uncertainty, Autonomy and approval |
| `coding.md` | Scope of a change |
| `workflow.md` | Autonomy and approval, Design documents and plans, Repo specifics |
| `option-explainer.md` | Presenting options |
| `communication.md` | Output shape (language deliberately unset) |
| `documentation.md` | Documentation |
| `memory.md` | Memory |
| `model-selection.md` | Reasoning effort |

Sections with no rule-file source — Debugging, and the design-document
structure — are Codex-side additions.
