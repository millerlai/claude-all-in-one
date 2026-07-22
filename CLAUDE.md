# Working on this repo

Bias toward caution over speed. For trivial tasks, use judgment.

The rules below are the same files the plugin ships to users, imported from
their single source of truth so editing them here changes what users get.

@plugins/ml-workflow/rules/epistemics.md
@plugins/ml-workflow/rules/coding.md
@plugins/ml-workflow/rules/workflow.md
@plugins/ml-workflow/rules/model-selection.md
@plugins/ml-workflow/rules/memory.md
@plugins/ml-workflow/rules/documentation.md

`communication.md` is deliberately not imported: the shipped copy defaults to
English, while the response language belongs to whoever is working — it is set
per-user in `~/.claude/rules/` by `/ml-workflow:setup`.

## Environment
- Windows, I usually work in Python.
- Avoid PowerShell for text processing on files containing UTF-8/Chinese characters;
  use direct Edit/Write tools to prevent character corruption.

## Before pushing
Run `python scripts/validate.py` — it checks the manifests, every component's
frontmatter, and that the bash guard still blocks what it should.
