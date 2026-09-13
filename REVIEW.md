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

| # | Hunt item | This repo today | Example to point at |
|---|---|---|---|
| H1 | shell execution | zero: every `subprocess.run` under `plugins/cai/scripts/` passes an argv list | plugins/cai/scripts/ticket_backend.py:143 |
| H2 | what reaches the argument vector | `CAI_TICKET_CLI` can supply the whole executable path, or a whole JSON argv array | plugins/cai/scripts/ticket_backend.py:141, built by `_cli_prefix()` at :68-98 |
| H3 | secrets and payloads in what is kept | `classify()` folds raw stderr to one word because a 401 message carries a credential-bearing URL; `_argv_summary()` truncates each arg to 40 | plugins/cai/scripts/ticket_backend.py:46-50 and :104-118 |
| H4 | guard bypass | the refusal table is `CASES`, run row by row against the guard | scripts/validate.py:716-810, run at :821-823; the `^`-anchor bypass is recorded at :760-766 |

## No fifth item

Four is the list. Adding a fifth is a requirement decision, not a review
preference -- take it to a track, not to this table.
