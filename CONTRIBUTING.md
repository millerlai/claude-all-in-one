# Contributing to claude-all-in-one

This file is for changing the plugin rather than using it: how to try a change
before it is released, what to run before pushing, and how a release is cut.
It never reaches an installed copy. [`README.md`](README.md) is what the
pieces are, [`MANUAL.md`](MANUAL.md) is how to drive them, and
[`GUIDE.md`](GUIDE.md) is where a new piece of guidance belongs.
[`CLAUDE.md`](CLAUDE.md) holds what Claude itself needs to know when it works
in this checkout.

## Which side a file is on

Everything users receive lives under `plugins/cai/` — the plugin cache
copies only that directory, so anything outside it never reaches an installer.
Decide which side a new file is on before writing it: [`CLAUDE.md`](CLAUDE.md)'s
"Who a file is for" draws the line between what ships and what only maintains
this repo (`docs/`, `scripts/`, `tests/`, `.github/`, `.claude/skills/`). The
plugin cache is keyed by version — no pull request changes `version` in
`plugins/cai/.claude-plugin/plugin.json` any more; `scripts/release.py`
writes it once, when a release is cut. See [Releasing](#releasing) below.

Adding guidance rather than code? [GUIDE.md](GUIDE.md) covers which component
should hold it — a convention, a procedure, or a constraint — and why putting it
in the wrong one makes it quietly stop working. It applies just as well to your
own `~/.claude/` setup.

## Testing unreleased changes

Test your changes from your checkout, not from an installed copy. Adding this
repo as a marketplace from a local checkout and installing from it does not
do that: the entry in `.claude-plugin/marketplace.json` is a `git-subdir`
source pinned to the latest release tag, so `/plugin install` fetches that
tag from GitHub, not your working tree.

Claude Code testers can point `claude` straight at an uninstalled tree with
`--plugin-dir /path/to/claude-all-in-one/plugins/cai`.

Codex testers can add a second, differently-named local marketplace entry —
`cai-dev`, say — pointed at their working checkout, to try changes without
disturbing the real `claude-all-in-one` marketplace entry. This is a
maintainer workaround with known limits, not a fully general local-dev setup.

## Before pushing

Run both:

```bash
python scripts/validate.py
python -m pytest
```

`validate.py` checks the manifests, that every agent and skill has the
frontmatter Claude Code needs to load it, that hook commands point at files
that exist, that the guard still blocks what it should, that every rule file
and the `track` and `goal` skills stay within their line ceilings, that every
`.cmd` file is pure ASCII and no text file starts with a UTF-8 BOM, that the
eval graders are well-formed and carry no secrets, and — through
`plugins/cai/scripts/provenance.py` — that
every entry in `docs/rule-provenance.md` still cites text that exists and that
every place restating a rule still agrees with it. Because every `description`
the model can match on is sent to it in every session, it also checks that the
combined size of every agent's and skill's `description` (skipping the 72
refactoring cards, which carry `disable-model-invocation: true` and so never
reach the model unbidden) hasn't grown past what it measured last. It's a
ratchet, not a target: it can only shrink or hold, never quietly drift back up.

A healthy run's last few lines look like this (checks vary; the shape is what
matters — every line `PASS`, no `FAIL`, exit code 0):

```
PASS plugins/cai/evals\options-six-fields\graders\reads-options-references.md frontmatter has an allowed type (found: 'tool_used')
PASS plugins/cai/evals\track-status-runs-the-script\graders\names-track-state-script.md frontmatter has an allowed type (found: 'regex')
PASS no evals file contains a sk-ant- (0 found)
PASS no evals file contains a ghp_ (0 found)
PASS no evals file contains a home-directory path (0 found)
```

`pytest` runs `tests/`, which exercises what the scripts under
`plugins/cai/scripts/` actually do. It and `pytest-xdist` are this repo's
only development-time dependencies (`pip install pytest pytest-xdist`):
`pyproject.toml` makes `python -m pytest` run the suite on one worker per
CPU, and without `pytest-xdist` it stops at `unrecognized arguments: -n`.
`--pdb` and `-s` need a single process: add `-n0` when debugging. `tests/`
sits at the repo root rather than under `plugins/cai/` so that neither it nor
pytest ever reaches an installed copy. A healthy run ends with a line like:

```
================= 1443 passed, 4 skipped in 157.17s (0:02:37) =================
```

CI runs both on every pull request, on Linux, with `-n auto`. Windows is
covered only by running them by hand; macOS not at all.

You rarely need to run `validate.py` yourself while editing:
`.claude/settings.json` registers a `PostToolUse` hook that runs it whenever the
Edit or Write tool touches `plugins/cai/` or `.claude-plugin/`, and reports
what failed. A file rewritten through the shell does not trigger it.

### Optional: a local eval run

When a change touches `plugins/cai/{skills,agents,hooks,rules,evals}/`, an
optional local eval run is worth doing — about US$0.24 a run on a
subscription. Point `--output-dir` outside the repo, or the results land
inside the tree that ships:

```
claude plugin eval plugins/cai --ablation none --max-cost-usd 1 --threshold 0 \
  --trust-plugin --no-publish --model haiku --output-dir <path outside this repo>
```

This is deliberately not wired into CI — the suite is too thin (3 cases, 11
graders) to carry a red/green gate yet; see issue #86 for the reopen
condition.

## Releasing

`scripts/release.py` has four subcommands, run in order:

1. `python scripts/release.py prepare X.Y.Z [--base REF]` drafts a
   `release/vX.Y.Z` branch and a `CHANGELOG.md` section. Edit that section
   by hand before continuing.
2. `python scripts/release.py cut X.Y.Z` writes the version, tags it, and
   calls `verify` automatically.
3. `python scripts/release.py verify X.Y.Z` can also be run standalone, to
   retry a check without cutting again.
4. `python scripts/release.py publish X.Y.Z` publishes the GitHub Release.

There's no fixed schedule — the maintainer cuts a release whenever they
decide to, typically after a `fix:` lands. The release PR merges with
`--merge` (a real merge commit), the one exception to this repo's usual
squash-merge habit: reverting it must never look like reverting the version
bump alone. A version number that got tagged but failed its checks and was
never served is simply skipped — the next release uses the next number, and
the CHANGELOG notes what was skipped. A GitHub tag ruleset, set up once by
the repo owner, protects `v*` tags from being moved or deleted.

Which part of the version a change bumps is in README's
[Compatibility](README.md#compatibility) table.

### Releasing with GitHub Actions

The `cut-release` workflow automates the work after the maintainer chooses
the version and reviews the release notes. It reuses `scripts/release.py`;
the local procedure above remains available. It does not choose a version
or turn commit subjects into final release notes.

One-time repository setup:

- Install a GitHub App on this repository only, with **Contents** and
  **Pull requests** read/write, and **Actions** and **Checks** read access.
  The App token lets the release PR and merge push trigger normal CI;
  do not grant it a bypass for the `v*` tag ruleset.
- Create environments named `release-tag` and `release-merge`. On each,
  configure a required maintainer reviewer, restrict deployment branches to
  `main`, and disable administrator bypass. Leave self-review enabled if
  the only maintainer also starts the workflow. An environment name in YAML
  does not by itself configure these protections.
- In both environments, set variable `RELEASE_APP_ID` and secret
  `RELEASE_APP_PRIVATE_KEY` to the App's ID and PEM private key. The workflow
  requests only the token permissions needed by each step. No model API
  keys are used: platform verification installs plugins without a model run.
- Keep the `validate` workflow enabled and merge commits permitted. The App
  must satisfy any branch protection; it does not approve its own PR.

For each release:

1. Follow the maintainer skill's preflight, version choice, `prepare`, and
   CHANGELOG review. Keep the candidate as **one** commit directly on the
   current `origin/main`, changing only the normal release files:

   ```sh
   git add -- plugins/cai/.claude-plugin/plugin.json .claude-plugin/marketplace.json .agents/plugins/marketplace.json plugins/cai-codex CHANGELOG.md
   git commit -m 'chore(release): vX.Y.Z'
   git push -u origin release/vX.Y.Z
   git rev-parse HEAD
   ```

2. In Actions, run `cut-release` **on main**, with version `X.Y.Z` and the
   complete SHA printed above. The initial check verifies the candidate and
   the successful `validate` push run for its main parent. Its summary shows
   the exact release notes. If main advances before the first tag push,
   rebuild the candidate from current main and start a new run with its SHA.
3. Review that summary and approve `release-tag`. The job validates and tests
   even an already committed candidate, pushes the immutable tag, verifies
   actual installs with both platform CLIs, creates the release PR, waits
   for that exact head's CI, and publishes the GitHub Release. CLI versions
   are pinned to the platform floors in `scripts/release.py`; update the
   workflow's installation step when those floors change.
4. Approve `release-merge` only after reviewing the PR and published Release.
   It uses `--merge --match-head-commit`, confirms the tag is an ancestor of
   main, and waits for the merge commit's own `validate` push run.

Re-run a failed workflow with the same version and SHA for transient
failures. If the tag is already on the remote, it reruns `verify` instead of
trying to tag again; a published Release is reused. The release branch was
saved before tagging, so recovery does not depend on a previous runner's
disk. If merge succeeded but its CI wait failed, re-running the **failed
merge job** checks the existing merge instead of merging twice. A changed
branch head or conflicting tag is refused. A real installation defect still
burns the version: fix it on main, explicitly retire the failed release
branch after review, and prepare the next number, recording the skipped
version in CHANGELOG. Never move or delete its tag. Runs are serialized and
do not automatically cancel an in-progress release.

### Stable fallback

If a platform's update path breaks and the fix isn't ready yet, the
maintainer can point a `stable` branch at the last known-good tag, with both
marketplace files reverted to the old relative-path form, so installs fall
back to that tag instead of a broken `main` HEAD. This is a manual,
maintainer-run procedure — `scripts/release.py` does not automate it.

## Maintainer tools

None of these is run by a shipped component:

- `scripts/activation.py` — which skills and agents were installed, and on how
  many days each one actually ran.
- `tests/review-benchmark/` with `scripts/review_benchmark_score.py` — labelled
  diffs that measure what the four `verify` lenses catch; the paid half is
  `scripts/review-benchmark-procedure.md`.
- `/gap-analysis` (`.claude/skills/gap-analysis/`) — compares cai against an
  external practice and writes the result under `docs/design/`.
- `/cut-release` (`.claude/skills/cut-release/`) — runs the four
  `scripts/release.py` steps in [Releasing](#releasing) above, with the version choice,
  the CHANGELOG rewrite and the confirmations before the tag push and the
  `--merge` of the release PR. Codex CLI uses `$cut-release [X.Y.Z]` via
  `.agents/skills/cut-release/`, which reads the same workflow and adds
  PowerShell execution guidance. Both entries are repository-only maintainer
  tools, not shipped plugin skills.
- `python plugins/cai/scripts/context_peak.py --track-dir .claude/track/<feature>`
  — a track's peak main-session context occupancy, read from local
  transcripts; it writes nothing.
