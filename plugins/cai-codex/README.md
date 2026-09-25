# cai-codex

The Codex CLI counterpart of the `cai` Claude Code plugin: the same
cost-tiered agents, skills and rules, kept in sync with `cai` automatically
rather than hand-translated.

## Requirements

- `codex-cli`.
- Python 3 reachable as `python3` (macOS, Linux) or `python`/`py -3`
  (Windows) in the shell Codex runs commands in. `$setup` records
  whichever interpreter it ran with, and every generated command reuses
  that recorded interpreter instead of guessing. If that Python moves or
  is removed, re-run `$setup`.

## Install

```
codex plugin marketplace add millerlai/claude-all-in-one
codex plugin add cai-codex@claude-all-in-one
```

Then, inside Codex, run:

```
$setup
```

This installs the agents and rules for your user, and tells you the response
language it set. Setup writes into `~/.codex`, outside your workspace — see
Usage's Windows notes below for what you'll be asked to approve. It ends by
telling you to run `/hooks` and trust the cai guard — until you do, the
guard is installed but **inactive**, and nothing stops a dangerous command.

## Usage

Invoke a skill with `$name` — the Claude Code form `/cai:name` becomes `$name`
on Codex. `$track <feature>` carries one feature through all six SDLC stages,
intake to ship; `$design`, `$verify`, `$git`, and `$chore` work the same way,
one `$` command per skill.

Start Codex with `--enable default_mode_request_user_input` if you want the
setup language question and the track's two human gates to render as a
clickable menu; without it, Codex's default mode has no question tool at
all, and cai asks in numbered text instead.

**The two human gates.** Exactly two points in a `$track` run stop for you:
after `design`, before any code exists, and before the irreversible
operations in `ship` — merging, tagging, publishing. Answer with the menu
when one is available, or the numbered text options otherwise.

**Where a track keeps its state.** `$track` writes each feature's state to
your project's `.claude/track/<feature>/` and reads ticket-mirroring
settings from `.claude/cai.json` — the same files the Claude Code plugin
uses. That is deliberate: both run the same scripts over the same files, so
one repository's track can be resumed from either tool, although switching
tools in the middle of a track has not been exercised end to end. Keep
`.claude/track/` out of git: `$track`'s intake stage reminds you when it is
not ignored, because `ship` refuses to start on a working tree with
uncommitted changes.

**After every plugin update, re-run `$setup`.** The installed agents are
version-stamped, and a stage's launcher refuses to run (exit 3) until the
stamp matches the plugin version you have installed.

**Choosing models.** `$setup` shows which model each cai role runs on and
asks whether to keep or switch, offering only models your account's model
list shows. To change a role later without re-running setup, use `$models`:
on its own it shows the mapping and offers to switch, `$models think
gpt-6-astra` sets one role, and `$models reset think` puts a role back on
cai's default. Your choice is saved, and every later `$setup` re-applies it.
The account's list is checked only while one of these runs: if a cai agent
later fails to start with a model error, run `$models` and switch that role.

**The ship push approval.** `ship`'s push to GitHub needs escalation outside
the sandbox, and Codex asks you to approve it. Answer "yes" once rather than
"don't ask again" if you want every future push confirmed too — "don't ask
again" saves a standing allow rule for that command shape.

**Seeing which agents need you.** `$viewer` opens a local-only web page
listing every running Claude Code and Codex main session, which ones need
you, and cai track progress. It starts a background server outside the
sandbox, so Codex asks you to approve that too. `$viewer stop` closes it.

**On Windows.** Setup writes into `~/.codex`, outside your workspace, so
approve running it outside the sandbox when asked. Codex's Windows sandbox
also runs your commands as a different user than the one who owns your
repository, so git reports "dubious ownership" for commands you run
yourself — add `-c safe.directory=<path>` to work around it; cai's own
scripts already handle this for themselves.

## Mapping table

Status is one of `verified` (observed on Codex), `documented, not tested`
(described in Codex's own docs or by this build's behavior, but not checked
end to end here), `degraded` (a Claude Code capability with no working
Codex equivalent, accepted as a known gap), or `unverified` (what cai relies
on here is neither described in Codex's documentation nor guaranteed to stay
as observed; it may change with a Codex update).

| Claude Code behaviour | Codex counterpart | Status | Evidence |
|---|---|---|---|
| Menu gate (`AskUserQuestion`) at design/ship | `request_user_input`, or numbered options answered in text when the tool is unavailable | verified | observed with codex-cli 0.155.1 on Windows 11, 2026-09-19: starting Codex with `--enable default_mode_request_user_input` made the `$setup` language question render as a real, clickable menu. This is not guaranteed on every gate — during a live track run the model asked a human gate in plain numbered text even though the flag was enabled and the tool was available. Without the flag, Codex's default mode has no question tool at all, so cai asks in numbered text there instead. |
| Per-agent model pin (`chore`/`build`/`think`) | A user-level `~/.codex/agents/*.toml` per agent, with `model` set | verified | observed with codex-cli 0.155.0 on Windows 11, 2026-09-18: dispatching a personal agent TOML by name applied its `model` override. |
| Choosing a model per role (chore/build/think) | `$setup`, or `$models`, which does only this part, reads the model list Codex keeps for your account in `$CODEX_HOME/models_cache.json`, offers only the models it lists, and saves your per-role choice in `$CODEX_HOME/cai-model-choice.json`, which every later `$setup` re-applies | unverified | observed with codex-cli 0.155.1 on Windows 11, 2026-09-22: the file lists each model's slug, whether it is shown or hidden, and its supported reasoning efforts. It is not described in Codex's documentation, so a Codex update may move or reshape it; setup then says it could not read the list and offers to keep the current models or type a name, rather than guessing. Whether the list leaves out models a restricted account cannot use was not checked. |
| Per-agent reasoning effort | The same TOML also sets `model_reasoning_effort` | documented, not tested | the field is documented for agent TOML configuration, but whether it takes effect was never exercised in this build — only `model` was observed. |
| `/cai:x` skill invocation | `$x` | verified | observed with codex-cli 0.155.0 on Windows 11, 2026-09-18: the bare `$name` form invoked a plugin skill on the first try, with no plugin-qualified form needed. |
| `${CLAUDE_PLUGIN_ROOT}`-relative paths to this plugin's own scripts | A small launcher installed at the fixed path `$HOME/.codex/cai/launcher.py` (always under the real home directory, never `$CODEX_HOME`), invoked through the interpreter `$setup` recorded rather than a literal `python`, that finds the newest installed cai-codex version and runs the named script | verified | observed with codex-cli 0.155.0 on Windows 11, 2026-09-18: `${CLAUDE_PLUGIN_ROOT}` and `${PLUGIN_ROOT}` come back literal and unsubstituted in a skill body, so this plugin never relies on substitution. Generated commands now call the launcher through the interpreter `$setup` recorded (its own `sys.executable`) rather than a hard-coded `python`. On Windows the recorded command additionally pipes the launcher's output through PowerShell (`ForEach-Object`), because a Python script's own output did not reach the tool output on Windows with codex-cli 0.155.x on Windows 11, 2026-09-19, and piping it through PowerShell did. In Codex's Windows sandbox, git reports "dubious ownership" for your own repository; cai's scripts handle this for the folder you opened, but your own git commands may still need `-c safe.directory=<path>` (observed with codex-cli 0.155.1 on Windows 11, 2026-09-19). cai's scripts ran through the recorded command for a whole `$track` run, intake through ship, on Windows (observed with codex-cli 0.155.1 on Windows 11, 2026-09-19). |
| `tools:` allowlist per agent | Codex `sandbox_mode`, declared on each agent but not enforced | degraded | observed with codex-cli 0.155.0 on Windows 11, 2026-09-18: a dispatched subagent declared `sandbox_mode = "read-only"` in its TOML, but ran with `workspace-write` inherited from the parent, and a file write it should not have been able to make succeeded. |
| Bash guard hook (`git push --force`, `rm -rf`, ...) | A `PreToolUse` entry `$setup` writes into `$CODEX_HOME/hooks.json`, running the same guard through the launcher, with a `commandWindows` override for the shell Codex runs hooks through on Windows | verified | https://learn.chatgpt.com/docs/hooks: installing or enabling a plugin does not automatically trust its hooks — Codex skips a hook, plugin-bundled or user-level, until you review and trust the current definition with `/hooks`; shell commands are matched as `"Bash"`; Windows-specific command overrides use `commandWindows`. Observed with codex-cli 0.155.0 on Windows 11: on Windows, Codex runs a hook's plain `command` through `powershell.exe -Command`, where the setup-written string is a syntax error, so the guard never ran and Codex reported "Hook failed" while still running the command; `commandWindows` fixes this by invoking the guard with `&` and re-surfacing its exit code with `exit $LASTEXITCODE`. The guard stays **inactive until trusted** — it does nothing until you trust it with `/hooks`. After trusting it with `/hooks`, a real `git push --force origin main` was blocked, reporting "bash_guard blocked this command: force push ..." (observed with codex-cli 0.155.1 on Windows 11, 2026-09-19). |
| Push, merge, tag and other irreversible `ship` steps held back by a Codex-side approval prompt | The main session runs them after the ship gate, relying on Codex's network-off-by-default approval prompt | verified | https://learn.chatgpt.com/docs/agent-approvals-security: "By default, network access remains disabled." Observed with codex-cli 0.155.1 on Windows 11, 2026-09-19: the ship stage's push to GitHub required escalation outside the sandbox, and Codex asked the user to approve it before running. Answering "don't ask again" saves an allow rule to Codex's own `~/.codex/rules/default.rules`, after which matching pushes are no longer asked — answer "yes" once rather than "don't ask again" if every push should stay confirmed. |
| Usage accounting in the ledger | The ledger still writes a record; the usage fields are left empty and the reason recorded | degraded | the ledger already records an explicit empty-usage reason whenever no session id is available in the environment, which is always the case on Codex; no Codex-side usage collector exists. |
| Rules installed into a global instructions file | All of this plugin's rules, in one marked block inside `$CODEX_HOME/AGENTS.md` | verified | https://learn.chatgpt.com/docs/config-file/config-reference documents a byte cap on how much of `AGENTS.md` Codex reads when building project instructions, but not its default value or whether it also applies to the global file. Observed with codex-cli 0.155.1 on Windows 11, 2026-09-19: Codex loaded the whole rules block, about 15.8 KB, into the model's instructions, final sentence included. The size cap that applies beyond that was not measured. |
| Agent dispatch | Agents are installed by `$setup` into `$CODEX_HOME/agents/` (`~/.codex/agents/` if that variable is unset), not shipped inside the plugin itself | verified | observed with codex-cli 0.155.0 on Windows 11, 2026-09-18: an agent TOML shipped inside a plugin's own `agents/` directory never appeared as a dispatchable option, while the same TOML installed under the user's personal `~/.codex/agents/` dispatched correctly. |
| Nested subagent dispatch (a reviewer or helper spawning another agent) | Flattened: the main session dispatches every helper itself, one level only | documented, not tested | whether a Codex subagent can spawn its own subagent was not exercised in this build; the generated procedure text says so and does not rely on it working. |
| Implicit skill invocation for the catalog's ordinary skills | Suppressed with `agents/openai.yaml`'s `policy.allow_implicit_invocation: false` on every one of them | verified | observed with codex-cli 0.155.0 on Windows 11, 2026-09-18: flipping this policy from `false` to `true` on an otherwise-identical skill and prompt was the only thing that changed whether the skill fired. |

## Not included on Codex

The status line, the usage report, and the plugin evals have no Codex
counterpart and are not part of this package. They read Claude-only data or
need `claude plugin eval`.

## Uninstall

```
codex plugin remove cai-codex@claude-all-in-one
```

Then remove what `$setup` wrote, since removing the plugin does not touch it:

- `$HOME/.codex/cai/` — the launcher, always under the real home directory,
  never `$CODEX_HOME`.
- `$CODEX_HOME/agents/cai_*.toml` — the installed agents.
- In `$CODEX_HOME/hooks.json`, the one `PreToolUse` entry whose command
  contains `.codex/cai/launcher.py`.
- In `$CODEX_HOME/AGENTS.md`, the block between `<!-- cai-codex:begin -->`
  and `<!-- cai-codex:end -->`.
- `$CODEX_HOME/cai-model-choice.json` — your saved per-role model choice.

There is no uninstall command for these; remove them by hand.
