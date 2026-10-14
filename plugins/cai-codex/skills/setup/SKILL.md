---
name: setup
description: Finish installing cai-codex - choose your response language, run the installer, optionally configure the status line, and trust the cai hooks. Run once after adding the plugin, and again after each update.
---

Install cai-codex for this user and finish the setup the installer cannot do
itself. Work through the steps in order and stop with a clear report if any
step fails.

## Menu policy — short, waiting menus

For all language, model and status-line menus in this skill, show a short question and
the labelled choices only, plus any installer warning required below.
This overrides the option-presentation requirements in
`rules/epistemics.md` and `rules/option-explainer.md` for these setup menus.
Do not add comparison dimensions, tables, six-field explanations, analogies,
or a closing recommendation. Do not run `options_lint.py` for these menus.
Do not mark any language as recommended or preselect one; the first language
listed is not a recommendation. Model menus retain the default and ordering
specified by the installer's `ask:` and `offer` lines below.

Use only `request_user_input` for all ordinary menus in this skill, and only
if it is in your tool list and the current mode permits it.
Do not use `request_user_input_async`. Wait for the tool's answer before
acting on that decision. Otherwise list labelled text options, then
end the turn and wait for the person's answer. A result with
no answer or cancellation is never consent; do not apply an unanswered choice.
System-required operation approvals follow the system's approval mechanism.

## Step 1 — Choose the response language

Before running the installer or asking any model question, ask which language
the user wants responses in. Use these choices, without extra explanations:

```text
A. English
B. Traditional Chinese (繁體中文)
C. Japanese
D. Other
```

For Other, accept a language name as free text; if none was supplied, ask for
it and wait. Accept the displayed label, its corresponding number, or a
language name. Use the chosen language for the remaining setup conversation.
Remember the choice for Step 4; do not write any files yet.

## Step 2 — Resolve `<cai-root>`

This file lives at `<cai-root>/skills/setup/SKILL.md`. Resolve `<cai-root>`
as two directories up from the absolute path you read this file from — the
launcher this would otherwise use does not exist yet on a first install.

## Step 3 — Run the installer

The installer writes into `~/.codex`, outside the workspace, so ask the user
up front to approve running it outside the sandbox before running anything —
don't wait to discover an "Access is denied" failure first.

Try interpreters in this order until one runs the installer successfully.
Never use `python3` or a bare `py` on Windows — both can resolve to a broken
stub there.

- macOS or Linux: `python3`, then `python`.
- Windows: `python`, then `py -3`.

macOS or Linux:

```
<interpreter> "<cai-root>/scripts/install_codex.py"
```

Windows — run it through this pipeline so the output shows up:

```
& { & <interpreter> "<cai-root>/scripts/install_codex.py" 2>&1 | ForEach-Object { "$_" }; exit $LASTEXITCODE }
```

Replace `<interpreter>` with the name from the list above for your OS.

If an interpreter fails to launch at all, or the installer exits non-zero,
try the next one in the list for your OS. If every interpreter in the list
fails, stop here and quote the last failure to the user rather than guessing
what went wrong.

### Read the mapping block

The installer's own stdout ends with a mapping block: a `models:` line
(and, when it applies, a `models: ignored ...` line), one `role <role>: ...`
line per role (with optional `effort choice <role>:` and `effort fallback
<role>:` lines), then, when detection succeeded, `offer <role>: ...` lines
per role and `effort offer <model>:` lines for models with known efforts,
then zero or more `ask again <role>:` and `not offered <role>:`
lines, then an `ask:` line, then an `answers file:` line. Read these lines
back out of the output you just captured.

Show the user the `role <role>: ...` lines as the current mapping. Show
every `ask again <role>:` line and every `not offered <role>:` line too,
each on its own line, verbatim — this file holds no rule about what they
mean beyond what they say.
Show every `effort fallback <role>:` line too: a saved effort is retained,
but the cached model list requires a supported fallback for the installed
agents. `$models <role> effort <effort>` changes that choice.

### Ask what the `ask:` line says to ask

Follow the `ask:` line exactly:

- `ask: keep-or-switch` — ask one question: keep the current mapping
  (first option, the default) or switch it.
  - If the user switches, ask one question per role, in the order chore,
    build, think: the options are that role's `offer <role>: ...` entries,
    in the same order the line lists them, first entry first.
  - If the user keeps, ask one question per role that has an `ask again
    <role>:` line only — a role with no stale saved slug is not re-asked.
    Its options again come from that role's `offer <role>: ...` line.
- `ask: keep-or-type <role> <role> ...` — ask one question per role named
  after `keep-or-type`: keep (first option, the default) or type a model
  name. Every one of these questions must carry this warning: "setup
  cannot check a typed name against your account".
- `ask: nothing` — ask no question at all. (Step 7's report says the saved
  choice was reused, and why.)

Menus for these questions follow the short, waiting menu policy above. The
mapping and warning lines required above still precede the model question;
do not expand its choices into a comparison.

### Apply the answers

If no role was answered with a slug this run — every answer was "keep", or
nothing was asked at all — write no answers file, run the installer no
further, and continue to Step 4.

Otherwise, write the answers file with the file-edit tool at the exact
path from the `answers file:` line:

```
{"format": 1, "roles": {"<role>": "<slug>", ...}}
```

with one entry for every role that was asked a question this run and
answered with a slug — a role answered "keep" gets no entry, even if it was
asked.

Then run the installer again, with `--apply` placed right after the script
path — on Windows, before the `2>&1` pipe segment — using the same
interpreter that just succeeded; do not retry the interpreter list.

macOS or Linux:

```
<interpreter> "<cai-root>/scripts/install_codex.py" --apply
```

Windows:

```
& { & <interpreter> "<cai-root>/scripts/install_codex.py" --apply 2>&1 | ForEach-Object { "$_" }; exit $LASTEXITCODE }
```

If this run exits non-zero, quote its output to the user and stop — do not
retry it with another interpreter, because it is the answers that failed,
not the interpreter.

Otherwise, capture and read this `--apply` run's own stdout the same way
you read run 1's in "Read the mapping block" above. The roles written to
the answers file are not necessarily the roles actually saved — the
installer drops a role from the saved file when the answered slug equals
that role's cai default and no effort override remains. A model-only answer
retains a saved effort override. Determine which roles were actually saved from
this apply run's own `role <role>: ...` lines: a role is saved this run
only if its tag reads `saved; cai default <default>`, not plain `cai
default`.

## Step 4 — Save the response language

Use the language chosen in Step 1; do not ask again. Save it after all
installer runs, including any `--apply` run. The installer keeps the language
an earlier setup saved, so the line may already name one.

Edit the language line inside the `<!-- cai-codex:begin -->` /
`<!-- cai-codex:end -->` block the installer just wrote into
`$CODEX_HOME/AGENTS.md`. With the shipped default, the line reads:

```
- Respond in English; keep technical terms in their original form.
```

Substitute the language name and nothing else:

```
- Respond in <language>; keep technical terms in their original form.
```

If the line already names the chosen language, leave it as-is.

## Step 5 — Offer the status line

Ask whether to configure the native Codex status line, with short choices:
configure it, or skip. It shows the current directory/project, git branch,
model with its live reasoning effort, remaining context, and the 5-hour and
weekly rate limits. Codex controls the formatting and hides unavailable data;
this does not install Claude Code's external status-line script.

If they skip, continue. If they accept, run the same interpreter as Step 3
with `--statusline`, using the same Windows output pipeline when applicable:

```
<interpreter> "<cai-root>/scripts/install_codex.py" --statusline
```

This writes `$CODEX_HOME/config.toml`, outside the workspace, so use the
system's approval mechanism for that write. The command needs Python 3.11
or later. It keeps any existing `tui.status_line`, including an empty list,
and backs up the configuration before adding a missing setting. Do not edit
the configuration yourself or silently replace an existing choice. Quote
any failure; `/statusline` is the built-in way to configure it manually.
Tell the user to restart Codex after a write, and that `/statusline` can
customize the fields and their order.

## Step 6 — Trust the hooks

The installer wrote cai's hook entries into `$CODEX_HOME/hooks.json`: the
guard on PreToolUse, and the stage timing hook on SubagentStart, PreToolUse,
PostToolUse and SubagentStop. A hook Codex has not been told to trust does
not fire. Tell the user to run `/hooks`, review the cai entries, and trust
them. Until they do, the guard and stage timing are installed but inactive.

## Step 7 — Report

Report concisely:

- The installer's own output, quoted.
- The full path on each `backup` line the installer printed — the copy of
  `AGENTS.md` it kept before changing it — or that it printed none. If it
  printed the line saying the cai block differed from what cai last wrote,
  say that the user's edits inside the block were replaced and are in that
  backup.
- Which interpreter succeeded.
- The response language that was set.
- Whether the status line was configured, kept, skipped, or failed, and any
  configuration backup path printed by the command. After a write, say that
  restarting Codex loads the setting. It includes the live reasoning effort.
- Whether the user still needs to run `/hooks` to activate the guard and stage timing.
- The `models:` line, quoted verbatim.
- Every `not offered <role>:` line, quoted verbatim.
- Which roles were saved this run, per the `--apply` run's own `role
  <role>: ...` tags (not per which roles were written to the answers
  file) — or, if `ask: nothing` meant no question was asked at all, that
  the saved choice was reused, and why (the `models:` line's own reason).
- This exact sentence: "If a cai agent later fails to start with a model
  error, run `$models` and switch that role."
