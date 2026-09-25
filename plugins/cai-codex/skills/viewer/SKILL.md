---
name: viewer
description: Open the local Agent Viewer web page, showing every running Claude Code and Codex session and which ones need you. Run $viewer to open it, $viewer stop to close it.
---

Open (or close) the local Agent Viewer web page. Work through the steps in
order and stop with a clear report if any step fails.

## Step 1 — Resolve `<cai-root>` and read the request

This file lives at `<cai-root>/skills/viewer/SKILL.md`. Resolve `<cai-root>`
as two directories up from the absolute path you read this file from.

Then read what the user asked for, from the words after `$viewer`:

- nothing — open (or report) the viewer;
- `stop` — close the running viewer.

For anything else, explain these two forms and stop without running
anything.

## Step 2 — Run it

Try interpreters in this order until one runs `viewer.py` successfully.
Never use `python3` or a bare `py` on Windows — both can resolve to a broken
stub there.

- macOS or Linux: `python3`, then `python`.
- Windows: `python`, then `py -3`.

macOS or Linux:

```
<interpreter> "<cai-root>/scripts/viewer.py" [stop]
```

Windows — run it through this pipeline so the output shows up:

```
& { & <interpreter> "<cai-root>/scripts/viewer.py" [stop] 2>&1 | ForEach-Object { "$_" }; exit $LASTEXITCODE }
```

If every interpreter in the list fails, stop and quote the last failure to
the user rather than guessing what went wrong.

## Step 3 — Approve running outside the sandbox

What follows starts a background server outside the sandbox, so ask the
user to approve running it outside the sandbox before running anything.

## Step 4 — Run and relay

Run the command from Step 2 with the interpreter that just succeeded.

Relay the line that starts `Agent Viewer: http://127.0.0.1:` exactly as
printed — do not translate or reword it. Relay every other stdout line in
the user's own language.

If the run exits non-zero, quote its `error:` line and stop. Do not retry
it with another interpreter: it is the run that failed, not the
interpreter. Never try to kill any process yourself.
