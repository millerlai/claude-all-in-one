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

Two trees ship: `plugins/cai/` to Claude Code (`.claude-plugin/marketplace.json`
points at `plugins/cai`), and `plugins/cai-codex/` to Codex
(`.agents/plugins/marketplace.json` points at `plugins/cai-codex`). Everything
else (`docs/`, `scripts/`, `tests/`, `.github/`, `.claude/skills/`, this file)
maintains the repo and never reaches an installed copy. Decide which side a
new file is on before writing it, not after.

`plugins/cai-codex/` is generated from `plugins/cai/` by `scripts/gen-codex.py`
and must not be hand-edited except its nine hand-written files:
`scripts/launcher.py`, `scripts/install_codex.py`, `skills/setup/SKILL.md`,
`skills/setup/agents/openai.yaml`, `skills/models/SKILL.md`,
`skills/models/agents/openai.yaml`, `skills/viewer/SKILL.md`,
`skills/viewer/agents/openai.yaml`, and `README.md` (the list is
`HAND_WRITTEN` in `scripts/gen-codex.py`). After changing
`plugins/cai/`, regenerate it (`python scripts/gen-codex.py`);
`validate.py` reports DRIFT when the generated tree is stale — just rerun
`python scripts/gen-codex.py`. `scripts/gen-codex.py` and its
`scripts/codex-*.json` data are Ours.

No PR changes `version` in `plugins/cai/.claude-plugin/plugin.json`;
`scripts/release.py` writes it when a release is cut (see CONTRIBUTING.md,
`## Releasing`).

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

A healthy run prints every line `PASS`, no `FAIL`, and exits 0.

Run `python -m pytest` too — the tests under `tests/`, which exercise
what the scripts in `plugins/cai/scripts/` actually do. `pyproject.toml`'s
`addopts` adds `-n auto`, which is what CI and `scripts/release.py`'s local
gate run too. It needs `pytest` and `pytest-xdist` installed
(`pip install pytest pytest-xdist`); without `pytest-xdist` pytest stops at once with
`error: unrecognized arguments: -n`. `--pdb` and `-s` need a single process:
add `-n0` when debugging.

[`CONTRIBUTING.md`](CONTRIBUTING.md) has sample healthy output for both, the
optional local `claude plugin eval` run (worth doing when a change touches
`plugins/cai/{skills,agents,hooks,rules,evals}/`; its `--output-dir` must
point outside the repo), releasing, and the maintainer tools.

You should rarely need to run `validate.py` by hand: `.claude/settings.json` registers a
`PostToolUse` hook that runs it whenever the **Edit or Write tool** touches
`plugins/cai/` or `.claude-plugin/`, and reports the failures. The matcher is
those two tools only — a file rewritten through Bash (redirection, a script,
`git apply`) does not trigger it, so run the script by hand after those. It goes through
`scripts/run-validate-hook.cmd`, the same polyglot launcher the shipped bash
guard uses, so it finds `py`/`python` on Windows and `python3`/`python`
elsewhere. Hook changes only take effect after a session restart. The hook
cannot block the edit — `PostToolUse` runs after the write — so it tells you
rather than stopping you.

Keep every `.cmd` file pure ASCII — CMD.exe reads them through the OEM codepage
and one multi-byte character mangles every line after it. `validate.py` checks.

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

## Mistakes Claude repeats here

<!-- Add an entry only once Claude makes the same mistake in this repo a
     second time. A mistake that would happen in any repo belongs in
     ~/.claude/rules/ instead. -->

- **Calling a PR done while its Linux CI is still running.** A green local
  run here is Windows only (see "Platform coverage"); Linux is covered by CI
  alone. #218 was handed off with CI pending and merged red. Before saying a
  PR is shipped, or merging it, wait until `gh pr checks <n>` finishes green.
- **A test that plants a fake executable as `git.bat`.** `shutil.which`
  finds a `.bat` only through Windows' PATHEXT, so on the Linux CI it found
  no `git` at all (#219). Write `git.bat` on Windows and, on POSIX, a file
  named `git` with a `#!/bin/sh` line and mode `0o755`; keep the assertion
  the same on both.
