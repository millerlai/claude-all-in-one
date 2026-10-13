# Sample written by v1.53.0

What cai `v1.53.0` (commit `00a67c764a75aa92bd3c36d38297d28973b2b30b`) leaves
on disk partway through a track, generated on 2026-10-13 as the follow-up to
that release. The plugin was extracted with `git archive v1.53.0 plugins/cai`
and its own scripts were run from a scratch project root, with
`CLAUDE_CODE_SESSION_ID` unset and `CAI_USAGE_LEDGER` and `CLAUDE_CONFIG_DIR`
pointing into the scratch directory -- so no record holds a session id, a
token count or a local path.

Nothing here is edited once it is merged. `tests/test_upgrade_axis.py` reads
a copy; CONTRIBUTING.md, `### Upgrade-axis samples`, has the rules.

| File | Written by |
|---|---|
| `track/current` | hand: the feature name, which that tag's `skills/track/SKILL.md` (line 40) has the main session create |
| `track/export-csv/state.md` | hand: the table that tag's `skills/track/SKILL.md` (lines 41-42) specifies, with the rows its passing and skip paths write; carried over from v1.52.0; this tag keeps the wording for both files |
| `track/export-csv/ledger.jsonl` | `scripts/ledger.py append`, three times |
| `track/export-csv/pending.md` | `scripts/pending.py start`, then `scripts/pending.py answer` |
| `config/cai/model-choice.json` | `scripts/model_choice.py set` |

The commands, run from the project root with `T=.claude/track/export-csv`:

```
ledger.py append --track-dir $T --stage intake --outcome passed --artifact $T/intake.md --note "Goal and AC1-AC2 confirmed with the user."
ledger.py append --track-dir $T --stage discover --outcome skipped --artifact — --note "the request already names every unknown"
ledger.py append --track-dir $T --stage design --outcome failed --note "the stance doc left the separator undecided"
pending.py start --track-dir $T --stage design --round 1 --report-file ../_inputs/report.md
pending.py answer --track-dir $T --question 1 --answer-file ../_inputs/answer-1.md
model_choice.py set chore=sonnet think=fable
```

No command had to change from v1.52.0's.

`$T/intake.md` was a copy of `../_inputs/intake.md`, and the ledger's `sha256`
is of that file. It is not kept here.
