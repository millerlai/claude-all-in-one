---
description: Finish installing cai — copy the shared rules into ~/.claude/rules/, set your preferred response language, and verify the bash guard actually fires. Run once after installing the plugin, and again after each /plugin update.
---

Install the cai rules for this user and verify the plugin is working.
Work through the steps in order and stop with a clear report if any step fails.

## Step 1 — Locate the installed plugin

The plugin ships its rules in `<plugin-root>/rules/`. Find `<plugin-root>` by
checking these locations in order and taking the first that exists:

1. The install cache, highest version number if several are present:
   `~/.claude/plugins/cache/claude-all-in-one/cai/*/`
2. A local checkout of the repo, if the current working directory is one:
   `./plugins/cai/`

Confirm `<plugin-root>/rules/` contains `.md` files before continuing. If you
cannot find it, stop and tell the user to run `/plugin install
cai@claude-all-in-one` first.

## Step 2 — Copy the rules to user scope

Create `~/.claude/rules/` if absent, then copy every `.md` file from
`<plugin-root>/rules/` into it.

These files are overwritten wholesale on each run — that is intended, it is how
updates propagate. Before overwriting, check whether any destination file
already differs from the source in ways that look hand-edited (rules the user
added themselves, not just the language line from Step 3). If so, list those
files, ask the user whether to overwrite or skip them, and respect the answer.

Use the platform's native copy — `cp` on macOS/Linux, `Copy-Item` on Windows.

## Step 3 — Set the response language

The shipped `communication.md` defaults to English. Ask the user which language
they want Claude to reply in, using the AskUserQuestion tool. Offer English,
Traditional Chinese (繁體中文), and Japanese (日本語) as options — the tool
always adds a free-text "Other" choice for anything else.

Then rewrite that single bullet in the **installed** copy
(`~/.claude/rules/communication.md`, not the plugin's copy) to match. The line
currently reads:

```
- Respond in English; keep technical terms in their original form.
```

For a non-English choice, keep technical terms in their original form — e.g. for
Traditional Chinese: `- Respond in Traditional Chinese; keep technical terms in English.`

If the user picks English, leave the line as-is.

## Step 4 — Bootstrap or review the user's global CLAUDE.md

`<plugin-root>/templates/CLAUDE.md.tpl` is a starting point for
`~/.claude/CLAUDE.md`. It is deliberately thin: the rules from Step 2 already
load automatically from `~/.claude/rules/`, so anything restated here would be
sent to the model twice in every session.

Handle whichever case applies:

**No `~/.claude/CLAUDE.md`** — whether `~/.claude/` was missing entirely or
just lacks the file, create what's needed and copy the template in. Then fill
the `## Environment` section: substitute the detected OS into the first
placeholder, ask the user what they mostly work in if you can't tell, and leave
the second placeholder as a comment for them to fill in later.

**It already exists** — never overwrite it. Read it, compare against the rules
you just installed in `~/.claude/rules/`, and report:

- Sections whose content is already covered by a rules file. Name the specific
  rules file for each. This is the normal case for anyone who kept their rules
  inline before installing this plugin, and it means the same instructions are
  being sent twice per session.
- Anything the template covers that their file is missing.

Then ask whether to slim their file down to what the rules don't cover —
usually the preamble plus `## Environment`. Show the proposed result and only
write it if they agree. If they decline, leave the file untouched and move on.

## Step 5 — Verify the bash guard fires

The guard is a PreToolUse hook, so a silent failure means the user is unprotected
without knowing it. Verify it end-to-end rather than assuming.

Write a temporary JSON file containing exactly:

```json
{"tool_input":{"command":"git push --force origin main"}}
```

Write it with the Write tool, not by echoing the string in a shell command — the
installed guard will block your own shell command otherwise.

Then feed that file to the dispatcher on stdin:

- macOS/Linux: `sh "<plugin-root>/hooks/run-guard.cmd" < <tmpfile>`
- Windows: `cmd /c "<plugin-root>\hooks\run-guard.cmd" < <tmpfile>`

Expected: exit code **2**, with a `bash_guard blocked this command` message on
stderr. Delete the temporary file afterwards.

If the exit code is **0**, no Python interpreter was found. The guard is inert.
Tell the user plainly that destructive commands are NOT being blocked, and that
they need Python 3 on PATH (`python3` on macOS/Linux, `python` or the `py`
launcher on Windows).

## Step 6 — Report

Report concisely:

- Which rules files were written to `~/.claude/rules/`, and any that were skipped.
- The response language that was set.
- What happened to `~/.claude/CLAUDE.md` — created, slimmed, or left alone with
  duplication still present.
- Whether the bash guard verification passed or failed.
- That a session restart is needed for newly copied rules to take effect.
