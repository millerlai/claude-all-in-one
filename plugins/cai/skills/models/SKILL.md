---
name: models
description: Choose which model each cai tier - chore, build, think - runs on, for you alone and across plugin updates. Run it when a new model comes out. Usage - /cai:models, /cai:models <tier> <model>, /cai:models reset [<tier>]
disable-model-invocation: true
---

Set which model each of cai's three tiers runs on. The choice is yours alone:
it is saved outside the plugin, so `/plugin update` does not undo it, and a
hook puts it back into each newly installed copy when a session starts.

## Step 1 — Read the request and the mapping

From the words after `/cai:models`:

- nothing — show the mapping and ask about all three tiers at once;
- `<tier> <model>` — set that one tier;
- `reset <tier>` — put that tier back on cai's default; `reset` alone puts
  every tier back.

A tier is `chore`, `build` or `think`. For anything else, list the three
forms above and stop.

Run `python ${CLAUDE_PLUGIN_ROOT}/scripts/model_choice.py show` and show the
user its `tier <tier>: ...` lines as the current mapping.

## Step 2 — Decide the answers

- **No arguments.** Ask all three tiers in one `AskUserQuestion` call: one
  question per tier, in the order chore, build, think. A question's options
  are that tier's `offer <tier>: ...` entries, in the order the line lists
  them; the first is the model in effect, so picking it keeps the tier. The
  tool adds a free-text entry of its own, which is how the user names a model
  the line does not list, such as one released after this plugin.
- **`<tier> <model>`.** That tier's answer is `<model>`; ask nothing.
- **`reset`.** Skip to Step 3.

Drop every answer equal to the model already in effect for its tier. If
nothing is left, say the mapping is unchanged and stop.

## Step 3 — Apply

Run one of these:

```
python ${CLAUDE_PLUGIN_ROOT}/scripts/model_choice.py set <tier>=<model> ...
python ${CLAUDE_PLUGIN_ROOT}/scripts/model_choice.py reset [<tier>]
```

If it exits non-zero, quote its output to the user and stop. Otherwise it
prints the new `tier <tier>: ...` lines and how many files it rewrote.

## Step 4 — Report

- The new `tier <tier>: ...` lines, quoted.
- That Claude Code reads these when it starts: restart it for the new models
  to take effect.
- That the choice is saved at the path from Step 1's `choice file:` line and
  is re-applied after every plugin update, which may ask for one more restart
  the first time a session starts on the updated copy.
