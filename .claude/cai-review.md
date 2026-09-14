# cai-review.md -- where the security lens's four hunt items land in this repo

Read by `security-reviewer` through
`plugins/cai/skills/track/references/finding-severity.md`'s "When the repo
under review keeps its own review policy": where each of the four items
lands here and one example to point at, and nothing else. It adds no fifth
item and does not change what Blocker, Major and Minor mean. Ours, not
theirs: `.claude/` is this repo's own tree and never installs anywhere.

Line numbers are checked by hand when this file changes, nothing pins them
(verified 2026-09-14 against `main` at 913c721).

| # | Hunt item | This repo today | Example to point at |
|---|---|---|---|
| H1 | shell execution | zero: every `subprocess.run` under `plugins/cai/scripts/` passes an argv list | plugins/cai/scripts/ticket_backend.py:143 |
| H2 | what reaches the argument vector | `CAI_TICKET_CLI` can supply the whole executable path, or a whole JSON argv array | plugins/cai/scripts/ticket_backend.py:141, built by `_cli_prefix()` at :68-98 |
| H3 | secrets and payloads in what is kept | `classify()` folds raw stderr to one word because a 401 message carries a credential-bearing URL; `_argv_summary()` truncates each arg to 40 | plugins/cai/scripts/ticket_backend.py:46-50 and :104-118 |
| H4 | guard bypass | the refusal table is `CASES`, run row by row against the guard | scripts/validate.py:739-833, run at :844-846; the `^`-anchor bypass is recorded at :783-789 |
