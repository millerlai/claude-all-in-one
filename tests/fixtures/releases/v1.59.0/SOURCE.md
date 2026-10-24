# Sample written by v1.59.0

What cai `v1.59.0` (commit `a8d91e0b95a0c90e3891fbefd6e734e908a7a967`) leaves
on disk partway through a track, generated on 2026-10-22 as the follow-up to
that release. The plugin was extracted with
`git archive --format=zip v1.59.0 plugins/cai` and its own scripts were run
from a scratch project root, with `CLAUDE_CODE_SESSION_ID` and
`CODEX_THREAD_ID` unset and `CAI_USAGE_LEDGER` and `CLAUDE_CONFIG_DIR` pointing
into the scratch directory, so no record holds a session id, a token count
or a local path.

Nothing here is edited once it is merged. `tests/test_upgrade_axis.py` reads
a copy; CONTRIBUTING.md, `### Upgrade-axis samples`, has the rules.

| File | Written by |
|---|---|
| `track/current` | hand: the feature name that this tag's `skills/track/SKILL.md` (line 40) has the main session create; copied unchanged from v1.58.0 |
| `track/export-csv/state.md` | hand: the table this tag's `skills/track/SKILL.md` (lines 41-42) specifies; copied unchanged from v1.58.0 because the state and current-file instructions did not change |
| `track/export-csv/ledger.jsonl` | `scripts/ledger.py append`, three times |
| `track/export-csv/pending.md` | `scripts/pending.py start`, then `scripts/pending.py answer` |
| `config/cai/model-choice.json` | `scripts/model_choice.py set`, including a saved effort |

The commands, run from the scratch project root with
`T=.cai/track/export-csv`, are unchanged from v1.58.0:

```
ledger.py append --track-dir $T --stage intake --outcome passed --artifact $T/intake.md --note "Goal and AC1-AC2 confirmed with the user."
ledger.py append --track-dir $T --stage discover --outcome skipped --artifact — --note "the request already names every unknown"
ledger.py append --track-dir $T --stage design --outcome failed --note "the stance doc left the separator undecided"
pending.py start --track-dir $T --stage design --round 1 --report-file ../_inputs/report.md
pending.py answer --track-dir $T --question 1 --answer-file ../_inputs/answer-1.md
model_choice.py set chore=sonnet think=fable chore.effort=low
```

The report and answer paths above refer to the fixture inputs; the commands
received their absolute paths without saving those paths in the output.
`$T/intake.md` was a copy of `../_inputs/intake.md`, and the ledger's `sha256`
is of that file. It is not kept here.

This release changes how tracks use worktrees, but keeps the saved formats.
Its track skill changed, so the release procedure calls for a new sample;
it was generated afresh with this tag's scripts rather than copying the
previous release's generated files.
