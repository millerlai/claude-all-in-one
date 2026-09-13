# Working on this repo

Bias toward caution over speed. For trivial tasks, use judgment.

The rules below are the same files the plugin ships to users, imported from
their single source of truth so editing them here changes what users get.

@plugins/cai/rules/epistemics.md
@plugins/cai/rules/coding.md
@plugins/cai/rules/workflow.md
@plugins/cai/rules/model-selection.md
@plugins/cai/rules/memory.md
@plugins/cai/rules/documentation.md
@plugins/cai/rules/option-explainer.md

`communication.md` is deliberately not imported: the shipped copy defaults to
English, while the response language belongs to whoever is working — it is set
per-user in `~/.claude/rules/` by `/cai:setup`.

## Who a file is for

`plugins/cai/` is the only thing that ships — `.claude-plugin/marketplace.json`
names `./plugins/cai` as the plugin's source and nothing else. Everything
outside it (`docs/`, `scripts/`, `tests/`, `.github/`, `.claude/skills/`, this
file) maintains the repo and never reaches an installed copy. Decide which side a new file is on
before writing it, not after.

**Theirs** is an agent, skill, rule, template, or a script some shipped
component actually invokes. It runs on a machine we will never see, against a
repo we know nothing about, and `/plugin update` overwrites it — so it may not
assume this repo's layout, and a maintainer tool nothing invokes does not
belong there however convenient the path is.

**Ours** is validation, tests, CI, design records, and codegen we run by hand.
It may assume this repo's layout, and it stays out of `plugins/cai/`.

Maintainer-side skills belong to that side too: a procedure we run *on this
repo* — `/gap-analysis`, which compares cai against an external practice and
writes the result under `docs/design/` — lives in `.claude/skills/<name>/`,
which Claude Code loads for this project only. It may name this repo's paths
freely and is tracked in git. A skill users should receive goes under
`plugins/cai/skills/` instead, and must not assume any of this.

**Shipped but not theirs** is a third thing: a file that reaches every
installed copy and yet no shipped component ever invokes, because the tool
that reads it refuses to look anywhere but under `plugins/cai/`. The eval
suite is today's only one — `claude plugin eval` rejects an eval directory
outside the plugin root, so the cases ship whether or not anyone runs them.
This is not an escape hatch: it covers only what an external tool's own path
rule forces into the shipping package, and it may no more assume this repo's
layout than Theirs may. Anything that could just as well live under
`scripts/` or `tests/` is Ours and stays out.

The Theirs/Ours split governs what a shipped file may *say*, not just where it sits.
`/cai:setup` copies `plugins/cai/rules/` into the user's `~/.claude/rules/`,
where it loads every session — so a sentence there spends every user's tokens
on every turn and must be about their work. A path into this repo's own
tooling, or an instruction only a maintainer could act on, is a defect there
even though nothing fails.

Not everything belongs in git. `docs/` and `.claude/track/` are ignored on
purpose; a document worth keeping is added deliberately with `git add -f`,
and working notes, scratch output and per-track state are not.

## Environment
- Windows, I usually work in Python.
- Avoid PowerShell for text processing on files containing UTF-8/Chinese characters;
  use direct Edit/Write tools to prevent character corruption.

## Before pushing
Run `python scripts/validate.py` — it checks the manifests, every component's
frontmatter, and that the bash guard still blocks what it should, plus the
repo's own prose against claims it makes about itself, by calling
`plugins/cai/scripts/provenance.py` against `docs/rule-provenance.md`:
whether every entry's citations still resolve, and whether any entry's
`Restated in:`/`Shared value:` lines still hold. Pinning a second restated
rule is two more ledger lines, not new code. The same script also runs
unconditionally in `/cai:track`'s `verify` stage, since it ships under
`plugins/cai/scripts/`.

Editing any rule sentence that `docs/rule-provenance.md` cites (a `Cited by:`
target) must update that ledger entry in the same edit.

Run `python -m pytest` too — the tests under `tests/`, which exercise what the
scripts in `plugins/cai/scripts/` actually do. It needs `pytest` installed
(`pip install pytest`), this repo's only development-time dependency. `tests/`
sits at the repo root rather than under `plugins/cai/` so that neither it nor
pytest ever reaches an installed copy: `.claude-plugin/marketplace.json:11`
ships `./plugins/cai` and nothing else.

You should rarely need to run it by hand: `.claude/settings.json` registers a
`PostToolUse` hook that runs it whenever the **Edit or Write tool** touches
`plugins/cai/` or `.claude-plugin/`, and reports the failures. The matcher is
those two tools only — a file rewritten through Bash (redirection, a script,
`git apply`) does not trigger it, so run the script by hand after those. It goes through
`scripts/run-validate-hook.cmd`, the same polyglot launcher the shipped bash
guard uses, so it finds `py`/`python` on Windows and `python3`/`python`
elsewhere. Hook changes only take effect after a session restart.

Keep every `.cmd` file pure ASCII — CMD.exe reads them through the OEM codepage
and one multi-byte character mangles every line after it. `validate.py` checks.
The hook cannot block the edit — `PostToolUse` runs after the write — so it
tells you rather than stopping you.

No text file may start with a UTF-8 BOM, and `validate.py` checks that too. A
BOM is invisible in an editor but the three bytes are still the start of the
file: `mermaid-cli` rejects a diagram outright with `Parse error on line 1`,
and CMD.exe prints them before the first line runs. PowerShell's `>`, `>>` and
`Out-File` write one by default here — which is the same reason the Environment
note above says to reach for Edit/Write instead of redirecting into a file.

Changing the guard means adding a case to `CASES` in `scripts/validate.py`.
That file and `tests/` are the two places this repo keeps tests: `validate.py`
checks the plugin's shape and the guard, `tests/` checks what the scripts do.

Platform coverage: Linux is covered by CI on every PR, which runs both
`validate.py` and `pytest`. Windows is covered only by the developer running
both by hand, as described above. macOS has no coverage at all.

Running `python plugins/cai/scripts/context_peak.py --track-dir .claude/track/<feature>`
prints that track's main-session peak context occupancy; it only reads local
transcripts and writes nothing.
