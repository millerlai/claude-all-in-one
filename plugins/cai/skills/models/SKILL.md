---
name: models
description: Choose which model and reasoning effort each cai tier - chore, build, think - runs on, for you alone and across plugin updates. Run it when a new model comes out. Usage - /cai:models, /cai:models <tier> <model> [<effort>], /cai:models <tier> effort <effort>, /cai:models reset [<tier>]
disable-model-invocation: true
---

Set which model, and which reasoning effort, each of cai's three tiers runs
on. The choice is yours alone: it is saved outside the plugin, so
`/plugin update` does not undo it, and a hook puts it back into each newly
installed copy when a session starts.

## Step 1 — Read the request and the mapping

From the words after `/cai:models`:

- nothing — show the mapping and ask about all three tiers;
- `<tier> <model> [<effort>]` — set that tier's model and, if given, its
  effort; without one, the tier keeps the effort it has;
- `<tier> effort <effort>` — set only that tier's effort;
- `reset <tier>` — put that tier's model and effort back on cai's defaults;
  `reset` alone puts every tier back.

A tier is `chore`, `build` or `think`. An effort is `low`, `medium`, `high`,
`xhigh` or `max`, or `default`, which puts every component of the tier back
on the effort it shipped with — they can differ within a tier, and a
component that ships none runs at the session's effort. A model that lacks
the effort asked for runs at the highest one it has below it. For anything
else, list the forms above and stop.

Run `python ${CLAUDE_PLUGIN_ROOT}/scripts/model_choice.py show` and show the
user its `tier <tier>: ...` and `effort <tier>: ...` lines as the current
mapping.

## Step 2 — Decide the answers

- **No arguments.** Ask in two `AskUserQuestion` calls, since one takes at
  most four questions. First the models: one question per tier, in the order
  chore, build, think, whose options are that tier's `offer <tier>: ...`
  entries in the order the line lists them. Then the efforts: one question
  per tier in the same order, whose options are that tier's
  `effort offer <tier>: ...` entries. In both, the first option is what is in
  effect, so picking it keeps the tier; the tool adds a free-text entry of
  its own, which is how the user names a model or an effort the line does not
  list.
- **`<tier> <model> [<effort>]`** or **`<tier> effort <effort>`.** Those are
  the answers; ask nothing.
- **`reset`.** Skip to Step 3.

Drop every answer equal to what is already in effect for its tier. If
nothing is left, say the mapping is unchanged and stop.

## Step 3 — Apply

Run one of these, with one word per answer — `<tier>=<model>` for a model,
`<tier>.effort=<effort>` for an effort:

```
python ${CLAUDE_PLUGIN_ROOT}/scripts/model_choice.py set <tier>=<model> <tier>.effort=<effort> ...
python ${CLAUDE_PLUGIN_ROOT}/scripts/model_choice.py reset [<tier>]
```

If it exits non-zero, quote its output to the user and stop. Otherwise it
prints the new `tier <tier>: ...` and `effort <tier>: ...` lines and how many
files it rewrote.

## Step 4 — Report

- The new `tier <tier>: ...` and `effort <tier>: ...` lines, quoted.
- That Claude Code reads these when it starts: restart it for the new models
  and efforts to take effect.
- That the choice is saved at the path from Step 1's `choice file:` line and
  is re-applied after every plugin update, which may ask for one more restart
  the first time a session starts on the updated copy.
