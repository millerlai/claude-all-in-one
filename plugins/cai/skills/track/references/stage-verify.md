# stage-verify — four lenses over one diff, and no claim without evidence

This file is read two ways: by the subagent the track dispatches to run this
stage, and by `/cai:verify` when someone runs the stage standing alone, with
no track underneath it. The procedure below is the same either way.

**Asking is the one thing that is not.** Dispatched by the track you are a
subagent, and the platform gives no subagent an interactive tool. Every place below that waits on the person — a
requirement decision, a parked proposal, `provenance.py` exiting 2 — then
means: stop there, and end the report with the `## Pending questions` section
`references/pending-questions.md` specifies. The main session puts it to the
person and re-dispatches this stage with the answer. Standing alone you are
the main session — ask directly. Re-dispatched with an answer: when the
round's report came from Step 0.5's stop, no lens has run and there are no
findings to take, so start again at Step 0; when the answer is to record the
start candidate, rerun Step 0.75, the runtime check, the synthesis and
`check`, take the findings from the previous round's report, and run no lens
again; otherwise take the findings from the round's report, apply the answer
under Fixing, and do not run Steps 0.5 to 2 again.

One reviewer reading a diff finds what that reviewer is tuned to find. The
misses are not random: a reader hunting off-by-one errors is not, in the
same pass, asking whether the feature was worth building. Splitting the
lenses and running them separately is what makes the second question get
asked at all.

## The evidence rule

No completion claim without having just run the command and read its
output. "Should pass" is not evidence, and neither is remembering that it
passed five minutes ago in this conversation — the tree has moved since
then. Every verdict below — the reconciled findings, the fix, the final
report — traces back to a command that was actually run in this pass.

## Step 0 — Fix the scope

Find the base ref, taking the first that works: the ref the user named, or
`git symbolic-ref --short refs/remotes/origin/HEAD`, or `origin/main` (or
`origin/master`). Then, as separate commands:

- `git merge-base HEAD <base-ref>` — the branch point.
- `git diff --stat <branch-point>...HEAD` — the file list.
- `git rev-parse --show-toplevel` — `<top>`, the directory Step 1's convention
  files live under.

Carry the values yourself. Do not wire them into one pipeline with shell
variables, `sed`, or `${VAR:-default}` — none of that parses under the
PowerShell tool, and this has to work on Windows.

An empty diff, or one that is entirely generated files, stops here. Say so.

## Step 0.5 — Provenance check

Run `python ${CLAUDE_PLUGIN_ROOT}/scripts/provenance.py` once, unconditionally
-- not gated on the diff being empty, unlike Step 0's early-stop. Exit 2 is a
Blocker: report it and stop right there, handing up one question under
`## Pending questions` -- the claim that drifted, and two ways forward: the
person re-confirms it, updates the ledger themselves and re-runs verify, or
stops. Never edit the ledger's citations or
a restated file to turn the red green -- a drift needs a person to re-confirm
the claim first, not a string edit that proves nothing.

## Step 0.75 — Verify plan

Run `python ${CLAUDE_PLUGIN_ROOT}/scripts/verify_plan.py plan --track-dir <dir>`
before the lenses are dispatched (`<dir>` is the track directory; standing
alone, with no track, leave `--track-dir` off). It reads files and starts
nothing. Keep its table: it says where each AC of the intake goes. An AC the
plan marks `Not covered` is not dispatched — no lens is asked about it — and
Step 3 lists it with the plan's reason.

- Exit 5: the intake's `## Verification levels` table is invalid, so there is
  no per-AC list to build. Name the problems it printed, start no runner, and
  make the verdict at least `Revise`.
- A legacy intake, no intake, no start declaration, or no `local-run` AC: the
  plan's `runtime: skipped (<reason>)` line says which, and Step 3 names that
  reason as the one that kept the runtime check from running.
- The plan prints `start candidates:` (there is a `local-run` AC, no start
  declaration, and the resolver found something in the project's files): hand
  up two questions under `## Pending questions`, never choosing a candidate
  yourself. The first: record one of the candidates, or keep it Not covered.
  The second, which blocks the recording: the ready URL. Its options are only
  ports or URLs you read in a project file, each with its `file:line`, plus
  one more, `{port}` — the start command with the port argument that tool
  accepts, appended — and free text is always there. When the first answer is
  to keep it Not covered, the second question is not asked. The main session
  writes the answer into `.claude/cai.json` with `record_start_command.py` and
  re-dispatches this stage; the opening paragraph says what runs then. The main
  session never reads this file, so the first question's recording option
  carries the command it is to run, written out whole:
  `python ${CLAUDE_PLUGIN_ROOT}/scripts/record_start_command.py --ready <the
  second answer> -- <the candidate's start words>`.
  Standing alone, ask the same two directly, one at a time.

## Step 1 — Dispatch the lenses

Four agents, in parallel, one message: three `reviewer` agents, one lens
each, plus the `security-reviewer` agent for the fourth. Four and not more —
`model-selection.md` caps parallel subagents at 2–4.

| Lens | What it hunts |
|---|---|
| **correctness** | Off-by-one and boundary errors, state leaking between instances or requests, a `match`/`switch` that silently falls through, a flag set and never cleared, an error swallowed, ordering assumed but not guaranteed |
| **conformance** | What the change does that nothing asked for, and what it was asked for and skipped. Compare against the plan, spec, issue, or the request in this conversation, and against the convention files at `<top>` — `<top>/CLAUDE.md` and `<top>/.claude/CLAUDE.md`, by file rather than by heading |
| **coverage** | For each behaviour change: is there a test that would **fail if this change were reverted**? Name the tests that are missing, not the coverage percentage |
| **security** | The four hunt items in `finding-severity.md`, and no fifth: an external call routed through a shell, who controls what reaches the argument vector, raw error/output/argument text reaching a print or a kept record, and a command shape the repo's own refusal list does not cover |

Give each agent the base ref, the file list, and the requirement it is
reviewing against — the plan, issue, or the user's own words. Before
dispatching, run `git diff <base-ref>` and supply its full output as text
or a readable file, including uncommitted changes when those are the review
scope. Supply any needed `git log`/`git show` output too: the lenses have
only Read/Grep/Glob and cannot fetch a diff or run tests themselves. Before
dispatching, check which of `<top>/CLAUDE.md` and `<top>/.claude/CLAUDE.md`
exist and give the conformance lens only the paths that do. `@path` imports
are not followed, and `CLAUDE.local.md` does not count — only a line inside
one of those two files themselves may be cited, and a convention finding
with no `file:line` in one of them is not a finding.

A written requirement and a convention file are independent inputs to
conformance. With neither, conformance is skipped and the other three
lenses still run, as before. With a requirement but no convention file,
compare only against the requirement, as before. With a convention file but
no requirement, conformance still runs and compares only against the
convention files. With both, compare against both.

When the dispatch brief names a requirement, that is the requirement. When it
names none, under a track it is the documents the design row of the track's
state table (`.claude/track/<feature>/`) names, plus the numbered acceptance
criteria in `.claude/track/<feature>/intake.md` (`.claude/track/current`
holds the feature name). Read them yourself; the dispatch brief does not have
to carry them. When none can be read, conformance has no requirement and Step
3's `Not covered` says so.

The three severity words Step 2 ranks by, and the security lens's four hunt
items, are defined in one place:
`${CLAUDE_PLUGIN_ROOT}/skills/track/references/finding-severity.md`. Read it
before classifying anything, and give `security-reviewer` its four items as the
lens it is reviewing against.

## Step 2 — Reconcile

Do this inline; it is dedup and ranking over data already gathered, not
worth another subagent run.

- Merge findings that name the same `file:line` and the same cause. Two
  lenses reaching the same defect independently is evidence, not noise.
- A convention finding whose `file:line` already appears in a command this
  pass actually ran and read the output of merges into that finding instead
  of standing alone — the repo's own verification command already caught
  it. One the commands run this pass never reached stays as its own
  finding, and Step 3's `Not covered` names which command would have
  covered it.
- Drop anything with no failure scenario, whichever lens produced it.
- Every surviving `Blocker`/`Major` must name what requirement it's based
  on — the original request's own words, a plan/issue paragraph, or an
  existing standing obligation (naming which file, which heading). A
  finding that can name none of those is not a defect this stage may fix —
  reject it or park it as a proposal instead of sending it into Fixing.
- Rank `Blocker` → `Major` → `Minor`. What the three mean is defined in one
  place, and ranking here applies those definitions rather than restating
  them: `${CLAUDE_PLUGIN_ROOT}/skills/track/references/finding-severity.md`.
- **Verify before reporting.** For each surviving Blocker and Major, open
  the file and confirm the line still says what the finding claims — the
  same evidence rule this stage opens with, applied to the reviewers'
  output rather than your own.

## Step 3 — Report

1. **Verdict.** `Ready` / `Revise` / `Rework`, one sentence of why.
2. **Findings**, ranked. Each keeps `file:line`, the failure with concrete
   inputs, and the smallest fix.
3. **Requirement decisions to confirm.** Everything the conformance lens
   found that the requirements do not reach, in either direction — the
   element, the requirement it implies as one sentence, and what follows
   from yes and from no. Not optional and not the findings list: code that
   does more than was asked is a decision someone made silently, and
   deleting it yourself is a second one. Surface it, don't take it: under a
   track each one goes into `## Pending questions`, one question per element.
4. **Not covered.** Under a track whose intake has a `## Verification levels`
   table, list every AC of the intake, one line each, with exactly one of four
   outcomes — `verified-by-test`, `verified-at-runtime`,
   `confirm-before-merge`, or `not-covered` with its reason — copied from the
   table `check` printed (the Runtime check section), `manifest:` line first;
   a `verified-by-test` line keeps the tests, command and counts it printed.
   With no such table, name which of Step 0.75's cases it was. Then what the
   lenses could not check, and why — including "no written requirement" or
   "no written conventions" when either was missing from conformance's
   inputs.

## Fixing

Fix `Blocker` and `Major` only. For anything that looks like a bug: write
the failing test first, **run it and read the output showing it fail**,
then fix it and **run it again and read the output showing it pass**. A fix
with no test run you watched is a fix you cannot prove, whatever it looks
like on the screen.

Leave `Minor` documented and unfixed unless asked. Touch nothing in section 3
until it is answered: hand each decision up under `## Pending questions`, fix
the Blocker/Major findings the answer does not block, and let the main
session re-dispatch this stage with the answer. Fix nothing Step 2 could not
trace to a requirement — a parked proposal stays parked until the user
answers, and must not be swept in together with ordinary `Minor` findings. A
parked proposal goes up the same way as a requirement decision, and its
question says which requirement it would need to stop being parked.

A change made from an answer is tested like any other fix, but it is not
re-reviewed by the four lenses: the report's left-open items say that changes
made from an answer were not reviewed by the four lenses.

## Runtime check

After Fixing, or after Step 2 when nothing was fixed, and unless Step 0.75's
plan printed `runtime: skipped`, run
`python ${CLAUDE_PLUGIN_ROOT}/scripts/local_run.py --track-dir <dir> --stage verify`
as one Bash call with `timeout` 600000. It starts the program the project
declared, runs each `local-run` check, saves each one's output under
`<dir>/evidence/verify/`, and stops everything it started. If anything was
fixed, the `local-run` evidence must come from a runner run after the last fix;
a run from before a fix proves nothing about what the fix changed.

The runner ends itself at 540 s, below the 600000 ms call timeout. If the Bash
call reports that it timed out or was moved to the background, do not wait for
it: report those ACs as not verified at runtime; do not read partial output.
Exit codes: 0 every check passed; 3 a check failed,
timed out or was not run; 4 nothing runnable, or the fixed port is taken; 5
invalid arguments or intake; 6 a process was left running — name the pids it
printed in the report as a Blocker, since something is still running on the
person's machine. A check that did not pass becomes `not-covered` through
`check` below, with its reason; never describe it as skipped.

Then write the synthesis with the Write tool to
`<dir>/evidence/verify/synthesis.json`, and run
`python ${CLAUDE_PLUGIN_ROOT}/scripts/verify_plan.py check --track-dir <dir> --synthesis <dir>/evidence/verify/synthesis.json --run <the runner's evidence dir>`.
The evidence dir is the directory of the `run record:` line the runner
printed; leave `--run` off when it printed none. The synthesis is one JSON
object:

```json
{"format": 1,
 "test_commands": [{"command": "python -m pytest", "passed": 12, "failed": 0}],
 "acs": {"AC1": {"tests": ["tests/test_x.py::test_y"],
                 "findings": [{"severity": "Major", "fixed": true}]}}}
```

`tests` are the tests you matched to that AC; `findings` are the reconciled
findings that bear on it, each with whether Fixing fixed it. `check` writes
`manifest.json` and prints its path and one line per AC, then checks what it
wrote. Its exit 3 means a rule broke, and stderr names it: an AC with an
unfixed Blocker or Major finding is never verified; an AC the plan marked Not
covered is never verified; a `test` AC with no matching test is Not covered;
an evidence file changed or missing; an AC missing from the manifest or not in
the intake. Correct the synthesis, not the manifest, and run it again. Exit 4:
no manifest for a legacy or standalone verify. Exit 5: the intake or the
synthesis is invalid.

## When not to use this

- The artifact is a plan, spec, or design doc, not a diff — that is
  `stage-design.md`'s gate, via `plan-review`.
- The change is one file and a few lines. Read it.

## When this is the wrong tool

- **Checking your own understanding of the diff, rather than its quality** —
  that is `/cai:quiz`, which stops and asks you questions. This stage never
  waits for an answer, because inside a track it has to run to completion;
  what needs a person goes up under `## Pending questions` instead.
- **Reviewing a plan rather than code** — that is `plan-review`.

## Report

This is what you hand back to the main session -- not the report this
file's own steps describe. Put these fields in a `## Report` section. The
main session, not you, is the only writer of the track's state table and
of the ledger's `--note`; you write no track file at all, with one exception:
`evidence/verify/synthesis.json`, which the Runtime check section has you write
(the runner and `check` write the evidence files they print themselves).

- the verdict
- the path of the last round's `manifest.json`, the `manifest:` line `check`
  printed, or `none` and why when `check` exited 4 or 5; the main session
  passes it as the verify ledger row's `--artifact`
- what was fixed
- what Step 3's **Requirement decisions to confirm** raised and how it was
  answered
- what remains unfixed and why
- what is left open -- every Minor left unfixed, every parked proposal, and
  the changes made from an answer (not reviewed by the four lenses), one item each
- what got parked as a proposal, and which requirement it would need to
  stop being parked
- every path you changed or added, new test files included, one per line,
  across every round of this stage (a re-dispatch takes the earlier rounds'
  paths from the report it was given), and a line saying you did not commit:
  you cannot. Step 0.5 of `stage-build.md` decided who does. After a
  commit "yes" the main session adds exactly those paths
  (`references/approval-gates.md`, "Verify's changes, inside a track"); after
  "no" they stay in the working tree, `ship`'s Step 1 `clean_tree` check stops
  on the tracked ones, and the person commits

Evidence goes in the artifact this stage already produces, never pasted
in here. 4000 characters is the ceiling for this section: the largest
note any finished track has written is 1941 characters, measured across
30 rows in five tracks, and a report carries those fields plus what never
reaches that cell. The number is the user's call, 2026-09-08. A
`## Pending questions` section (`references/pending-questions.md`) sits
outside the ceiling -- a decision handed up has to carry its evidence.
