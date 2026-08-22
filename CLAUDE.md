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

`communication.md` is deliberately not imported: the shipped copy defaults to
English, while the response language belongs to whoever is working — it is set
per-user in `~/.claude/rules/` by `/cai:setup`.

## Environment
- Windows, I usually work in Python.
- Avoid PowerShell for text processing on files containing UTF-8/Chinese characters;
  use direct Edit/Write tools to prevent character corruption.

## Before pushing
Run `python scripts/validate.py` — it checks the manifests, every component's
frontmatter, and that the bash guard still blocks what it should.

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
It is the only test this repo has.
