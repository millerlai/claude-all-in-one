# Changelog

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
