# claude-all-in-one

A [Claude Code](https://claude.com/claude-code) plugin — with a generated
Codex CLI counterpart, `cai-codex` — that installs a working set of everyday
capabilities — cheaper model routing, safer git, and a shared set of
behavioural rules — into every project on your machine.

Four documents, and they answer different questions. This one is what the
pieces are and how to install them. [`MANUAL.md`](MANUAL.md) is how to drive
them — what to type, what happens next, and what every refusal means.
[`GUIDE.md`](GUIDE.md) is where a new piece of guidance belongs when you are
extending the plugin rather than using it. [`CONTRIBUTING.md`](CONTRIBUTING.md)
is for changing this repo: testing, checks before pushing, and releases.

## The shape of it

Four layers, plus one underneath all of them.

- **The track.** `/cai:track <feature>` carries one feature through six SDLC
  stages, keeping state in `.claude/track/<feature>/state.md` so a new session
  with no memory of this conversation can resume it. `/cai:track status` names
  where it stopped; `/cai:track skip <stage> --reason "<why>"` records why a
  stage was skipped instead of silently omitting it.
- **The six stages.** `intake`, `discover`, `design`, `build`, `verify`,
  `ship`. Each stage's procedure is a reference file under
  `skills/track/references/stage-*.md`, read two ways: by the subagent the
  track dispatches, and by that stage's own thin skill (`/cai:intake`,
  `/cai:discover`, `/cai:design`, `/cai:build`, `/cai:verify`, `/cai:ship`)
  when someone wants to run just that stage, track or no track. Exactly two
  stages stop for a human sign-off: after `design`, before any code exists,
  and before the irreversible operations inside `ship` — merging, tagging,
  publishing. Both arrive as a menu you pick from, never as a prompt asking
  you to type `approved`, and the first one is enforced rather than
  remembered: `build` refuses to start until the ledger records a person
  picking Approve, and again if the design document changed since.
- **The tools.** Reachable any time, with no track running: `/cai:refactor`,
  `/cai:debug`, `/cai:git`, `/cai:chore`, `/cai:quiz`, `/cai:plan-review`,
  `/cai:options`, `/cai:usage`, `/cai:models`, `/cai:viewer`.
- **The knowledge.** Reference files that cost nothing until something reads
  them: 72 named refactoring cards under `refactoring-catalog/`, the
  smell-to-refactoring routing table, the six stage procedures above, and a
  template for each kind of design document — diagnosis, stance, decisions,
  detail, delta.

Underneath all of it: `preflight.py`, `track_state.py`, `design_probe.py`,
`options_lint.py`, and `validate.py` answer what a deterministic check can
settle — is this stage allowed to start, where did the track stop, does this
design document actually have the shape it claims, can a reader find "how
reversible" in the options they are being asked to choose between — before
anything reaches a model. `ledger.py` keeps the record those checks read:
every attempt at every stage, appended and never edited, so a new session can
say how many times a stage has been tried, why it failed last time, and who
let it through.

### The six stages, and who runs each one

Stages run in order, top to bottom. The dotted line off each one names the
subagent it dispatches to — `stages.json` decides that, never judgement,
because the model tier rides on the agent. Agent colour is that tier: purple
is `think`, teal is `build`, grey is `chore`. Amber is a person: exactly two
boundaries wait for one.

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart TB
    START(["/cai:track feature"]) --> S1

    S1["intake<br/>a problem statement you can check"] --> S2
    S2["discover<br/>what nobody knows yet"] --> S3
    S3["design<br/>diagnosis or stance, then<br/>decisions, then detail"] --> HG1
    HG1[/"human gate · menu<br/>sign off, no code exists yet"/] --> S4
    S4["build<br/>the work breakdown, unit by unit"] --> S5
    S5["verify<br/>four lenses over the diff"] --> S6
    S6["ship<br/>one commit, plus a release note"] --> HG2
    HG2[/"human gate · menu<br/>before merge, tag, publish"/] --> DONE(["/cai:track done"])

    S1 -.-> AR
    S2 -.-> AR
    S3 -.-> DE
    S4 -.-> IM
    S5 -.-> VE
    S6 -.-> SH

    AR(["architect · think<br/>Read Grep Glob"])
    DE(["designer · think<br/>+ Write"])
    IM(["implementer · build<br/>+ Edit, Bash, Agent"])
    VE(["verifier · build<br/>tests + git reads + Agent"])
    SH(["shipper · build<br/>git + gh"])

    classDef stage fill:#e8eefc,stroke:#4a6fb5,color:#17335f
    classDef human fill:#fff3cd,stroke:#c79100,color:#6b4e00
    classDef think fill:#efe6f7,stroke:#7d5ba6,color:#3d2757
    classDef build fill:#e6eef3,stroke:#4a7c94,color:#1f3f4d
    classDef ends fill:#ffffff,stroke:#9aa5b1,color:#33404d

    class S1,S2,S3,S4,S5,S6 stage
    class HG1,HG2 human
    class AR,DE think
    class IM,VE,SH build
    class START,DONE ends
```

Two things the diagram cannot show. Every stage runs `preflight.py` first — a
check that costs nothing and refuses before any model is called; the shape of
that is in [`MANUAL.md`](MANUAL.md). And `architect` appears twice because
`intake` and `discover` both only read: one agent, two callers, which is the
test for whether an agent deserves its own file at all.

Agent choice follows tool grant, not tier. `design` needs an agent that can
`Write`, `ship` one that can run `git` — picking by tier alone is how an
earlier draft pointed `ship` at a read-only agent that could never have pushed.

### The track's tools

| Command | What it does |
|---|---|
| `/cai:track <feature>` | Create or resume a track. Refuses `current` and `done` as names; refuses a sixth active track (`done/` tracks don't count). Also `status`, `skip <stage> --reason "<why>"`, and `done`. |
| `/cai:intake` | Turn a request into an acceptance-testable problem statement before any code exists: explore context, ask one question at a time, propose 2-3 approaches, wait for approval. User-invoked only. |
| `/cai:discover` | Surface what you don't know before writing code — a blindspot pass, a vocabulary ladder, an interview, an option space, or a mock, whichever unknown would change the most work. Also fires on its own when the codebase is unfamiliar or the result will be judged by look and feel. |
| `/cai:design` | Write a design document for review. Two entrances, picked by one test — can you write a test that fails now and would pass if an existing promise held? Yes: **diagnosis** (root cause and fix, one page). No, because nothing ever promised it: **stance** (what this optimises for and what it gives up, one page). Then **decisions** (the choices that follow, routed so only what needs a person reaches one), **detail** (what gets built from), or **delta** (recovers the decisions already made in a built branch). User-invoked only. |
| `/cai:build` | Build a detail design's work breakdown unit by unit, test-first, verifying and committing each one before the next starts — or cut your own checkpointed units with no design doc. With a detail design whose glossary names project concepts, it asks which to add to `CONTEXT.md` at the repo's top level, which intake, design, debug and refactor read when it exists. User-invoked only. |
| `/cai:verify` | Dispatch four read-only reviewers (correctness, conformance, coverage, security) over a branch diff in parallel, reconcile their findings, then fix Blockers and Majors with a failing test before and a passing one after. |
| `/cai:ship` | Squash a branch into one conventional commit, write a release note, and stop before merging, tagging, or publishing until a person confirms. User-invoked only. |

### The other tools

| Command | What it does |
|---|---|
| `/cai:refactor` | Restructure code without changing its behaviour: the safety-net loop, the smell routing table, and the mechanics for all 72 named refactorings, on the `build` tier. |
| `/cai:debug` | Find the root cause of a bug before proposing any fix — a failing test, a crash, a stack trace, something that used to work and stopped. |
| `/cai:git` | Runs git and `gh` operations on the `chore` tier instead of the main session model. Confirms what it will touch before acting, never stages files you didn't name. |
| `/cai:chore` | Runs any mechanical one-off — renames, formatting, lookups — on the `chore` tier, and reports back if the task turns out to need real reasoning. |
| `/cai:quiz` | Quizzes you on your own branch diff before you merge it: a report on the non-obvious behaviours, then questions you have to answer — none of them answerable from the report alone. |
| `/cai:plan-review` | Reads an implementation plan, design doc, or spec the way a senior architect would: traces every design element back to a requirement, then eight lenses — over-engineering, boundaries, data and state, failure modes, testability, delivery, sequencing, and precision. Ships a skeleton for each kind of design document. Runs on Claude's own plans too, before they reach you. |
| `/cai:options` | Lays out two or more ways forward so a person can actually choose between them: shared comparison dimensions, six fields per option including an everyday-life ELI5 analogy, a recommendation, and the condition that voids it. Use before a list of options goes out, or after one already did and the reader could not act on it. |
| `/cai:usage` | Token usage and equivalent API spend for one track, or across every project over the last N days — plus per-stage process metrics: whether the first attempt passed, cycle time, rework, and how often a person actually signed off. Every number comes from `usage_report.py`; the model restates none of them. On the `chore` tier. |
| `/cai:models` | Puts each tier — `chore`, `build`, `think` — on the model you choose, for you alone, all three in one pass: run it when a new model comes out. The choice survives `/plugin update`; restart Claude Code for it to take effect. |
| `/cai:viewer` | Opens a local-only web page listing every running Claude Code and Codex main session, which ones need you, and cai track progress. `/cai:viewer stop` closes it. |

### The 72 named refactorings

Every refactoring in Fowler's catalog is also its own slash command —
`/cai:extract-method`, `/cai:replace-conditional-with-polymorphism`, and 70
more — living under `plugins/cai/refactoring-catalog/`. Each one carries
`disable-model-invocation: true`, so only a person typing the name can start
it, and its `description` is skipped by the always-on budget check below —
72 procedures that would otherwise sit in every session's context whether
or not anyone ever refactors that day.

### `/cai:goal` — still here, on its way out

`/cai:goal` predates the track: it reviews a design document and routes it —
a work breakdown goes unit by unit, everything else to a single implementer,
both converging on the same test-and-report step. It still ships and still
works, but `/cai:track` is meant to replace it, and `goal`'s own routing
already overlaps what the `design` → `build` → `verify` stages now do more
explicitly. It was to stay only until someone had run a track end to end;
that has long since happened, so its retirement is now its own change, not a
condition still waiting. If you're starting fresh, reach for `/cai:track`
instead.

### Subagents

No component names a model — everything below names a **tier**; see
[Model tiers](#model-tiers). Each subagent is dispatched either by a track
stage or by one of the tools above.

| Agent | Tier | Dispatched by |
|---|---|---|
| `explorer` | `chore` | Read-only scouting. |
| `test-runner` | `chore` | Runs the repo's own automated checks. |
| `implementer` | `build` | The `build` stage, `/cai:build`, `/cai:goal`. |
| `shipper` | `build` | The `ship` stage. |
| `reviewer` | `build` | The `verify` stage, `/cai:verify` — three at once, one lens each: correctness, conformance, coverage. |
| `security-reviewer` | `build` | The `verify` stage's fourth lens: shell execution, what reaches an argument vector, secrets in what is kept, guard bypass — those four and no fifth. |
| `refactoring-detector` | `build` | Parallel smell analysis across module groups during a refactoring scan. |
| `verifier` | `build` | The `verify` stage. |
| `architect` | `think` | The `intake` and `discover` stages. |
| `designer` | `think` | The `design` stage. |

### Also always on

| | |
|---|---|
| **Bash safety guard** | A `PreToolUse` hook on the Bash *and* PowerShell tools. Blocks force pushes (`--force`, `-f`, a `+refspec`, or `--force-with-lease`), `reset --hard`, `git clean -f`, `--no-verify`, `rm -rf` and its `Remove-Item -Recurse -Force` equivalent, commits made straight onto `main`/`master`, any push — force or not — whose destination resolves to `main`/`master`, and PowerShell here-string syntax inside a Bash command — the one that leaves stray `@` characters in your commit messages. In Bash it also blocks a backtick that Bash would run as a command, in double quotes or an unquoted heredoc, where it silently rewrites a commit message, and a `$(…)` that a stray apostrophe left outside the single quotes it was written in, and it reads the parts of a heredoc that Bash executes, so a force push inside one, or behind a quoted `<<EOF` that only looks like one, is still caught. It also blocks `git checkout -- <paths>` and `git restore` **when the working tree is dirty**, which is the shape of a verification step eating the fix it was meant to check; on a clean tree those discard nothing and go straight through. On Claude Code, `test-runner`, `verifier` and `designer` are held to commands of their own on top of all that: the resolver and the test commands it resolved (the verifier also a few read-only git shapes and `provenance.py`), and for the designer its probes, its renderer, `date +%F` and `git rev-parse --show-toplevel`; anything else is blocked. The guard needs a working Python. The first call tries `py -3` then `python` on Windows (`python3` then `python` elsewhere) on empty input and records the first one that runs the guard, in `cai/` under your Claude config directory; later calls start only that one. With none working, those three agents can run no Bash at all, and every other caller gets a reduced check that blocks only `--force`/`-f`/`+refspec` pushes, `reset --hard`, `git clean -f`, `--no-verify` and `rm -rf`: commits and pushes to `main`/`master` go through then. If the recorded interpreter fails on a real call, that one call is blocked for every caller, and the record is dropped unless it still runs the guard on empty input. `gh pr merge`, and a `gh api` call to the same merge endpoint, are neither blocked nor let through silently: merging is a person's call, so Claude Code gets a permission prompt instead; Codex parses but does not act on that "ask" decision, so there the guard denies it and hands back the exact command for the person to run themselves. Hands the command back with the fix rather than just a refusal. |
| **Shared rules** | Eight instruction files covering how Claude should communicate, verify claims, write code, run its workflow, choose models, use memory, write docs, and lay out options. Installed to user scope by `/cai:setup`. |
| **Attempt ledger** | Every stage attempt a track makes — `passed`, `failed`, `blocked`, `skipped`, or `unavailable` when the provider refused to serve it — is appended to `.claude/track/<feature>/ledger.jsonl` with its gate (`auto` or `human`), the SHA-256 of the artifact it named, and the tokens the session spent since the last record. A copy carrying the project and track name goes to `~/.claude/cai/usage.jsonl`, which is what `/cai:usage` reads across projects. Five failed or blocked attempts since a stage last passed or was skipped cap it, and the refusal prints the three ways out; `unavailable` never counts. |

### Which test command runs — resolved, never guessed

Every stage that runs tests — `build`, `verify`, `/cai:goal`, `/cai:refactor`,
and the `test-runner` and `verifier` agents — asks one read-only program for
the command instead of picking one itself. It looks, in this order:

1. **A declaration.** `test.commands` in `.claude/cai.json`, a non-empty list.
   Every command in it runs, in order, and any failure fails the whole run.
2. **Detection**, only when there is no declaration, and only at the project
   root (subdirectories are not searched). It reads entry files — a
   `Makefile`, `justfile` or Task's file (the first present of `Taskfile.yml`,
   `taskfile.yml`, `Taskfile.yaml`, `taskfile.yaml`, `Taskfile.dist.yml`,
   `taskfile.dist.yml`, `Taskfile.dist.yaml`, `taskfile.dist.yaml`) with a
   `test` target, a `package.json` with a real `scripts.test`, `tox.ini`, `noxfile.py` — and
   marker files — pytest configuration (run with the first of `python`,
   `python3`, `py -3` found on `PATH`), `go.mod`, `Cargo.toml`, `pom.xml`,
   `build.gradle` with `gradlew`, a `.sln` or `.csproj`. It never runs
   anything it finds.

```json
{ "test": { "commands": ["python -m pytest", "npm test"] } }
```

When detection finds more than one command, nothing runs: the main session asks
you which, and the answer is written to `test.commands` for next time (other
keys in the file, such as `ticket`, are kept). When it finds none, the stage
says so rather than guessing, and a `.claude/cai.json` that cannot be read as
JSON is reported as it is, with no fallback to detection.

### Ticket mirroring — opt-in, per project

A track can mirror its progress into one GitHub issue. Nothing happens unless
the project turns it on in `.claude/cai.json`:

```json
{ "ticket": { "enabled": true, "backend": "github" } }
```

Then start a track from the issue itself — `/cai:track
https://github.com/<owner>/<repo>/issues/123`. `intake` reads the issue as
its starting request and routes it by evidence, not by its wording; every
passing stage and every skip rewrites one comment on the issue; and
`/cai:track done` asks whether to close it. It uses the `gh` CLI against the
repo's own remote, and a failed update never fails a stage. What each stage
does with the issue, and a worked example from an issue link to a merged PR,
are in [`MANUAL.md`](MANUAL.md#mirroring-a-track-into-a-github-issue).

## What it deliberately leaves out

Four things the large-company AI-SDLC write-ups all have, and this plugin
does not. Each is a trade-off with a cost, not a gap waiting to be filled,
and each names the condition under which it would change.

**The artifact chain stays on your machine.** A track's `state.md`, its
attempt ledger and its implementation notes live under `.claude/track/` and
are not version-controlled: the ledger is append-only, so a tracked copy
would conflict on every merge, and a stage pointer is not a deliverable.
What links a track to the outside is a ticket number — `ticket.py` projects
each stage's row onto the linked issue, one way. Design documents are the
exception: the ones worth keeping go into `docs/design/` and travel with the
PR. The cost is that a design document cannot be reviewed on a PR before it
is built against, and one machine's ledger cannot be compared with
another's. It would change if a second person needed to sign off a design
on the PR rather than in the session.

**No fleet of background agents opening pull requests.** A track is one
lane through six stages: the main session runs it, dispatches one subagent
per stage, and stops at two human gates. There is no issue-to-PR path where
agents pick work up unattended. It would change if a stage ever needed to
fan out past five subagents with merge logic between them, if the flow grew
a real "on failure, go back to build" loop, or if the stage order were found
being skipped in use — the three conditions recorded when this was first
declined.

**No review or eval job on pull requests.** The four review lenses run in
the `verify` stage, on the machine driving the track, on a subscription; the
eval suite runs from an optional local command. Neither is wired to CI. A
PR-triggered job would bill every PR against an API key and needs a runner
credential nobody has set up, and the eval suite (three cases, eleven
graders) is too thin to carry a red/green gate. Measured: one four-lens
review is about US$3.25 of equivalent API spend, one eval run about US$0.24.
It would change when the eval suite can gate — enough cases that a red means
something — or when a contributor's PR needs a review nobody local will run.

**No maintain-stage automation.** The large-company write-ups' Stage 6 comes
with automatic triggers when a control band is breached, scheduled scans, an
agent sitting on-call — all of it assuming a running service with a signal to
watch and an on-call rotation to page. This plugin has neither. What it keeps
instead: `/cai:track done` runs `track_state.py left-open` and prints the
track's `Left open` items in a form that pastes straight into `/cai:intake`
to start the next track — it opens no issue and schedules nothing on its
own. It would change if cai ever ran against a live service with a signal
worth watching.

## Prerequisites

- Claude Code CLI, installed and authenticated. Requires 2.1.283 or later.
- Git.
- Python 3 on `PATH` — `python3` on macOS/Linux, `python` or the `py` launcher
  on Windows. The bash guard needs it; `/cai:setup` tells you if it's
  missing.
- Optional: the GitHub CLI (`gh`), authenticated — for the pull request
  `ship` opens and for ticket mirroring.

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
want Claude to reply in, sets up your global `~/.claude/CLAUDE.md`, offers a
project CLAUDE.md for the current repo, verifies the bash guard actually
fires, and offers to install the status line. Restart once more so the new
rules load.

Agents, commands, and the guard work in every project from then on. The rules
apply to every project too, since they live at user scope.

## Updating

The marketplace is cloned locally, so refresh it first — otherwise an update
re-serves the cached commit:

```
/plugin marketplace update claude-all-in-one
/plugin update cai
```

Restart the session — running sessions don't hot-reload plugin agents or
hooks. If the update changed the rules, run `/cai:setup` to copy them into
`~/.claude/rules/` and restart once more, since rules are read at startup.

The installed copy lives under `~/.claude/plugins/cache/`, keyed by version,
and tracks the marketplace's default branch on GitHub, not a local checkout:
editing a clone of this repo changes nothing your sessions run until the
change is merged and released.

If the cache looks corrupted:

```
/plugin marketplace update claude-all-in-one
/plugin uninstall cai@claude-all-in-one
/plugin install cai@claude-all-in-one
```

## Using it with Codex CLI

`cai-codex` is a generated counterpart of this plugin for Codex CLI — the
same cost-tiered agents, skills, and rules, kept in sync automatically
rather than hand-translated. See
[`plugins/cai-codex/README.md`](plugins/cai-codex/README.md) for exactly
what's equivalent, what's degraded, and what's documented but not yet
checked end to end.

### Install

```
codex plugin marketplace add millerlai/claude-all-in-one
codex plugin add cai-codex@claude-all-in-one
```

The `owner/repo` form is the one Codex documents and was exercised end to end
during the v1.39.0 release; an earlier build exercised the equivalent local
form, `codex plugin marketplace add <path to a clone>`.

Requires `codex-cli` 0.157.1 or later — check with `codex --version`. An
older codex-cli won't see this plugin at all: it drops the marketplace entry
silently, with no error message.

Start Codex with `--enable default_mode_request_user_input` so `$setup`'s
language question renders as a menu. The track's two human gates ask the
same way when the flag is on, but can still fall back to numbered text even
then — observed once during a live run. Then, inside Codex:

```
$setup
```

Approve running it outside the sandbox when asked — it writes into
`~/.codex`, outside your workspace. Then run `/hooks`, review the cai
entry, and trust it; restart Codex.

### Use

`$track <feature>` carries one feature through the same six stages as
`/cai:track`, intake to ship. Every other skill works the same way with a
`$` instead of `/cai:` — `$design`, `$verify`, `$git`, `$chore`, and the
rest. See [`plugins/cai-codex/README.md`](plugins/cai-codex/README.md)'s
Usage section for the human gates, the ship push approval, and
Windows-specific notes.

### Update

```
codex plugin marketplace upgrade
codex plugin add cai-codex@claude-all-in-one
```

Then run `$setup` inside Codex. Re-running `add` alone is enough to move to
a new version once the marketplace is upgraded — no separate `remove` step
needed. The first line refreshes Codex's copy of this repository ("Refresh
configured Git marketplace snapshots", in `codex plugin marketplace
--help`). Both lines were exercised end to end against the GitHub-hosted
marketplace at v1.39.0, moving an install from 1.38.1 to 1.39.0 on
codex-cli 0.157.1.

### Uninstall

```
codex plugin remove cai-codex@claude-all-in-one
```

Then remove what `$setup` wrote by hand — see
[`plugins/cai-codex/README.md`](plugins/cai-codex/README.md)'s Uninstall
section for the exact list.

## Compatibility

One version number, in `plugins/cai/.claude-plugin/plugin.json`, covers both
`cai` and its generated `cai-codex` counterpart — they always ship together
at the same version.

That version follows [SemVer](https://semver.org/) against a public
interface: skill names, `/cai:setup`'s write locations, the model-choice
save format, and the two platform floors below.

| Change | Bump | Example |
|---|---|---|
| Removing or renaming a skill; an old save file no longer loading; raising a platform floor | MAJOR | Dropping `/cai:quiz` |
| Adding a skill; adding an omittable field to an old save file; a track-format change | MINOR | Adding a new tool, or changing what `.claude/track/<feature>/state.md` records (called out on that release's GitHub Release page) |
| A script bug fix that doesn't change format; rewording a rule | PATCH | Fixing a guard regex |

Platform floors: Claude Code 2.1.283 or later, codex-cli 0.157.1 or later.

## If an update stops installing

If updating stops working on either platform, check the most recent GitHub
Release page first. If a fallback is active, it gives exact instructions for
a `stable` branch — a `#stable` ref suffix on Claude Code, `--ref stable` on
Codex. The specific commands aren't documented here ahead of time: they
depend on details only confirmed when the fallback is actually used.

## Model tiers

No component names a model. They name a **tier**, and one file says what each
tier currently resolves to:

| Tier | Resolves to | The work it is for |
|---|---|---|
| `chore` | `haiku` | Needs no judgement on any given run — locating files, running a known command, a stated git operation, mechanical rewrites. |
| `build` | `sonnet` | Engineering judgement inside a fixed contract — writing code to a spec, reviewing one diff through one lens. |
| `think` | `opus` | Design trade-offs and repair — architecture choices, reviewing a plan against its requirements, ambiguous requirements. |

The test is *"does this step still need judgement on every run?"* — not how often
the task comes up. Frequency decides total volume; judgement risk decides tier.

Two things follow, and both are enforced rather than remembered:

- **Nothing is pinned to a model version.** Aliases already track the newest
  model of their family — Anthropic's docs are explicit that they "point to the
  recommended version for your provider and update over time" — so `haiku` keeps
  working when Haiku 5 ships. `validate.py` fails the build if any component
  pins a concrete version like `claude-haiku-4-5-20251001`.
- **Re-tiering is a one-line edit.** Change a tier's alias in
  `plugins/cai/models.json`, run `python plugins/cai/scripts/gen-models.py`, and
  every component in that tier moves together. `--check` reports drift without
  writing; `--list` prints the table. `validate.py` fails if any component's
  frontmatter disagrees with the table, if a component declaring a model isn't
  in it, or if any component names a model family in its prose.
- **Your own tiers, without waiting for a release.** `/cai:models` puts any
  tier on another model, an alias or a full model id, for you alone. It saves
  the choice in `~/.claude/cai/model-choice.json` and rewrites the `model:`
  lines of your installed copy (never a source tree), and a SessionStart hook
  re-applies it to each copy `/plugin update` installs. Claude Code reads
  those lines when it starts, so restart it after a change.

Deciding *whether* to re-tier stays a human's call — that is a judgement, and
judgements are exactly what this table says not to automate.

**When this account cannot run a tier's model, Claude Code v2.1.247 or later
handles most of it already:**

- A subagent whose alias (`sonnet`, `opus`, `haiku`) is blocked by an
  `availableModels` allowlist moves to the newest permitted version of that
  family, or, when no version is permitted, to the main conversation's model
  ([Restrict model selection](https://code.claude.com/docs/en/model-config#restrict-model-selection),
  [Choose a model](https://code.claude.com/docs/en/sub-agents#choose-a-model)).
- A skill or command whose `model` frontmatter is blocked is ignored; the
  skill runs on the session's own model instead
  ([Restrict model selection](https://code.claude.com/docs/en/model-config#restrict-model-selection)).
- An organisation cannot disable `haiku` — every member keeps at least one
  usable model — though that guarantee only reaches the Anthropic API and an
  LLM gateway deployment
  ([Organization model restrictions](https://code.claude.com/docs/en/model-config#organization-model-restrictions)).

Not covered: a subagent whose model the API rejects outright — a retired model
ID, for example — fails instead of substituting. Claude Code v2.1.247 or later
can route around that with a fallback chain — set `fallbackModel` in
`~/.claude/settings.json` as an array (entries accept an alias):

```json
{
  "fallbackModel": ["sonnet", "haiku"]
}
```

It applies to every Claude Code session, switches only when a request fails
— an overloaded, unavailable, or otherwise non-retryable model, never an
authentication, billing, or organisation-policy denial, which are never
retried this way — lasts for the current turn only, and isn't shown in
`/status`
([Fallback model chains](https://code.claude.com/docs/en/model-config#fallback-model-chains)).

## The rules

`/cai:setup` writes these to `~/.claude/rules/`. They are ordinary
Markdown — edit your copies freely; setup flags files that look hand-edited and
asks before overwriting them.

| File | What it governs |
|---|---|
| `communication.md` | Response language, conciseness, leading with the answer. In a non-English reply or document, a term kept in English gets its meaning in that language first, then the term in parentheses — or a glossary up front. |
| `epistemics.md` | Check before answering, cite sources, never fabricate, re-read as a skeptic before delivering. When to stop and ask, and how: one decision per turn, through the question tool, recommended option first. Verify against the original request before claiming done. |
| `coding.md` | Pure functions, comment the why, read the reference's source when matching an existing implementation, minimum code, surgical changes only. |
| `workflow.md` | Branch before touching code, plan non-trivial changes and order them by what you're likeliest to change, prototype taste-driven work, log deviations from the plan, run tests before claiming done, never commit unless asked. |
| `model-selection.md` | Settle what a deterministic check can before paying for a model, then which subagent and model tier to use for the rest. |
| `memory.md` | Record stable facts only; don't persist implementation details that go stale. |
| `documentation.md` | Markdown, Mermaid for structure, validate diagrams before shipping. |
| `option-explainer.md` | How to lay out two or more ways forward: shared dimensions, six fields per option including an everyday-life analogy, a real sample of each when the options differ in something you will see, and a pick with the condition that voids it. |

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

## Your project CLAUDE.md

`~/.claude/CLAUDE.md` above is user scope — your machine and your personal
habits, and it applies to every repo you touch. A project's own CLAUDE.md is
the other scope: the one command that proves a change is done in *this* repo,
its architecture, and conventions specific to it. It is checked in and shared
with every teammate, including ones who never installed cai.

Setup checks the repo you ran it from (`git rev-parse --show-toplevel`, not
just the current directory — Claude Code loads a CLAUDE.md from every parent
of your cwd, so the file that matters is the one at the repo's top level).

If neither `<repo>/CLAUDE.md` nor `<repo>/.claude/CLAUDE.md` exists, setup
offers to add one from `plugins/cai/templates/CLAUDE-project.md.tpl`, asks
once, and copies it verbatim on yes — it fills in nothing.

If one already exists, setup never overwrites it and never removes a
sentence. It reports which of the template's sections already have a
counterpart, which don't, and which sentences already live in a file under
`~/.claude/rules/` — then offers to **append** only the missing sections,
showing the result before writing.

Outside a git repository, setup skips this step and just prints the template
path so you can copy it in yourself.

## The status line

Optional, and offered by `/cai:setup` rather than shipped with the plugin —
Claude Code reads only the `agent` and `subagentStatusLine` keys out of a
plugin's settings, so a status line can only reach you through your own
`~/.claude/settings.json`.

```
claude-all-in-one · main · Opus 5 [max] · ctx 92% · 5h 75% · 7d 60%
```

Project name in bright cyan, git branch, the model with its live `/effort`
level, then three gauges that all read the same way — how much is **left**, not
how much is spent. Green at 50% or more, amber down to 21%, red at 20% or below,
so a colour means the same thing whichever number you look at. The two
rate-limit gauges appear only for Claude.ai subscribers, and only after the
session's first API response.

Setup copies the script to `~/.claude/cai-statusline.py` and points
`statusLine.command` at it. It never writes `~/.claude/statusline.py`, which
belongs to Claude Code's own `/statusline` command. If you already have a status
line configured, setup shows you what it is and asks before replacing it, and
leaves a `settings.json.bak` either way. Re-running setup after a plugin update
refreshes the copied script; it takes effect on save, with no restart.

## Also included

- `templates/multi-repo.settings.json`, at this repo's root rather than in the
  installed plugin — drop into a repo's `.claude/settings.json`
  to grant Claude access to a sibling repo via `additionalDirectories`, and
  optionally load that repo's own `CLAUDE.md`/rules too.
- Optional: [mermaid-cli](https://github.com/mermaid-js/mermaid-cli)
  (`npm install -g @mermaid-js/mermaid-cli`) so Claude can actually render and
  validate the diagrams `documentation.md` asks for.

Claude Code's built-in auto memory keeps per-project notes in
`~/.claude/projects/<project>/memory/` — inspect with `/memory`. Curated
instructions belong in the rules; hard constraints belong in hooks.

## Contributing

Changing the plugin rather than using it? [`CONTRIBUTING.md`](CONTRIBUTING.md)
covers testing an unreleased checkout, the checks to run before pushing, and
cutting a release; [`GUIDE.md`](GUIDE.md) covers which component a new piece
of guidance belongs in.
