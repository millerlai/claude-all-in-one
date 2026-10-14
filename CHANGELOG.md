# Changelog

## v1.56.0 — 2026-10-14

This release makes setup keep a timestamped backup before it changes a file and tell a hand edit from an outdated copy by hash, lets Codex setup turn on the native status line, and fixes setup's Python checks under Windows PowerShell.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.55.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.55.0 to 1.56.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- An in-progress track keeps its saved state and ledger; this release does not change what either records.
- The first setup after updating asks about more files than usual. Installs from earlier versions have no hash record, so every installed rule that differs from the shipped copy is listed as `user-modified` with its diff, even if you never edited it. Choose overwrite or skip per file; an overwritten file is kept as a backup. Setup records the hashes on that run, so later updates overwrite an outdated copy without asking and ask only about files you changed. (#456)

### Setup

- `/cai:setup` and `$setup` now decide whether a rule file was hand-edited by comparing hashes recorded in `.cai-manifest.json` (in `~/.claude/rules/` and in `$CODEX_HOME`), not by a model's reading. Identical files are left alone; only files you changed are put to you, with their diff. (#456)
- Before changing an existing file, setup copies it next to the original as `<name>.<YYYY-MM-DD-HHMMSS>.bak` and prints a `backup <full path>` line, and the final report lists every backup made. This covers rule files, `~/.claude/CLAUDE.md` before it is slimmed, and Codex's `AGENTS.md`. The project's `CLAUDE.md` is still appended to without a backup. (#456)
- Rule comparison ignores line endings and the language named on the `- Respond in ...` line, and a rewrite keeps the language you installed, so an update no longer resets it. (#456)
- Codex setup refuses an `AGENTS.md` whose end marker sits above its begin marker, instead of duplicating the text between them. A cai block you edited by hand is reported as edited and still replaced, with the old text in the backup. (#456)

### Codex status line

- Codex setup now offers to turn on Codex's native status line: current directory and git branch, model with its live reasoning effort, remaining context, and the five-hour and weekly limits. Codex formats the line and hides data it does not have. (#458)
- Choosing it writes `$CODEX_HOME/config.toml` after a timestamped backup, keeps an existing status-line choice (including a disabled footer), comments and other settings, and leaves a symlinked config a symlink. Writing needs Python 3.11 or later; `/statusline` stays the built-in way to customize or to configure it by hand. (#458)

### Windows

- Setup's Python checks no longer fail under Windows PowerShell, which stripped the quotes inside `python -c`. The check is now sent through stdin from a single-quoted here-string. (#457)

## v1.55.0 — 2026-10-14

This release groups unfixed track findings into one menu, makes codemap updates and status cheaper, reduces query memory use, and fixes the Windows write fallback when Python is unavailable.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.54.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.54.0 to 1.55.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- An in-progress track keeps its saved state and ledger. Existing format-1 open-item records still load, with their items treated as major; imported `Left open:` entries are also major. New records use format 2 with a severity field. Before ship or track done, remaining items use the grouped menu. (#444)
- A codemap index written by v1.54.0 is reported as `unsupported` until the next `update` or `build`, which rebuilds it once. A track refreshes an existing index itself. (#451, #452)

### Track

- Before ship and at track done, unfixed findings appear under Major and Minor in one menu. Choose to fix major findings, fix all findings, note them on the pull request, or accept them as is; when every finding is minor, the fix choice is Fix minor. Available choices at track done still depend on the pull request's state and remaining fix rounds. (#444)
- Choosing Fix major queues minor findings as a note on the pull request so reviewers still see them. Choosing to fix all sends the findings through verify together. (#444)
- Ask to decide items individually when you want separate choices or to file a GitHub issue for an item. An item whose earlier filing result is unknown keeps its own confirmation question. (#444)
- Build and verify reports now assign each new open item a major or minor severity. A missing or invalid severity is rejected when the report is recorded. (#444)

### Codemap

- Update and status reuse a file's saved content hash when its size and modification time are unchanged and its timestamp is safely older than the previous scan. Recently modified files are still read again. A tool that restores both size and an old modification time can hide a change from this shortcut; run `build` to force a full rescan in that case. (#451)
- Status reads the count of files with symbols from saved metadata instead of parsing every symbol record. It still checks the symbol file's digest; update and query retain full record validation. (#452)
- Query scans text one file at a time, reducing memory use while returning the same hits. Splitting large repository maps into shards groups files in one pass, preserving the output. (#447, #453)

### Guard

- On Windows, Claude Code's write fallback now reads its protected-name rules successfully when Python is unavailable. Subagent writes to the track ledger and guard launcher records are blocked; main-session writes and unrelated files still pass. Mixed-case protected filenames remain covered. (#446)

## v1.54.0 — 2026-10-13

This release asks what to do with each unfixed track finding before shipping, helps local fix sessions avoid working the same item, and improves commit consent, codemap safety and incremental updates.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.53.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.53.0 to 1.54.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- An in-progress track keeps its saved state and ledger. Existing `Left open:` entries become undecided open items; before ship drafts anything, each needs a decision. New reports keep unfixed findings separately from manual reminders. (#424)
- You can withdraw an earlier yes to commits. Build and verify check the current answer again immediately before every commit; an edited design must be approved again before the affected work resumes. (#433)
- A codemap index written by v1.53.0 is reported as `unsupported` until the next `update` or `build`, which rebuilds it. A track refreshes an existing index itself; standalone discover only reads its status. (#427, #430, #435)

### Track

- Before ship, each unfixed finding gets a choice: Fix now, File a GitHub issue, Note on the PR, or Accept as is. Fix-now items go through verify together; filing and notes wait for your choice. Track done also asks about items still undecided, awaiting a fix or being filed. (#424)
- Left-open reports and the final mirrored ticket comment show each finding's state. Cancelling a track posts nothing queued and reports how many items remain undecided. (#424)
- Gate 1 now shows the planned build's units, parallel pairs, verification commands and remaining questions above its approval menu. Build reports any sizing difference from that plan. (#439)
- Approve without commits now states its existing exception: it prevents commits before the pull request opens, while a later fix round still commits so it can push. Ship leaves tracked changes for you to commit and stops. (#428)
- Build and verify re-check consent before each commit, and their reports label the answer they used as `acted_on`. Withdrawing consent turns yes into no; a changed approved design stops the resume for another Gate 1 approval. (#433)
- If a stage check cannot read a file or decode its text, preflight reports the failed check and still prints the commit answer instead of ending with a traceback. (#438)

### Fix

- Fix claims an item locally before working it. A second session on the same machine and configuration root skips an item held by another session; issue lists untick claimed items and show who holds them. Claude Code and Codex share the registry. Claims expire after 30 minutes, and an unavailable registry lets work proceed with a warning. (#432)
- New `/cai:fix-unclaim` and `$fix-unclaim` release only the claim matching the supplied item, platform, session and start time. Use this for a stopped session rather than waiting for expiry. Claims do not coordinate different machines or write to GitHub or Jira. (#432)

### Codemap

- Build and update refuse a second writer and unsafe entries in the index directory. Files are staged before replacement, with state written last; a directory occupying a data-file name is refused before any replacement, preserving the previous index. (#422, #426)
- Paths, source hits and map labels escape control characters so repository text cannot add forged status lines or map rows. Non-fresh status details are kept out of stage prompts, and file-related error messages omit local absolute paths. (#425)
- Symbol and text-hit line numbers now match editor line breaks. Python declarations under top-level or class-level if, try and with blocks are included; distinct non-UTF-8 file names stay distinct. Invalid source encoding and syntax errors are classified separately. (#427, #435)
- Standalone discover never updates the index. A fresh status line names the index directory so read-only agents can find its map; a map that cannot be opened is treated as absent. (#430)
- An unchanged update leaves index files untouched. Status with no index reads no tracked file contents, path-detail lists stop at ten with a remaining count, and tracked-file enumeration allows 60 seconds for larger repositories. (#440)

### Build

- Glossary reruns skip an empty commit and keep a term beside its handwritten `_Avoid_` lines. Reports still quote replaced definitions when the checker cannot run. A new entry deleted by hand is written again on a rerun, as it would be after an interrupted write. (#434)

### Guard and scratch files

- Subagents cannot directly write the guard's launcher record or run commands naming it, including reads. Claude Code also applies the direct-write check without a working Python interpreter; Codex receives the command check. Arbitrary scripts that later touch the record remain outside these checks. (#429)
- Claude Code's fix and track scratch files use a dedicated temporary root that removes siblings untouched for six hours. Codex continues to use the workspace's permitted scratch directory and leaves consumed files in place. (#431)

## v1.53.0 — 2026-10-13

This release lets build update the project's glossary without a selection menu, protects the track ledger and commit choice, and fixes untracked-file handling, codemap reads and the final merge command.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.52.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.52.0 to 1.53.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- An in-progress track keeps its saved state and ledger. When build next reaches its glossary step, it selects and writes checked project terms automatically; it can replace an existing same-name definition, and its report lists what was written, replaced or kept out. An earlier glossary selection does not serve as the new step's completed record. (#419)
- Any matching Gate 1 approval with `commit: no` now keeps build from committing, even if a later matching approval says yes. Commit the changes yourself, or change the design and approve it again. (#416)
- A codemap index written by v1.52.0 is reported as `unsupported` until the next `update` or `build`, which rebuilds it. A track that already refreshes its index performs that update itself. (#412)

### Build

- Build no longer pauses for a glossary selection menu. It takes project terms from the Detail design's glossary, checks them, records its choices before writing `.claude/cai-context.md`, and reports each term written, definition replaced and term rejected. (#419)
- A completed glossary record is reused when the same design resumes. A definition changed by hand since the record was written is left alone and quoted in the report. New terms use the Domain or Process heading; a same-name definition is replaced where it already stands. (#419)

### Track

- An explicit `commit: no` in any matching Gate 1 approval cannot be overruled by a later yes. A corrupt ledger line after the first matching approval also makes the commit answer unreadable, which build treats as no. (#416)
- The final merge command now specifies squash and the commit that was checked: `gh pr merge <n> --squash --match-head-commit <sha>`. If the pull request head changes after the check, GitHub refuses the merge; a difference between the checked commit and the reported head is shown in the merge list. (#410)

### Fix

- `/cai:fix` and its Codex counterpart no longer stop just because the checkout has untracked files. They record those initial paths, leave them untouched and keep them outside fix commits; uncommitted changes to tracked files still stop the run. (#418)
- Staging a pre-existing untracked file stops the run before it can be committed. Staging commands use literal paths, so a fix named `notes/[a].txt` cannot accidentally include an existing `notes/a.txt` on Linux. (#418)

### Codemap

- Damaged or incomplete indexes are refused instead of crashing their readers, and an index built by another codemap or Python version is rebuilt rather than reused. The `fresh` status line now includes how many files have symbols. (#412)
- Inventory, parsing and query text scans refuse symbolic links, FIFOs and paths outside the repository without opening them. Parsing and text scans also respect the size cap; files that cannot be opened are marked `partial` and retried on the next update. (#412)

### Guard

- Claude Code now guards subagent Write, Edit and NotebookEdit calls that target `ledger.jsonl`, including recognised path aliases. Subagent commands that name the ledger or call `ledger.py append` are also refused; read commands naming the ledger are refused as well, so read it with a file-reading tool or `ledger.py show`. The main session remains responsible for recording stage results. (#416)
- Claude Code's command checks now cover Monitor as well as Bash and PowerShell. Codex continues to register the command guard only; the new direct-write hook applies to Claude Code. These checks inspect tool paths and command text, not the contents of arbitrary scripts. (#416)

## v1.52.0 — 2026-10-12

This release adds `/cai:codemap`, an optional index of a repo that intake, discover and design can start from, and moves a track's commit question from build to the design approval at Gate 1.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.51.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.51.0 to 1.52.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- Finish any track that has passed Gate 1 before updating if you can. Its design approval carries no commit answer, so after the update it reads as "no": build makes no per-unit commits for the units still to do, and `ship` stops on tracked files with uncommitted changes until you commit them yourself.
- A track whose `intake` is done but has no `.claude/track/<feature>/intake.md` is stopped by the `discover` and `design` preflight until the intake report is saved there.
- The new skill changes nothing in a repo that has no index.

### Added

- `/cai:codemap build` creates an optional, disposable index of a repo's tracked files and their top-level declarations in `.cai/codemap/`, which git ignores. Python is read with `ast`; Go and TypeScript/JavaScript by line patterns, and those entries are marked as heuristic. (#386)
- Before `intake`, `discover` or `design` runs, a track refreshes an index that already exists and passes its status line on. The agents use the index only when that line says `fresh`, and only as a pointer, not as evidence. Only a person typing `/cai:codemap build` creates an index. (#386)
- Codex gets the same skill as `$codemap`; that Codex can run its scripts has not been checked yet. (#386)

### Track

- Gate 1 has four options: Approve, Approve without commits, Changes requested, Reject. Neither approving option is marked recommended. (#387)
- The commit question moved there from build: under a track, `build` no longer asks whether to commit each unit. Approve makes one local commit per verified unit and pushes nothing before Gate 2; Approve without commits leaves the changes in the working tree, and `ship` stops until you commit them. Standalone `/cai:build` still asks once. (#387)
- The answer is read from the Gate 1 ledger row and printed by preflight as `commit_answer`. A note can no longer forge a second `commit_answer` line with a newline, and a loosely worded note, an Approve row for a different file with the same hash, or a malformed ledger line after the newest Approve reads as unreadable, which counts as "no". Build commits only when the answer is yes. (#388)
- `intake` now saves its report as `.claude/track/<feature>/intake.md`, written by the main session before the approval menu. `discover` and `design` stop if a done intake has no readable file or an invalid verification-levels table. (#384)
- A pending-question "round" is now defined: only a hand-up that no fixed step asks for, or Changes requested at the stance approval or Gate 1, spends one of the three rounds. `track_state.py status` prints `N of 3 rounds spent`, and `pending.py` gains `--stop` to record a prescribed stop without spending one. (#381)
- A designer dispatched by a track runs `plan-review` by dispatching `architect` with the skill file, the document and the requirements, but not its own conclusions. Run alone, the main session invokes the skill. (#380)

### Fix

- `/cai:fix <issues URL>` shows one checkbox per issue, up to 15 with four per question and a shortcut that ticks all recommended ones, instead of one two-option question with every other choice typed by number. (#378)
- Subagent output tokens in `/cai:usage` and the ledger's `agents` column were undercounted by about two orders of magnitude on Claude Code 2.1.296 transcripts, because only a request's first line was kept. Each request is now counted at its largest `output_tokens`; records written earlier are not corrected. (#383)

## v1.51.0 — 2026-10-11

This release adds `/cai:fix`, a command that fixes an issue, a Jira ticket, a set of chosen open issues, or a pull request's review threads all the way to a pushed result without stopping for approval along the way. It also fixes a track push gate that hid skipped stages, a design-fix step that rewrote whole documents, a viewer time format, and reorganizes README.md.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.50.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.50.0 to 1.51.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress keeps its saved state and ledger; the only change it sees is at the push gate, where a new line now names any stage it skipped.
- No further action is needed beyond the update steps above.

### Fix

- `/cai:fix <url>` fixes an issue, a Jira ticket, a list of chosen open issues, or a pull request's review threads, running from start to a pushed result without pausing between steps. (#369)
- Given a pull request, it makes one commit per review thread on the pull request's own branch, pushes once, then replies on and resolves the fixed threads. (#369)
- Given an issues URL, it shows a selection screen and asks only one question: which issues to fix. (#369)
- It never merges, never force-pushes, and never pushes to the default branch, and it only runs when typed. (#369)

### Track

- Pushing now shows a new `skipped_stages` line listing every skipped stage and its recorded reason in the same message as the push commands, so a skipped `verify` (or any other skipped stage) is visible at the push gate itself, not only in `/cai:track status`. (#368)

### Design

- A design fix made after `plan-review` now edits the existing document in place instead of writing the whole document out again on each round. (#365)

### Viewer

- A stage that ran for an hour or more now shows its time as `hh:mm:ss` instead of minutes rolling past 60. (#359)

### Docs

- README.md is shorter and now serves as a front door, with the longer material — subagents, hooks, test-command resolution, the full Codex steps, and more — moved into a new REFERENCE.md. (#358)

## v1.50.0 — 2026-10-10

This release lets `/cai:git-sweep` free merged branches that are checked out in a worktree, instead of leaving them stuck as `held` with no indication they're already merged.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.49.5.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.49.5 to 1.50.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress is unaffected; nothing changes in its saved state or ledger.
- No further action is needed beyond the update steps above.

### Git Sweep

- Branches checked out in another worktree are no longer automatically reported as `held`; a merge signal is read for every branch regardless of worktree status. (#357)
- A new `detachable` status appears for a branch that's proven merged but still checked out in another worktree, with the WHY column showing that worktree's path. (#357)
- `--delete --detach` moves the worktree onto the same commit with no branch attached, then deletes the branch; `--delete` alone behaves as before, and `--detach` alone exits with an error. (#357)
- The branch checked out where the script itself runs still shows as `held`. (#357)
- Each freed branch now prints two undo commands. (#357)
- A worktree with no commits of its own may show as `detachable` even though work has just started there; the tool flags this before asking for `--detach`. (#357)

## v1.49.5 — 2026-10-09

This release fixes a bug from v1.49.4 that broke every new Claude Code session on macOS and Linux: the SessionStart hook failed with a permission error instead of running. If you're on v1.49.4, update right away.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.49.4.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.49.4 to 1.49.5.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress is unaffected; nothing changes in its saved state or ledger.

### Hooks

- The SessionStart hook now runs on macOS and Linux instead of failing with `run-models.cmd: Permission denied`, a regression introduced in v1.49.4. (#356)

## v1.49.4 — 2026-10-09

This release fixes a bug that undercounted build-stage time, makes the Agent Viewer show coverage-only stage times as lower bounds instead of flagging them incomplete, cuts the viewer's CPU use by stepping its animations, and keeps Codex's test-command approvals stable so you aren't re-asked for every pytest run.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.49.3.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.49.3 to 1.49.4.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress is unaffected; its saved state and ledger keep the same fields, but any build stage with a subagent tool error now keeps counting instead of stopping early, and a stage measured only from coverage now shows its time as a plain lower bound. (#349, #351)

### Track

- A build stage no longer drops all time after an implementer subagent's failed Edit call; counting continues through the rest of the subagent instead of stopping at that point. (#349)

### Viewer

- A stage or track total measured only from coverage now reads "At least m:ss" without "Incomplete data", since that case is a lower bound, not missing data; a stage with another reason for being incomplete still shows "Incomplete data" as before. (#351)
- The tab's looping animations (the logo, LIVE dots, row lamps and glows, waiting gates, and progress spinners) now step instead of smoothly tweening, cutting measured CPU use roughly in half in testing. (#353)

### Codex

- An approval for a command needing a known resource (a localhost socket or network) is reused on later runs with the same fixed leading words, instead of asking again each time test paths or variables change. (#354)

## v1.49.3 — 2026-10-09

This release stops a `$track` question round from pausing for approval on Codex for macOS by piping report, draft and answer text straight into the scripts instead of writing it to scratch files.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.49.2.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.49.2 to 1.49.3.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress is unaffected; its saved state and ledger keep the same fields, and it simply stops needing a scratch file for the current round's text. (#346)

### Track

- On macOS and Linux, a `$track` question round writes no scratch file for the stage report, each answer, or a non-Tier-1 options draft; the text is piped in directly instead. (#346)
- A Tier 1 options draft is still written to `options-<id>.md` in the track directory, where `preflight.py` reads it. (#346)
- Only a shell without heredoc support, such as PowerShell, still writes a scratch file for this text, and that file is now left in place rather than deleted afterwards. (#346)

### Codex

- A pending question round no longer stops to ask approval for a `rm -f` on a scratch file, since on macOS and Linux there is no longer a scratch file to remove. (#346)

## v1.49.2 — 2026-10-09

This release fixes Codex stage timing, which recorded nothing after a recent change, and makes the Agent Viewer ring the same chime for inferred permission waits as for confirmed ones.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.49.1.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.49.1 to 1.49.2.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress is unaffected; nothing about its saved state or ledger changes. (#344)
- Run `$setup` again so the installer copies the fixed launcher to `~/.codex/cai/launcher.py`; this is required for Codex stage timing to work again. (#344)

### Codex

- Codex tracks record stage timing again: `timing begin`/`timing end` now run through to `timing.py` instead of being swallowed by the launcher's hook path. (#344)

### Viewer

- An inferred permission wait now rings the same two-note `ask` chime as a question or a confirmed permission wait, instead of a quieter, easy-to-miss tone. (#343)
- The "Also chime for inferred permission waits" checkbox still controls whether an inferred wait rings at all. (#343)

## v1.49.1 — 2026-10-09

This release reworks `$setup` so it asks about response language before models, keeps both choices to short menus without recommending a language, and saves the chosen language so a later `--apply` run cannot overwrite it.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.49.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.49.0 to 1.49.1.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress is unaffected by this update; nothing about its saved state or ledger changes. (#340)
- Re-run `$setup` (or `/cai:setup`) to pick your response language and model preferences through the new, shorter menus. (#340)

### Usage

- `$setup` now asks you to choose your response language before it asks about models. (#340)
- The language and model menus are now short choices instead of long comparisons, and the language menu no longer recommends one option. (#340)
- Once you choose a response language during setup, a later `--apply` run no longer overwrites that choice. (#340)

## v1.49.0 — 2026-10-09

This release adds per-stage timing on Codex so the Agent Viewer shows subagent model time for `$track` runs there too, and fixes a track bug where `intake` and `discover` deferred web lookups to a stage that could never reach the internet either.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.48.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.48.0 to 1.49.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress is unaffected by this update; nothing about its saved state or ledger changes. (#337, #336)
- On Codex, rerun `$setup` and trust the new timing hooks in `/hooks` so a `$track` stage can record and show its time. (#337)

### Codex

- A `$track` run on Codex now records each stage's subagent model time, the same as Claude Code, and the Agent Viewer shows it. (#337)
- `$setup` lists a new timing mapping row, marked `unverified` until a real session is seen writing a timing record, and the trust step now names the timing hooks. (#337)

### Track

- `intake` and `discover` now look up facts from outside the repo themselves, with web search and web fetch tools, instead of deferring the lookup to a later stage that could not reach the internet either. (#336)
- A lookup that fails during `intake` or `discover` is named in the stage's Report as a deviation, so you can see it was not done. (#336)
- On Codex, `intake` and `discover` have no equivalent web tools, so a lookup is reported as a deviation there instead. (#336)

## v1.48.0 — 2026-10-08

This release fixes the Agent Viewer to show each track's total measured time and stops it from inferring a finished track onto a brand-new session, adds a glossary entry check that moves cai's glossary file into `.claude/`, and settles the test command before build so a missing or ambiguous one never blocks entry into the stage.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.47.1.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.47.1 to 1.48.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress keeps working as before: the next time you enter `build`, you're asked to confirm or skip the test command before the stage dispatches, instead of only being told about it afterward. (#325)
- If your project has a top-level `CONTEXT.md` from an earlier cai, it's left alone but no longer read; move any entries you want into the new `.claude/cai-context.md` yourself. (#328)

### Viewer

- `/cai:viewer` shows each track's six-stage measured total time and name in the left identity column, in `hh:mm:ss`, without wrapping after 24 hours; a partial measurement shows a lower bound. (#331)
- A brand-new session no longer shows a finished track left over from an earlier session in the same project; it shows `AGENT` until that session actually runs one. (#330)

### Build

- Entering `build` no longer blocks on the test command: if one is found you confirm it, if several are found you're offered candidates or can skip, and if none is found you can type one, check again, or skip. (#325)
- Skipping the test command carries through build and verify without asking again: build marks affected units `done (unverified)` and verify runs with no test command, doing everything else as normal. (#325)

### Glossary

- cai's glossary file moves from `CONTEXT.md` at the top of your project to `.claude/cai-context.md`. (#328)
- Writing a glossary entry now checks it first and rejects a decision id, a track-document path, a number with a unit, an overlong definition, or a reused term name, showing the reason; menus for picking terms offer at most four at a time. (#328)

## v1.47.1 — 2026-10-08

This release fixes a bug where a stage run more than once (for example build → verify → build) showed only its last run's time in `/cai:viewer`, and makes timing settles much faster so they're less likely to be cancelled by the hook timeout.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.47.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.47.0 to 1.47.1.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress keeps its existing `state.md` and ledger records unchanged; after you update, a re-run stage's time is no longer dropped from the spool, and settles on a track with several live subagents finish much faster instead of risking the 5 s hook timeout. (#321, #323)

### Timing

- A stage run more than once keeps its earlier run's recorded time instead of losing it once that run's track closes; `/cai:viewer` now shows the sum of all its runs. (#321)
- A timing settle on a journal with several live subagents completes in a fraction of the time it used to, cutting the risk of a hook being cancelled before its stage time is recorded. (#321, #323)

## v1.47.0 — 2026-10-07

This release lets `/cai:track`'s verify stage check acceptance criteria against a running copy of your program, not just a diff and the test suite, and lets `ship`'s draft start the moment verify passes instead of waiting for you to type `ship`.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.46.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.46.0 to 1.47.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress keeps its existing `state.md` and ledger records; neither format changed. Its next `verify` stage reads a `## Verification levels` table if the intake has one, or verifies exactly as before if it doesn't; once `verify` passes, `ship`'s draft starts on its own instead of waiting to be asked. (#317, #318)

### Verify

- An intake can end with a `## Verification levels` table marking each acceptance criterion `test`, `local-run`, `deployed`, or `manual`; verify prints this plan before running its review lenses and does not dispatch an AC marked Not covered. (#317)
- For a `local-run` AC, verify can start your program, wait until it's ready, and run HTTP or end-to-end checks against it, keeping each check's output as evidence. (#317)
- The verify report lists every acceptance criterion as verified-by-test, verified-at-runtime, confirm-before-merge, or not-covered with a reason, instead of only reporting lens findings and test results. (#317)
- An intake without a `## Verification levels` table verifies exactly as it did before this release. (#317)

### Ship

- Once `/cai:track`'s verify stage is recorded passed and its fixes are committed, `ship`'s draft starts on its own; Gate 2's push menu still requires your go-ahead before anything irreversible runs. (#318)

### Codex

- `cai-codex` is regenerated with the updated verify and ship behaviour; its README documents the new local-run verification as unverified. (#317)

## v1.46.0 — 2026-10-06

This release stops `/cai:track` from littering `.claude/track/<feature>/` with throwaway option drafts, drops the five-active-track limit, cuts unnecessary macOS permission prompts during Codex verification, and adds per-stage subagent time to `/cai:viewer` for Claude Code tracks.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.45.1.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.45.1 to 1.46.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress keeps its existing `state.md` and ledger records; neither format changed. Its next stage dispatch starts recording subagent model time automatically (Claude Code only), and it is no longer subject to the old five-track cap. (#303, #310)
- Run `$setup` again after updating so Codex picks up the refreshed workflow rules that reduce macOS permission prompts. (#306)

### Track

- Starting a new track no longer stops you at a sixth active track; `/cai:track <feature>` creates it regardless of how many others are open. (#310)
- Only the Tier 1 decision's options draft is kept in `.claude/track/<feature>/`; drafts for every other question go to a scratch location outside the repo instead. (#312)

### Codex

- Codex verification requests fewer extra macOS permissions by avoiding unnecessary `uv sync`/downloads and writing disposable files to a checked, Git-ignored scratch location instead of outside the allowed roots. (#306)

### Viewer

- Each `/cai:track` stage now shows a time in `/cai:viewer`, built from how long its Claude Code subagents spend generating responses; it reads "At least m:ss · Incomplete data" rather than a total, since tool execution and main-session time aren't counted. (#303)

## v1.45.1 — 2026-10-05

This release closes places where a planted program in the current directory, or a viewer token following a redirect, could act with your rights, tightens what the verifier agent may do, and makes pytest, make and just detection more accurate.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.45.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.45.0 to 1.45.1.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress keeps its existing state and ledger records; neither format changed. Its next verify stage runs under the tightened dispatch guard below. (#295)
- Restart your Claude Code session after updating — the new Agent-dispatch guard only takes effect from the next session on. (#295)

### Guard

- `cai:verifier` can no longer write files with `git diff`, `git log` or `git show --output` (or a near-abbreviation down to `--out`); these are refused. (#295)
- `cai:verifier` can now dispatch only `cai:reviewer` or `cai:security-reviewer` (or their bare names) as sub-agents; dispatching anything else is blocked with a message naming the two allowed types. (#295)
- Without a working Python, the reduced guard now also blocks `cai:verifier`'s agent dispatch entirely. (#295)

### Windows

- git and gh commands run by the guard, status line, preflight, track start, branch sweep, ticket backend and ship no longer risk running a same-named program planted in the current directory; they run only a trusted copy found on `PATH`. (#297, #292)
- pytest now runs with whichever of `python`, `python3` or `py -3` is actually on your `PATH`, instead of always `python`. (#293)

### Viewer

- The viewer's access token is no longer sent on to a server a redirect points to; it stays on your local machine. (#297)

### Test detection

- A `.claude/cai.json` saved as UTF-16 is now rejected as invalid, matching how the rest of the plugin reads it. (#291)
- make projects are detected via `GNUmakefile`, `makefile` or `Makefile` by exact name, and just projects via `justfile` or `.justfile` in any letter case, matching how those tools actually look for their files. (#291)

## v1.45.0 — 2026-10-05

Ship asks fewer questions between the push and the merge: one menu covers the squash, the push and the PR, and the merge is confirmed by the guard's permission prompt. On Codex, the agents can now read files they could not before.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.44.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.44.0 to 1.45.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress keeps its existing state and ledger records; neither format changed. Its next `ship` stage runs the new flow below. (#287)

### Track

- Ship's first step only drafts the squash message and the PR description and changes nothing. The push menu shows both in full with the commands, and one "Run them" covers the squash, the push and creating or editing the PR. The separate squash question and the ticket-comment question at ship are gone. (#287)
- When the open PR has two to four Blockers or Majors, they are offered as one multi-select question. A Minor you name by its list number is fixed too. (#287)
- The merge menu is replaced by a plain list and a bare `gh pr merge <n>`, which the guard's permission prompt confirms. A merge that did not run is handed back to you, never retried. On Codex you still run `gh pr merge` yourself. (#287)

### Guard

- `gh pr merge` now asks for permission also when it sits behind a compound statement, a wrapper command, or a string handed to a shell (`bash -c`, `eval`, `pwsh -Command`). (#287)
- With no working Python found, the reduced check now blocks `gh pr merge` and the API call that merges a PR, so you run the merge yourself. (#287)

### Codex

- Agents are told what replaces Claude's file tools on Codex (read-only shell commands for reading and searching, `apply_patch` for editing). `cai_designer`, `cai_verifier` and `cai_test-runner` can now read files outside their fixed command list, so `cai_designer` can read the design document and the code it cites; `cai_explorer` is no longer told it has no shell. (#289)

## v1.44.0 — 2026-10-04

Stages that run tests now find the project's test command instead of guessing it. A track keeps unanswered questions across sessions, asks the build and verify consents once, and lists a PR's unresolved findings before merging. The guard no longer lets a call through when the Python it finds is broken.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.43.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.43.0 to 1.44.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress keeps its existing state and ledger records; neither format changed. A `pending.md` appears in the track's directory only when a stage hands questions up after the update. A round left unanswered before the update was never saved, so that stage runs again. (#278)
- Nothing to do for the guard: its first call after the update finds a working Python once and records it under the config root's `cai/` folder. (#282)

### Test command

- Test-runner, verifier and designer no longer guess how to run tests. A non-empty `test.commands` list in `.claude/cai.json` wins: every command runs, and any failure fails the run. Otherwise the repo root's Makefile, justfile, Taskfile, `package.json`, `tox.ini`, `noxfile.py` and marker files (`go.mod`, `Cargo.toml`, `pom.xml`, Gradle, `.sln`/`.csproj`, pytest config) are read. A single candidate is used. With several or none, you are asked once, and the answer is saved to `test.commands`. A malformed declaration is reported, never replaced by detection. (#270)
- On Claude Code a hook holds those three agents to that command and a few read-only ones; `cd`, chaining, `2>&1` and `find`/`ls` are blocked for them. On Codex the same boundary is an instruction only. (#270)
- A UTF-8 BOM no longer hides an entry file or `.claude/cai.json`, all eight Task file names are read (the first one present wins), and a Makefile with only `test ::= ...` or `test :::= ...` is not taken for a `make test` target. (#279)

### Track

- Unanswered questions a stage hands up are saved to `.claude/track/<feature>/pending.md`, with each answer recorded as it comes. A later session resumes from the `pending:` section of `track_state.py status` instead of running the stage again. (#278)
- Build asks its Step 0.5 questions in one round before any unit starts; verify no longer asks the commit question again. A stop mid-build blocks only the stuck unit, the units depending on it and those sharing its files; the rest keep going. Inside a track, build skips its own four-lens review, since verify reviews the branch once. Verify hands its decisions up instead of waiting for an answer it cannot get, and after it passes, its changes are committed if you said yes at Step 0.5. Run on their own, `/cai:build` and `/cai:verify` still ask directly. (#283)
- Verify checks first whether the branch merges cleanly with the remote default branch, and stops before the four review lenses if it does not. Each such stop counts as a `blocked` attempt. (#268)
- After pushing, ship waits for the PR's checks and lists unresolved review threads and check annotations. The Blockers and Majors among them get a fix menu (at most two rounds), and the merge is asked on its own menu after that. The listing needs a `gh` that supports `gh api --slurp`; with an older one those sources show as unchecked. On Codex you run `gh pr merge` yourself. (#281)

### Guard

- A Python that is found but broken, such as the Windows Store stub, no longer lets commands through. The guard probes once and records a working launcher. With none, `cai:test-runner`, `cai:verifier` and `cai:designer` are blocked, and every other caller gets a reduced check: force push, `reset --hard`, `git clean -f`, `--no-verify` and `rm -rf`. A direct commit or push to `main`/`master` is not blocked in that mode. `/cai:setup` Step 6 now says whether the guard is healthy, degraded, or its launcher failed. (#282)

## v1.43.0 — 2026-10-03

Codex roles can now save a reasoning-effort choice alongside their model, and the Agent Viewer handles pending tool approvals and agent waits more accurately.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.42.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.42.0 to 1.43.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress is unaffected: neither `state.md` nor the ledger format changed.
- Restart a running viewer to pick up the Codex status fixes: `/cai:viewer stop`, then `/cai:viewer` (on Codex, `$viewer stop`, then `$viewer`). (#261, #263)

### Codex Models

- `$models <role> <model> [<effort>]` saves a model and optional reasoning effort for that role; `$models <role> effort <effort>` changes only the effort. An explicit effort applies to every agent in the role. Model-only changes preserve a saved effort, `default` restores each agent's shipped effort, and `$models reset <role>` restores both model and effort defaults. Existing saved model choices remain supported and later `$setup` runs re-apply them. (#262)
- Choices are checked against supported effort levels when the cached model list provides them. When a saved effort is no longer supported, the installer retains the saved choice and reports the supported fallback it writes; menu previews distinguish that future write from settings already applied. (#262)
- The default model for `chore` is now `gpt-6-luna` with low effort, and `build` uses `gpt-6.1-sol` with medium effort, retaining high effort for reviewers. `think` remains `gpt-6-astra` with high effort. (#262)

### Viewer

- Codex custom tool calls now count as pending until their matching output arrives. After 30 seconds, a pending call can show an inferred permission wait; this remains a time-based inference, so a long-running tool can also show that state. (#261)
- An unresolved Codex `spawn_agent` call keeps the session shown as running instead of becoming an inferred permission wait after 30 seconds. (#263)

## v1.42.0 — 2026-09-30

You can now cancel an unfinished track with a recorded reason. Track checks, command guards and Codex question handling also get fixes.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.41.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.41.0 to 1.42.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress keeps its existing state and ledger records; neither format changed. Design checks now require an approved diagnosis and its first failing-test path when a detail design is based on a diagnosis. (#247)
- Restart a running viewer to pick up the question-handling fix: `/cai:viewer stop`, then `/cai:viewer` (on Codex, `$viewer stop`, then `$viewer`). (#258)

### Track

- `/cai:track cancel --reason "<why>"` (Codex: `$track cancel --reason "<why>"`) records the date and reason in `cancelled.md`, archives the track under `done/`, and clears `current` even when stages are unfinished. The branch, PR and mirrored ticket stay as they are. (#254)
- Checks no longer demand a new local options draft for a Tier 1 decision whose `Decided` date strictly predates the track's first ledger record. Same-day, missing, invalid or ambiguous dates still require a draft. (#257)
- A detail design based on a diagnosis must reference an approved diagnosis and name its first failing-test path. Stance detection now checks the full template headings, and failures name the upstream documents that were read. (#247)
- Build handoffs now include ownership, a brief and acceptance criteria when no detail design exists. Read-only agents have narrower tool access; Claude Code also enforces the designer's command boundary through a hook. Codex does not enforce those source-agent hooks. (#256)
- Git failures stop intake, verify and ship checks with an explicit reason instead of being mistaken for normal answers. Non-ASCII filenames no longer crash these checks, and diagnostic text cannot forge extra PASS/FAIL lines. (#248)
- Parallel build lanes use a temporary commit to set work aside. Git and ship instructions recommend a stash only when the repository has a single worktree, since linked worktrees share it. (#246)

### Guard

- Commit, discard and push checks use the directory targeted by the command, including supported directory changes and `git -C`, rather than always using the session directory. Denials name the directory checked, and multiple commit or discard commands on one line are each checked. (#245)

### Codex and Viewer

- Codex menus require a submitted answer; cancellation, timeout or a preselected choice never counts as consent. When a blocking question tool is unavailable, the agent shows numbered options and waits for a reply. (#255)
- The Agent Viewer shows an asynchronous Codex question as waiting while the turn is still running. Background updates and turn completion preserve the question's identity to avoid repeated chimes; questions from earlier turns are cleared. (#258)

### Usage and Models

- Malformed transcript lines and missing timestamps are summarized per file and kind, reducing repeated problems in usage records. (#256)
- Changing an agent's model tier on Windows preserves its existing line endings. (#249)

## v1.41.0 — 2026-09-28

The Agent Viewer's top bar now counts cards by the state they show instead of by whether Seen was pressed, and `/cai:git` keeps its message files out of your repository.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.40.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.40.0 to 1.41.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress is unaffected: neither `state.md` nor the ledger changed.
- A viewer started before the update keeps serving the old top bar. Run `/cai:viewer stop`, then `/cai:viewer` (on Codex, `$viewer stop`, then `$viewer`).

### Viewer

- The top bar shows three chips named with the words the cards use: **Waiting for you** (question, permission and attention cards), **Done**, and **Running** — 等待處理, 完成 and 執行中 in Traditional Chinese. They replace "Needs you N / N unread". (#240)
- The numbers follow each card's state only. Pressing Seen on a card still stops it flashing, but no longer changes any number. (#240)
- A chip takes its cards' colour while its count is above zero and stays grey at zero; Waiting for you still glows as the one alert. (#240)
- The browser tab title reads "(N) Waiting for you", N being the waiting count. (#240)

### Git

- `/cai:git` is now told to write a multi-line commit message or PR body to a file in the system temp directory, never inside your repository, and to delete that file once the command has run. Before, such a file could stay in the work tree as an untracked file the next `git status` reported. (#238)

## v1.40.0 — 2026-09-27

`/cai:track` now starts each new track on its own branch, ship no longer blocks on untracked files, and the guard keeps direct pushes off `main`/`master`.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later, unchanged from v1.39.0.

### What to do when you update

- **Claude Code** — `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.39.0 to 1.40.0.
- **Codex** — `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one`, then run `$setup` inside Codex.
- A track already in progress keeps working: `state.md` did not change. Such a track has no record of which files were untracked when it started, so ship's report lists every untracked file instead of only the ones the track added. It still never blocks on them.

### Track

- `/cai:track <feature>` first runs a new `track_start.py`. On `main`/`master` it pulls (fast-forward only) and switches to `track/<feature>`, so intake no longer stops on the branch check. It stops and creates nothing if that branch already exists or the pull fails. (#226)
- Ship's clean-tree check blocks only on tracked files with uncommitted changes, and names up to 10 of them. Untracked files never block; the ship approval lists the ones this track added, and afterwards names the track's design documents git does not track. (#226)
- The ship approval also lists build's manual steps that are still unverified. (#227)
- With a ticket pointer, ship refers to the issue as `Refs #<number>` only, so the PR never closes it; the issue is closed from `/cai:track done`'s menu. A new `ship_draft_check.py` checks the drafted commit message and PR body before they are shown. (#227)
- `/cai:track done` ends by naming the post-merge routine: switch to the base branch, `git pull`, then `/cai:git-sweep`. (#226)
- `/cai:track status` shows where every other active track stopped. (#229)
- The ledger refuses any record that is not `passed` and carries no note. (#228)
- The test-runner reports a named test file that ran no tests as `NOT RUN`, and build treats that as a failure. (#228)

### Guard

- The bash guard blocks every force push and any push to `main`/`master`, `--force-with-lease` included, so a change reaches a protected branch only through a merged PR. A first, non-force push that creates `main` or `master` on a remote that does not have that branch yet is still allowed. (#228)
- `gh pr merge` now asks for permission under Claude Code. Codex cannot ask yet, so there it is denied and the command is handed back for you to run. (#228)

### Usage

- `/cai:usage metrics` prints `human_signed=n/a` for stages that have no human gate, and counts only gated stages in the total. (#229)

## v1.39.0 — 2026-09-27

First unified version: Claude Code and Codex now share one version number, and both install from this tag.

Requires Claude Code 2.1.283 or later and codex-cli 0.157.1 or later. Check with `claude --version` and `codex --version`. Update codex-cli the way you installed it (it also updates itself between runs) before updating this plugin; an older codex-cli stops seeing it.

No skill, agent or rule changed in this release. What changed is how versions are numbered and how the plugin reaches you.

### What to do when you update

- **Claude Code** — the usual steps: `/plugin marketplace update claude-all-in-one`, then `/plugin update cai`, re-run `/cai:setup`, and restart the session. The version moves from 1.38.1 to 1.39.0.
- **Codex** — `cai-codex` drops its own 0.2.x numbering and now carries the same version as `cai`. Update with `codex plugin marketplace upgrade`, then `codex plugin add cai-codex@claude-all-in-one` (no `remove` needed), then run `$setup` inside Codex. Until you do, the first cai script a skill runs stops and asks you to run `$setup`, because the installed agents still carry the old version.

### How releases work from now on

- Both marketplaces install a release tag, not `main`: each plugin entry is a `git-subdir` source pinned to `vX.Y.Z`. Changes merged to `main` reach you when the next version is released.
- Each tag is installed from GitHub on Claude Code and on Codex before the marketplaces point at it.
- Versions follow SemVer against a declared public interface: skill names, `/cai:setup`'s write locations, the model-choice save format, and the two platform floors above. The README's Compatibility section lists what bumps which number.
- If an update stops installing, check the latest GitHub Release page first (README, "If an update stops installing").
- For contributors: pull requests no longer change `version`; a maintainer cuts each release with `scripts/release.py` (README, "Releasing").
