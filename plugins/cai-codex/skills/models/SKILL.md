---
name: models
description: Show or change the model and reasoning effort for each cai role (chore, build, think), without re-running $setup. Usage - $models, $models <role> <model> [<effort>], $models <role> effort <effort>, $models reset <role>.
---

Change the model and reasoning effort cai's roles run on. `$setup` installs
cai; this rewrites the model and effort lines of the agents it installed.
An explicit effort applies to every agent in that role; `default` restores
each agent's own shipped effort, which can differ within a role.
Work through the steps in order and stop with a clear report if any step
fails.

## Step 1 — Resolve `<cai-root>` and read the request

This file lives at `<cai-root>/skills/models/SKILL.md`. Resolve `<cai-root>`
as two directories up from the absolute path you read this file from.

Then read what the user asked for, from the words after `$models`:

- nothing — show the mapping and offer to change models or efforts;
- `<role> <model> [<effort>]`, such as `think gpt-6-astra high` — set that
  role's model and, if supplied, its effort. Omitting the effort retains a
  saved effort override, or each agent's shipped effort if none was saved;
- `<role> effort <effort>`, such as `build effort high` — change only the
  effort, keeping the model from the current mapping;
- `reset <role>` — restore both the model and each agent's effort to cai's
  defaults.

A role is `chore`, `build` or `think`. Recognized efforts are `low`, `medium`,
`high`, `xhigh`, `max` and `ultra`; the selected model may support fewer.
`default` clears the saved effort override. For any other form, list the
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
as the mapping that the next apply would write, and every `ask again <role>:` and `not offered
<role>:` line verbatim.
Also show any `effort choice <role>:` (saved override) and `effort fallback
<role>:` (the cached model list no longer supports that override) lines.
The `effort offer <model>:` lines list the recognized efforts advertised
for each model. A missing line means the installer cannot check that model's
effort support; say so before accepting a typed effort.
This run is a preview: `would apply` in a fallback line describes the next
write, not the effort currently in the installed agent files.

## Step 3 — Decide the answers

- **No arguments.** Follow `<cai-root>/skills/setup/SKILL.md`'s "Ask what
  the `ask:` line says to ask" section, menus included. Explain that switching
  can change only an effort while keeping the selected model. In a
  `keep-or-type` question, keeping means use the model in that role's mapping
  as its model answer, then still ask about effort. After collecting
  model answers, ask about each answered role's effort, one question at a time
  in chore, build, think order. Show the selected model's `effort offer` values
  in prose; offer to keep the saved effort (or per-agent defaults), restore
  per-agent defaults, or type a supported effort. Omit a duplicate default
  option. Offer to keep a saved effort only if it is supported or support is
  unknown. Collect an explicit model/effort answer for that role.
- **`<role> <model> [<effort>]`.** Use those values; ask nothing. If effort
  was omitted, use a model-only answer to preserve the current effort choice.
- **`<role> effort <effort>`.** Read the current model from that role's
  `role <role>:` line and pair it with the requested effort; ask nothing.
- **`reset <role>`.** Read that role's `role <role>: ...` line. If its tag is
  plain `(cai default)`, the role is already on cai's defaults: say so and
  stop. Otherwise the tag reads `(saved; cai default <default>)`, and that
  role's answer is `{"model": "<default>", "effort": null}`.

For an explicit effort, use only a value in the selected model's `effort
offer` line, or `default`. If the model has no such line, explain that its
effort support could not be checked and accept a recognized effort name.
If the `models:` line says detection failed, tell the user this cannot check
a typed model against their account, and carry on.

If no role ended up with an answer, stop here and write nothing.

## Step 4 — Apply the answers

What follows writes into `$CODEX_HOME`, outside the workspace, so ask the
user to approve running it outside the sandbox before writing anything.

Write the answers file with the file-edit tool at the exact path from the
`answers file:` line:

```
{"format": 1, "roles": {"think": {"model": "gpt-6-astra", "effort": "high"}}}
```

Use one entry per role that has an answer. A model-only entry remains a string,
such as `"build": "gpt-6.1-sol"`; a model/effort entry is an object as above.
For `default` effort, write `null` as the object's `effort` value. This clears
only the effort override; a full reset also uses the role's default model.

Then run the installer again with
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
- Any `effort fallback <role>:` lines, quoted; the saved effort is retained
  and `applied` confirms a supported fallback was written. If only the preview
  ran, `would apply` means the installed files have not changed.
- That the choice is saved in `$CODEX_HOME/cai-model-choice.json`, and that
  every later `$setup` re-applies it.
