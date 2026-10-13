---
name: fix-unclaim
description: Clear one named local session claim without waiting for it to expire. Usage: $fix-unclaim <issue or ticket URL> <platform> <session> <started>
---
> `<cai>` is the cai-codex command line that `$setup` wrote into your instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what `<cai> --root` prints.


## What typing this command authorises

Typing `$fix-unclaim` authorises deleting only the claim matching the URL,
platform, session and start time supplied. It may belong to another session
that is still active.

## Steps

1. Require exactly four arguments, in order: the issue or ticket URL, then the
   three words from the blocked item's `detail`: platform, session and start
   time. Copy those three words as they are, without the `detail:` label.
   If there are not exactly four arguments (including an extra `detail:`), or
   any argument contains a single quote, do not call the script: reply with
   one line starting `rejected unrecognised:` and stop.
2. Run `<cai> fix_claims clear --project-dir <project root> --platform '<platform>' --session '<session>' --started '<started>' '<issue or ticket URL>'`.
   Single-quote all four arguments; `<project root>` is the directory you are
   working in. Run the script once and paste its output as it is. Exit 2 or 3:
   paste the output and stop. Do not retry or change flags.

## No questions

Ask no questions and wait for no answer during this command.
