---
name: setup
description: Finish installing cai-codex - run the installer, set your response language, and trust the guard hook. Run once after adding the plugin, and again after each update.
---

Install cai-codex for this user and finish the setup the installer cannot do
itself. Work through the steps in order and stop with a clear report if any
step fails.

## Step 1 — Resolve `<cai-root>`

This file lives at `<cai-root>/skills/setup/SKILL.md`. Resolve `<cai-root>`
as two directories up from the absolute path you read this file from — the
launcher this would otherwise use does not exist yet on a first install.

## Step 2 — Run the installer

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
line per role, then, when detection succeeded, `offer <role>: ...` lines
per role, then zero or more `ask again <role>:` and `not offered <role>:`
lines, then an `ask:` line, then an `answers file:` line. Read these lines
back out of the output you just captured.

Show the user the `role <role>: ...` lines as the current mapping. Show
every `ask again <role>:` line and every `not offered <role>:` line too,
each on its own line, verbatim — this file holds no rule about what they
mean beyond what they say.

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
- `ask: nothing` — ask no question at all. (Step 5's report says the saved
  choice was reused, and why.)

Menus for these questions follow the same rule Step 3 already states: a
menu tool if one is available, else numbered text.

### Apply the answers

If no role was answered with a slug this run — every answer was "keep", or
nothing was asked at all — stop here: write no answers file, and run the
installer no further.

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
that role's cai default. Determine which roles were actually saved from
this apply run's own `role <role>: ...` lines: a role is saved this run
only if its tag reads `saved; cai default <default>`, not plain `cai
default`.

## Step 3 — Set the response language

Ask the user which language they want responses in. If a menu tool is
available, offer English, Traditional Chinese (繁體中文), and Japanese
(日本語), plus an explicit "other" choice for anything not listed — do not
assume the tool adds a free-text choice on its own. If no menu tool is
available, list the same choices as numbered text and accept whatever number
or free text the user answers with.

Then edit the language line inside the `<!-- cai-codex:begin -->` /
`<!-- cai-codex:end -->` block the installer just wrote into
`$CODEX_HOME/AGENTS.md`. The line currently reads:

```
- Respond in English; keep technical terms in their original form.
```

Substitute the language name and nothing else:

```
- Respond in <language>; keep technical terms in their original form.
```

If the user picks English, leave the line as-is.

## Step 4 — Trust the guard

The installer wrote a PreToolUse hook entry into `$CODEX_HOME/hooks.json`,
but a hook Codex has not been told to trust does not fire. Tell the user to
run `/hooks`, review the cai entry, and trust it. Until they do, the guard is
installed but inactive.

## Step 5 — Report

Report concisely:

- The installer's own output, quoted.
- Which interpreter succeeded.
- The response language that was set.
- Whether the user still needs to run `/hooks` to activate the guard.
- The `models:` line, quoted verbatim.
- Every `not offered <role>:` line, quoted verbatim.
- Which roles were saved this run, per the `--apply` run's own `role
  <role>: ...` tags (not per which roles were written to the answers
  file) — or, if `ask: nothing` meant no question was asked at all, that
  the saved choice was reused, and why (the `models:` line's own reason).
- This exact sentence: "If a cai agent later fails to start with a model
  error, run `$models` and switch that role."
