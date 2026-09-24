---
name: models
description: Show or change which model each cai role (chore, build, think) runs on, without re-running $setup. Run $models to review and switch, $models <role> <model> to set one role, or $models reset <role> to put it back on cai's default.
---

Change which model cai's roles run on without reinstalling anything. `$setup`
installs cai; this only rewrites the model lines of the agents it installed.
Work through the steps in order and stop with a clear report if any step
fails.

## Step 1 — Resolve `<cai-root>` and read the request

This file lives at `<cai-root>/skills/models/SKILL.md`. Resolve `<cai-root>`
as two directories up from the absolute path you read this file from.

Then read what the user asked for, from the words after `$models`:

- nothing — show the mapping and offer to switch it;
- `<role> <model>`, such as `think gpt-6-astra` — set that one role;
- `reset <role>` — put that one role back on cai's default.

A role is `chore`, `build` or `think`. For anything else, list the three
forms above and stop.

## Step 2 — Read the mapping

This step writes nothing. Try interpreters in this order until one runs the
installer successfully. Never use `python3` or a bare `py` on Windows — both
can resolve to a broken stub there.

- macOS or Linux: `python3`, then `python`.
- Windows: `python`, then `py -3`.

macOS or Linux:

```
<interpreter> "<cai-root>/scripts/install_codex.py" --models
```

Windows — run it through this pipeline so the output shows up:

```
& { & <interpreter> "<cai-root>/scripts/install_codex.py" --models 2>&1 | ForEach-Object { "$_" }; exit $LASTEXITCODE }
```

If every interpreter in the list fails, stop and quote the last failure to
the user rather than guessing what went wrong. Otherwise read the mapping
block out of the output, as `<cai-root>/skills/setup/SKILL.md`'s "Read the
mapping block" section describes. Show the user the `role <role>: ...` lines
as the current mapping, and every `ask again <role>:` and `not offered
<role>:` line verbatim.

## Step 3 — Decide the answers

- **No arguments.** Follow `<cai-root>/skills/setup/SKILL.md`'s "Ask what
  the `ask:` line says to ask" section exactly, menus included.
- **`<role> <model>`.** That role's answer is `<model>`; ask nothing. If the
  `models:` line says detection failed, tell the user this cannot check a
  typed name against their account, and carry on.
- **`reset <role>`.** Read that role's `role <role>: ...` line. If its tag is
  plain `(cai default)`, the role is already on cai's default: say so and
  stop. Otherwise the tag reads `(saved; cai default <default>)`, and that
  role's answer is `<default>`.

If no role ended up with an answer, stop here and write nothing.

## Step 4 — Apply the answers

What follows writes into `$CODEX_HOME`, outside the workspace, so ask the
user to approve running it outside the sandbox before writing anything.

Write the answers file with the file-edit tool at the exact path from the
`answers file:` line:

```
{"format": 1, "roles": {"<role>": "<slug>", ...}}
```

with one entry per role that has an answer. Then run the installer again with
`--apply` in place of `--models`, using the same interpreter that just
succeeded — on Windows, `--apply` still goes before the `2>&1` pipe segment.

If this run exits non-zero, quote its output to the user and stop. Do not
retry it with another interpreter: it is the answers that failed, not the
interpreter. Otherwise read this run's own `role <role>: ...` lines: a role
now on a model of its own reads `saved; cai default <default>`, and a role
back on cai's default reads plain `cai default`.

## Step 5 — Report

Report concisely:

- The `models:` line, quoted verbatim.
- The mapping as it stands now: the `--apply` run's `role <role>: ...` lines
  if it ran, otherwise Step 2's.
- Which roles changed this run, and to what.
- That the choice is saved in `$CODEX_HOME/cai-model-choice.json`, and that
  every later `$setup` re-applies it.
