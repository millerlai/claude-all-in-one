# Sample written by v2.4.0

What cai `v2.4.0` (commit `a81946c44668740634eaedf66d1462ced297243c`) leaves
on disk partway through a track, generated on 2026-11-27 as the follow-up to
that release. The plugin was extracted with `git archive v2.4.0 plugins/cai`
and its own scripts were run from a scratch project root, with
`CLAUDE_CODE_SESSION_ID` and `CODEX_THREAD_ID` unset and `CAI_USAGE_LEDGER`
and `CLAUDE_CONFIG_DIR` pointing into the scratch directory, so no record
holds a session id, a token count or a local path.

Nothing here is edited once it is merged. `tests/test_upgrade_axis.py` reads
a copy; CONTRIBUTING.md, `### Upgrade-axis samples`, has the rules.

| File | Written by |
|---|---|
| `track/current` | hand: the feature name that this tag's `skills/track/SKILL.md` (line 40) has the main session create; copied unchanged from v2.0.0 |
| `track/export-csv/state.md` | hand: the table this tag's `skills/track/SKILL.md` (lines 40-42) specifies, one row per `stages.json` stage (`design`, `build`, `verify`, `ship`); copied unchanged from v2.0.0 |
| `track/export-csv/ledger.jsonl` | `scripts/ledger.py append`, once |
| `track/export-csv/pending.md` | `scripts/pending.py start`, then `scripts/pending.py answer` |
| `config/cai/model-choice.json` | `scripts/model_choice.py set`, including a saved effort |

The commands, run from the scratch project root with
`T=.cai/track/export-csv`:

```
ledger.py append --track-dir $T --stage design --outcome failed --note "the stance doc left the separator undecided"
pending.py start --track-dir $T --stage design --round 1 --report-file ../_inputs/report-why-asked.md
pending.py answer --track-dir $T --question 1 --answer-file ../_inputs/answer-1.md
model_choice.py set chore=sonnet think=fable chore.effort=low
```

These are v2.0.0's commands, unchanged. CONTRIBUTING's listing still starts
with `intake` and `discover` appends and passes `../_inputs/report.md`; this
tag's `ledger.py` refuses those stages (`unknown stage: intake (expected one
of design, build, verify, ship)`) and its `pending.py start` needs the
`Why asked:` lines of `report-why-asked.md`, as v2.0.0's `SOURCE.md`
explains. The output was not touched.

The report and answer paths above refer to the fixture inputs; the commands
received their absolute paths without saving those paths in the output.
`answers.md`, which answering an `evidence-split` question appends to in the
scratch project, is not kept here.

Since v2.0.0 this tag's track skill changed how stages run (the main session
runs `design`, `verify` and `ship` itself) and `ledger.py` changed one
comment; neither changed what `state.md` or `current` hold, and every file
here except the ledger's timestamp is byte-identical to v2.0.0's. The track
skill's diff is what makes the release procedure call for a new sample.
