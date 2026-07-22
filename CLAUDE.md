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
