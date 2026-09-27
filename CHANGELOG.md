# Changelog

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
