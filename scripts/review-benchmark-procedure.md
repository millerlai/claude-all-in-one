# review-benchmark-procedure — how to turn one case into a scoreable run

Follow these nine steps verbatim to turn one case directory under
`tests/review-benchmark/` into a `findings.json` the scorer
(`scripts/review_benchmark_score.py`) accepts. This is the only part of the
benchmark that costs money and the only part that is non-deterministic
(dispatching the four lens agents); everything before and after it is a
plain file operation.

`findings.json`'s shape is defined in `scripts/review_benchmark_score.py`'s
module docstring and in the design doc
(`docs/design/2026-09-14-gap03-review-benchmark-detail.md`, "計分器" →
"Data — `findings.json` 的形狀"). It is never committed: it is one run's
record, not part of the collection, and lives in the scratchpad.

1. Pick a case directory. Read its `expected.json`. Note `base_sha` and
   `base_ref`.

2. Move the working tree to the base version: `git checkout <base_sha>`, or
   `git worktree add` a separate tree for it. **`diff.patch` is never
   applied.** Per decision one (D11 in the detail design), `base_sha`'s tree
   already carries the defect -- the stored patch is only text to paste into
   the dispatch message so the lens can read it. This step must never
   contain a patch-apply command; only a future *constructed* sample (none
   exist this round) would add an apply step after checkout. If the working
   tree is dirty, stop here rather than checkout over it -- this repo's bash
   guard has refused a `git checkout` against a dirty tree before
   (`.claude/track/done/pb04-security-lens/implementation-notes.md:74-83`).

3. In one message, dispatch four subagents: three `reviewer` agents, one
   lens each (`correctness`, `conformance`, `coverage`), plus one
   `security-reviewer` for the fourth
   (`plugins/cai/skills/track/references/stage-verify.md:44-48`). Each
   dispatch message carries three things: this case's diff, the lens it is
   reviewing with, and the requirement it is checking against -- the
   `conformance` lens is useless without that last one
   (`stage-verify.md:57-60`). Give `security-reviewer` the four hunt items
   from `finding-severity.md` instead (`:64-66`).

4. In that same dispatch message, additionally ask each lens to append a
   fenced JSON block, with the same fields as a `findings` record, after its
   prose report. This is the zero-cost probe for whether a dispatch message
   alone can carry a structured-output request; it is never a source of any
   score this round (decision one).

5. Once the four reports come back, transcribe every finding: one record
   per finding, noting `lens`, `file`, `line`, `severity`, `cause`. The
   prose gives `file:line` (`plugins/cai/agents/reviewer.md:15`), so `line`
   is a single number, not a range.

6. Record what each lens actually returned into `lens_runs`: one of
   `answered` / `empty` / `failed`, plus the verbatim text of its trailing
   "what this didn't cover" line. An empty lens is an explicitly allowed
   result (`reviewer.md:22`) -- so "the dispatch failed" and "it genuinely
   found nothing" must be recorded separately here, or the two-run variance
   this benchmark measures would count a failed dispatch as model
   instability.

7. Restore the working tree. This repo has a recorded precedent for the
   same shape of operation, including why it used `git stash` rather than
   `git checkout` to restore
   (`.claude/track/done/pb04-security-lens/implementation-notes.md:74-83`):
   the bash guard refuses a `git checkout` against a dirty tree.

8. Repeat steps 2-7 a second time, on the same case (the benchmark scores
   every case twice).

9. Run the scorer and paste its report into the measurement doc
   (`docs/design/2026-09-14-gap03-review-benchmark-measurement.md`).

## Errors

- **A lens doesn't come back.** Record `failed` in `lens_runs` for it and
  keep going through the other three -- do not redispatch it. Redispatching
  until it succeeds would turn "this run's result" into "the result after
  retrying until it worked," which is a different (and dishonest) thing to
  measure.
- **The base version can't be resolved.** Stop at step 2. Record this case
  as unrunnable for this pass. Do not substitute an approximate version.
