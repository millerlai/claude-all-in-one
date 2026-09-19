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
