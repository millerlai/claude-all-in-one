# claude-all-in-one

A [Claude Code](https://claude.com/claude-code) plugin that installs a working
set of everyday capabilities — cheaper model routing, safer git, and a shared
set of behavioural rules — into every project on your machine.

## What you get

| | |
|---|---|
| **Cost-tiered subagents** | `explorer` (Haiku, read-only scouting), `implementer` (Sonnet), `test-runner` (Haiku), `reviewer` (Sonnet, read-only, one lens of a diff at a time), `architect` (Opus, read-only design). Claude picks the cheapest model that can do the job instead of defaulting to the strongest. |
| **`/cai:git`** | Runs git and `gh` operations under Haiku 4.5 rather than the main session model. Confirms what it will touch before acting, never stages files you didn't name. |
| **`/cai:haiku`** | Runs any mechanical one-off — renames, formatting, lookups — under Haiku, and reports back if the task turns out to need real reasoning. |
| **`/cai:git-pr-rebase`** | Squashes a PR branch into one well-written conventional commit. Takes a backup branch first and shows you the message before rewriting anything. |
| **`finding-unknowns`** | Fires before implementation when the code is unfamiliar, the spec is vague, the solution space is unexplored, or the result is judged by look and feel — and offers the cheapest artifact that would settle it: a blindspot pass, a vocabulary ladder, a one-question-at-a-time interview, a sized option list, or four incompatible mocks. Asks before it runs. |
| **`/cai:design-high-level-doc`** | Writes the high-level design and stops there. Use cases first, then a feasibility table marking every capability the design needs `verified`, `UNVERIFIED`, or `infeasible` against a real `file:line` or the vendor's own documentation — never against what a library is generally assumed to do. Gathering that evidence is delegated to Haiku; reading it is not. The main flow and the components as Mermaid that gets rendered rather than eyeballed, and every architecture choice put to you one at a time with the options costed, instead of picked and then justified. |
| **`/cai:design-implementation-detail-doc`** | Turns an approved high-level design into something an engineering team can build from without asking follow-up questions: a traceability table proving every use case is reached, a glossary written *before* the prose, four validated diagrams, per-component signatures and data shapes, and a `Naming` table where every name the system will create is either your decision or an existing convention with the line that shows it — never an invented `p5` or `u3`. Gates on the high-level design's own `Status` line rather than on the conversation, so it works in a fresh session. |
| **`templates/design-*.md.tpl`** | The two shapes the commands write to, so a second run does not produce a second format. Guidance lives in HTML comments that the probe does not count as content — an untouched template fails its own probe, which `validate.py` asserts, along with the templates, `design_probe.py`, and `plan-review`'s skeletons all listing the same headings. |
| **`design_probe.py`** | What stops the two commands above being prose nobody checks. Zero-dependency, zero-token, and run before any review: are the headings filled, does every capability carry an id and a citation, is every capability cited by some option, does any recommendation rest on something `UNVERIFIED`, is every use case in the high-level design reached by the detail design, does every glossary `file:line` resolve to a file that long. `validate.py` exercises it with one clean document per kind and one deliberate defect per probe. |
| **`plan-review`** | Reads an implementation plan, design doc, or spec the way a senior architect would. Traces every design element back to a requirement first — an element no requirement reaches is neither kept quietly nor cut quietly, it comes back as the requirement it implies, for you to accept or reject. Then eight lenses: over-engineering, boundaries, data and state, failure modes, testability, delivery, the plan's own sequencing, and precision — the sentence two engineers would implement differently while both claiming they followed it. Ships a skeleton for each kind of document, high-level and detail. Runs on Claude's own plans too, before they reach you. |
| **`/cai:quiz`** | Quizzes you on your own branch diff before you merge it: a report on the non-obvious behaviours, then questions you have to answer — none of them answerable from the report alone. |
| **`/cai:goal`** | Takes a design/plan doc from requirement to verified implementation in three phases, each on its own model tier: reviews and fixes the doc on this session's own model, implements and checks conformance on Sonnet, then verifies — automated tests on Haiku, everything else synthesized inline with a numbered manual-verification checklist. |
| **`diff-review`** | Sends three read-only `reviewer` agents over the branch diff in parallel — correctness, conformance, coverage — then reconciles them into one ranked list, verifying each finding against the file before reporting it. Code that does more than was asked comes back as a requirement to confirm, not a silent deletion. |
| **`checkpointed-execution`** | Runs a long multi-file change as units that each compile, verify, and commit on their own, tracked in a status table, so a session limit resumes instead of reverting. Asks once, up front, for permission to commit per unit. |
| **Bash safety guard** | A `PreToolUse` hook on the Bash *and* PowerShell tools. Blocks force pushes, `reset --hard`, `git clean -f`, `--no-verify`, `rm -rf` and its `Remove-Item -Recurse -Force` equivalent, commits made straight onto `main`/`master`, and PowerShell here-string syntax inside a Bash command — the one that leaves stray `@` characters in your commit messages. Hands the command back with the fix rather than just a refusal. |
| **Shared rules** | Seven instruction files covering how Claude should communicate, verify claims, write code, run its workflow, choose models, use memory, and write docs. Installed to user scope by `/cai:setup`. |

## Prerequisites

- Claude Code CLI, installed and authenticated.
- Git.
- Python 3 on `PATH` — `python3` on macOS/Linux, `python` or the `py` launcher
  on Windows. The bash guard needs it; `/cai:setup` tells you if it's
  missing.

## Install

Inside any Claude Code session:

```
/plugin marketplace add millerlai/claude-all-in-one
/plugin install cai@claude-all-in-one
```

Restart the session, then run:

```
/cai:setup
```

Setup copies the rule files into `~/.claude/rules/`, asks which language you
want Claude to reply in, sets up your global `~/.claude/CLAUDE.md`, and verifies
the bash guard actually fires. Restart once more so the new rules load.

Agents, commands, and the guard work in every project from then on. The rules
apply to every project too, since they live at user scope.

## Updating

The marketplace is cloned locally, so refresh it first — otherwise an update
re-serves the cached commit:

```
/plugin marketplace update claude-all-in-one
/plugin update cai
```

Re-run `/cai:setup` afterwards to pick up rule changes, and restart the
session — running sessions don't hot-reload plugin agents or hooks.

If content changed without a version bump, or the cache looks corrupted:

```
/plugin marketplace update claude-all-in-one
/plugin uninstall cai@claude-all-in-one
/plugin install cai@claude-all-in-one
```

## The rules

`/cai:setup` writes these to `~/.claude/rules/`. They are ordinary
Markdown — edit your copies freely; setup flags files that look hand-edited and
asks before overwriting them.

| File | What it governs |
|---|---|
| `communication.md` | Response language, conciseness, leading with the answer. |
| `epistemics.md` | Check before answering, cite sources, never fabricate, re-read as a skeptic before delivering. |
| `coding.md` | Pure functions, comment the why, read the reference's source when matching an existing implementation, minimum code, surgical changes only. |
| `workflow.md` | Branch before touching code, plan non-trivial changes and order them by what you're likeliest to change, prototype taste-driven work, log deviations from the plan, run tests before claiming done, never commit unless asked. |
| `model-selection.md` | Which subagent and model tier to use for which kind of task. |
| `memory.md` | Record stable facts only; don't persist implementation details that go stale. |
| `documentation.md` | Markdown, Mermaid for structure, validate diagrams before shipping. |

`communication.md` ships defaulting to English; `/cai:setup` rewrites
that line to whatever language you pick.

## Your global CLAUDE.md

`~/.claude/rules/` loads automatically, so your `~/.claude/CLAUDE.md` only needs
what the rules can't know — your OS, your stack, and the mistakes you don't want
repeated. Setup writes a thin starter there if you don't have one.

If you already have a CLAUDE.md, setup never overwrites it. It reports which of
your sections are now covered by a rules file and offers to slim the file down,
because a rule kept in both places is sent to the model twice in every session
and the two copies drift apart as soon as one is edited. `validate.py` enforces
the same invariant on the shipped template.

## Also included

- `docs/multi-repo.md` — cross-repo sessions with `--add-dir` and worktrees,
  plus `templates/multi-repo.settings.json`.
- `docs/multi-session.md` — sessions, background agents, agent teams, memory.
  Agent teams are experimental and need `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.
- Optional: [mermaid-cli](https://github.com/mermaid-js/mermaid-cli)
  (`npm install -g @mermaid-js/mermaid-cli`) so Claude can actually render and
  validate the diagrams `documentation.md` asks for.

Claude Code's built-in auto memory keeps per-project notes in
`~/.claude/projects/<project>/memory/` — inspect with `/memory`. Curated
instructions belong in the rules; hard constraints belong in hooks.

## Contributing / developing

Add the marketplace from a local checkout, then install to test your changes:

```
/plugin marketplace add /path/to/claude-all-in-one
/plugin install cai@claude-all-in-one
```

Everything users receive lives under `plugins/cai/` — the plugin cache
copies only that directory, so anything outside it never reaches an installer.

Adding guidance rather than code? [GUIDE.md](GUIDE.md) covers which component
should hold it — a convention, a procedure, or a constraint — and why putting it
in the wrong one makes it quietly stop working. It applies just as well to your
own `~/.claude/` setup.

Before pushing, run:

```bash
python scripts/validate.py
```

It checks the manifests, that every agent/command/skill has the frontmatter
Claude Code needs to load it, that hook commands point at files that exist, and
that the guard still blocks what it should — through the same dispatcher the
hook uses, on your platform.
