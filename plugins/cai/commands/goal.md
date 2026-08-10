---
description: "Review a design doc, implement it, then verify — three phases, each on the model suited to the work. Usage: /cai:goal <path to design/plan doc>"
argument-hint: "<path to design/plan doc>"
---

Take this design/plan doc from requirement to verified implementation: $ARGUMENTS

Work through the three steps in order. Each step runs at a different model
tier on purpose — do not skip a step or collapse them into one pass.

## Step 1 — Review the design document (this session's own model)

Invoke the `plan-review` skill against the doc. This step runs inline, at
whatever model this session is already on — do not dispatch a subagent for it.

- Blocker/Major findings that are objective errors in the doc → fix the doc
  directly, then re-run `plan-review`'s Step 1 on the fixed version, per its
  own "Folding it back" rule.
- Section 4 ("requirement decisions to confirm") → surface these with
  `AskUserQuestion` and wait for an answer. Never resolve them yourself —
  that section exists specifically so scope decisions aren't made silently.
- If `plan-review`'s Step 0 gate fails (no stated requirement, or no
  acceptance criteria), stop and ask for whichever is missing. Do not move to
  Step 2 against a doc that isn't reviewable yet.

## Step 2 — Implement, then check the code against the design (Sonnet)

Dispatch the `cai:implementer` agent (model: sonnet — well-specified, scoped
feature work) with the corrected design doc as its spec. It starts with no
context of this conversation, so give it the doc's content or path plus the
specific files/behaviors it names — not just "see the plan."

Once it returns, invoke the `diff-review` skill, passing the design doc as
the requirement for its `conformance` lens. This dispatches three `reviewer`
agents (model: sonnet, pinned in their own definition) in parallel.

- Fix Blocker/Major findings per `diff-review`'s own "Fixing" section:
  failing test first, then the fix, then show it passing.
- If findings remain, run one more implementer → diff-review round at most.
  If issues are still open after that, stop and report them rather than
  looping further.
- Leave Minor findings documented and unfixed unless asked.

## Step 3 — Verify (Haiku for the automated part, inline for the rest)

Dispatch the `cai:test-runner` agent (model: haiku — mechanical test
execution and reporting) to run every automated test/check this repo already
has, and report pass/fail.

Then, inline at this session's own model:

- Confirm the data and preconditions the design doc needs to execute are
  actually present, and say what was checked and how.
- Write the final report:
  - what was fixed in the design doc (Step 1)
  - what was implemented, file by file (Step 2)
  - the `diff-review` verdict and any open Minor findings
  - the `test-runner` results
  - a **Manual verification** section: concrete, numbered steps for whatever
    could not be automated

Do not report the goal as complete until this report exists. Don't claim
something works without having actually run it.
