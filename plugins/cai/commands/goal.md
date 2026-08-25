---
description: "Review a design doc, then route it: a document with a work breakdown schedule goes to build-from-design unit by unit, everything else goes to a single implementer — both lanes converge on the same test-and-report step. Usage: /cai:goal <path to design/plan doc>"
argument-hint: "<path to design/plan doc>"
---

Take this design/plan doc from requirement to verified implementation: $ARGUMENTS

Step 1 always runs, and can end the run two ways — its gate fails, sending
you to Step 2, or its findings outlast three rounds. Otherwise Step 3 picks
a lane and Step 4 closes out, at tiers the skills set, not anything here.

## Step 1 — Review the design document

Decide the skeleton first: a document carrying a `## Work breakdown` or
`## Implementation spec` heading is `detail`, otherwise `hld`. Invoke the
`plan-review` skill against the doc, passing both the doc and that skeleton.
The second argument is not optional — `plan-review` runs lens 8 first for a
detail design (`plugins/cai/skills/plan-review/SKILL.md:71-74`), and without
it that rule never fires.

- Blocker/Major findings that are objective errors in the doc → fix the doc
  directly, then re-run `plan-review`'s Step 1 on the fixed version, per its
  own "Folding it back" rule.
- Section 4 ("requirement decisions to confirm") → surface these with
  `AskUserQuestion` and wait for an answer. Never resolve them yourself —
  that section exists specifically so scope decisions aren't made silently.
- **At most three rounds of fix-and-recheck.** Findings open after the third
  end the run — report them rather than implementing against them.
- If `plan-review`'s Step 0 gate fails (no stated requirement, or no
  acceptance criteria), go to the next step below instead of testing for a
  schedule against a doc that isn't reviewable yet.

This step runs on Opus at high effort: `plan-review` pins `model: opus,
effort: high` in its own frontmatter (`plugins/cai/skills/plan-review/SKILL.md:4-5`),
and a skill's model override holds for the rest of this turn. The real
trajectory through this file: `plan-review` (opus/high) → routing →
`build-from-design` (sonnet/medium) → the shared verification step (sonnet
on that lane; still opus/high on the other, where nothing overrides it).

## Step 2 — When the doc isn't reviewable yet

`plan-review`'s Step 0 gate failed: no stated requirement, or no acceptance
criteria. Ask with `AskUserQuestion`, two options — produce a high-level
design now, or stop and fill the gap yourself. Say plainly, before the user
answers, that choosing the first option ends this run either way:
`/cai:design-high-level-doc` hands back a document with `## Status: draft`,
and only the user can turn that into `approved`.

Agree → invoke the `/cai:design-high-level-doc` command with the user's own
requirement text, then stop. Decline → stop and say which of the two —
requirement or acceptance criteria — was missing. Non-interactive (`-p`)
mode, where the question can't be answered → the same fallback as decline.

Do not fall back to a lane below either way. A doc with no stated
requirement has nothing for either lane to build against.

## Step 3 — Which lane

Read `## Work breakdown`: does it have data rows — rows other than the
separator, with `Depends on` filled in? No table, or a table with only its
header, means no schedule. This criterion is copied verbatim from
`plugins/cai/skills/build-from-design/SKILL.md:32-34`, not invented here — if
this file were looser than the gate it hands off to, the user would get a
hand-off immediately followed by a rejection.

Put the result and its basis (how many data rows were found) into the final
report, so the user can see why a lane was chosen. This differs from Step 1's
skeleton decision — skeleton looks at whether headings exist, this looks at
whether the table under one has rows — so a document with the heading and an
empty table correctly gets `skeleton: detail` plus the whole-document lane.

### The unit-by-unit lane — data rows found

Invoke the `build-from-design` skill with the document path and the target
project directory. **This lane does not invoke `diff-review` and does not
write its own report.** Both happen inside that skill's own Step 6
(`plugins/cai/skills/build-from-design/SKILL.md:276-285`); running either
again here would duplicate its close-out.

If that skill's own Step 0 gate fails on any of its four checks, stop and
relay the rejection verbatim. **Do not fall back to the whole-document
lane** — each failure means the design document genuinely has a hole;
building it whole-document just covers the hole with one large diff. Do not
open git worktrees here — if `build-from-design` runs two units in
parallel, that is its own business.

### The whole-document lane — no data rows

Dispatch the `cai:implementer` agent with the design doc as its spec. It
starts with no context of this conversation, so give it the doc's content or
path plus the specific files/behaviors it names — not just "see the plan."
Once it returns, invoke the `diff-review` skill, passing the design doc as
the requirement for its `conformance` lens.

Fix Blocker/Major findings per `diff-review`'s own "Fixing" section: failing
test first, then the fix, then show it passing. If findings remain, run one
more implementer → diff-review round at most; if still open after that, stop
and report rather than looping further. Leave Minor findings documented and
unfixed unless asked. This lane's behavior is unchanged from before this
rewrite — only which lane it belongs to is now explicit.

## Step 4 — The shared verification step

Both lanes arrive here. Dispatch the `cai:test-runner` agent to run every
automated test/check the target repo already has — do not hardcode a
specific command; this file ships to any repo. Report pass/fail with the
real output; if no automated tests exist, say so rather than leaving the
section blank.

Then write one report with exactly five sections: what was fixed in the
design doc (Step 1); what was implemented — file by file on the
whole-document lane, or the unit-by-unit lane's own per-unit landings,
traceability table, and deviations, quoted rather than rewritten; the
review verdict and any open Minor findings — `diff-review`'s on the
whole-document lane, `build-from-design`'s Step 6 verdict on the other; the
`test-runner` results; and a **Manual verification** section of concrete,
numbered steps for whatever could not be automated.

Do not report the goal as complete until this report exists. Don't claim
something works without having actually run it.
