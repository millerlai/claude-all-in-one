# Rule provenance ledger

Scope: hard rules in this repo's always-on prose (`plugins/cai/rules/*.md`,
`CLAUDE.md`) or in its standing procedures (`plugins/cai/skills/**`) that
were born from a real failure -- a concrete incident that cost a correction
round, traceable to a commit, an issue, or a `file:line`. A preference with
no failure behind it does not belong here, however reasonable it sounds.

A rule not being in this ledger does not mean it lacks value or grounding --
it only means nobody has yet written down the failure that produced it, or
the rule was a preference from the start.

Writing convention: keep each entry's rule sentence on one line.
`provenance_entries()` splits this file on lines that start with `## `, so a
rule sentence that pastes in a full line starting that way -- quoting a
heading, or a fenced code block that contains one -- gets misread as the
start of a new, fieldless entry and fails the ledger's own checks.

## subagent-parallel-cap — parallel subagent limit of 2-3

- Date: 2026-08-29
- Failure: source unverifiable. `docs/design/2026-08-29-capability-gap-analysis.md:112` records that a repo-wide search for `429` (the rate-limit HTTP status the rule's own wording names) turns up only the rule sentence itself -- no commit, issue, or session record ties this cap to a specific incident in this repo's tracked history; the line has been present since the repo's first commit (415da10) with no earlier history to trace. Kept in the ledger anyway because UC2's derivation depends on an entry citing this heading, not because a source was found -- see the ledger's own scope note above.
- Rule: Use at most 2-3 subagents in parallel; prefer sequential execution with worktrees for large multi-file tasks to avoid rate-limit failures.
- Cited by: plugins/cai/rules/model-selection.md § Subagents

## epistemics-one-decision-per-turn — ask one decision at a time

- Date: 2026-09-03
- Failure: commit 606f2a0 ("feat(cai): ask one decision at a time, through the question tool (#52)"). Before this commit, nothing in the shipped rules said how many decisions could ride in one turn or which tool to ask through, so the default behaviour was several questions per turn, each in a different shape, all of them prose the reader had to type a reply to.
- Rule: One decision per turn. Several pending ones queue: ask the one that constrains the rest, act on the answer, then ask the next. A turn carrying two questions carries none — the second gets answered against a guess about the first.
- Cited by: plugins/cai/rules/epistemics.md § How to ask, once you have to

## epistemics-question-not-decision — a question is not a decision

- Date: 2026-08-30
- Failure: commit 3ca4973 ("fix(cai): narrow the build gate, and close four unguarded failures (#45)"), found by reading a month of session telemetry against what the plugin actually ships. Advice and comparison questions ("what are my options", "which X should I use") were being turned into a question-tool prompt instead of being answered in prose.
- Rule: A question is not a decision. Advice, comparison, "what are my options", "which X should I use" — answer in prose, with a recommendation and why. Reaching for a question tool, a brainstorming pass, or any multi-step workflow instead answers nothing and costs a turn; do it only when asked, or when that work is under way.
- Cited by: plugins/cai/rules/epistemics.md § When to stop and ask

## epistemics-half-the-gate — working is only half the gate

- Date: 2026-07-26
- Failure: commit e2d8738 ("docs: require spec conformance check before claiming done"). Completion was gated only on "does it build and pass tests" -- nothing required mapping the result back to what was actually asked for, so a change could pass its own tests while still not matching the request.
- Rule: Working is only half the gate; matching what was asked is the other half. Restate the design — spec, plan, issue, or my original request, whichever exists — as a checklist and point each item at the code that satisfies it (file:line). Report anything unimplemented, partially done, or built differently rather than declaring it done.
- Cited by: plugins/cai/rules/epistemics.md § Verification & Completion

## option-explainer-shared-dimensions — name the axes before the options

- Date: 2026-08-29
- Failure: commit df89a20 ("feat(cai): give options a fixed shape, so a reader can actually compare them (#42)"). A reply that lists "option A / B / C" is usually unreadable for a reason that is not missing information: each option was described on its own selling points, so every paragraph made sense on its own and none of them could be compared against the others.
- Rule: Name 2-4 comparison dimensions first, then the options. Describe every option on the same ones; "not applicable" needs a reason, not a blank.
- Cited by: plugins/cai/rules/option-explainer.md § Before the list

## option-explainer-gloss-bare-code — gloss bare option codes too

- Date: 2026-08-30
- Failure: commit 3ca4973 ("fix(cai): narrow the build gate, and close four unguarded failures (#45)"). The glossing rule df89a20 shipped covered terms, abbreviations, and package names, but not a bare option code like `A1` -- readers hit the same unglossed-jargon problem one level lower, at the label rather than the term.
- Rule: Gloss every term, abbreviation, package name and bare code (`A1`) on first use, in words that introduce no new term. A gloss needing its own is not one.
- Cited by: plugins/cai/rules/option-explainer.md § Before the list

## stage-build-no-design-edit — the schedule table never lives in the design document

- Date: 2026-09-07
- Failure: commit 6207ef8 ("fix(cai): stop stage-build sending the build stage into the signed-off design (#71)"). Step 1 used to send the build stage into the signed-off design document to record its schedule/progress columns there; `artifact_unchanged` hashes that document against the digest recorded at sign-off, so that edit made every later `preflight.py build` exit 2, including the resumed run the schedule table exists to serve.
- Rule: This whole table lives in implementation-notes.md, never in the design document itself.
- Cited by: plugins/cai/skills/track/references/stage-build.md § Step 1 — Turn the schedule into a state table

## stage-build-no-traceability-edit — the traceability table never lives in the design document

- Date: 2026-09-07
- Failure: commit 6207ef8 ("fix(cai): stop stage-build sending the build stage into the signed-off design (#71)"). Step 6.1 had the same defect as Step 1, on the same document, for the traceability table this time -- filling it back into the design's own `### Traceability` section tripped `artifact_unchanged` the same way.
- Rule: It goes in implementation-notes.md and the report, never back into the design document's own ### Traceability, for the reason Step 1 gives.
- Cited by: plugins/cai/skills/track/references/stage-build.md § Step 6 — Close it out

## model-selection-free-layer-first — make the free layer bigger before routing by judgement risk

- Date: 2026-08-27
- Failure: commit 73d0a3a ("docs(cai): add the layer that costs nothing to model-selection"). The rule described three tiers and all three spent model tokens; the layer underneath -- work a deterministic check settles, at zero cost -- was missing from the always-on prose even though design_probe.py, preflight.py, track_state.py and validate.py were already doing exactly that job.
- Rule: Make the free layer bigger before routing what's left by judgement risk. Moving a judgement call down a paid tier to save money, before asking whether it needed a model at all, is the mistake to avoid.
- Cited by: plugins/cai/rules/model-selection.md § Layers, cheapest first
