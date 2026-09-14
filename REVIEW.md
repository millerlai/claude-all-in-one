# REVIEW.md -- this repo's review policy

Ours, not theirs: this file never installs anywhere. The shipped side must not
name it, per CLAUDE.md's "Who a file is for" -- a path into this repo's own
tree, written into a shipped file, claims every user has that path.

## The four passes

| Pass | What it hunts | Defined in |
|---|---|---|
| correctness | boundaries, leaked state, swallowed errors, assumed ordering | plugins/cai/skills/track/references/stage-verify.md |
| conformance | what was done that nothing asked for, and what was asked and skipped | plugins/cai/skills/track/references/stage-verify.md |
| coverage | for each behaviour change, a test that fails if the change is reverted | plugins/cai/skills/track/references/stage-verify.md |
| security | the four hunt items below, and no fifth | plugins/cai/skills/track/references/finding-severity.md |

## Where the four hunt items land in this repo

In `.claude/cai-review.md`, and only there. That is the path the security
lens reads (finding-severity.md's "When the repo under review keeps its own
review policy"); a copy here was the one it never saw, and its line numbers
had already drifted by the time anyone checked (2026-09-14).

## Review on pull requests

Deliberately not wired. The four lenses run in the `verify` stage on the
machine driving a track, on a subscription; a PR-triggered job would bill
every PR against an API key and needs a runner credential nobody has set
up. Measured 2026-09-13: one four-lens verify is about US$3.25 of
equivalent API spend, so roughly US$39 a month at this repo's merge rate --
the number a future issue would weigh, not this file.

## No fifth item

Four is the list. Adding a fifth is a requirement decision, not a review
preference -- take it to a track, not to that table.
