# Changelog

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
