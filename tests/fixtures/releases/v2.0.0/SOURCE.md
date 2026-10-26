# Sample written by v2.0.0

What cai `v2.0.0` (commit `e30c2f4da1a1909e544923a51fed94ec772dc468`) leaves
on disk partway through a track, generated on 2026-10-26 as the follow-up to
that release. The plugin was extracted with `git archive v2.0.0 plugins/cai`
and its own scripts were run from a scratch project root, with
`CLAUDE_CODE_SESSION_ID` and `CODEX_THREAD_ID` unset and `CAI_USAGE_LEDGER`
and `CLAUDE_CONFIG_DIR` pointing into the scratch directory, so no record
holds a session id, a token count or a local path.

Nothing here is edited once it is merged. `tests/test_upgrade_axis.py` reads
a copy; CONTRIBUTING.md, `### Upgrade-axis samples`, has the rules.

| File | Written by |
|---|---|
| `track/current` | hand: the feature name that this tag's `skills/track/SKILL.md` (line 40) has the main session create; copied unchanged from v1.59.0 |
| `track/export-csv/state.md` | hand: the table this tag's `skills/track/SKILL.md` (lines 41-42) specifies, one row per `stages.json` stage, so four rows (`design`, `build`, `verify`, `ship`) where v1.59.0's had six |
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

Two commands changed from v1.59.0's, and the output was not touched:

- This tag's `ledger.py` refuses `--stage intake` and `--stage discover`
  (`unknown stage: intake (expected one of design, build, verify, ship)`):
  #478 merged both into `design`. The two `append` lines for them are gone,
  so the ledger has one record where v1.59.0's had three, and `intake.md` is
  not needed as an artifact.
- This tag's `pending.py start` refuses a report whose question has no
  `Why asked:` line. `../_inputs/report.md` has none, so the run used
  `../_inputs/report-why-asked.md`, which is that file with one
  `Why asked: evidence-split` line added to each question.

The report and answer paths above refer to the fixture inputs; the commands
received their absolute paths without saving those paths in the output.
`answers.md`, which answering an `evidence-split` question appends to in the
scratch project, is not kept here.

This release merges the intake, discover and design stages, so a track's
`state.md` has four rows and its ledger no longer takes two of the stage names
v1.59.0's did. Its track skill changed, so the release procedure calls for a
new sample; it was generated afresh with this tag's scripts rather than
copying the previous release's generated files.
